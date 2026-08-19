"""
================================================================================
第05站 Error Log 关卡检查器 (pages/copier_server/page_05_error_log.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 Error Log (Menu ID: apy_b0i23text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格列: Server | Total (值为 'No Error' 或 'X Records')
   - 已知服务器超过 50 台，数量庞大

2. 判定规则:
   - Total == 'No Error'        → OK 正常
   - Total > 4000 Records      → Tier 3 提醒（Notify 通知，不阻断 Checkpoint）
   - Total > 0 但 <= 4000      → Tier 3 提醒（Notify 通知，不阻断 Checkpoint）

3. 解析方式:
   - 使用 JS 通过关键词 'Server' 和 'Total' 精准定位表格
   - 无条件打印所有服务器的 Error Log 状态明细（无论是否有错）

4. 打印内容:
   - 全部服务器 Server + Total 状态行
   - Tier 汇总统计
================================================================================
"""

import time
from core.base_checker import BaseChecker


class ErrorLogChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第05站 Error Log", menu_id="apy_b0i23text")
        try:
            # [步骤 1] 导航切入 Error Log 页面
            self.navigate_to_menu("Error Log", menu_id="apy_b0i23text", section="Copier")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 2] 使用 JavaScript 通过关键词 'Server' 和 'Total' 精准定位并解析表格
            error_data = self.driver.execute_script("""
                var result = {
                    servers: [],      // 所有服务器行数据
                    tier1Count: 0,    // Total >= 1000 Records 的严重错误数
                    tier3Count: 0,    // Total > 0 但 < 1000 的警告提醒数
                    okCount: 0,       // No Error 正常数
                    totalCount: 0
                };

                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 通过关键词 'Server' 和 'Total' 定位 Error Log 主表
                    if (txt.indexOf("Server") !== -1 && txt.indexOf("Total") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            if (tds.length < 2) continue;

                            var serverName = tds[0].innerText.trim();
                            var totalVal   = tds[1].innerText.trim();

                            // 跳过表头行与空行
                            if (!serverName || serverName === "Server" || serverName === "" ) continue;
                            if (totalVal === "Total" || totalVal === "") continue;

                            // 解析 Total 值: 'No Error' 或 'X Records' 或纯数字
                            var tier   = "OK";
                            var tag    = " [OK/No Error]";
                            var count  = 0;

                            if (totalVal === "No Error" || totalVal === "" || totalVal === "0") {
                                tier = "OK";
                                tag  = " [OK/No Error]";
                                result.okCount++;
                            } else {
                                // 尝试解析数字: '1500 Records' → 1500
                                var m = totalVal.match(/(\\d+)/);
                                if (m) {
                                    count = parseInt(m[1]);
                                    if (count > 4000) {
                                        tier = "TIER3_HIGH";
                                        tag  = " [WARN/Tier 3 > 4000 Records 提醒]";
                                        result.tier3Count++;
                                    } else if (count > 0) {
                                        tier = "TIER3";
                                        tag  = " [WARN/Tier 3 <= 4000 Records 提醒]";
                                        result.tier3Count++;
                                    } else {
                                        tier = "OK";
                                        tag  = " [OK/No Error]";
                                        result.okCount++;
                                    }
                                } else {
                                    // 无法解析数值，视为未知状态
                                    tier = "UNKNOWN";
                                    tag  = " [WARN/无法解析状态]";
                                    result.tier3Count++;
                                }
                            }

                            result.servers.push({
                                server: serverName,
                                total: totalVal,
                                count: count,
                                tier: tier,
                                tag: tag
                            });
                        }
                        break; // 找到主表即停止
                    }
                }

                result.totalCount = result.servers.length;
                return result;
            """)

            servers     = error_data.get("servers", [])
            tier1_count = error_data.get("tier1Count", 0)
            tier3_count = error_data.get("tier3Count", 0)
            ok_count    = error_data.get("okCount", 0)
            total_count = error_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 Error Log 表格，共捕获 {total_count} 台服务器状态 "
                f"(OK: {ok_count}, Tier 3 提醒: {tier3_count})"
            )
            self.log_check_method(
                "规则: Total > 4000 Records → Tier 3 提醒（不阻断）；"
                "Total > 0 → Tier 3 提醒（不阻断）；"
                "Total == 'No Error' → OK 正常。全量打印所有服务器状态明细"
            )

            # [步骤 3] 无条件打印所有服务器 Error Log 状态明细
            summary_lines = ["【Error Log 全量巡检数据明细】:"]
            summary_lines.append(f"--- [Error Log 服务器状态列表 (共 {total_count} 台)] ---")

            tier1_list = []
            tier3_list = []

            for srv in servers:
                line = f"{srv['server']} | Total: {srv['total']}{srv['tag']}"
                summary_lines.append(f"   * {line}")

                if srv["tier"] == "TIER1":
                    tier1_list.append(f"{srv['server']} ({srv['total']})")
                elif srv["tier"] == "TIER3":
                    tier3_list.append(f"{srv['server']} ({srv['total']})")

            if not servers:
                summary_lines.append("   * (未捕获到任何服务器数据，请检查页面是否正常加载)")

            # 汇总段
            summary_lines.append(f"")
            summary_lines.append(f"--- [汇总统计] ---")
            summary_lines.append(f"   * OK (No Error): {ok_count} 台")
            summary_lines.append(f"   * Tier 3 提醒 (1 ~ 999 Records): {tier3_count} 台")
            summary_lines.append(f"   * Tier 1 致命 (>= 1000 Records): {tier1_count} 台")

            self.log_data_summary(summary_lines)

            # [步骤 4] Tier 3 打印提醒通知，不阻断 Checkpoint
            if tier3_count > 0:
                self.log(f"[Notice] Error Log: {tier3_count} 台服务器有 Error Log 记录（Tier 3 提醒，不阻断 Checkpoint）")
                for item in tier3_list:
                    self.log(f"   [WARN] {item}")

            # [步骤 5] 巡检完成，不阻断 Checkpoint
            self.log_check_result(
                True,
                f"Error Log 巡检通过！(OK: {ok_count} 台"
                + (f"，Tier 3 提醒: {tier3_count} 台" if tier3_count > 0 else "")
                + ")，无阻断问题！"
            )

            # [步骤 6] 点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Error Log 检查出现异常: {e}")
            return False
