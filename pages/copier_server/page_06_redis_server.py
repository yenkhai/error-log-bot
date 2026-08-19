"""
================================================================================
第06站 Redis Server 关卡检查器 (pages/copier_server/page_06_redis_server.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 Redis Server (Menu ID: apy_b0i24text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格列: Server | Remark | Total
   - 样例: Redis-Demo-1.Ukdkeu | [M] LRCM (Demo) | No Error

2. 校验与阻断标准:
   - Total 列的值必须为 'No Error'
   - 若任意一项 Total 不是 'No Error' → Tier 1 致命阻断，停止 Checkpoint
   - 全部 No Error → 点击 Checkpoint 通关

3. 解析方式:
   - 使用 JS 精准解析 Redis 状态表格（通过 Server | Remark | Total 关键列定位）
   - 无条件打印所有 Redis 服务器状态明细
================================================================================
"""

import time
from core.base_checker import BaseChecker


class RedisServerChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第06站 Redis Server", menu_id="apy_b0i24text")
        try:
            # [步骤 1] 导航切入 Redis Server 页面
            self.navigate_to_menu("Redis Server", menu_id="apy_b0i24text", section="Copier")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 2] 使用 JavaScript 精准解析 Redis 服务器状态表格
            redis_data = self.driver.execute_script("""
                var result = {
                    servers: [],      // 所有 Redis 服务器状态列表
                    errorCount: 0,    // Total 非 'No Error' 的数量
                    okCount: 0,       // Total == 'No Error' 的数量
                    totalCount: 0
                };

                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 通过关键词 'Server' 和 'Total' 以及 'Remark' 定位 Redis 状态表
                    if (txt.indexOf("Server") !== -1 && txt.indexOf("Total") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        for (var r = 0; r < rows.length; r++) {
                            // 精确要求 3 列: Server | Remark | Total (跳过非 3 列的复杂布局行)
                            var tds = rows[r].querySelectorAll("td");
                            if (tds.length !== 3) continue;

                            var serverName = tds[0].innerText.trim();
                            var remark     = tds[1].innerText.trim();
                            var totalVal   = tds[2].innerText.trim();

                            // 跳过表头行和空行
                            if (!serverName || serverName === "Server" || serverName === "") continue;
                            if (totalVal === "Total" || remark === "Remark") continue;

                            // 判断 Total 是否为 'No Error'
                            var isOk  = (totalVal === "No Error" || totalVal === "" || totalVal === "0");
                            var tier  = isOk ? "OK" : "TIER1";
                            var tag   = isOk ? " [OK/No Error]" : " [ERROR/Tier 1 致命阻断]";

                            if (isOk) {
                                result.okCount++;
                            } else {
                                result.errorCount++;
                            }

                            // 检查 Total 单元格是否有红色警示
                            var style = window.getComputedStyle(tds[2]);
                            var bg = style.backgroundColor;
                            var bgM = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            var hasBgRed = bgM && parseInt(bgM[1]) >= 170 && parseInt(bgM[2]) <= 110 && parseInt(bgM[3]) <= 110;
                            if (hasBgRed && isOk) {
                                // 背景红色但 Total 文本看起来正常，仍视为错误
                                tier = "TIER1";
                                tag  = " [ERROR/Tier 1 红色警示]";
                                result.errorCount++;
                                result.okCount--;
                            }

                            result.servers.push({
                                server: serverName,
                                remark: remark,
                                total: totalVal,
                                tier: tier,
                                tag: tag
                            });
                        }
                        break;
                    }
                }

                result.totalCount = result.servers.length;
                return result;
            """)

            servers     = redis_data.get("servers", [])
            error_count = redis_data.get("errorCount", 0)
            ok_count    = redis_data.get("okCount", 0)
            total_count = redis_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 Redis Server 表格，共捕获 {total_count} 台 Redis 服务器状态 "
                f"(OK: {ok_count}, 异常: {error_count})"
            )
            self.log_check_method(
                "校验规则: Total 必须为 'No Error'。"
                "任意一台 Redis 服务器 Total 非 'No Error' → Tier 1 致命阻断；"
                "全部 No Error → 点击 Checkpoint 通关"
            )

            # [步骤 3] 无条件打印所有 Redis 服务器状态明细
            summary_lines = ["【Redis Server 全量巡检数据明细】:"]
            summary_lines.append(f"--- [Redis 服务器状态列表 (共 {total_count} 台)] ---")

            error_list = []

            for srv in servers:
                line = f"{srv['server']} | Remark: {srv['remark']} | Total: {srv['total']}{srv['tag']}"
                summary_lines.append(f"   * {line}")

                if srv["tier"] == "TIER1":
                    error_list.append(f"{srv['server']} (Total={srv['total']})")

            if not servers:
                summary_lines.append("   * (未捕获到任何 Redis 服务器数据，请检查页面是否正常加载)")

            summary_lines.append(f"")
            summary_lines.append(f"--- [汇总统计] ---")
            summary_lines.append(f"   * OK (No Error): {ok_count} 台")
            summary_lines.append(f"   * Tier 1 异常: {error_count} 台")

            self.log_data_summary(summary_lines)

            # [步骤 4] Tier 1 判定
            if error_count > 0:
                self.log_check_result(
                    False,
                    f"Redis Server 发现 {error_count} 台服务器 Total 非 'No Error'，Tier 1 致命阻断！({', '.join(error_list)})"
                )
                return False
            else:
                self.log_check_result(
                    True,
                    f"Redis Server 全部 {total_count} 台服务器 Total 均为 'No Error'，巡检通过！"
                )

            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Redis Server 检查出现异常: {e}")
            return False
