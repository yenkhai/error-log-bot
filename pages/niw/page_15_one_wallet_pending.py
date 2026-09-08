"""
================================================================================
第15站 1 Wallet Pending 关卡检查器 (pages/niw/page_15_one_wallet_pending.py)
--------------------------------------------------------------------------------
【核心功能详解与判定规则】
1. 页面分为左右两大板块:
   - 左侧表格: Total Pending Transaction (Tier 1 规则)
     * 字段: Company, Type, 120s (超时积压), Function
     * 规则: 120s 积压数 > 0 或出现红字/红底 -> Tier 1 致命阻断
   - 右侧表格: 5 个 Pending API 监控 (Tier 3 规则)
     * 字段: Company, Rollback, Acknowledgement, Lose, Settle, Promotion (各含 120s 列)
     * 规则: 120s 积压数 > 0 或出现红字/红底 -> Tier 3 提醒通知 (【不阻断 Checkpoint】)
2. 全量打印:
   - 左侧所有公司的 Total Pending 状态
   - 右侧所有公司的 5 大 API 挂单状态
3. 全部正常或仅有 Tier 3 时，点击 Checkpoint 提交通关！
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class OneWalletPendingChecker(BaseChecker):
    """
    1 Wallet Pending 挂单积压检查器类
    负责监控左侧 Total Pending Transaction (120s 积压属于 Tier 1 阻断) 与
    右侧 5 个 Pending API 监控 (属于 Tier 3 提醒，仅通报不阻断)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 1 Wallet Pending 页面 (apy_b0i17text)
        2. 执行前端 JavaScript 深度抓取左表 (Total Pending) 与右表 (5 个 Pending API)
        3. 核验左侧 120s 积压是否大于 0 或呈红字红底 (Tier 1 阻断规则)
        4. 核验右侧 5 个 API 的 120s 积压 (Tier 3 提醒规则，不阻断 Checkpoint)
        5. 全量打印左右两侧明细日志，无 Tier 1 错误时保存快照并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID 与页面键
        self.log_station_header("第15站 1 Wallet Pending", menu_id="apy_b0i17text", page_key="niw_15")
        try:
            # 1. 导航切入 1 Wallet Pending 页面
            self.navigate_to_menu("1 Wallet Pending", menu_id="apy_b0i17text", section="NIW")

            # 智能等待页面数据渲染完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # 2. 核心 JavaScript 脚本：同时提取左右两侧全部表格数据
            parsed_data = self.driver.execute_script("""
                // 初始化前端抓取数据字典
                var result = {
                    leftRows: [],          // 左侧 Total Pending 文本明细
                    leftErrCount: 0,       // 左侧 Tier 1 异常统计
                    rightRows: [],         // 右侧 5 大 API 文本明细
                    rightWarnCount: 0,     // 右侧 Tier 3 警告统计
                    tableHeaders: ["Company", "Type", "120s Pending", "Right APIs Status", "Result"],
                    tableRows: []          // 结构化合并数据行 (供 ASCII 表格与仪表盘展示)
                };

                // 辅助函数: 判断 RGB 颜色字符串是否呈红色预警
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110);
                    }
                    return false;
                }

                function cleanNum(txt) {
                    if (!txt) return 0;
                    var n = parseInt(txt.replace(/[^0-9]/g, ""));
                    return isNaN(n) ? 0 : n;
                }

                var tables = document.querySelectorAll("table");
                var leftMap = {};  // company -> { type, val120s, fn, isErr }
                var rightMap = {}; // company -> { warns, isWarn }

                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // ── A. 左侧表格 (Total Pending Transaction - Tier 1) ──
                    if (txt.indexOf("Total Pending Transaction") !== -1 || (txt.indexOf("Company") !== -1 && txt.indexOf("120s") !== -1 && txt.indexOf("Function") !== -1)) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var com = tds[0].innerText.trim();
                                var type = tds[1].innerText.trim();
                                var val120sStr = tds[2].innerText.trim();
                                var fn = tds.length >= 4 ? tds[3].innerText.trim() : "-";
                                var bg = window.getComputedStyle(tds[2]).backgroundColor;
                                var fg = window.getComputedStyle(tds[2]).color;

                                if (com && com !== "Company" && com !== "Type" && com.indexOf("Total Pending") === -1 && com.indexOf("Checkpoint") === -1) {
                                    var val120s = cleanNum(val120sStr);
                                    var isRedCell = isRed(bg) || isRed(fg);
                                    var isErr = val120s > 0 || isRedCell;

                                    if (isErr) result.leftErrCount++;

                                    var tag = isErr ? " [ERROR/Tier 1 积压阻断]" : " [OK/正常]";
                                    var line = com + " (" + type + "): 120s = " + val120sStr + ", Function = " + fn + tag;
                                    result.leftRows.push(line);

                                    leftMap[com] = {
                                        type: type,
                                        val120s: val120sStr,
                                        isErr: isErr
                                    };
                                }
                            }
                        });
                    }

                    // ── B. 右侧表格 (5 个 Pending API - Tier 3) ──
                    if (txt.indexOf("Total Pending Rollback Api") !== -1 || txt.indexOf("Total Pending Acknowledgement Api") !== -1 || (txt.indexOf("Rollback") !== -1 && txt.indexOf("Promotion") !== -1)) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 11) {
                                var com = tds[0].innerText.trim();
                                if (com && com !== "Company" && com.indexOf("Total Pending") === -1) {
                                    var apiNames = ["Rollback", "Ack", "Lose", "Settle", "Promo"];
                                    var rowWarns = [];

                                    for (var i = 0; i < 5; i++) {
                                        var valIdx = 2 + (i * 2); // 120s 对应列索引: 2, 4, 6, 8, 10
                                        if (valIdx < tds.length) {
                                            var valStr = tds[valIdx].innerText.trim();
                                            var numVal = cleanNum(valStr);
                                            var bg = window.getComputedStyle(tds[valIdx]).backgroundColor;
                                            var fg = window.getComputedStyle(tds[valIdx]).color;

                                            if (numVal > 0 || isRed(bg) || isRed(fg)) {
                                                rowWarns.push(apiNames[i] + "=" + valStr);
                                            }
                                        }
                                    }

                                    var isWarn = rowWarns.length > 0;
                                    if (isWarn) result.rightWarnCount++;

                                    var tag = isWarn ? " [WARN/Tier 3 仅通知: " + rowWarns.join(", ") + "]" : " [OK/全部0]";
                                    var line = com + ": " + (isWarn ? rowWarns.join(", ") : "5 APIs 全 0 积压") + tag;
                                    result.rightRows.push(line);

                                    rightMap[com] = {
                                        warns: isWarn ? rowWarns.join(", ") : "All 0",
                                        isWarn: isWarn
                                    };
                                }
                            }
                        });
                    }
                });

                // 组装结构化表格行
                var allComps = Object.keys(leftMap);
                if (allComps.length === 0) allComps = Object.keys(rightMap);

                allComps.forEach(function(com) {
                    var lInfo = leftMap[com] || { type: "-", val120s: "0", isErr: false };
                    var rInfo = rightMap[com] || { warns: "All 0", isWarn: false };

                    var statusText = "OK/正常";
                    if (lInfo.isErr) {
                        statusText = "ERROR/Tier 1 阻断";
                    } else if (rInfo.isWarn) {
                        statusText = "WARN/Tier 3 提醒";
                    }

                    result.tableRows.push([
                        com,
                        lInfo.type,
                        lInfo.val120s,
                        rInfo.warns,
                        statusText
                    ]);
                });

                return result;
            """)

            left_rows = parsed_data.get("leftRows", [])
            left_err = parsed_data.get("leftErrCount", 0)
            right_rows = parsed_data.get("rightRows", [])
            right_warn = parsed_data.get("rightWarnCount", 0)

            # 3. 组装全量巡检日志
            all_summary = ["【1 Wallet Pending 左右两侧全量数据明细】:"]
            
            all_summary.append("==================================================")
            all_summary.append("PART 1: 【左侧表格】 Total Pending Transaction (Tier 1 规则)")
            all_summary.append("==================================================")
            if left_rows:
                all_summary.extend([f"   * {line}" for line in left_rows])
            else:
                all_summary.append("   * (左侧表格暂无数据或全部为 0)")

            all_summary.append("\n==================================================")
            all_summary.append("PART 2: 【右侧表格】 5 个 Pending API 监控 (Tier 3 规则: 仅通知不阻断)")
            all_summary.append("==================================================")
            if right_rows:
                all_summary.extend([f"   * {line}" for line in right_rows])
            else:
                all_summary.append("   * (右侧表格暂无数据或全部为 0)")

            total_items = len(left_rows) + len(right_rows)
            self.log_data_extracted(f"成功抓取 1 Wallet Pending 左右两侧共 {total_items} 条监控记录 (左表 Tier 1 错误: {left_err}, 右表 Tier 3 提示: {right_warn})")
            self.log_check_method("全量打印左右两侧: 左侧 120s 积压 > 0 为 Tier 1 (阻断 Checkpoint)；右侧 5 大 API 积压 > 0 为 Tier 3 (仅 Notify 提示不阻断)")
            self.log_data_summary(all_summary)

            # 4. 记录结构化表格供 ASCII 文本日志与 HTML 仪表盘使用
            t_headers = parsed_data.get("tableHeaders", ["Company", "Type", "120s", "Right APIs", "Status"])
            t_rows = parsed_data.get("tableRows", [])
            if t_rows:
                self.log_table_data(t_headers, t_rows)

            # 5. Checkpoint 巡检结论判定
            if left_err > 0:
                self.log(f"[Error] 1 Wallet Pending 左侧检测到 {left_err} 项 120s 超时积压，属于 Tier 1 致命异常，阻断 Checkpoint！")
                if right_warn > 0:
                    self.log(f"[Warn] 同时右侧存在 {right_warn} 项 Tier 3 提示 (仅通知不阻断)")
                self.log_check_result(False, f"1 Wallet Pending 左侧存在 {left_err} 项 120s 超时积压，阻断 Checkpoint。")
                CheckpointStore.save(
                    page_key="niw_15",
                    title="1 Wallet Pending",
                    status=False,
                    headers=t_headers,
                    rows=[[CheckpointStore.make_cell(str(c)) for c in r] for r in t_rows],
                    summary=f"Tier 1 errors: {left_err}, Tier 3 warnings: {right_warn}"
                )
                return False
            else:
                if right_warn > 0:
                    self.log(f"[Notice] 1 Wallet Pending 右侧检测到 {right_warn} 项 API 积压，符合规则：仅 Notify 提示，【不阻断 Checkpoint】！")
                self.log_check_result(True, "1 Wallet Pending 左侧 120s 积压全部为 0，巡检通过！")

            # 6. 点击 Checkpoint 打勾提交
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_15",
                title="1 Wallet Pending",
                status=True,
                headers=t_headers,
                rows=[[CheckpointStore.make_cell(str(c)) for c in r] for r in t_rows],
                summary=f"Tier 3 warnings: {right_warn}" if right_warn > 0 else "All Pending APIs clear"
            )
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("niw_15", "1 Wallet Pending", e)
