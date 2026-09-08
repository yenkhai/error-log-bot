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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class MatchesWagersChecker(BaseChecker):
    def check(self) -> bool:
        # 1. 记录当前关卡页头日志 (Menu ID: apy_b0i4text)
        self.log_station_header("第3站 Matches & Wagers", menu_id="apy_b0i4text", page_key="niw_03")
        try:
            # 2. 自动化导航切入 Matches & Wagers 菜单页面 
            self.navigate_to_menu("Matches & Wagers", menu_id="apy_b0i4text", section="NIW")
            
            # 3. 智能等待页面加载完成 (最小保底等待 2 秒，最长超时阈值 30 秒)
            self.wait_for_page_loaded(seconds=2, max_wait=30)

            # 4. 核心 JavaScript 脚本：在前端浏览器层高效提取全量 HTML DOM 数据
            matches_data = self.driver.execute_script("""
                // 【A. 初始化结果容器对象】：用来存储抓取到的所有数据结构和全局计数器
                var result = {
                    rcmUncompletedScore: {},  // RCM 比分积压对象 (soccer, basketball...)
                    lrcmUncompletedScore: {}, // LRCM 比分积压对象
                    rcmWagers: [],            // RCM 未完成注单格式化字符串列表 (Table [0])
                    rcmPoly: [],              // RCM 多元未完成市场格式化字符串列表 (Table [1])
                    rcmIncentive: [],         // RCM 异常激励格式化字符串列表 (Table [2])

                    lrcmWagers: [],           // LRCM 未完成注单列表
                    lrcmPoly: [],             // LRCM 多元未完成市场列表
                    lrcmIncentive: [],        // LRCM 异常激励列表
                    
                    rightRcmMatrix: [],       // 右侧 RCM 1Plus 规则矩阵解析结果
                    rightLrcmMatrix: [],      // 右侧 LRCM 1Plus 规则矩阵解析结果
                    
                    tier1ErrorCount: 0,       // 致命错误总计数 (Tier 1: 若 > 0 阻断 Checkpoint)
                    tier3WarningCount: 0      // 警告通知总计数 (Tier 3: 仅 Notice 提醒，不阻断 Checkpoint)
                };

                // 【辅助函数 1】: 根据 DOM 节点 ID 安全获取内部文本值，若找不到节点则默认返回 "0"
                function getVal(id) {
                    var el = document.getElementById(id);
                    return el ? el.innerText.trim() : "0";
                }

                // 【辅助函数 2】: 清理并提取文本中的纯数字，过滤掉千分位逗号或非数字字符（如 "5" -> 5）
                function cleanNum(txt) {
                    if (!txt) return 0;
                    var n = parseInt(txt.replace(/[^0-9]/g, ""));
                    return isNaN(n) ? 0 : n; // 转换失败时安全回退为 0
                }

                // 【辅助函数 3】: 检查单元格的计算样式（CSS），判断其背景或文字颜色是否呈现红底警示
                function isRed(el) {
                    if (!el) return false;
                    try {
                        var style = window.getComputedStyle(el);
                        var bg = style.backgroundColor || "";
                        var color = style.color || "";
                        // 检测背景色或字体颜色是否包含 255, 0, 0 或 "red"
                        if (bg.indexOf("255, 0, 0") !== -1 || bg.indexOf("red") !== -1 ||
                            color.indexOf("255, 0, 0") !== -1 || color.indexOf("red") !== -1) {
                            return true;
                        }
                    } catch(e) {}
                    return false;
                }

                // ─────────────────────────────────────────────────────────────
                // 板块 1: 提取 Uncompleted Score (未完成比分积压表)
                // 网页采用固定 ID: s_RCM_{sport} 和 s_LRCM_{sport}
                // ─────────────────────────────────────────────────────────────
                var rcmScores = {
                    soccer:     getVal("s_RCM_soccer"),     // 足球比分积压
                    basketball: getVal("s_RCM_basketball"), // 篮球比分积压
                    outright:   getVal("s_RCM_outright"),   // 冠军盘比分积压
                    othersport: getVal("s_RCM_othersport")  // 其他运动比分积压
                };

                var lrcmScores = {
                    soccer:     getVal("s_LRCM_soccer"),
                    basketball: getVal("s_LRCM_basketball"),
                    outright:   getVal("s_LRCM_outright"),
                    othersport: getVal("s_LRCM_othersport")
                };

                result.rcmUncompletedScore = rcmScores;
                result.lrcmUncompletedScore = lrcmScores;

                // 检查比分积压：任何一项体育项目的比分积压数 > 0 均记为 Tier 1 致命错误
                ["soccer", "basketball", "outright", "othersport"].forEach(function(k) {
                    if (cleanNum(rcmScores[k]) > 0) result.tier1ErrorCount++;
                    if (cleanNum(lrcmScores[k]) > 0) result.tier1ErrorCount++;
                });

                // ─────────────────────────────────────────────────────────────
                // 板块 2: 深度解析 satellite TD 节点内部嵌套的 3 个子表格
                // 参数: tdId(卫星TD的ID), wagersOut(注单输出数组), polyOut(多元输出数组), incOut(激励输出数组)
                // ─────────────────────────────────────────────────────────────
                function parseSatellite(tdId, wagersOut, polyOut, incOut) {
                    var satTd = document.getElementById(tdId); // 找到 s_RCM_satellite 或 s_LRCM_satellite 节点 rcm or lrcm
                    if (!satTd) return;
                    var tables = satTd.querySelectorAll("table"); // 提取 TD 里面的所有子表格 <table>

                    // ── Table [0]: Uncomplete Wagers (未完成注单表 - 每 3 列一组: 公司名, 运动, 积压单数) ──
                    if (tables.length > 0) { // 1. 确保存在第 1 个子表格
                        var rows = tables[0].querySelectorAll("tr"); // 取出表格中的所有行 <tr>
                        
                        for (var r = 0; r < rows.length; r++) {      // 2. 遍历每一行 <tr>
                            var cells = rows[r].querySelectorAll("td, th"); // 获取行内所有的单元格 <td> or <th>
                            
                            // 核心技巧: c += 3 (步进 3 列循环)，打包解析同行中的多组数据
                            for (var c = 0; c < cells.length; c += 3) {
                                if (c + 2 < cells.length) { // 3. 边界防护：确保当前组剩余单元格满足 3 个
                                    var node = cells[c].innerText.trim();      // 第 1 列: 节点/站点名称 (如 p0001)
                                    //var sport = cells[c+1].innerText.trim();  // 第 2 列: 运动类型 (如 sport)
                                    var cntStr = cells[c+2].innerText.trim(); // 第 3 列: 未完成单数文本 (如 "5")
                                    // 检查当前 3 列单元格是否有背景变红
                                    var hasRed = isRed(cells[c+2]);

                                    // 4. 过滤表头文字，只处理真正的站点数据行
                                    if (node && node !== "satellite" && node !== "Uncomplete Wager") {
                                        var cnt = cleanNum(cntStr);        // 清理转为纯数字
                                        var isErr = cnt > 0 || hasRed;     // 判定异常：单数 > 0 或 背景红底
                                        if (isErr) result.tier1ErrorCount++; // 触发 Tier 1 错误计数

                                        // 拼装可视化标红日志行
                                        var tag = isErr ? "[ERROR]" : "[OK]";
                                        wagersOut.push(node + ": " + cntStr + " 单 pending" + tag);
                                    }
                                }
                            }
                        }
                    }

                    // ── Table [1]: Uncomplete Poly Market (多元未完成市场表 - 每 3 列一组: 公司, 注单数, 赛事数) ──
                    if (tables.length > 1) { // 1. 确保存在第 2 个子表格
                        var rows = tables[1].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll("td, th");
                            // 🌟 步进 3 列循环：[公司(c), 注单数(c+1), 赛事数(c+2)]
                            for (var c = 0; c < cells.length; c += 3) {
                                if (c + 2 < cells.length) {
                                    var com = cells[c].innerText.trim();     // 第 1 列: 公司代码
                                    var wager = cells[c+1].innerText.trim(); // 第 2 列: 未完成注单数
                                    var event = cells[c+2].innerText.trim(); // 第 3 列: 未完成赛事数
                                    var hasRed = isRed(cells[c]) || isRed(cells[c+1]) || isRed(cells[c+2]);

                                    // 过滤表头文字
                                    if (com && com !== "Com." && com !== "Uncomplete Poly Market") {
                                        var wCnt = cleanNum(wager);
                                        var eCnt = cleanNum(event);
                                        // 判定警告：注单数 > 0 或 赛事数 > 0 或 红底
                                        var isWarn = wCnt > 0 || eCnt > 0 || hasRed;
                                        if (isWarn) result.tier3WarningCount++; // 触发 Tier 3 警告计数 (不阻断)

                                        // 拼装可视化标黄日志行
                                        var tag = isWarn ? "[WARN]" : "[OK]";
                                        polyOut.push(com + ": Wager=" + wager + ", Event=" + event + tag);
                                    }
                                }
                            }
                        }
                    }

                    // ── Table [2]: Abnormal Incentive (异常激励单表 - 每 2 列一组: 公司, 异常注单数) ──
                    if (tables.length > 2) { // 1. 确保存在第 3 个子表格
                        var rows = tables[2].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll("td, th");
                            // 🌟 步进 2 列循环：[公司(c), 异常注单数(c+1)]
                            for (var c = 0; c < cells.length; c += 2) {
                                if (c + 1 < cells.length) {
                                    var com = cells[c].innerText.trim();     // 第 1 列: 公司代码
                                    var wager = cells[c+1].innerText.trim(); // 第 2 列: 异常激励注单数
                                    var hasRed = isRed(cells[c]) || isRed(cells[c+1]);

                                    // 过滤表头文字
                                    if (com && com !== "Com." && com !== "Abnormal Incentive") {
                                        var wCnt = cleanNum(wager);
                                        var isErr = wCnt > 0 || hasRed;     // 判定异常：单数 > 0 或 背景红底
                                        if (isErr) result.tier1ErrorCount++; // 触发 Tier 1 致命错误计数

                                        // 拼装可视化标红日志行
                                        var tag = isErr ? " 🔴[ERROR/Tier 1 异常阻断]" : " [OK/正常]";
                                        incOut.push(com + ": Wager=" + wager + tag);
                                    }
                                }
                            }
                        }
                    }
                }

                // 执行对 RCM 与 LRCM 的卫星子表格解析
                parseSatellite("s_RCM_satellite", result.rcmWagers, result.rcmPoly, result.rcmIncentive);
                parseSatellite("s_LRCM_satellite", result.lrcmWagers, result.lrcmPoly, result.lrcmIncentive);

                // ─────────────────────────────────────────────────────────────
                // 板块 3: 提取右侧 1Plus Mapping & AS Action 规则矩阵
                // ID 规则：m_ (NoMap), a_ (A5Act>120s), ann_ (Announcement), esp_ (EventScore>180s)
                // ─────────────────────────────────────────────────────────────
                var comps = ["RCM", "LRCM"];
                var games = ["soccer", "basketball", "othersport", "outright"];

                comps.forEach(function(comp) {
                    games.forEach(function(game) {
                        // 1. 根据 ID 获取 DOM 节点
                        var mEl = document.getElementById("m_" + comp + "_" + game);      // NoMap 节点
                        var aEl = document.getElementById("a_" + comp + "_" + game);      // A5Act 节点
                        var annEl = document.getElementById("ann_" + comp + "_" + game);  // Announcement 节点
                        var espEl = document.getElementById("esp_" + comp + "_" + game);  // EventScore 节点

                        // 2. 提取文本
                        var mVal = mEl ? mEl.innerText.trim() : "0";
                        var aVal = aEl ? aEl.innerText.trim() : "0";
                        var annVal = annEl ? annEl.innerText.trim() : "0";
                        var espVal = espEl ? espEl.innerText.trim() : "0";

                        // 3. 转为数字
                        var mCnt = cleanNum(mVal);
                        var aCnt = cleanNum(aVal);
                        var annCnt = cleanNum(annVal);
                        var espCnt = cleanNum(espVal);

                        // 4. 级别判定
                        var hasTier3NoMap = mCnt > 0; // NoMap 属于 Tier 3 提示
                        var hasTier1Block = (aCnt > 0 || annCnt > 0 || espCnt > 0); // 任何超时/积压均属于 Tier 1 阻断

                        if (hasTier1Block) result.tier1ErrorCount++;
                        if (hasTier3NoMap) result.tier3WarningCount++;

                        // 5. 状态标签拼装
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

                // 将解析出来的全量数据返回 Python
                return result;
            """)

            # 5. 在 Python 侧解构 JavaScript 返回的数据字典
            tier1_errors = matches_data.get("tier1ErrorCount", 0)     # Tier 1 致命错误数
            tier3_warnings = matches_data.get("tier3WarningCount", 0) # Tier 3 提示警告数

            rcm_score = matches_data.get("rcmUncompletedScore", {})   # RCM 比分字典
            lrcm_score = matches_data.get("lrcmUncompletedScore", {}) # LRCM 比分字典

            # 6. 组装全量巡检日志 (严格打印顺序：先左侧 RCM 4板块 -> 再左侧 LRCM 4板块 -> 后右侧矩阵)
            all_summary = ["【Matches & Wagers 全量巡检数据明细】:"]
            all_summary.append("==================================================")
            all_summary.append("PART 1: 【左侧表格】 (按 RCM 与 LRCM 分类)")
            all_summary.append("==================================================")

            # 比分明细格式化子函数
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

            # --- RCM 板块 ---
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

            # --- LRCM 板块 ---
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
            
            # 输出全量明细日志到界面
            self.log_data_summary(all_summary)

            # 7. 构筑写回 CheckpointStore 持久化存储层的结构化表格数据
            table_headers = ["Section", "Group", "Sport / Item", "Pending / Value", "Status"]
            table_rows = []

            # 7.1 表格行构筑: Uncompleted Score
            for grp, scores in [("RCM", matches_data.get("rcmUncompletedScore", {})), ("LRCM", matches_data.get("lrcmUncompletedScore", {}))]:
                for sport, val in scores.items():
                    is_err = False
                    try:
                        is_err = int(str(val).replace(",", "").strip()) > 0
                    except Exception:
                        pass
                    table_rows.append([
                        CheckpointStore.make_cell("Uncompleted Score"),
                        CheckpointStore.make_cell(grp),
                        CheckpointStore.make_cell(sport),
                        CheckpointStore.make_cell(str(val), bg="red" if is_err else "green"),
                        CheckpointStore.make_cell("ERROR" if is_err else "OK", bg="red" if is_err else "green")
                    ])

            # 7.2 表格行构筑: Wagers
            for grp, w_list in [("RCM", rcm_wagers), ("LRCM", lrcm_wagers)]:
                for w in w_list:
                    is_err = "ERROR" in w
                    table_rows.append([
                        CheckpointStore.make_cell("Uncomplete Wagers"),
                        CheckpointStore.make_cell(grp),
                        CheckpointStore.make_cell(w.split(":")[0] if ":" in w else w),
                        CheckpointStore.make_cell(w.split(":")[1].split("[")[0].strip() if ":" in w else w, bg="red" if is_err else "green"),
                        CheckpointStore.make_cell("ERROR" if is_err else "OK", bg="red" if is_err else "green")
                    ])

            # 7.3 表格行构筑: Poly Market & Incentives
            for grp, p_list in [("RCM", rcm_poly), ("LRCM", lrcm_poly)]:
                for p in p_list:
                    table_rows.append([
                        CheckpointStore.make_cell("Poly Market"),
                        CheckpointStore.make_cell(grp),
                        CheckpointStore.make_cell(p.split(":")[0] if ":" in p else p),
                        CheckpointStore.make_cell(p.split(":")[1].strip() if ":" in p else "-", bg="white"),
                        CheckpointStore.make_cell("NOTICE", bg="white")
                    ])

            for grp, inc_list in [("RCM", rcm_inc), ("LRCM", lrcm_inc)]:
                for inc in inc_list:
                    is_err = "ERROR" in inc
                    table_rows.append([
                        CheckpointStore.make_cell("Abnormal Incentive"),
                        CheckpointStore.make_cell(grp),
                        CheckpointStore.make_cell(inc.split(":")[0] if ":" in inc else inc),
                        CheckpointStore.make_cell(inc.split(":")[1].strip() if ":" in inc else "-", bg="red" if is_err else "green"),
                        CheckpointStore.make_cell("ERROR" if is_err else "OK", bg="red" if is_err else "green")
                    ])

            # 7.4 表格行构筑: Right Rule Matrix
            for grp, m_list in [("RCM", matches_data.get("rightRcmMatrix", [])), ("LRCM", matches_data.get("rightLrcmMatrix", []))]:
                for m in m_list:
                    is_err = "ERROR" in m
                    is_warn = "WARN" in m or "NOTICE" in m
                    bg_col = "red" if is_err else ("white" if is_warn else "green")
                    table_rows.append([
                        CheckpointStore.make_cell("Rule Matrix"),
                        CheckpointStore.make_cell(grp),
                        CheckpointStore.make_cell(m.split(":")[0].strip() if ":" in m else m),
                        CheckpointStore.make_cell(m.split(":")[1].split("[")[0].strip() if ":" in m else "-", bg=bg_col),
                        CheckpointStore.make_cell("ERROR" if is_err else ("WARN" if is_warn else "OK"), bg=bg_col)
                    ])

            # 8. Checkpoint 巡检最终结论判定
            if tier1_errors > 0:
                # 存在 Tier 1 致命积压：报错阻断
                self.log(f"[Error] Matches & Wagers 检测到 {tier1_errors} 项 Tier 1 致命异常，阻断 Checkpoint！")
                if tier3_warnings > 0:
                    self.log(f"[Warn] 同时存在 {tier3_warnings} 项 Tier 3 提示项 (仅 Notify 提示)")
                self.log_check_result(False, f"Matches & Wagers 存在 {tier1_errors} 项 Tier 1 积压，阻断 Checkpoint。")
                CheckpointStore.save(
                    page_key="niw_03",
                    title="Matches Wagers",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Tier 1 异常: {tier1_errors} 项, Tier 3 提示: {tier3_warnings} 项"
                )
                return False
            else:
                # 无 Tier 1 致命积压：通过巡检
                if tier3_warnings > 0:
                    self.log(f"[Notice] Matches & Wagers 检测到 {tier3_warnings} 项 Tier 3 提示 (Poly Market / NoMap)，符合规则：仅 Notify 通知，【不阻断 Checkpoint】！")
                self.log_check_result(True, "Matches & Wagers Tier 1 阻断项全部 0 积压，巡检通过！")

            # 9. 巡检通过后点击 Checkpoint 打勾提交
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_03",
                title="Matches Wagers",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全部 Tier 1 阻断项 0 积压正常" + (f" (含 {tier3_warnings} 项 Tier 3 提示)" if tier3_warnings > 0 else "")
            )
            return True

        except Exception as e:
            # 捕获未知异常并记录失败
            return self.handle_exception("niw_03", "Matches Wagers", e)
