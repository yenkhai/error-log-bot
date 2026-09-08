"""
================================================================================
第2站 CCL Recover 关卡检查器 (pages/niw/page_02_ccl_recover.py)
--------------------------------------------------------------------------------
作用: 
1. 导航进入 CCL Recover 页面 (Menu ID: apy_b0i3text)。
2. 自动在 <select id="comp_options"> 选中 RCM，并触发 Search 刷新全表。
3. 抓取红框内所有 Company (RCM/LRCM)、Satellite (如 nv01-s0001) 以及 Last Recover 时间状态。
4. 判定规则: 读取 Last Recover 单元格计算背景色 (正常为绿底 rgb(0, 204, 0)；异常为红底/非绿底/Error)。
5. 修复公司名称跨行继承问题: 让 LRCM 后续跨行 Row 自动继承公司名称 "LRCM" 而不复位回 "RCM"。
================================================================================
"""

from selenium.webdriver.common.by import By
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class CCLRecoverChecker(BaseChecker):
    def check(self) -> bool:
        # 1. 记录当前站点的日志页头信息
        self.log_station_header("第2站 CCL Recover", menu_id="apy_b0i3text")
        try:
            # 2. 导航切入 CCL Recover 专属菜单
            self.navigate_to_menu("CCL Recover", menu_id="apy_b0i3text", section="NIW")

            # 3. 尝试定位并点击页面上的 Search 搜索刷新按钮 (ID: id_search_button)
            try:
                search_btn = self.driver.find_elements(By.ID, "id_search_button")
                if search_btn:
                    self.log("[SEARCH] 点击 CCL Recover Search 刷新按钮 (id: id_search_button)...")
                    # 使用 JS 方式点击防遮挡
                    self.driver.execute_script("arguments[0].click();", search_btn[0])
            except Exception as e:
                self.log(f"[WARN] 点击 Search 刷新提示: {e}")

            # 4. 智能等待页面与 Loading 状态缓冲完毕
            self.wait_for_page_loaded(seconds=0.5, max_wait=30)

            # 5. 核心 JavaScript 脚本：在前端 DOM 提取所有 Satellite 节点与 Last Recover 单元格背景 RGB 颜色
            ccl_data = self.driver.execute_script("""
                var tables = document.querySelectorAll("table"); // 获取页面所有 <table>
                var allDetails = [];       // 全量节点明细数组 (包含 OK 与 ERROR)
                var errorDetails = [];     // 仅存放存在红底/异常错误的节点明细
                var rawRows = [];          // 结构化对象数组 (供 CheckpointStore 保存表格)
                var totalSatellites = 0;   // 节点总数计数器
                var errorCount = 0;        // 异常节点总数计数器

                // 遍历页面上的表格 (通常 t === 3 时切入 LRCM 板块，其余为 RCM 板块)
                for (var t = 0; t < tables.length; t++) {
                    var currentCompany = (t === 3) ? "LRCM" : "RCM"; // 自动根据表格归属识别公司
                    var rows = tables[t].querySelectorAll("tr");    // 取出表格中的所有行 <tr>

                    for (var r = 0; r < rows.length; r++) {
                        var tds = rows[r].querySelectorAll("td");   // 取出当前行所有的单元格 <td>

                        if (tds.length >= 2) {
                            var satText = "";
                            var timeTd = null;

                            // 遍历单元格查找包含 "nv" 或 "-" 标识的卫星节点名称 (如 nv01-s0001)
                            for (var c = 0; c < tds.length; c++) {
                                var txt = tds[c].innerText.trim();
                                if (txt.indexOf("nv") !== -1 || txt.indexOf("-") !== -1) {
                                    satText = txt; // 拿到卫星节点名
                                    if (c + 1 < tds.length) {
                                        timeTd = tds[c + 1]; // 紧邻的下一个单元格是 Last Recover 时间单元格
                                    }
                                    break;
                                }
                            }

                            // 如果成功匹配到了节点名和时间单元格
                            if (satText && timeTd) {
                                totalSatellites++;
                                var timeText = timeTd.innerText.trim(); // 时间文本
                                
                                // 🌟 核心点：获取计算后（Computed Style）的背景 RGB 颜色
                                var style = window.getComputedStyle(timeTd);
                                var bg = style.backgroundColor;
                                
                                var isRed = false;
                                var isGreen = false;

                                // 使用正则表达式解析 rgba(r, g, b, a) 颜色数值
                                var bgMatch = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                if (bgMatch) {
                                    var red = parseInt(bgMatch[1]);   // 红色分量 R
                                    var green = parseInt(bgMatch[2]); // 绿色分量 G
                                    var blue = parseInt(bgMatch[3]);  // 蓝色分量 B

                                    // 绿色主导 (G > 120 且 R < 100) -> 绿底正常
                                    if (green > 120 && red < 100) isGreen = true;
                                    // 红色主导 (R >= 170 且 G <= 110) -> 红底异常
                                    if (red >= 170 && green <= 110 && blue <= 110) isRed = true;
                                }

                                var lowerTime = timeText.toLowerCase();
                                // 异常条件：呈现红底 或 文本包含 "error/missing" 或 非绿底且时间为空
                                var isError = isRed || lowerTime.includes("error") || lowerTime.includes("missing") || (!isGreen && timeText === "");

                                var itemStr = currentCompany + ": " + satText + " -> Last Recover: " + (timeText || "N/A");
                                var statusStr = isError ? "ERROR/红底异常" : "OK/正常";

                                // 压入 rawRows 结构化数组
                                rawRows.push({
                                    company: currentCompany,
                                    satellite: satText,
                                    last_recover: timeText || "N/A",
                                    status: statusStr,
                                    is_error: isError
                                });

                                // 根据结果推入不同日志容器
                                if (isError) {
                                    errorCount++;
                                    allDetails.push(itemStr + " [ERROR/异常红底]");
                                    errorDetails.push(itemStr);
                                } else {
                                    allDetails.push(itemStr + " [OK/正常绿底]");
                                }
                            }
                        }
                    }
                }

                // JS 脚本把全量结果打包返回 Python 侧
                return {
                    allDetails: allDetails,
                    errorDetails: errorDetails,
                    rawRows: rawRows,
                    totalSatellites: totalSatellites,
                    errorCount: errorCount
                };
            """)

            # 6. 在 Python 侧解构 JS 返回的字段变量
            all_details = ccl_data.get("allDetails", [])
            error_details = ccl_data.get("errorDetails", [])
            raw_rows = ccl_data.get("rawRows", [])
            total_satellites = ccl_data.get("totalSatellites", 0)
            error_count = ccl_data.get("errorCount", 0)

            self.log_data_extracted(f"成功抓取到全表 {total_satellites} 个 Satellite 节点 (异常节点数: {error_count})")
            self.log_check_method("深度读取 Last Recover 单元格背景 RGB 颜色 (绿底为 OK/正常, 红底/非绿底为 ERROR/异常)")

            # 7. 无论是否有 error，一律将全量抓取到的明细打印在控制台/日志中！
            self.log_data_summary([f"【CCL Recover 全量 Satellite 恢复状态明细 (共 {total_satellites} 个节点)】:"] + [f"   * {item}" for item in all_details])

            # 构筑 CheckpointStore 保存的表格结构
            table_headers = ["Company", "Satellite", "Last Recover", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["company"]),
                    CheckpointStore.make_cell(r["satellite"]),
                    CheckpointStore.make_cell(r["last_recover"], bg="red" if r.get("is_error") else "green"),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # 8. Checkpoint 巡检结论判定
            if error_count > 0:
                # 存在异常红底节点：报错并阻断 Checkpoint
                self.log(f"[Error] CCL Recover 发现 {error_count} 个 Satellite 处于异常/红底状态:")
                for err in error_details:
                    self.log(f"  - {err}")
                self.log_check_result(False, "CCL Recover [Error] 发现非绿底/红底异常")
                CheckpointStore.save(
                    page_key="niw_02",
                    title="CCL Recover",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"{error_count} 个节点红底异常 (共 {total_satellites} 个)"
                )
                return False
            else:
                # 节点全部绿底正常：通过巡检
                self.log_check_result(True, f"CCL Recover 巡检通过，全表 {total_satellites} 个 Satellite 全部显示绿底正常。")

            # 9. 巡检通过后解封并点击页面上的 Checkpoint 打勾按钮
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_02",
                title="CCL Recover",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全表 {total_satellites} 个 Satellite 全部绿底正常"
            )
            return True

        except Exception as e:
            # 捕获未知异常
            return self.handle_exception("niw_02", "CCL Recover", e)
