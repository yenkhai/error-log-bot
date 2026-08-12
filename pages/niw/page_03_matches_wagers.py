"""
================================================================================
第3站 Matches & Wagers 关卡检查器 (pages/niw/page_03_matches_wagers.py)
--------------------------------------------------------------------------------
全量日志与分级规则:
1. 打印顺序: 先打印【左侧表格】(严格按 RCM、LRCM 精准分类)，然后打印【右侧表格】(1Plus Mapping 矩阵)。
2. 左侧表格包含 4 大板块:
   - Uncompleted Score (soccer, basketball, outright, othersport, satellite)
   - Uncomplete Wager (卫星节点 pending 单数)
   - Uncomplete Poly Market (Com., Wager, Event)
   - Abnormal Incentive (Com., Wager)
3. Tier 3 提示项 (仅 Notify 警告通知，【不阻断 Checkpoint】):
   - Uncomplete Poly Market (Wager / Event / 红底)
   - 右侧 1Plus Mapping 矩阵中的 NoMap (m_RCM_*, m_LRCM_*)
4. Tier 1 阻断项 (【有错立即阻断 Checkpoint】):
   - Uncompleted Score (非 0 阻断)
   - Uncomplete Wager (非 0 阻断)
   - Abnormal Incentive (非 0 阻断)
   - 右侧 1Plus Mapping 矩阵中的 A5Act > 120s, Announcement, EventScore > 180s
================================================================================
"""

import time
from selenium.webdriver.common.by import By
from core.base_checker import BaseChecker

class MatchesWagersChecker(BaseChecker):
    def check(self) -> bool:
        # 记录当前站点的日志页头信息
        self.log_station_header("第3站 Matches & Wagers", menu_id="apy_b0i4text")
        try:
            # 1. 导航切入 Matches & Wagers 菜单页面 (等待页面加载 4 秒)
            self.navigate_to_menu("Matches & Wagers", menu_id="apy_b0i4text", section="NIW", wait_seconds=5)

            # 2. 核心 JavaScript 脚本：在前端浏览器执行，直接解析 HTML DOM 树提取左右两侧表格数据
            # 这里返回一个 Python 字典对象 (matches_data)
            matches_data = self.driver.execute_script("""
                // 【result 对象】：用于封装前端解析出来的所有完整数据和汇总统计
                var result = {
                    // 左侧 RCM / LRCM 的比分积压统计 (soccer: 足球, basketball: 篮球, outright: 冠军盘, othersport: 其他运动)
                    rcmUncompletedScore: { soccer: "0", basketball: "0", outright: "0", othersport: "0" },
                    lrcmUncompletedScore: { soccer: "0", basketball: "0", outright: "0", othersport: "0" },

                    // 左侧卫星节点未完成注单列表 (格式化后的日志字符串数组)
                    rcmUncompleteWager: [],
                    lrcmUncompleteWager: [],

                    // 左侧多盘口/多元市场未完成列表 (Format: Com, Wager, Event)
                    rcmUncompletePolyMarkets: [],
                    lrcmUncompletePolyMarkets: [],

                    // 左侧异常激励列表 (Format: Com, Wager)
                    rcmAbnormalIncentives: [],
                    lrcmAbnormalIncentives: [],

                    // 右侧 1Plus Mapping & AS Action 规则矩阵解析日志结果
                    rightRcmMatrix: [],
                    rightLrcmMatrix: [],

                    // 全局计数器：
                    tier1ErrorCount: 0,   // Tier 1 致命阻断错误数（若 > 0 则 Checkpoint 失败）
                    tier3WarningCount: 0  // Tier 3 轻量提示警告数（仅 Notification，不阻断 Checkpoint）
                };

                // ============================================================================
                // A. 抓取右侧表格：1Plus Mapping & AS Action 规则矩阵
                // 网页右侧矩阵元素采用固定的 ID 命名规则：
                //   m_{company}_{game}   -> m  = NoMap (未映射数量，属于 Tier 3 提示)
                //   a_{company}_{game}   -> a  = A5Act (AS Action > 120s 延时单，属于 Tier 1 阻断)
                //   ann_{company}_{game} -> ann= Announcement (公告积压数，属于 Tier 1 阻断)
                //   esp_{company}_{game} -> esp= EventScore (比分更新 > 180s 延迟数，属于 Tier 1 阻断)
                // ============================================================================
                var companies = ["RCM", "LRCM"]; // 遍历两个域/平台
                var games = ["soccer", "basketball", "othersport", "outright"]; // 遍历 4 种运动类型

                companies.forEach(function(comp) {
                    games.forEach(function(game) {
                        // 根据 ID 规则在网页中精准获取对应的 DOM 节点
                        var mEl = document.getElementById("m_" + comp + "_" + game);      // NoMap DOM 元素
                        var aEl = document.getElementById("a_" + comp + "_" + game);      // A5Act > 120s DOM 元素
                        var annEl = document.getElementById("ann_" + comp + "_" + game);  // Announcement DOM 元素
                        var espEl = document.getElementById("esp_" + comp + "_" + game);  // EventScore > 180s DOM 元素

                        // 获取 DOM 中的内部文本并去除首尾空格，若节点不存在则默认为 "0"
                        var mVal = mEl ? mEl.innerText.trim() : "0";     // NoMap 原始文本值
                        var aVal = aEl ? aEl.innerText.trim() : "0";     // A5Act 原始文本值
                        var annVal = annEl ? annEl.innerText.trim() : "0"; // Announcement 原始文本值
                        var espVal = espEl ? espEl.innerText.trim() : "0"; // EventScore 原始文本值

                        // 安全转为整型数字（用于逻辑判断），无法解析时回退为 0
                        var mCnt = parseInt(mVal) || 0;     // mCnt: NoMap count
                        var aCnt = parseInt(aVal) || 0;     // aCnt: AS Action count
                        var annCnt = parseInt(annVal) || 0; // annCnt: Announcement count
                        var espCnt = parseInt(espVal) || 0; // espCnt: EventScore count

                        // 判断判定级别: boolean
                        var hasTier3NoMap = mCnt > 0; // NoMap 积压触发 Tier 3 提示
                        var hasTier1Block = (aCnt > 0 || annCnt > 0 || espCnt > 0); // 任一数值 > 0 触发 Tier 1 阻断

                        // 累加对应等级的计数器
                        if (hasTier1Block) result.tier1ErrorCount++;
                        if (hasTier3NoMap) result.tier3WarningCount++;

                        // 生成可视化状态标签
                        var statusTag = " [OK/正常]";
                        if (hasTier1Block) {
                            statusTag = " [ERROR/Tier 1 停止]";
                        } else if (hasTier3NoMap) {
                            statusTag = " [WARN/Tier 3 NoMap 仅通知]";
                        }

                        // 拼装单行说明字符串
                        var line = game + ": NoMap=" + mCnt + ", A5Act>120s=" + aCnt + ", Announcement=" + annCnt + ", EventScore>180s=" + espCnt + statusTag;
                        
                        // 分别放入 RCM 或 LRCM 的右侧矩阵数据集合
                        if (comp === "RCM") {
                            result.rightRcmMatrix.push(line);
                        } else {
                            result.rightLrcmMatrix.push(line);
                        }
                    });
                });

                // ============================================================================
                // B. 遍历左侧表格：以所属祖先 Table / 位置判断 Company 属于 RCM 还是 LRCM
                // ============================================================================
                var tables = document.querySelectorAll("table"); // 获取页面所有 <table> 节点

                for (var t = 0; t < tables.length; t++) {
                    var tableTxt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 精准判定当前 <table> 属于 RCM 还是 LRCM 区域：
                    // 向上查找祖先 DOM 节点，对比 "LRCM" 和当前表格在页面父层容器文本中的出现的先后位置 (indexOf)
                    var currentComp = "RCM"; // 缺省默认为 RCM
                    var parentNode = tables[t].parentElement;
                    while (parentNode && parentNode.tagName !== "BODY") {
                        var pTxt = parentNode.innerText || "";
                        if (pTxt.indexOf("LRCM") !== -1 && pTxt.indexOf("RCM") !== -1) {
                            var fullText = parentNode.innerText;
                            var lrcmPos = fullText.indexOf("LRCM");      // "LRCM" 文本位置
                            var myPos = fullText.indexOf(tableTxt);      // 当前表格文本位置
                            if (lrcmPos !== -1 && myPos > lrcmPos) {
                                currentComp = "LRCM"; // 若表格位置在 "LRCM" 标头之后，判定为 LRCM
                            }
                            break;
                        }
                        parentNode = parentNode.parentElement;
                    }

                    // ------------------------------------------------------------------------
                    // 1. 解析板块 1: Uncompleted Score (未完成比分表)
                    // ------------------------------------------------------------------------
                    if (tableTxt.indexOf("Uncompleted Score") !== -1) {
                        var rows = tables[t].querySelectorAll("tr"); // 遍历表格每一行 <tr>
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td");     // 遍历行内的单元格 <td>
                            if (tds.length >= 2) {
                                var sName = tds[0].innerText.trim().toLowerCase(); // sName = sport name (运动名称)
                                var scoreVal = tds[1].innerText.trim();            // scoreVal = score value (积压数值)
                                var sCnt = parseInt(scoreVal) || 0;                // sCnt = score count (整型数量)
                                if (sCnt > 0) result.tier1ErrorCount++;            // 任何未比分项 > 0 均记为 Tier 1 阻断

                                // 更新到对应公司 (RCM/LRCM) 的比分结构字典中
                                if (sName === "soccer" || sName === "basketball" || sName === "outright" || sName === "othersport") {
                                    if (currentComp === "RCM") {
                                        result.rcmUncompletedScore[sName] = scoreVal;
                                    } else {
                                        result.lrcmUncompletedScore[sName] = scoreVal;
                                    }
                                }
                            }
                        });
                    }

                    // 过滤包含嵌套子表的父级外框 <table>，避免二次重复解析内嵌表
                    if (tables[t].querySelector("table") !== null) continue;

                    // ------------------------------------------------------------------------
                    // 2. 解析板块 2: Uncomplete Wager (未完成注单 / 卫星节点 pending 单数)
                    // ------------------------------------------------------------------------
                    if (tableTxt.indexOf("Uncomplete Wager") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            // 单元格按每 3 列为一个组合循环：[卫星节点, 运动类型, 积压单数]
                            for (var c = 0; c < tds.length; c += 3) {
                                if (c + 2 < tds.length) {
                                    var sat = tds[c].innerText.trim();        // sat = satellite (卫星节点名称)
                                    var sport = tds[c+1].innerText.trim();    // sport = 运动类型 (如 soccer)
                                    var cntVal = tds[c+2].innerText.trim();   // cntVal = count value (未完成单数)
                                    
                                    // 排除表头文字行
                                    if (sat && sat !== "satellite" && sat !== "Uncomplete Wager" && sport) {
                                        var wCnt = parseInt(cntVal) || 0;     // wCnt = wager count (注单整型数)
                                        var isErr = wCnt > 0;                 // 单数 > 0 即判定 Tier 1 错误
                                        if (isErr) result.tier1ErrorCount++;

                                        var line = sat + " (" + sport + "): " + wCnt + " 单 pending" + (isErr ? " [ERROR/Tier 1 积压阻断]" : " [OK/正常]");
                                        if (currentComp === "RCM") {
                                            result.rcmUncompleteWager.push(line);
                                        } else {
                                            result.lrcmUncompleteWager.push(line);
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ------------------------------------------------------------------------
                    // 3. 解析板块 3: Uncomplete Poly Market (多元/多盘口未完成市场)
                    // ------------------------------------------------------------------------
                    if (tableTxt.indexOf("Uncomplete Poly Market") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            // 单元格按每 3 列为一个组合循环：[Com.(公司), Wager(注单数), Event(赛事数)]
                            for (var c = 0; c < tds.length; c += 3) {
                                if (c + 2 < tds.length) {
                                    var com = tds[c].innerText.trim();       // com = company (公司标识)
                                    var wager = tds[c+1].innerText.trim();   // wager = 未完成注单数文本
                                    var event = tds[c+2].innerText.trim();   // event = 未完成赛事数文本

                                    // 排除表头文字
                                    if (com && com !== "Com." && com !== "Uncomplete Poly Market") {
                                        var wCnt = parseInt(wager) || 0;     // wCnt = wager count
                                        var eCnt = parseInt(event) || 0;     // eCnt = event count
                                        
                                        // 检查 CSS 计算样式，查看 Event 单元格背景是否为红底警示色
                                        var style = window.getComputedStyle(tds[c+2]);
                                        var bg = style.backgroundColor;
                                        var isRed = bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1; // 判定 rgb(255, 0, 0)
                                        
                                        // 注单数>0 或 赛事数>0 或 出现红底，触发 Tier 3 提示（不阻断 Checkpoint）
                                        var isWarn = wCnt > 0 || eCnt > 0 || isRed;
                                        if (isWarn) result.tier3WarningCount++;

                                        var line = com + ": Wager=" + wCnt + ", Event=" + eCnt + (isWarn ? " [WARN/Tier 3 仅通知]" : " [OK/正常]");
                                        if (currentComp === "RCM") {
                                            result.rcmUncompletePolyMarkets.push(line);
                                        } else {
                                            result.lrcmUncompletePolyMarkets.push(line);
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ------------------------------------------------------------------------
                    // 4. 解析板块 4: Abnormal Incentive (异常激励单)
                    // ------------------------------------------------------------------------
                    if (tableTxt.indexOf("Abnormal Incentive") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            // 单元格按每 2 列为一个组合循环：[Com.(公司), Wager(异常注单数)]
                            for (var c = 0; c < tds.length; c += 2) {
                                if (c + 1 < tds.length) {
                                    var com = tds[c].innerText.trim();       // com = company (公司标识)
                                    var wager = tds[c+1].innerText.trim();   // wager = 异常激励注单数
                                    if (com && com !== "Com." && com !== "Abnormal Incentive") {
                                        var wCnt = parseInt(wager) || 0;     // wCnt = wager count (整型)
                                        var isErr = wCnt > 0;                 // 任何异常激励单 > 0 记为 Tier 1 阻断
                                        if (isErr) result.tier1ErrorCount++;

                                        var line = com + ": Wager=" + wCnt + (isErr ? " [ERROR/Tier 1 异常阻断]" : " [OK/正常]");
                                        if (currentComp === "RCM") {
                                            result.rcmAbnormalIncentives.push(line);
                                        } else {
                                            result.lrcmAbnormalIncentives.push(line);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // JS 脚本执行完毕，返回完整抓取结果和错误汇总统计
                return result;
            """)

            # 3. 在 Python 侧解构 JavaScript 返回的数据字典
            tier1_errors = matches_data.get("tier1ErrorCount", 0)     # Tier 1 阻断性错误数
            tier3_warnings = matches_data.get("tier3WarningCount", 0) # Tier 3 轻量通知警告数

            rcm_score_obj = matches_data.get("rcmUncompletedScore", {})   # RCM 比分对象
            lrcm_score_obj = matches_data.get("lrcmUncompletedScore", {}) # LRCM 比分对象

            # 4. 组装全量巡检日志 (严格遵循规则: 先打印左侧【RCM 4 板块】-> 【LRCM 4 板块】，最后打印【右侧矩阵】)
            all_summary = ["【Matches & Wagers 全量巡检数据明细】:"]

            all_summary.append("==================================================")
            all_summary.append("PART 1: 【左侧表格】 (按 RCM 与 LRCM 分类)")
            all_summary.append("==================================================")

            # --- RCM 左侧 ---
            all_summary.append("<<< COMPANY: RCM (左侧 4 大板块) >>>")
            all_summary.append("--- [1. Uncompleted Score 比分表 (Tier 1)] ---")
            rcm_score_line = f"soccer: {rcm_score_obj.get('soccer', '0')} | basketball: {rcm_score_obj.get('basketball', '0')} | outright: {rcm_score_obj.get('outright', '0')} | othersport: {rcm_score_obj.get('othersport', '0')} [OK/正常]"
            all_summary.append(f"   * {rcm_score_line}")

            all_summary.append("--- [2. Uncomplete Wager 卫星单数明细 (Tier 1)] ---")
            rcm_wagers = matches_data.get("rcmUncompleteWager", [])
            all_summary.extend([f"   * {line}" for line in rcm_wagers] if rcm_wagers else ["   * (无数据/全部 0)"])

            all_summary.append("--- [3. Uncomplete Poly Market 明细 (Tier 3: 仅通知不阻断)] ---")
            rcm_polys = matches_data.get("rcmUncompletePolyMarkets", [])
            all_summary.extend([f"   * {line}" for line in rcm_polys] if rcm_polys else ["   * (无数据/全部 0)"])

            all_summary.append("--- [4. Abnormal Incentive 激励明细 (Tier 1)] ---")
            rcm_inc = matches_data.get("rcmAbnormalIncentives", [])
            all_summary.extend([f"   * {line}" for line in rcm_inc] if rcm_inc else ["   * (无数据/全部 0)"])

            # --- LRCM 左侧 ---
            all_summary.append("\n<<< COMPANY: LRCM (左侧 4 大板块) >>>")
            all_summary.append("--- [1. Uncompleted Score 比分表 (Tier 1)] ---")
            lrcm_score_line = f"soccer: {lrcm_score_obj.get('soccer', '0')} | basketball: {lrcm_score_obj.get('basketball', '0')} | outright: {lrcm_score_obj.get('outright', '0')} | othersport: {lrcm_score_obj.get('othersport', '0')} [OK/正常]"
            all_summary.append(f"   * {lrcm_score_line}")

            all_summary.append("--- [2. Uncomplete Wager 卫星单数明细 (Tier 1)] ---")
            lrcm_wagers = matches_data.get("lrcmUncompleteWager", [])
            all_summary.extend([f"   * {line}" for line in lrcm_wagers] if lrcm_wagers else ["   * (无数据/全部 0)"])

            all_summary.append("--- [3. Uncomplete Poly Market 明细 (Tier 3: 仅通知不阻断)] ---")
            lrcm_polys = matches_data.get("lrcmUncompletePolyMarkets", [])
            all_summary.extend([f"   * {line}" for line in lrcm_polys] if lrcm_polys else ["   * (无数据/全部 0)"])

            all_summary.append("--- [4. Abnormal Incentive 激励明细 (Tier 1)] ---")
            lrcm_inc = matches_data.get("lrcmAbnormalIncentives", [])
            all_summary.extend([f"   * {line}" for line in lrcm_inc] if lrcm_inc else ["   * (无数据/全部 0)"])

            # --- 右侧矩阵 ---
            all_summary.append("\n==================================================")
            all_summary.append("PART 2: 【右侧表格】 (1Plus Mapping & AS Action 规则矩阵)")
            all_summary.append("==================================================")
            
            all_summary.append("--- [RCM 规则矩阵] ---")
            rcm_matrix = matches_data.get("rightRcmMatrix", [])
            all_summary.extend([f"   * {line}" for line in rcm_matrix])

            all_summary.append("--- [LRCM 规则矩阵] ---")
            lrcm_matrix = matches_data.get("rightLrcmMatrix", [])
            all_summary.extend([f"   * {line}" for line in lrcm_matrix])

            # 计算提取到的数据总项数
            total_items = (2 + len(rcm_wagers) + len(lrcm_wagers) + 
                           len(rcm_polys) + len(lrcm_polys) + len(rcm_inc) + len(lrcm_inc) + 
                           len(rcm_matrix) + len(lrcm_matrix))
            
            # 输出数据提取的汇总日志
            self.log_data_extracted(f"成功抓取 Matches & Wagers 左右两侧共 {total_items} 项指标 (Tier 1 阻断项异常: {tier1_errors}, Tier 3 提示项通知: {tier3_warnings})")
            self.log_check_method("全量打印: 先左侧(RCM/LRCM 4 大板块) -> 后右侧(1Plus 矩阵)。NoMap & PolyMarket 为 Tier 3 (仅 Notify 不阻断)；其余指标为 Tier 1 (有错阻断 Checkpoint)")

            # 输出完整格式化的全量数据列表到控制台/日志
            self.log_data_summary(all_summary)

            # 5. Checkpoint 巡检结论判定
            if tier1_errors > 0:
                # 存在致命 Tier 1 错误，记录错误并返回 False 阻断后续流转
                self.log(f"[Error] Matches & Wagers 检测到 {tier1_errors} 项 Tier 1 致命异常，阻断 Checkpoint！")
                if tier3_warnings > 0:
                    self.log(f"[Warn] 同时存在 {tier3_warnings} 项 Tier 3 提示项 (仅 Notify 提示)")
                self.log_check_result(False, f"Matches & Wagers 存在 {tier1_errors} 项 Tier 1 积压，阻断 Checkpoint。")
                return False
            else:
                # 无 Tier 1 错误，若有 Tier 3 仅输出 Notification 提示
                if tier3_warnings > 0:
                    self.log(f"[Notice] Matches & Wagers 检测到 {tier3_warnings} 项 Tier 3 提示 (Poly Market / NoMap)，符合规则：仅 Notify 通知，【不阻断 Checkpoint】！")
                self.log_check_result(True, "Matches & Wagers Tier 1 阻断项全部 0 积压，巡检通过！")

            # 6. 巡检通过后自动点击 Checkpoint 按钮提交
            self.click_checkpoint()
            return True

        except Exception as e:
            # 捕获异常并记录失败结果
            self.log_check_result(False, f"Matches & Wagers 检查出现异常: {e}")
            return False
