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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class ErrorLogChecker(BaseChecker):
    """
    Error Log 错误日志检查器类
    负责监控 Copier & Server 体系下所有服务器的错误日志积压情况 (Total 列)，
    将错误记录按数量分层归类为 Tier 3 提醒 (不阻断 Checkpoint)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Error Log 页面 (apy_b0i23text, section="Copier")
        2. 执行前端 JavaScript 定位并解析包含 Server 与 Total 的错误日志主表
        3. 解析每台服务器的错误记录数值 (No Error 为正常，>0 条记录归类为 Tier 3 提醒)
        4. 全量打印所有服务器日志状态明细
        5. 保存巡检记录至 CheckpointStore 并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i23text
        self.log_station_header("第05站 Error Log", menu_id="apy_b0i23text")
        try:
            # [步骤 1] 导航切入 Error Log 页面
            self.navigate_to_menu("Error Log", menu_id="apy_b0i23text", section="Copier")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 通过关键词 'Server' 和 'Total' 精准定位并解析表格
            error_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    servers: [],      // 所有服务器行数据列表
                    tier3Count: 0,    // Total > 0 的警告提醒数
                    okCount: 0,       // No Error 正常服务器数
                    totalCount: 0     // 捕获到的服务器总数
                };

                // 2. 获取页面中所有的 table 标签
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 3. 通过关键词 'Server' 和 'Total' 定位 Error Log 主表
                    if (txt.indexOf("Server") !== -1 && txt.indexOf("Total") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        // 4. 遍历表格中所有的行
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            if (tds.length < 2) continue;

                            var serverName = tds[0].innerText.trim();
                            var totalVal   = tds[1].innerText.trim();

                            // 跳过表头行与空行
                            if (!serverName || serverName === "Server" || serverName === "" ) continue;
                            if (totalVal === "Total" || totalVal === "") continue;

                            // 5. 解析 Total 值: 'No Error' 或 'X Records' 或纯数字
                            var tier   = "OK";
                            var tag    = " [OK/No Error]";
                            var count  = 0;

                            if (totalVal === "No Error" || totalVal === "" || totalVal === "0") {
                                tier = "OK";
                                tag  = " [OK/No Error]";
                                result.okCount++;
                            } else {
                                // 尝试用正则提取数字: 如 '1500 Records' -> 1500
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

                            // 6. 存入服务器列表
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

                // 7. 统计总数并返回给 Python
                result.totalCount = result.servers.length;
                return result;
            """)

            servers     = error_data.get("servers", [])
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

            tier3_list = []
            
            headers = ["Server", "Total"]
            rows = []

            for srv in servers:
                line = f"{srv['server']} | Total: {srv['total']}{srv['tag']}"
                summary_lines.append(f"   * {line}")
                
                bg = "red" if srv["tier"] in ("TIER3", "TIER3_HIGH", "UNKNOWN") else "green"
                rows.append([
                    srv['server'],
                    CheckpointStore.make_cell(srv['total'], bg)
                ])

                if srv["tier"] == "TIER3" or srv["tier"] == "TIER3_HIGH":
                    tier3_list.append(f"{srv['server']} ({srv['total']})")

            if not servers:
                summary_lines.append("   * (未捕获到任何服务器数据，请检查页面是否正常加载)")

            # 汇总段
            summary_lines.append(f"")
            summary_lines.append(f"--- [汇总统计] ---")
            summary_lines.append(f"   * OK (No Error): {ok_count} 台")
            summary_lines.append(f"   * Tier 3 提醒 (> 0 Records): {tier3_count} 台")

            self.log_data_summary(summary_lines)

            # [步骤 4] Tier 3 打印提醒通知，不阻断 Checkpoint
            if tier3_count > 0:
                self.log(f"[Notice] Error Log: {tier3_count} 台服务器有 Error Log 记录（Tier 3 提醒，不阻断 Checkpoint）")
                for item in tier3_list:
                    self.log(f"   [WARN] {item}")

            # [步骤 5] 巡检完成，不阻断 Checkpoint
            msg = f"Error Log 巡检通过！(OK: {ok_count} 台" + (f"，Tier 3 提醒: {tier3_count} 台" if tier3_count > 0 else "") + ")，无阻断问题！"
            self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_05",
                title="Error Log",
                status=True,
                headers=headers,
                rows=rows,
                summary=msg
            )
            # [步骤 6] 点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_05", "Error Log", e)
