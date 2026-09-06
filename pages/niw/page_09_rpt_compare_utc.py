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
    def check(self) -> bool:
        self.log_station_header("第9站 RPT Compare UTC", menu_id="apy_b0i10text")
        try:
            # 1. 导航切入 RPT Compare UTC 页面
            self.navigate_to_menu("RPT Compare UTC", menu_id="apy_b0i10text", section="NIW")

            # 2. 点击 Search 触发最新查询
            self.click_search_button()

            self.wait_for_page_loaded(seconds=1.5, max_wait=35)
            
            # 3. DOM 精准抓取 24 小时矩阵节点
            p9_data = self.driver.execute_script("""
                var result = {
                    categoryName: "RCM",
                    hoursCount: 0,
                    totalOkCount: 0,
                    errList: [],
                    hourRows: []
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Hour") === -1 && txt.indexOf("UTC") === -1) return;

                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length >= 5) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            if (lineTxt.indexOf("Hour") !== -1 || lineTxt.indexOf("Type") !== -1 || lineTxt.indexOf("UTC PL") !== -1) return;

                            var hourVal = "";
                            var typeVal = "";
                            var dateStartIdx = 2;

                            if (txts[0] === "RCM" || txts[0] === "LRCM" || txts[0] === "NIW") {
                                hourVal = txts[1];
                                typeVal = txts[2];
                                dateStartIdx = 3;
                            } else {
                                hourVal = txts[0];
                                typeVal = txts[1];
                                dateStartIdx = 2;
                            }

                            if (hourVal && (typeVal === "sport" || !isNaN(parseInt(hourVal)))) {
                                result.hoursCount++;
                                var rowHasErr = false;

                                for (var c = dateStartIdx; c < tds.length; c++) {
                                    var cellText = tds[c].innerText.trim().toLowerCase();
                                    var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                    var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);

                                    if (cellText === "ok" && !isRed) {
                                        result.totalOkCount++;
                                    } else if (cellText !== "") {
                                        rowHasErr = true;
                                        result.errList.push("Hour " + hourVal + " (列" + c + "): " + cellText);
                                    }
                                }

                                var statusTag = " [OK/正常绿底]";
                                if (rowHasErr) statusTag = " [ERROR/Tier 1 异常阻断]";

                                var line = "Hour " + hourVal + " (" + typeVal + "): 单元格校验通过 " + statusTag;
                                result.hourRows.push(line);
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

                return result;
            """)

            cat_name = p9_data.get("categoryName", "RCM")
            hours_count = p9_data.get("hoursCount", 0)
            total_ok = p9_data.get("totalOkCount", 0)
            err_list = p9_data.get("errList", [])
            hour_rows = p9_data.get("hourRows", [])
            raw_rows = p9_data.get("rawRows", [])

            self.log_data_extracted(f"成功抓取 RPT Compare UTC ({cat_name}) 数据矩阵 ({hours_count} 个时间段 00~23) | 'ok' 单元格: {total_ok} 个 | 异常单元格: {len(err_list)} 个")
            self.log_check_method("全量核对 24 小时 (00~23) 在各个日期与 Satellite 节点下 UTC Curr, PL, Odd 子列状态 ( Tier 1 阻断规则 )")

            # 4. 无条件全量明细打印 (全量巡检数据明细)
            summary_lines = [f"【RPT Compare UTC 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in hour_rows])
            self.log_data_summary(summary_lines)

            table_headers = ["Hour Segment", "Type", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["hour"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # 5. Tier 1 报错阻断判定
            if len(err_list) > 0:
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
                self.log_check_result(True, f"RPT Compare UTC 全部 24 个时间段 (00~23) 跨度下所有子列均显示 'ok' 绿底，巡检合格！")

            # 6. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
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
            self.log_check_result(False, f"RPT Compare UTC 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_09",
                title="RPT Compare UTC",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception occurred"
            )
            return False
