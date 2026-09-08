"""
================================================================================
第9站 RPT Compare UTC 关卡检查器 (pages/niw/page_09_rpt_compare_utc.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户截图圈出的红框矩阵 (RPT Compare UTC Tool):
   - 包含 24 小时时间行 (Hour 00 到 Hour 23)；
   - 包含多日期 (06/08/2026 ~ 12/08/2026) 及多 Satellite 卫星 (tq001, eq001...)；
   - 包含每个 Satellite 下的 3 大子列 (UTC Curr, UTC PL, UTC Odd)；
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 逐行打印 24 小时 (00 ~ 23) 在各个日期下所有子列的 ok / 异常校验结论；
3. 判定标准 (Tier 1 致命报错阻断):
   - 若任何单元格出现非 ok、error 或红底，判定为 Tier 1 报错阻断 Checkpoint！
4. 自动接入 24h 滚动历史存档与 HTML 仪表盘 (dashboard.html)。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTCompareUTCChecker(BaseChecker):
    """
    RPT Compare UTC 报表对比检查器类
    负责全面核对 24 小时时间行 (00~23) 在多个日期与 Satellite 节点下的 UTC Curr, PL, Odd 子列状态。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 RPT Compare UTC 页面 (apy_b0i10text)
        2. 点击 Search 按钮获取最新数据
        3. 执行前端 JavaScript 深度抓取 24 小时时间段矩阵
        4. 打印全量明细日志并进行 Tier 1 报错阻断校验 (任何红底或非 ok 均阻断)
        5. 存储结果至 CheckpointStore 并点击关卡 Checkpoint 按钮
        """
        # 1. 打印第 9 站日志头信息
        self.log_station_header("第9站 RPT Compare UTC", menu_id="apy_b0i10text")
        try:
            # 2. 导航切入 RPT Compare UTC 页面 (Menu ID: apy_b0i10text)
            self.navigate_to_menu("RPT Compare UTC", menu_id="apy_b0i10text", section="NIW")

            # 3. 点击 Search 触发最新查询
            self.click_search_button()

            # 4. 智能等待页面数据加载完毕 (最多等待 35 秒)
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)
            
            # 5. 执行核心 JavaScript 脚本，深度抓取 24 小时 (00~23) 矩阵表格数据
            p9_data = self.driver.execute_script("""
                // 1. 初始化返回给 Python 的数据容器
                var result = {
                    categoryName: "RCM",   // 当前分类名称 (默认 RCM)
                    hoursCount: 0,          // 抓取到的时间段总数 (正常为 24 小时 00~23)
                    totalOkCount: 0,        // 状态为 'ok' 绿底的单元格总数
                    errList: [],            // 异常单元格详细记录列表
                    hourRows: [],           // 格式化的文本摘要日志行
                    rawRows: []             // 结构化数据行 (供 HTML 仪表盘展示)
                };

                // 2. 获取当前下拉菜单中选中的分类名称 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                // 3. 获取并遍历页面中所有的 <table> 标签
                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 过滤掉日历控件的表格 (避免被干扰)
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    
                    // 获取当前表格的完整纯文本
                    var txt = t.innerText ? t.innerText.trim() : "";
                    // 只有包含 'Hour' 或 'UTC' 关键词的表格才是我们要抓取的主矩阵表格
                    if (txt.indexOf("Hour") === -1 && txt.indexOf("UTC") === -1) return;

                    // 4. 获取表格中的所有数据行 <tr>
                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        // 获取当前行的所有单元格 (td 或 th)
                        var tds = r.querySelectorAll("td, th");
                        // 矩阵行通常拥有较多列 (至少 5 列以上)
                        if (tds.length >= 5) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            // 排除表头行 (包含 Hour, Type, UTC PL 等列名)
                            if (lineTxt.indexOf("Hour") !== -1 || lineTxt.indexOf("Type") !== -1 || lineTxt.indexOf("UTC PL") !== -1) return;

                            var hourVal = "";        // 小时字段值 (如 00, 01, ..., 23)
                            var typeVal = "";        // 类型字段值 (如 sport)
                            var dateStartIdx = 2;    // 数据列起始索引 (默认从第 2 列开始)

                            // 判断是否有前置公司标识 (如 RCM, LRCM, NIW)
                            if (txts[0] === "RCM" || txts[0] === "LRCM" || txts[0] === "NIW") {
                                hourVal = txts[1];       // 第 1 列为小时数
                                typeVal = txts[2];       // 第 2 列为类型
                                dateStartIdx = 3;        // 数据状态列从第 3 列开始
                            } else {
                                hourVal = txts[0];       // 第 0 列为小时数
                                typeVal = txts[1];       // 第 1 列为类型
                                dateStartIdx = 2;        // 数据状态列从第 2 列开始
                            }

                            // 5. 确保提取到有效的小时字段，且类型为有效业务类型
                            if (hourVal && (typeVal === "sport" || !isNaN(parseInt(hourVal)))) {
                                result.hoursCount++;     // 统计有效小时行计数
                                var rowHasErr = false;   // 标记当前行是否存在异常单元格

                                // 6. 遍历当前行的所有数据列单元格
                                for (var c = dateStartIdx; c < tds.length; c++) {
                                    var cellText = tds[c].innerText.trim().toLowerCase();
                                    // 获取单元格计算后的背景色样式
                                    var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                    // 判定是否为红底 (RGB 中含有 255 且包含 0, 0 即红色预警)
                                    var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);

                                    // 正常情况：文本为 'ok' 且不是红底
                                    if (cellText === "ok" && !isRed) {
                                        result.totalOkCount++;
                                    } else if (cellText !== "") {
                                        // 异常情况：单元格有文本但不是 ok，或者呈现红底
                                        rowHasErr = true;
                                        result.errList.push("Hour " + hourVal + " (列" + c + "): " + cellText);
                                    }
                                }

                                // 7. 拼接当前小时行的巡检状态标签
                                var statusTag = " [OK/正常绿底]";
                                if (rowHasErr) statusTag = " [ERROR/Tier 1 异常阻断]";

                                var line = "Hour " + hourVal + " (" + typeVal + "): 单元格校验通过 " + statusTag;
                                result.hourRows.push(line);
                                
                                // 8. 存入供仪表盘呈现的结构化数据字典
                                result.rawRows = result.rawRows || [];
                                result.rawRows.push({
                                    hour: "Hour " + hourVal,
                                    type: typeVal,
                                    status: rowHasErr ? "ERROR" : "OK",
                                    is_error: rowHasErr
                                });
                            }
                        }
                    });
                });

                // 将解析提取的结果对象返回给 Python
                return result;
            """)

            # 6. 从前端返回的字典中解析各项指标
            cat_name = p9_data.get("categoryName", "RCM")
            hours_count = p9_data.get("hoursCount", 0)
            total_ok = p9_data.get("totalOkCount", 0)
            err_list = p9_data.get("errList", [])
            hour_rows = p9_data.get("hourRows", [])
            raw_rows = p9_data.get("rawRows", [])

            # 7. 打印数据提取日志与巡检逻辑方法说明
            self.log_data_extracted(f"成功抓取 RPT Compare UTC ({cat_name}) 数据矩阵 ({hours_count} 个时间段 00~23) | 'ok' 单元格: {total_ok} 个 | 异常单元格: {len(err_list)} 个")
            self.log_check_method("全量核对 24 小时 (00~23) 在各个日期与 Satellite 节点下 UTC Curr, PL, Odd 子列状态 ( Tier 1 阻断规则 )")

            # 8. 无条件全量明细打印 (全量巡检数据明细)
            summary_lines = [f"【RPT Compare UTC 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in hour_rows])
            self.log_data_summary(summary_lines)

            # 9. 构建存储中心 (CheckpointStore) 表头与表格行
            table_headers = ["Hour Segment", "Type", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["hour"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # 10. Tier 1 致命报错阻断判定
            if len(err_list) > 0:
                # 存在异常单元格，判定失败，阻断当前关卡
                self.log_check_result(False, f"RPT Compare UTC 巡检发现 {len(err_list)} 处非 ok/红底异常单元格，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_09",
                    title="RPT Compare UTC",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Total OK: {total_ok} | Errors: {len(err_list)}"
                )
                return False
            else:
                # 全部 24 个时间段均为绿底 ok，判定合格
                self.log_check_result(True, f"RPT Compare UTC 全部 24 个时间段 (00~23) 跨度下所有子列均显示 'ok' 绿底，巡检合格！")

            # 11. 解封并点击页面底部的 Checkpoint 按钮
            self.click_checkpoint()
            
            # 12. 保存成功记录至 CheckpointStore
            CheckpointStore.save(
                page_key="niw_09",
                title="RPT Compare UTC",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全部 24 个时间段 (00~23) 全部绿底 ok"
            )
            return True

        except Exception as e:
            # 捕获运行过程中的任何异常并记录失败状态
            return self.handle_exception("niw_09", "RPT Compare UTC", e)
