"""
================================================================================
第15站 1 Wallet Pending 关卡检查器 (pages/niw/page_15_wallet_pending.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南 (与用户手绘红线图 100% 对应)】
1. 页面两大区域划分 (用红线划开的两大板块):
   - 左侧红线区域: Total Pending Transaction 板块 $\rightarrow$ **Tier 1 强阻断**
     包含 Company, Type, 120s, Function 字段。
     规则: 监控 120s 列，若数值大于 0 或呈红底/红字，判定为 Tier 1 致命报错阻断 Checkpoint！
   - 右侧红线区域: 5 大 API 挂起监控板块 $\rightarrow$ **Tier 3 提醒/不阻断**
     包含 5 大 API 监控列:
       1) Total Pending Rollback Api
       2) Total Pending Acknowledgement Api
       3) Total Pending Lose Api
       4) Total Pending Settle Api
       5) Total Pending Promotion Api
     规则: 即使这 5 大 API 出现红底/挂起（如 ag002 Ack=5, t0001 Rollback=1），
     系统也会在摘要中无条件详细打印节点与 API 名称，归类为 【Tier 3 提醒/不阻断】，
     解封并自动点击 Checkpoint！

2. DOM 解析逻辑:
   - 左侧表格只有 4 列 (`Company`, `Type`, `120s`, `Function`)，按索引 2 抓取 `120s` 列。
   - 右侧表格包含 11 列以上的扩展结构 (`Company` + 5 组 `Type/120s` 对)，
     每隔 2 列定位一个 API 的 `120s` 统计列（索引分别为 2, 4, 6, 8, 10）。
================================================================================
"""

import time
from core.base_checker import BaseChecker

class WalletPendingChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i17text (对应 NIW 区域的 1 Wallet Pending 按钮)
        self.log_station_header("第15站 1 Wallet Pending", menu_id="apy_b0i17text")
        try:
            # [步骤 2] 导航切入 1 Wallet Pending 页面，缓冲等待 3.5 秒让左右两大表格完整渲染
            self.navigate_to_menu("1 Wallet Pending", menu_id="apy_b0i17text", section="NIW", wait_seconds=3.5)

            # [步骤 3] JavaScript 脚本抓取左右两大分级板块
            p15_parsed = self.driver.execute_script("""
                var result = {
                    category: "ALL",
                    leftRows: [],
                    leftErrCount: 0,
                    leftErrList: [],
                    rightRows: [],
                    rightWarnCount: 0,
                    rightWarnList: []
                };

                // 获取下拉框当前选择的分区 (如 ALL / RCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.category = sel.options[sel.selectedIndex].text;
                }

                // 判断颜色是否为红色警示
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110);
                    }
                    return false;
                }

                // 纯数字提取清洗函数
                function cleanNum(txt) {
                    if (!txt) return 0;
                    var n = parseInt(txt.replace(/[^0-9]/g, ""));
                    return isNaN(n) ? 0 : n;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 3.1 抓取左侧表格: Total Pending Transaction (Tier 1 规则)
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

                                // 过滤表头与无用表格项
                                if (com && com !== "Company" && com !== "Type" && com.indexOf("Total Pending") === -1 && com.indexOf("Checkpoint") === -1) {
                                    var val120s = cleanNum(val120sStr);
                                    var isRedCell = isRed(bg) || isRed(fg);
                                    var isErr = val120s > 0 || isRedCell; // 只要 120s > 0 即判定为 Tier 1 错误

                                    if (isErr) {
                                        result.leftErrCount++;
                                        result.leftErrList.push(com + " 120s = " + val120sStr);
                                    }

                                    var tag = isErr ? " [ERROR/Tier 1 强阻断]" : " [OK/正常]";
                                    result.leftRows.push(com + " (" + type + "): 120s = " + val120sStr + ", Function = " + fn + tag);
                                }
                            }
                        });
                    }

                    // 3.2 抓取右侧表格: 5 大 API 挂起板块 (Tier 3 提醒/不阻断规则)
                    if (txt.indexOf("Total Pending Rollback Api") !== -1 || txt.indexOf("Total Pending Acknowledgement Api") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            // 包含 5 组 API (列数 >= 11)
                            if (tds.length >= 11) {
                                var com = tds[0].innerText.trim();
                                if (com && com !== "Company" && com.indexOf("Total Pending") === -1) {
                                    var apiNames = ["Rollback", "Acknowledgement", "Lose", "Settle", "Promotion"];
                                    var rowWarns = [];

                                    // 循环检测 5 大 API 的 120s 字段
                                    for (var i = 0; i < 5; i++) {
                                        var valIdx = 2 + (i * 2); // 索引 2, 4, 6, 8, 10
                                        if (valIdx < tds.length) {
                                            var valStr = tds[valIdx].innerText.trim();
                                            var numVal = cleanNum(valStr);
                                            var bg = window.getComputedStyle(tds[valIdx]).backgroundColor;
                                            var fg = window.getComputedStyle(tds[valIdx]).color;

                                            // 只要数值 > 0 或呈红色，即记录为 Tier 3 提醒
                                            if (numVal > 0 || isRed(bg) || isRed(fg)) {
                                                rowWarns.push(apiNames[i] + " Api = " + valStr);
                                            }
                                        }
                                    }

                                    var isWarn = rowWarns.length > 0;
                                    if (isWarn) {
                                        result.rightWarnCount++;
                                        result.rightWarnList.push(com + ": " + rowWarns.join(", "));
                                    }

                                    var tag = isWarn ? " [Tier 3 提醒/不阻断: " + rowWarns.join(", ") + "]" : " [OK/正常]";
                                    result.rightRows.push(com + tag);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p15_parsed.get("category", "ALL")
            left_rows = p15_parsed.get("leftRows", [])
            left_err_count = p15_parsed.get("leftErrCount", 0)
            left_err_list = p15_parsed.get("leftErrList", [])

            right_rows = p15_parsed.get("rightRows", [])
            right_warn_count = p15_parsed.get("rightWarnCount", 0)
            right_warn_list = p15_parsed.get("rightWarnList", [])

            self.log_data_extracted(f"成功抓取 1 Wallet Pending ({cat_name}) 数据 | 左侧 Total Pending Trans: {len(left_rows)} 项 (Tier 1 异常 {left_err_count} 项) | 右侧 5 大 API 挂起: {len(right_rows)} 项 (Tier 3 提醒 {right_warn_count} 项)")
            self.log_check_method("校验规则: 左侧 Total Pending Transaction 120s > 0 (Tier 1 强阻断)；右侧 5 大 API 挂起 (Tier 3 提醒/不阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【1 Wallet Pending 全量巡检数据明细 ({cat_name})】:"]

            if left_rows:
                summary_lines.append(f"--- [1. 左侧 Total Pending Transaction 板块 (Tier 1 规则/共 {len(left_rows)} 个节点)] ---")
                summary_lines.extend([f"   * {l}" for l in left_rows])

            if right_rows:
                summary_lines.append(f"--- [2. 右侧 5 大 API 挂起板块 (Tier 3 提醒/共 {len(right_rows)} 个节点)] ---")
                summary_lines.extend([f"   * {r}" for r in right_rows])

            self.log_data_summary(summary_lines)

            # [步骤 5] 分级判定 (左侧强阻断 vs 右侧通报放行)
            # 5.1 如果左侧 Tier 1 存在 120s > 0，直接判定失败，强阻断 Checkpoint！
            if left_err_count > 0:
                self.log_check_result(False, f"1 Wallet Pending 巡检发现 Tier 1 致命异常: 左侧 Total Pending Trans 存在 {left_err_count} 项 120s 挂起 ({', '.join(left_err_list)})，强阻断 Checkpoint！")
                return False

            # 5.2 如果左侧合格，即使右侧 Tier 3 存在 API 挂起 (如 ag002 Ack=5, t0001 Rollback=1)，通报提醒，巡检通过！
            if right_warn_count > 0:
                self.log_check_result(True, f"1 Wallet Pending 左侧合格，右侧存在 {right_warn_count} 项 API 挂起节点 ({'; '.join(right_warn_list)}) [Tier 3 提醒/不阻断]，巡检通过！")
            else:
                self.log_check_result(True, "1 Wallet Pending 左右两大板块全部节点状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint 按钮
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"1 Wallet Pending 检查出现异常: {e}")
            return False
