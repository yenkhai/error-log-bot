"""
================================================================================
第4站 Result Process 关卡检查器 (pages/niw/page_04_result_process.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 监控 5 大表格:
   - Event Score Process
   - Syn Event
   - Result Action
   - Promotion Action
   - Satellite Score Missing
2. 判定标准:
   - 单元格文字为 'success' 且非红底/红字判定为 [OK/正常绿底]
   - 单元格文字非 success (如 fail/missing/error) 或颜色为 RGB 真实红底判定为 [ERROR/异常阻断]
   - 解决误报: 采用 RGB 三原色解析 (R>=170 & G<=110 & B<=110)，精准过滤掉白色(255,255,255)与透明色造成的伪红字误报。
3. 【无条件全量打印】: 5 大表格下所有 satellite 节点的两个日期 (D1/D2) 状态全量透明化逐行打印。
================================================================================
"""

import time
from core.base_checker import BaseChecker

class ResultProcessChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第4站 Result Process", menu_id="apy_b0i5text")
        try:
            # 1. 导航切入 Result Process 菜单
            self.navigate_to_menu("Result Process", menu_id="apy_b0i5text", section="NIW")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # 2. 精准提取 5 大监控表格数据
            p4_data = self.driver.execute_script("""
                var result = {
                    eventScoreDetails: [],
                    synEventDetails: [],
                    resultActionDetails: [],
                    promotionActionDetails: [],
                    missingDetails: [],
                    errorCount: 0
                };

                // 核心 RGB 红底判定逻辑 (R >= 170 且 G <= 110 且 B <= 110)
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110);
                    }
                    return false;
                }

                function checkSuccessCell(tdEl) {
                    if (!tdEl) return false;
                    var txt = tdEl.innerText ? tdEl.innerText.trim().toLowerCase() : "";
                    var bg = window.getComputedStyle(tdEl).backgroundColor;
                    var fg = window.getComputedStyle(tdEl).color;

                    var hasRed = isRed(bg) || isRed(fg);
                    var isSuccessText = (txt === "success" || txt === "");
                    
                    // 若文本为 fail/missing/error 或命中红底/红字，判定为异常
                    if (!isSuccessText || hasRed || txt.indexOf("error") !== -1 || txt.indexOf("fail") !== -1) {
                        return true; // isError = true
                    }
                    return false;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 1. Event Score Process
                    if (txt.indexOf("Event Score Process") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var sat = tds[0].innerText.trim();
                                var d1 = tds[1].innerText.trim();
                                var d2 = tds[2].innerText.trim();
                                if (sat && sat !== "Satellite" && sat.indexOf("Event Score Process") === -1 && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[1]);
                                    var isErr2 = checkSuccessCell(tds[2]);

                                    if (isErr1 || isErr2) result.errorCount++;
                                    var tag = (isErr1 || isErr2) ? " [ERROR/异常阻断]" : " [OK/正常绿底]";
                                    result.eventScoreDetails.push(sat + " -> D1: " + d1 + ", D2: " + d2 + tag);
                                }
                            }
                        }
                    }

                    // 2. Syn Event
                    if (txt.indexOf("Syn Event") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var sat = tds[0].innerText.trim();
                                var d1 = tds[1].innerText.trim();
                                var d2 = tds[2].innerText.trim();
                                if (sat && sat !== "Satellite" && sat.indexOf("Syn Event") === -1 && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[1]);
                                    var isErr2 = checkSuccessCell(tds[2]);

                                    if (isErr1 || isErr2) result.errorCount++;
                                    var tag = (isErr1 || isErr2) ? " [ERROR/异常阻断]" : " [OK/正常绿底]";
                                    result.synEventDetails.push(sat + " -> D1: " + d1 + ", D2: " + d2 + tag);
                                }
                            }
                        }
                    }

                    // 3. Result Action
                    if (txt.indexOf("Result Action") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var sat = tds[0].innerText.trim();
                                var d1 = tds[1].innerText.trim();
                                var d2 = tds[2].innerText.trim();
                                if (sat && sat !== "Satellite" && sat.indexOf("Result Action") === -1 && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[1]);
                                    var isErr2 = checkSuccessCell(tds[2]);

                                    if (isErr1 || isErr2) result.errorCount++;
                                    var tag = (isErr1 || isErr2) ? " [ERROR/异常阻断]" : " [OK/正常绿底]";
                                    result.resultActionDetails.push(sat + " -> D1: " + d1 + ", D2: " + d2 + tag);
                                }
                            }
                        }
                    }

                    // 4. Promotion Action
                    if (txt.indexOf("Promotion Action") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var sat = tds[0].innerText.trim();
                                var d1 = tds[1].innerText.trim();
                                var d2 = tds[2].innerText.trim();
                                if (sat && sat !== "Satellite" && sat.indexOf("Promotion Action") === -1 && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[1]);
                                    var isErr2 = checkSuccessCell(tds[2]);

                                    if (isErr1 || isErr2) result.errorCount++;
                                    var tag = (isErr1 || isErr2) ? " [ERROR/异常阻断]" : " [OK/正常绿底]";
                                    result.promotionActionDetails.push(sat + " -> D1: " + d1 + ", D2: " + d2 + tag);
                                }
                            }
                        }
                    }

                    // 5. Satellite Score Missing
                    if (txt.indexOf("Satellite Score Missing") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td, th");
                            if (tds.length >= 2) {
                                var d1 = tds[0].innerText.trim();
                                var d2 = tds[1].innerText.trim();
                                if (d1 && d1 !== "Satellite Score Missing" && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[0]);
                                    var isErr2 = checkSuccessCell(tds[1]);

                                    if (isErr1 || isErr2) result.errorCount++;
                                    var tag = (isErr1 || isErr2) ? " [ERROR/异常阻断]" : " [OK/正常绿底]";
                                    result.missingDetails.push("Score Missing Check -> D1: " + d1 + ", D2: " + d2 + tag);
                                }
                            }
                        }
                    }
                });

                return result;
            """)

            event_details = p4_data.get("eventScoreDetails", [])
            syn_details = p4_data.get("synEventDetails", [])
            result_details = p4_data.get("resultActionDetails", [])
            promo_details = p4_data.get("promotionActionDetails", [])
            missing_details = p4_data.get("missingDetails", [])
            
            error_count = p4_data.get("errorCount", 0)
            total_items = len(event_details) + len(syn_details) + len(result_details) + len(promo_details) + len(missing_details)

            self.log_data_extracted(f"成功抓取 Result Process 全局 5 大监控表格共 {total_items} 项节点数据 (异常发现数: {error_count})")
            self.log_check_method("校验 5 大表格所有节点单元格是否为 success 以及 RGB 正常绿底")

            # 3. 无论是否有 Error，全量明细无条件透明化打印在 Log 控制台中
            all_summary = ["【Result Process 全量巡检数据明细】:"]
            
            if event_details:
                all_summary.append("--- [1. Event Score Process 板块] ---")
                all_summary.extend([f"   * {line}" for line in event_details])

            if syn_details:
                all_summary.append("--- [2. Syn Event 板块] ---")
                all_summary.extend([f"   * {line}" for line in syn_details])

            if result_details:
                all_summary.append("--- [3. Result Action 板块] ---")
                all_summary.extend([f"   * {line}" for line in result_details])

            if promo_details:
                all_summary.append("--- [4. Promotion Action 板块] ---")
                all_summary.extend([f"   * {line}" for line in promo_details])

            if missing_details:
                all_summary.append("--- [5. Satellite Score Missing 板块] ---")
                all_summary.extend([f"   * {line}" for line in missing_details])

            self.log_data_summary(all_summary)

            # 4. 判定结论
            if error_count > 0:
                self.log(f"[Error] Result Process 检测到 {error_count} 项非 success 或红底异常，阻断 Checkpoint！")
                self.log_check_result(False, f"Result Process 存在 {error_count} 项状态异常，阻断 Checkpoint。")
                return False
            else:
                self.log_check_result(True, "Result Process 5 大表格状态全部为 success 且绿底正常，巡检通过！")

            # 5. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Result Process 检查出现异常: {e}")
            return False
