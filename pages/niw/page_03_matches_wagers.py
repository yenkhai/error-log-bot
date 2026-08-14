"""
================================================================================
第3站 Matches & Wagers 关卡检查器 (pages/niw/page_03_matches_wagers.py)
--------------------------------------------------------------------------------
【核心功能详解与判定规则】
1. 结构定位:
   - 页面左侧主结构由两个 tbody 分割：
     * tbody id="tr_RCM"   -> RCM 板块
     * tbody id="tr_LRCM"  -> LRCM 板块
2. 比分积压 (Uncompleted Score):
   - RCM:  td id="s_RCM_soccer", s_RCM_basketball, s_RCM_outright, s_RCM_othersport
   - LRCM: td id="s_LRCM_soccer", s_LRCM_basketball, s_LRCM_outright, s_LRCM_othersport
3. 卫星三合一表格 (td id="s_RCM_satellite" / "s_LRCM_satellite"):
   - Table [0]: Uncomplete Wagers (卫星未完成注单，Tier 1 阻断)
   - Table [1]: Uncomplete Poly Market (多元市场未完成，Tier 3 提示)
   - Table [2]: Abnormal Incentive (异常激励，Tier 1 阻断)
4. 右侧 1Plus Mapping 矩阵:
   - NoMap (Tier 3 提醒), A5Act>120s (Tier 1 阻断), Announcement (Tier 1 阻断), EventScore>180s (Tier 1 阻断)
5. 视觉规范:
   - 任何有错、有积压、有红底的项 100% 打上 🔴[ERROR/Tier 1] 标红高亮！
   - 告警项打上 🟡[WARN/Tier 3] 标橙高亮！
   - 正常项显示清爽白灰/绿色，绝不杂乱。
================================================================================
"""

import time
from core.base_checker import BaseChecker


class MatchesWagersChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第3站 Matches & Wagers", menu_id="apy_b0i4text", page_key="niw_03")
        try:
            # 1. 导航切入 Matches & Wagers 菜单页面 (等待数据加载 5 秒)
            self.navigate_to_menu("Matches & Wagers", menu_id="apy_b0i4text", section="NIW", wait_seconds=5)

            # 2. 核心 JavaScript 脚本：精准提取数据并分解节点
            matches_data = self.driver.execute_script("""
                var result = {
                    rcmUncompletedScore: {},
                    lrcmUncompletedScore: {},
                    rcmWagers: [],
                    rcmPoly: [],
                    rcmIncentive: [],
                    lrcmWagers: [],
                    lrcmPoly: [],
                    lrcmIncentive: [],
                    rightRcmMatrix: [],
                    rightLrcmMatrix: [],
                    tier1ErrorCount: 0,
                    tier3WarningCount: 0
                };

                function getVal(id) {
                    var el = document.getElementById(id);
                    return el ? el.innerText.trim() : "0";
                }

                function cleanNum(txt) {
                    if (!txt) return 0;
                    var n = parseInt(txt.replace(/[^0-9]/g, ""));
                    return isNaN(n) ? 0 : n;
                }

                function isRed(el) {
                    if (!el) return false;
                    try {
                        var style = window.getComputedStyle(el);
                        var bg = style.backgroundColor || "";
                        var color = style.color || "";
                        if (bg.indexOf("255, 0, 0") !== -1 || bg.indexOf("red") !== -1 ||
                            color.indexOf("255, 0, 0") !== -1 || color.indexOf("red") !== -1) {
                            return true;
                        }
                    } catch(e) {}
                    return false;
                }

                // ─────────────────────────────────────────────────────────────
                // 1. 提取 Uncompleted Score (比分积压)
                // ─────────────────────────────────────────────────────────────
                var rcmScores = {
                    soccer:     getVal("s_RCM_soccer"),
                    basketball: getVal("s_RCM_basketball"),
                    outright:   getVal("s_RCM_outright"),
                    othersport: getVal("s_RCM_othersport")
                };

                var lrcmScores = {
                    soccer:     getVal("s_LRCM_soccer"),
                    basketball: getVal("s_LRCM_basketball"),
                    outright:   getVal("s_LRCM_outright"),
                    othersport: getVal("s_LRCM_othersport")
                };

                result.rcmUncompletedScore = rcmScores;
                result.lrcmUncompletedScore = lrcmScores;

                ["soccer", "basketball", "outright", "othersport"].forEach(function(k) {
                    if (cleanNum(rcmScores[k]) > 0) result.tier1ErrorCount++;
                    if (cleanNum(lrcmScores[k]) > 0) result.tier1ErrorCount++;
                });

                // ─────────────────────────────────────────────────────────────
                // 2. 深度解析 satellite TD 内的 3 个子表格（拆解为单项清晰条目）
                // ─────────────────────────────────────────────────────────────
                function parseSatellite(tdId, wagersOut, polyOut, incOut) {
                    var satTd = document.getElementById(tdId);
                    if (!satTd) return;
                    var tables = satTd.querySelectorAll("table");

                    // ── Table [0]: Uncomplete Wagers (每 3 列一组: 节点, 运动, 数量) ──
                    if (tables.length > 0) {
                        var rows = tables[0].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll("td, th");
                            for (var c = 0; c < cells.length; c += 3) {
                                if (c + 2 < cells.length) {
                                    var node = cells[c].innerText.trim();
                                    var sport = cells[c+1].innerText.trim();
                                    var cntStr = cells[c+2].innerText.trim();
                                    var hasRed = isRed(cells[c]) || isRed(cells[c+1]) || isRed(cells[c+2]);

                                    if (node && node !== "satellite" && node !== "Uncomplete Wager" && sport) {
                                        var cnt = cleanNum(cntStr);
                                        var isErr = cnt > 0 || hasRed;
                                        if (isErr) result.tier1ErrorCount++;

                                        var tag = isErr ? " 🔴[ERROR/Tier 1 积压阻断]" : " [OK/正常]";
                                        wagersOut.push(node + " (" + sport + "): " + cntStr + " 单 pending" + tag);
                                    }
                                }
                            }
                        }
                    }

                    // ── Table [1]: Uncomplete Poly Market (每 3 列一组: 公司, 注单, 赛事) ──
                    if (tables.length > 1) {
                        var rows = tables[1].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll("td, th");
                            for (var c = 0; c < cells.length; c += 3) {
                                if (c + 2 < cells.length) {
                                    var com = cells[c].innerText.trim();
                                    var wager = cells[c+1].innerText.trim();
                                    var event = cells[c+2].innerText.trim();
                                    var hasRed = isRed(cells[c]) || isRed(cells[c+1]) || isRed(cells[c+2]);

                                    if (com && com !== "Com." && com !== "Uncomplete Poly Market") {
                                        var wCnt = cleanNum(wager);
                                        var eCnt = cleanNum(event);
                                        var isWarn = wCnt > 0 || eCnt > 0 || hasRed;
                                        if (isWarn) result.tier3WarningCount++;

                                        var tag = isWarn ? " 🟡[WARN/Tier 3 仅通知]" : " [OK/正常]";
                                        polyOut.push(com + ": Wager=" + wager + ", Event=" + event + tag);
                                    }
                                }
                            }
                        }
                    }

                    // ── Table [2]: Abnormal Incentive (每 2 列一组: 公司, 异常注单数) ──
                    if (tables.length > 2) {
                        var rows = tables[2].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll("td, th");
                            for (var c = 0; c < cells.length; c += 2) {
                                if (c + 1 < cells.length) {
                                    var com = cells[c].innerText.trim();
                                    var wager = cells[c+1].innerText.trim();
                                    var hasRed = isRed(cells[c]) || isRed(cells[c+1]);

                                    if (com && com !== "Com." && com !== "Abnormal Incentive") {
                                        var wCnt = cleanNum(wager);
                                        var isErr = wCnt > 0 || hasRed;
                                        if (isErr) result.tier1ErrorCount++;

                                        var tag = isErr ? " 🔴[ERROR/Tier 1 异常阻断]" : " [OK/正常]";
                                        incOut.push(com + ": Wager=" + wager + tag);
                                    }
                                }
                            }
                        }
                    }
                }

                parseSatellite("s_RCM_satellite", result.rcmWagers, result.rcmPoly, result.rcmIncentive);
                parseSatellite("s_LRCM_satellite", result.lrcmWagers, result.lrcmPoly, result.lrcmIncentive);

                // ─────────────────────────────────────────────────────────────
                // 3. 提取右侧 1Plus Mapping 矩阵
                // ─────────────────────────────────────────────────────────────
                var comps = ["RCM", "LRCM"];
                var games = ["soccer", "basketball", "othersport", "outright"];

                comps.forEach(function(comp) {
                    games.forEach(function(game) {
                        var mEl = document.getElementById("m_" + comp + "_" + game);
                        var aEl = document.getElementById("a_" + comp + "_" + game);
                        var annEl = document.getElementById("ann_" + comp + "_" + game);
                        var espEl = document.getElementById("esp_" + comp + "_" + game);

                        var mVal = mEl ? mEl.innerText.trim() : "0";
                        var aVal = aEl ? aEl.innerText.trim() : "0";
                        var annVal = annEl ? annEl.innerText.trim() : "0";
                        var espVal = espEl ? espEl.innerText.trim() : "0";

                        var mCnt = cleanNum(mVal);
                        var aCnt = cleanNum(aVal);
                        var annCnt = cleanNum(annVal);
                        var espCnt = cleanNum(espVal);

                        var hasTier3NoMap = mCnt > 0;
                        var hasTier1Block = (aCnt > 0 || annCnt > 0 || espCnt > 0);

                        if (hasTier1Block) result.tier1ErrorCount++;
                        if (hasTier3NoMap) result.tier3WarningCount++;

                        var statusTag = " [OK/正常]";
                        if (hasTier1Block) {
                            statusTag = " 🔴[ERROR/Tier 1 积压阻断]";
                        } else if (hasTier3NoMap) {
                            statusTag = " 🟡[WARN/Tier 3 NoMap 仅通知]";
                        }

                        var line = game + ": NoMap=" + mCnt + ", A5Act>120s=" + aCnt + ", Announcement=" + annCnt + ", EventScore>180s=" + espCnt + statusTag;

                        if (comp === "RCM") {
                            result.rightRcmMatrix.push(line);
                        } else {
                            result.rightLrcmMatrix.push(line);
                        }
                    });
                });

                return result;
            """)

            tier1_errors = matches_data.get("tier1ErrorCount", 0)
            tier3_warnings = matches_data.get("tier3WarningCount", 0)

            rcm_score = matches_data.get("rcmUncompletedScore", {})
            lrcm_score = matches_data.get("lrcmUncompletedScore", {})

            # 3. 组装全量巡检日志 (清晰分块，错误行带 🔴 触发红色高亮)
            all_summary = ["【Matches & Wagers 全量巡检数据明细】:"]
            all_summary.append("==================================================")
            all_summary.append("PART 1: 【左侧表格】 (按 RCM 与 LRCM 分类)")
            all_summary.append("==================================================")

            def format_score_str(scores):
                items = []
                has_err = False
                for sport in ["soccer", "basketball", "outright", "othersport"]:
                    val_str = scores.get(sport, "0")
                    val_num = int(val_str) if val_str.isdigit() else 0
                    if val_num > 0:
                        items.append(f"{sport.capitalize()}: {val_num} 🔴[积压]")
                        has_err = True
                    else:
                        items.append(f"{sport.capitalize()}: 0")
                line = " | ".join(items)
                return line + (" 🔴[ERROR/Tier 1 比分积压阻断]" if has_err else " [OK/全部0]")

            # --- RCM ---
            all_summary.append("<<< COMPANY: RCM (左侧 4 大板块) >>>")
            all_summary.append("--- [1. Uncompleted Score 比分积压 (Tier 1)] ---")
            all_summary.append(f"   * {format_score_str(rcm_score)}")

            all_summary.append("--- [2. Uncomplete Wagers 卫星未完成注单 (Tier 1)] ---")
            rcm_wagers = matches_data.get("rcmWagers", [])
            all_summary.extend([f"   * {line}" for line in rcm_wagers] if rcm_wagers else ["   * (无未完成注单 / 全部 0)"])

            all_summary.append("--- [3. Uncomplete Poly Market 多元市场 (Tier 3: 仅通知)] ---")
            rcm_poly = matches_data.get("rcmPoly", [])
            all_summary.extend([f"   * {line}" for line in rcm_poly] if rcm_poly else ["   * (无多元市场未完成 / 全部 0)"])

            all_summary.append("--- [4. Abnormal Incentive 异常激励 (Tier 1)] ---")
            rcm_inc = matches_data.get("rcmIncentive", [])
            all_summary.extend([f"   * {line}" for line in rcm_inc] if rcm_inc else ["   * (无异常激励 / 全部 0)"])

            # --- LRCM ---
            all_summary.append("\n<<< COMPANY: LRCM (左侧 4 大板块) >>>")
            all_summary.append("--- [1. Uncompleted Score 比分积压 (Tier 1)] ---")
            all_summary.append(f"   * {format_score_str(lrcm_score)}")

            all_summary.append("--- [2. Uncomplete Wagers 卫星未完成注单 (Tier 1)] ---")
            lrcm_wagers = matches_data.get("lrcmWagers", [])
            all_summary.extend([f"   * {line}" for line in lrcm_wagers] if lrcm_wagers else ["   * (无未完成注单 / 全部 0)"])

            all_summary.append("--- [3. Uncomplete Poly Market 多元市场 (Tier 3: 仅通知)] ---")
            lrcm_poly = matches_data.get("lrcmPoly", [])
            all_summary.extend([f"   * {line}" for line in lrcm_poly] if lrcm_poly else ["   * (无多元市场未完成 / 全部 0)"])

            all_summary.append("--- [4. Abnormal Incentive 异常激励 (Tier 1)] ---")
            lrcm_inc = matches_data.get("lrcmIncentive", [])
            all_summary.extend([f"   * {line}" for line in lrcm_inc] if lrcm_inc else ["   * (无异常激励 / 全部 0)"])

            # --- 右侧矩阵 ---
            all_summary.append("\n==================================================")
            all_summary.append("PART 2: 【右侧表格】 (1Plus Mapping & AS Action 规则矩阵)")
            all_summary.append("==================================================")
            all_summary.append("--- [RCM 规则矩阵] ---")
            all_summary.extend([f"   * {line}" for line in matches_data.get("rightRcmMatrix", [])])
            all_summary.append("--- [LRCM 规则矩阵] ---")
            all_summary.extend([f"   * {line}" for line in matches_data.get("rightLrcmMatrix", [])])

            total_items = (2 + len(rcm_wagers) + len(lrcm_wagers) + len(rcm_poly) + len(lrcm_poly) + len(rcm_inc) + len(lrcm_inc) + len(matches_data.get("rightRcmMatrix", [])) + len(matches_data.get("rightLrcmMatrix", [])))
            self.log_data_extracted(f"成功抓取 Matches & Wagers 左右两侧全部指标共 {total_items} 项 (Tier 1 阻断项异常: {tier1_errors}, Tier 3 提示项通知: {tier3_warnings})")
            self.log_check_method("全量打印: 先左侧(RCM/LRCM 4 大板块) -> 后右侧(1Plus 矩阵)。NoMap & PolyMarket 为 Tier 3 (仅 Notify 提示不阻断)；其余指标为 Tier 1 (有错立即阻断 Checkpoint)")
            self.log_data_summary(all_summary)

            # 4. Checkpoint 巡检结论判定
            if tier1_errors > 0:
                self.log(f"[Error] Matches & Wagers 检测到 {tier1_errors} 项 Tier 1 致命异常，阻断 Checkpoint！")
                if tier3_warnings > 0:
                    self.log(f"[Warn] 同时存在 {tier3_warnings} 项 Tier 3 提示项 (仅 Notify 提示)")
                self.log_check_result(False, f"Matches & Wagers 存在 {tier1_errors} 项 Tier 1 积压，阻断 Checkpoint。")
                return False
            else:
                if tier3_warnings > 0:
                    self.log(f"[Notice] Matches & Wagers 检测到 {tier3_warnings} 项 Tier 3 提示 (Poly Market / NoMap)，符合规则：仅 Notify 通知，【不阻断 Checkpoint】！")
                self.log_check_result(True, "Matches & Wagers Tier 1 阻断项全部 0 积压，巡检通过！")

            # 5. Checkpoint 打勾提交
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Matches & Wagers 检查出现异常: {e}")
            return False
