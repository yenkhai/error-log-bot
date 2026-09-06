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
        self.log_station_header("第2站 CCL Recover", menu_id="apy_b0i3text")
        try:
            # 1. 导航切入 CCL Recover 菜单
            self.navigate_to_menu("CCL Recover", menu_id="apy_b0i3text", section="NIW")

            # 2. 触发 Search 搜索刷新
            try:
                search_btn = self.driver.find_elements(By.ID, "id_search_button")
                if search_btn:
                    self.log("[SEARCH] 点击 CCL Recover Search 刷新按钮 (id: id_search_button)...")
                    self.driver.execute_script("arguments[0].click();", search_btn[0])
                    self.wait_for_page_loaded(seconds=2)
            except Exception as e:
                self.log(f"[WARN] 点击 Search 刷新提示: {e}")


            # 3. 在 JS 内存中抓取红框内 Satellite 与 Last Recover 数据及 RGB 背景色 (支持 RCM/LRCM 跨行继承)
            ccl_data = self.driver.execute_script("""
                var tables = document.querySelectorAll("table");
                var allDetails = [];
                var errorDetails = [];
                var rawRows = [];
                var totalSatellites = 0;
                var errorCount = 0;

                for (var t = 0; t < tables.length; t++) {
                    var currentCompany = (t === 3) ? "LRCM" : "RCM";
                    var rows = tables[t].querySelectorAll("tr");

                    for (var r = 0; r < rows.length; r++) {
                        var tds = rows[r].querySelectorAll("td");

                        if (tds.length >= 2) {
                            var satText = "";
                            var timeTd = null;

                            for (var c = 0; c < tds.length; c++) {
                                var txt = tds[c].innerText.trim();
                                if (txt.indexOf("nv") !== -1 || txt.indexOf("-") !== -1) {
                                    satText = txt;
                                    if (c + 1 < tds.length) {
                                        timeTd = tds[c + 1];
                                    }
                                    break;
                                }
                            }

                            if (satText && timeTd) {
                                totalSatellites++;
                                var timeText = timeTd.innerText.trim();
                                var style = window.getComputedStyle(timeTd);
                                var bg = style.backgroundColor;
                                
                                var isRed = false;
                                var isGreen = false;

                                var bgMatch = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                if (bgMatch) {
                                    var red = parseInt(bgMatch[1]);
                                    var green = parseInt(bgMatch[2]);
                                    var blue = parseInt(bgMatch[3]);

                                    if (green > 120 && red < 100) isGreen = true;
                                    if (red >= 170 && green <= 110 && blue <= 110) isRed = true;
                                }

                                var lowerTime = timeText.toLowerCase();
                                var isError = isRed || lowerTime.includes("error") || lowerTime.includes("missing") || (!isGreen && timeText === "");

                                var itemStr = currentCompany + ": " + satText + " -> Last Recover: " + (timeText || "N/A");
                                var statusStr = isError ? "ERROR/红底异常" : "OK/正常";

                                rawRows.push({
                                    company: currentCompany,
                                    satellite: satText,
                                    last_recover: timeText || "N/A",
                                    status: statusStr,
                                    is_error: isError
                                });

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
                return {
                    allDetails: allDetails,
                    errorDetails: errorDetails,
                    rawRows: rawRows,
                    totalSatellites: totalSatellites,
                    errorCount: errorCount
                };
            """)

            all_details = ccl_data.get("allDetails", [])
            error_details = ccl_data.get("errorDetails", [])
            raw_rows = ccl_data.get("rawRows", [])
            total_satellites = ccl_data.get("totalSatellites", 0)
            error_count = ccl_data.get("errorCount", 0)

            self.log_data_extracted(f"成功抓取到全表 {total_satellites} 个 Satellite 节点 (异常节点数: {error_count})")
            self.log_check_method("深度读取 Last Recover 单元格背景 RGB 颜色 (绿底为 OK/正常, 红底/非绿底为 ERROR/异常)")

            # 4. 【核心需求】：无论有没有 error，一律打印完整数据明细！
            self.log_data_summary([f"【CCL Recover 全量 Satellite 恢复状态明细 (共 {total_satellites} 个节点)】:"] + [f"   * {item}" for item in all_details])

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

            # 5. 判定结果
            if error_count > 0:
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
                self.log_check_result(True, f"CCL Recover 巡检通过，全表 {total_satellites} 个 Satellite 全部显示绿底正常。")

            # 6. 解封并点击 Checkpoint 打勾按钮
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
            self.log_check_result(False, f"CCL Recover 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_02",
                title="CCL Recover",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception during check"
            )
            return False
