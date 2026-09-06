"""
================================================================================
第6站 RPT PolyMarket 关卡检查器 (pages/niw/page_06_rpt_polymarket.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户截图核心两大红框:
   - 左框: Reset Log 列数值 (如 0, 0, 0...)；
   - 右框: 05/08/2026 ~ 11/08/2026 跨度下所有 Satellite 卫星公司 (f0001, e1002, e2002...) sport 类型的 RPT 日期状态；
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 无论正确与否，逐行全量打印所有 Satellite 卫星公司的 Reset Log 数值与各日期 ok 状态！
3. 级别划分 (Tier 1 报错阻断 Checkpoint):
   - 根据用户最新明确指令: "以 Tier 1 警示通报"；
   - 若 Reset Log > 0 或某日期状态不为 ok (如 error 或红底)，直接判定为 Tier 1 报错阻断 Checkpoint！
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTPolyMarketChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第6站 RPT PolyMarket", menu_id="apy_b0i7text")
        try:
            # 1. 导航切入 RPT PolyMarket 菜单
            self.navigate_to_menu("RPT PolyMarket", menu_id="apy_b0i7text", section="NIW")

            self.wait_for_page_loaded(seconds=0.5, max_wait=30)
            # 2. 精准抓取左框 Reset Log 与右框 7 天 RPT 矩阵数据
            p6_data = self.driver.execute_script("""
                var result = {
                    categoryName: "RCM",
                    satelliteRows: [],
                    rawRows: [],
                    totalOkCount: 0,
                    errCount: 0,
                    resetLogTotal: 0
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null || t.querySelector("table") !== null) return;

                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Reset Log") === -1 && txt.indexOf("Satellite") === -1) return;

                    var dates = ["05/08", "06/08", "07/08", "08/08", "09/08", "10/08", "11/08"];

                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length >= 10) {
                            var resetLog = "";
                            var sat = "";
                            var type = "";
                            var dateStartIdx = 3;

                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });

                            if (txts.indexOf("sport") !== -1) {
                                var sportIdx = txts.indexOf("sport");
                                type = "sport";
                                sat = txts[sportIdx - 1];
                                resetLog = txts[sportIdx - 2];
                                dateStartIdx = sportIdx + 1;

                                if (sat && sat !== "Satellite" && sat.indexOf("Satellite") === -1) {
                                    var dateStatuses = [];
                                    var rowHasErr = false;

                                    for (var c = dateStartIdx; c < tds.length; c++) {
                                        var cellText = tds[c].innerText.trim().toLowerCase();
                                        var dIdx = c - dateStartIdx;
                                        var dateHeader = dates[dIdx] || ("D" + (dIdx + 1));

                                        if (cellText === "ok") {
                                            result.totalOkCount++;
                                            dateStatuses.push(dateHeader + ":ok");
                                        } else {
                                            result.errCount++;
                                            rowHasErr = true;
                                            dateStatuses.push(dateHeader + ":" + cellText + "[Tier 1 报错]");
                                        }
                                    }

                                    var rLogNum = parseInt(resetLog) || 0;
                                    result.resetLogTotal += rLogNum;

                                    var isErr = (rowHasErr || rLogNum > 0);
                                    var statusTag = isErr ? " [ERROR/Tier 1 异常阻断]" : " [OK/正常]";

                                    var line = sat + " (" + type + "): Reset Log = " + resetLog + " | 日期状态(05/08~11/08): " + dateStatuses.join(", ") + statusTag;
                                    result.satelliteRows.push(line);
                                    result.rawRows.push({
                                        satellite: sat,
                                        type: type,
                                        reset_log: resetLog,
                                        date_status: dateStatuses.join(", "),
                                        status: isErr ? "ERROR" : "OK",
                                        is_error: isErr
                                    });
                                }
                            }
                        }
                    });
                });

                return result;
            """)

            cat_name = p6_data.get("categoryName", "RCM")
            sat_rows = p6_data.get("satelliteRows", [])
            raw_rows = p6_data.get("rawRows", [])
            total_ok = p6_data.get("totalOkCount", 0)
            total_err = p6_data.get("errCount", 0)
            reset_sum = p6_data.get("resetLogTotal", 0)

            self.log_data_extracted(f"成功抓取 RPT PolyMarket ({cat_name}) 数据矩阵 ({len(sat_rows)} 个卫星节点) | 'ok' 单元格: {total_ok} 个 | Reset Log 总数: {reset_sum}")
            self.log_check_method("全量核对 Satellite 卫星节点 Reset Log 及 7 天 RPT 日期状态 ( Tier 1 规则: Reset Log > 0 或非 ok 状态为 Tier 1 报错阻断 )")

            # 3. 无条件全量打印明细 (全量巡检数据明细)
            summary_lines = [f"【RPT PolyMarket 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in sat_rows])
            self.log_data_summary(summary_lines)

            table_headers = ["Satellite", "Type", "Reset Log", "7-Day Dates Status", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["satellite"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["reset_log"], bg="red" if int(r["reset_log"] or 0) > 0 else "green"),
                    CheckpointStore.make_cell(r["date_status"]),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # 4. Tier 1 阻断逻辑判定
            if total_err > 0 or reset_sum > 0:
                self.log_check_result(False, f"RPT PolyMarket 发现 {total_err} 项日期异常或 Reset Log={reset_sum} > 0，判定为 Tier 1 报错，阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_06",
                    title="RPT PolyMarket",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"异常: {total_err} 项日期异常, Reset Log={reset_sum}"
                )
                return False
            else:
                self.log_check_result(True, "RPT PolyMarket 所有 Satellite 卫星节点 Reset Log 均为 0 且日期状态全为 ok，巡检合格！")

            # 5. 巡检合格，解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_06",
                title="RPT PolyMarket",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全部 {len(raw_rows)} 个 Satellite 节点 7 天全部正常"
            )
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT PolyMarket 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_06",
                title="RPT PolyMarket",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e))]],
                summary="Exception during check"
            )
            return False
