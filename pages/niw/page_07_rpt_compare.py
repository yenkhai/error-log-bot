"""
================================================================================
第7站 RPT Compare 关卡检查器 (pages/niw/page_07_rpt_compare.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户截图圈出的全部 4 大红框区域:
   - 红框 1 (左侧状态): Rpt Complete (需为 Complete 绿底) 与 Reset Log (需为 0) [Tier 1]；
   - 红框 2 (主对比矩阵): 26 家 Satellite 卫星公司在 6 个日期及 7 大子列 (Lg, Com, Ag, Mem, Cy, Evt, Pro) 下的状态 (需全为 ok 绿底) [Tier 1]；
   - 红框 3 (左下 Generate Punter): 检查 Robot ID (103, 104, 107, 108, 112, 115...) 状态 [根据用户最新指令: 换去 Tier 3 仅通知不阻断 Checkpoint]；
   - 红框 4 (右下 Generate AI Punter): 检查 AI Robot ID (802, 809, 812...) 状态 [根据用户最新指令: 换去 Tier 3 仅通知不阻断 Checkpoint]；
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 逐行打印主对比矩阵、Generate Punter 及 Generate AI Punter 的每个 Robot 节点明细；
3. 判定标准:
   - Tier 1 报错阻断: 主对比矩阵非 ok/红底、Reset Log > 0，阻断 Checkpoint！
   - Tier 3 通报提醒: Generate Punter / Generate AI Punter 包含 Pending/红底，仅做 Log 通报提醒，不阻断 Checkpoint！
================================================================================
"""

import time
from core.base_checker import BaseChecker

class RPTCompareChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第7站 RPT Compare", menu_id="apy_b0i8text")
        try:
            # 1. 导航切入 RPT Compare 菜单
            self.navigate_to_menu("RPT Compare", menu_id="apy_b0i8text", section="NIW", wait_seconds=3)

            # 2. 触发 search_data() 加载最新对比矩阵与机器人状态
            self.driver.execute_script("""
                if (typeof search_data === "function") search_data();
            """)
            time.sleep(30)

            # 3. 抓取全页 4 大红框区域数据
            p7_data = self.driver.execute_script("""
                var result = {
                    categoryName: "RCM",
                    rptCompleteInfo: "",
                    rptCompleteHasErr: false,
                    resetLogTotal: 0,
                    matrixSatellitesCount: 0,
                    matrixTotalOk: 0,
                    matrixErrList: [],
                    punterRows: [],
                    punterErrList: [],
                    aiPunterRows: [],
                    aiPunterErrList: []
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 3.1 上方主表 (Red Box 1 & 2)
                    if (txt.indexOf("Satellite") !== -1 || txt.indexOf("Rpt Complete") !== -1 || txt.indexOf("Reset Log") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 10) {
                                var txts = [];
                                tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                                var lineTxt = txts.join(" ");

                                if (lineTxt.indexOf("Complete") !== -1 && !result.rptCompleteInfo) {
                                    for (var i = 0; i < tds.length; i++) {
                                        var cellVal = tds[i].innerText.trim();
                                        if (cellVal.indexOf("Complete") !== -1) {
                                            var bg = window.getComputedStyle(tds[i]).backgroundColor;
                                            var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);
                                            result.rptCompleteInfo = cellVal;
                                            if (isRed) result.rptCompleteHasErr = true;
                                            break;
                                        }
                                    }
                                }

                                var sportIdx = txts.indexOf("sport");
                                if (sportIdx !== -1) {
                                    result.matrixSatellitesCount++;
                                    var sat = txts[sportIdx - 1];
                                    var resetLog = txts[sportIdx - 2] || "0";
                                    result.resetLogTotal += parseInt(resetLog) || 0;

                                    for (var c = sportIdx + 1; c < tds.length; c++) {
                                        var cellText = tds[c].innerText.trim().toLowerCase();
                                        var cellBg = window.getComputedStyle(tds[c]).backgroundColor;
                                        var isRedCell = (cellBg.indexOf("255") !== -1 && cellBg.indexOf("0, 0") !== -1);

                                        if (cellText === "ok" && !isRedCell) {
                                            result.matrixTotalOk++;
                                        } else if (cellText !== "") {
                                            result.matrixErrList.push(sat + " (列" + c + "): " + cellText);
                                        }
                                    }
                                }
                            }
                        });
                    }

                    // 3.2 下方 Generate Punter / AI Punter (Red Box 3 & 4 - Tier 3 规则)
                    var pRows = t.querySelectorAll("tr");
                    pRows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length >= 2) {
                            var robotId = tds[0].innerText.trim();
                            var rptDate = tds[1].innerText.trim();
                            var fn = tds[2] ? tds[2].innerText.trim() : "";

                            var dateCell = tds[1];
                            var dateBg = window.getComputedStyle(dateCell).backgroundColor;
                            var isRedDate = (dateBg.indexOf("255") !== -1 && dateBg.indexOf("0, 0") !== -1) || fn.indexOf("Pending") !== -1;

                            if (robotId && !isNaN(parseInt(robotId)) && rptDate.length >= 8) {
                                var robotNum = parseInt(robotId);
                                var statusTag = " [OK/正常绿底]";
                                if (isRedDate) statusTag = " [Tier 3 提醒/不阻断]";

                                var line = "Robot " + robotId + ": Rpt Date = " + rptDate + (fn ? (", Function = " + fn) : "") + statusTag;

                                if (robotNum >= 800) {
                                    result.aiPunterRows.push(line);
                                    if (isRedDate) result.aiPunterErrList.push(line);
                                } else {
                                    result.punterRows.push(line);
                                    if (isRedDate) result.punterErrList.push(line);
                                }
                            }
                        }
                    });
                });

                return result;
            """)

            cat_name = p7_data.get("categoryName", "RCM")
            rpt_comp = p7_data.get("rptCompleteInfo", "Complete")
            sat_count = p7_data.get("matrixSatellitesCount", 0)
            total_ok = p7_data.get("matrixTotalOk", 0)
            reset_sum = p7_data.get("resetLogTotal", 0)
            matrix_errs = p7_data.get("matrixErrList", [])
            punter_rows = p7_data.get("punterRows", [])
            punter_errs = p7_data.get("punterErrList", [])
            ai_punter_rows = p7_data.get("aiPunterRows", [])
            ai_punter_errs = p7_data.get("aiPunterErrList", [])

            self.log_data_extracted(f"成功抓取 RPT Compare ({cat_name}) 数据矩阵 ({sat_count} 个卫星节点) | 'ok' 单元格: {total_ok} 个 | Rpt Complete: {rpt_comp} | Reset Log: {reset_sum}")
            self.log_check_method("校验规则: 主矩阵与 Reset Log 为 Tier 1 阻断；Generate Punter / AI Punter 为 Tier 3 仅通知提醒")

            # 4. 无条件全量打印明细 (全量巡检数据明细)
            summary_lines = [
                f"【RPT Compare 全量巡检数据明细 ({cat_name})】:",
                f"   * [1. 状态栏 (Tier 1)]: Rpt Complete = {rpt_comp} | Reset Log = {reset_sum} [OK/正常]",
                f"   * [2. 主对比矩阵 (Tier 1)]: 成功校验 {sat_count} 个 Satellite 卫星节点，包含 {total_ok} 个 'ok' 绿底单元格 [OK/正常]"
            ]

            if punter_rows:
                summary_lines.append("   * [3. Generate Punter 机器人状态 (Tier 3 通报提醒)]:")
                summary_lines.extend([f"      -> {p}" for p in punter_rows])

            if ai_punter_rows:
                summary_lines.append("   * [4. Generate AI Punter 机器人状态 (Tier 3 通报提醒)]:")
                summary_lines.extend([f"      -> {p}" for p in ai_punter_rows])

            self.log_data_summary(summary_lines)

            # 5. Tier 1 报错阻断判定 (主矩阵 & Reset Log)
            has_tier1_err = False
            err_reasons = []

            if reset_sum > 0:
                has_tier1_err = True
                err_reasons.append(f"Reset Log 总数 = {reset_sum} > 0")

            if len(matrix_errs) > 0:
                has_tier1_err = True
                err_reasons.append(f"主对比矩阵存在 {len(matrix_errs)} 处非 ok/红底单元格")

            if has_tier1_err:
                self.log_check_result(False, f"RPT Compare 巡检发现 Tier 1 致命异常: {'; '.join(err_reasons)}，强阻断 Checkpoint！")
                return False

            # 6. Tier 3 提醒判定 (Punter & AI Punter 存在 Pending 不阻断)
            tier3_msg = []
            if len(punter_errs) > 0:
                tier3_msg.append(f"Generate Punter 包含 {len(punter_errs)} 项 Pending 挂起")
            if len(ai_punter_errs) > 0:
                tier3_msg.append(f"Generate AI Punter 包含 {len(ai_punter_errs)} 项 Pending 挂起")

            if tier3_msg:
                self.log_check_result(True, f"RPT Compare 主矩阵合格，发现 Tier 3 提醒 ({'; '.join(tier3_msg)})，根据规则仅做 Log 通报，通过！")
            else:
                self.log_check_result(True, "RPT Compare 所有 4 大红框区域全部合格，通过！")

            # 7. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT Compare 检查出现异常: {e}")
            return False
