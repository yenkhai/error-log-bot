"""
================================================================================
第8站 RPT AI 关卡检查器 (pages/niw/page_08_rpt_ai.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户截图圈出的红框矩阵 (RPT Compare AI Tool):
   - 包含 24 家 Satellite 卫星公司 (d0005, d0008, d0009... 到 eq001)；
   - 包含多日期梯度 (10/08/2026, 11/08/2026...) 下的 3 大子列:
     1. Satellite Wager (卫星注单)
     2. RPT Punter (会员报表)
     3. RPT Punter IP (会员 IP 报表)
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 逐行打印 24 家 Satellite 卫星公司在各个日期下 3 大子列的 ok / 异常状态；
3. 判定标准 (Tier 1 致命报错阻断):
   - 若任何单元格出现非 ok、error 或红底，判定为 Tier 1 报错阻断 Checkpoint！
4. 自动接入 24h 滚动历史存档与 HTML 仪表盘 (dashboard.html)。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTAIChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第8站 RPT AI", menu_id="apy_b0i9text")
        try:
            # 1. 导航切入 RPT AI 页面
            self.navigate_to_menu("RPT AI", menu_id="apy_b0i9text", section="NIW")
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)
            # 3. DOM 精准抓取 24 家 Satellite 节点矩阵
            p8_data = self.driver.execute_script("""
                var result = {
                    categoryName: "RCM",
                    satellitesCount: 0,
                    totalOkCount: 0,
                    errList: [],
                    satelliteRows: [],
                    rawRows: [],
                    mainTableHeaders: [],
                    mainTableRows: [],
                    punterList: [],
                    aiPunterList: []
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Satellite") === -1 && txt.indexOf("RPT Punter") === -1 && txt.indexOf("Punter IP") === -1) return;

                    var rows = t.querySelectorAll("tr");

                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length >= 5) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            if (result.mainTableHeaders.length === 0 && (lineTxt.indexOf("Satellite") !== -1 || lineTxt.indexOf("Date") !== -1)) {
                                result.mainTableHeaders = txts;
                            }

                            if (lineTxt.indexOf("Satellite Wager") !== -1 || lineTxt.indexOf("RPT Punter IP") !== -1 || lineTxt.indexOf("Date") !== -1) return;

                            var sat = "";
                            var dateStartIdx = 2;

                            if (txts[0] === "RCM" || txts[0] === "LRCM" || txts[0] === "NIW") {
                                sat = txts[1];
                                dateStartIdx = 2;
                            } else {
                                sat = txts[0];
                                dateStartIdx = 1;
                            }

                            if (sat && sat !== "Satellite" && sat.indexOf("Satellite") === -1) {
                                result.satellitesCount++;
                                var cellStatuses = [];
                                var rowHasErr = false;

                                var rowCells = [];
                                for (var c = 0; c < tds.length; c++) {
                                    var cellText = tds[c].innerText.trim().toLowerCase();
                                    var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                    var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);
                                    var isGreen = (bg.indexOf("0, 128") !== -1 || bg.indexOf("0, 204") !== -1 || bg.indexOf("0, 230") !== -1 || bg.indexOf("0, 255") !== -1 || cellText === "ok");

                                    var bgTag = isRed ? "red" : (isGreen ? "green" : "white");
                                    rowCells.push({ text: tds[c].innerText.trim(), bg: bgTag });

                                    if (c >= dateStartIdx) {
                                        if (cellText === "ok" && !isRed) {
                                            result.totalOkCount++;
                                            cellStatuses.push("col" + (c - dateStartIdx + 1) + ":ok");
                                        } else if (cellText !== "") {
                                            rowHasErr = true;
                                            result.errList.push(sat + " (列" + c + "): " + cellText);
                                            cellStatuses.push("col" + (c - dateStartIdx + 1) + ":" + cellText + "[Tier 1 报错]");
                                        }
                                    }
                                }
                                result.mainTableRows.push(rowCells);

                                var statusTag = " [OK/正常绿底]";
                                if (rowHasErr) statusTag = " [ERROR/Tier 1 异常阻断]";

                                var line = sat + ": 单元格状态(" + cellStatuses.length + "项) " + statusTag;
                                result.satelliteRows.push(line);
                                result.rawRows.push({
                                    satellite: sat,
                                    sub_cols: "Wager / Punter / IP",
                                    total_items: cellStatuses.length,
                                    errors: rowHasErr ? "Has Errors" : "0",
                                    status: rowHasErr ? "ERROR" : "OK",
                                    is_error: rowHasErr
                                });
                            }
                        }
                    });
                });

                // 尝试抓取 Generate Punter / AI Punter 表格 (若存在)
                tables.forEach(function(t) {
                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Robot ID") !== -1 && (txt.indexOf("Rpt Date") !== -1 || txt.indexOf("Function") !== -1)) {
                        var pRows = t.querySelectorAll("tr");
                        pRows.forEach(function(r) {
                            var tds = r.querySelectorAll("td");
                            if (tds.length >= 2) {
                                var robotId = tds[0].innerText.trim();
                                var rptDate = tds[1].innerText.trim();
                                var fn = tds[2] ? tds[2].innerText.trim() : "";
                                var dateBg = window.getComputedStyle(tds[1]).backgroundColor;
                                var isRedDate = (dateBg.indexOf("255") !== -1 && dateBg.indexOf("0, 0") !== -1) || fn.indexOf("Pending") !== -1;
                                if (robotId && !isNaN(parseInt(robotId)) && rptDate.length >= 8) {
                                    var num = parseInt(robotId);
                                    var item = { robotId: robotId, rptDate: rptDate, fn: fn, isRed: isRedDate };
                                    if (num >= 800) {
                                        result.aiPunterList.push(item);
                                    } else {
                                        result.punterList.push(item);
                                    }
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p8_data.get("categoryName", "RCM")
            sat_count = p8_data.get("satellitesCount", 0)
            total_ok = p8_data.get("totalOkCount", 0)
            err_list = p8_data.get("errList", [])
            sat_rows = p8_data.get("satelliteRows", [])
            raw_rows = p8_data.get("rawRows", [])

            self.log_data_extracted(f"成功抓取 RPT AI ({cat_name}) 数据矩阵 ({sat_count} 个卫星节点) | 'ok' 单元格: {total_ok} 个 | 异常单元格: {len(err_list)} 个")
            self.log_check_method("全量核对 Satellite 卫星节点在各个日期下 3 大子列 (Satellite Wager, RPT Punter, RPT Punter IP) 状态 ( Tier 1 阻断规则 )")

            # 4. 无条件全量明细打印 (全量巡检数据明细)
            summary_lines = [f"【RPT AI 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in sat_rows])
            self.log_data_summary(summary_lines)

            # 构筑 1:1 原生多表
            subtables = []
            main_rows = p8_data.get("mainTableRows", [])
            main_headers = p8_data.get("mainTableHeaders", [])
            if main_rows:
                if not main_headers:
                    first_len = len(main_rows[0])
                    main_headers = ["Col " + str(i+1) for i in range(first_len)]
                subtables.append({
                    "title": f"RPT AI Satellite Matrix ({cat_name})",
                    "header_bg": "#C8D7A6",
                    "headers": main_headers,
                    "rows": main_rows
                })
            else:
                table_headers = ["Satellite", "3 Sub-Columns", "Total Checks", "Errors", "Status"]
                table_rows = [
                    [
                        CheckpointStore.make_cell(r["satellite"]),
                        CheckpointStore.make_cell(r["sub_cols"]),
                        CheckpointStore.make_cell(str(r["total_items"])),
                        CheckpointStore.make_cell(r["errors"], bg="red" if r.get("is_error") else "green"),
                        CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                    ]
                    for r in raw_rows
                ]
                subtables.append({
                    "title": f"RPT AI Satellite Matrix ({cat_name})",
                    "header_bg": "#C8D7A6",
                    "headers": table_headers,
                    "rows": table_rows
                })

            p_list = p8_data.get("punterList", [])
            if p_list:
                subtables.append({
                    "title": "Generate Punter",
                    "header_bg": "#C8D7A6",
                    "headers": ["Robot ID", "Rpt Date", "Function"],
                    "rows": [
                        [
                            p["robotId"],
                            CheckpointStore.make_cell(p["rptDate"], "red" if p.get("isRed") else "white"),
                            CheckpointStore.make_cell(p["fn"], is_link="Generate" in p.get("fn", ""))
                        ]
                        for p in p_list
                    ]
                })

            ai_p_list = p8_data.get("aiPunterList", [])
            if ai_p_list:
                subtables.append({
                    "title": "Generate AI Punter",
                    "header_bg": "#C8D7A6",
                    "headers": ["Robot ID", "Rpt Date", "Function"],
                    "rows": [
                        [
                            p["robotId"],
                            CheckpointStore.make_cell(p["rptDate"], "red" if p.get("isRed") else "white"),
                            CheckpointStore.make_cell(p["fn"], is_link="Generate" in p.get("fn", ""))
                        ]
                        for p in ai_p_list
                    ]
                })

            # 5. Tier 1 报错阻断判定 (Check Logic 保持 100% 不变)
            if len(err_list) > 0:
                self.log_check_result(False, f"RPT AI 巡检发现 {len(err_list)} 处非 ok/红底异常单元格，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_08",
                    title="RPT AI",
                    status=False,
                    tables=subtables,
                    summary=f"{len(err_list)} error(s) found in {sat_count} satellites"
                )
                return False
            else:
                self.log_check_result(True, f"RPT AI 全部 {sat_count} 个 Satellite 卫星节点所有子列均显示 'ok' 绿底，巡检合格！")

            # 6. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_08",
                title="RPT AI",
                status=True,
                tables=subtables,
                summary=f"全部 {sat_count} 个 Satellite 节点全部绿底 ok"
            )
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT AI 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_08",
                title="RPT AI",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception during check"
            )
            return False
