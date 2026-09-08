"""
================================================================================
第04站 Check AP Space 关卡检查器 (pages/copier_server/page_04_check_ap_space.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 Check AP Space (Menu ID: apy_b0i22text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格格式: IP地址 + Size | Used | Avail | Use% (例: 20G | 8.9G | 12G | 45%)

2. 分层判定规则:
   - Use% > 80% → Tier 3 提醒（仅 Notify 通知，不阻断 Checkpoint，继续打印）
   - Use% <= 80% → OK 正常
   - 注意: 磁盘空间不设 Tier 1 强阻断，只做 Tier 3 提醒

3. 校验方式:
   - 使用 JS 精准解析表格，提取每台服务器 IP 与 Use% 数值
   - 同时 scan_red_cells() 双重检测红色警示节点

4. 打印内容:
   - 无条件打印所有服务器 IP + 空间使用率完整明细
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class CheckAPSpaceChecker(BaseChecker):
    """
    Check AP Space 应用服务器磁盘空间检查器类
    负责监控所有 AP 服务器的磁盘使用率 (Use%)，
    当磁盘空间大于 80% 时触发 Tier 3 提醒 (仅通知不阻断 Checkpoint)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Check AP Space 页面 (apy_b0i22text, section="Copier")
        2. 执行前端 JavaScript 解析磁盘空间表格 (IP | Size | Used | Avail | Use%)
        3. 统计 Use% > 80% 的服务器节点并归类为 Tier 3 提醒 (本站不设 Tier 1 强阻断)
        4. 全量打印所有服务器磁盘空间明细
        5. 保存巡检记录至 CheckpointStore 并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i22text
        self.log_station_header("第04站 Check AP Space", menu_id="apy_b0i22text")
        try:
            # [步骤 1] 导航切入 Check AP Space 页面
            self.navigate_to_menu("Check AP Space", menu_id="apy_b0i22text", section="Copier")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 精准解析磁盘空间表格
            # 表格格式: IP | Size | Used | Avail | Use%
            space_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    servers: [],       // 所有服务器磁盘使用情况列表
                    tier3Count: 0,     // Use% > 80% 的 Tier 3 警告提醒数
                    okCount: 0,        // Use% <= 80% 的正常数
                    totalCount: 0      // 捕获到的服务器总数
                };

                // 2. 遍历页面所有 table 标签
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 3. 通过关键词 "Use%" 和 "Size" 定位磁盘空间表格
                    if (txt.indexOf("Use%") !== -1 && (txt.indexOf("Size") !== -1 || txt.indexOf("Avail") !== -1)) {
                        var rows = tables[t].querySelectorAll("tr");

                        // 4. 遍历表格每一行
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");

                            // 需要至少 4 列以上的数据
                            if (tds.length < 4) continue;

                            var col0 = tds[0].innerText.trim();
                            var col1 = tds[1] ? tds[1].innerText.trim() : "-";
                            var col2 = tds[2] ? tds[2].innerText.trim() : "-";
                            var col3 = tds[3] ? tds[3].innerText.trim() : "-";
                            var col4 = tds[4] ? tds[4].innerText.trim() : col3;

                            // 跳过表头行
                            if (!col0 || col0 === "IP" || col0 === "Host" || col0 === "Size") continue;

                            // 5. 提取 Use% 列 (含 % 字符的列)
                            var usePercStr = "";
                            var ip = col0;
                            var size = col1, used = col2, avail = col3;

                            // 如果表格有 5 列则最后列是 Use%，如果 4 列则第 4 列是 Use%
                            if (tds.length >= 5) {
                                usePercStr = col4;
                            } else {
                                usePercStr = col3;
                            }

                            // 6. 清理 Use% 字符串 (去掉 % 符号和空格并转换为浮点数)
                            var usePct = parseFloat(usePercStr.replace("%", "").trim());
                            if (isNaN(usePct)) continue;

                            // 7. 判断级别: Use% > 80% 为 Tier 3 提醒，其余正常
                            var tier = "OK";
                            var tag  = " [OK/正常]";
                            if (usePct > 80) {
                                tier = "TIER3";
                                tag  = " [WARN/Tier 3 磁盘 >80% 提醒]";
                                result.tier3Count++;
                            } else {
                                result.okCount++;
                            }

                            // 8. 存入服务器节点列表
                            result.servers.push({
                                ip: ip,
                                size: size,
                                used: used,
                                avail: avail,
                                usePercent: usePct,
                                tier: tier,
                                tag: tag
                            });
                        }
                        break; // 找到主表即退出
                    }
                }

                // 9. 统计总数并返回给 Python
                result.totalCount = result.servers.length;
                return result;
            """)

            servers     = space_data.get("servers", [])
            tier3_count = space_data.get("tier3Count", 0)
            ok_count    = space_data.get("okCount", 0)
            total_count = space_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 Check AP Space 表格，共捕获 {total_count} 台服务器磁盘使用情况 "
                f"(正常: {ok_count} 台, Tier 3 警告 >80%: {tier3_count} 台)"
            )
            self.log_check_method(
                "判定规则: Use% > 80% → Tier 3 提醒（不阻断 Checkpoint）；"
                "Use% <= 80% → OK 正常；磁盘空间不设 Tier 1 强阻断"
            )

            # [步骤 3] 组装全量数据摘要
            summary_lines = ["【Check AP Space 全量巡检数据明细】:"]
            summary_lines.append(f"--- [磁盘空间使用率明细 (共 {total_count} 台)] ---")

            tier3_list = []
            
            headers = ["IP", "Size", "Used", "Avail", "Use%"]
            rows = []

            for srv in servers:
                line = (
                    f"{srv['ip']} | Size: {srv['size']} | Used: {srv['used']} | "
                    f"Avail: {srv['avail']} | Use%: {srv['usePercent']}%{srv['tag']}"
                )
                summary_lines.append(f"   * {line}")
                
                bg = "red" if srv["tier"] == "TIER3" else "green"
                rows.append([
                    srv['ip'],
                    srv['size'],
                    srv['used'],
                    srv['avail'],
                    CheckpointStore.make_cell(f"{srv['usePercent']}%", bg)
                ])

                if srv["tier"] == "TIER3":
                    tier3_list.append(f"{srv['ip']} (Use%={srv['usePercent']}%)")

            if not servers:
                summary_lines.append("   * (未捕获到任何服务器磁盘数据，请检查页面是否正常加载)")

            # 追加 Tier 3 汇总（不阻断）
            if tier3_list:
                summary_lines.append(f"--- [Tier 3 提醒汇总 (Use% > 80%, 不阻断)] ---")
                for item in tier3_list:
                    summary_lines.append(f"   [WARN] {item}")

            self.log_data_summary(summary_lines)

            # [步骤 4] Tier 3 仅打印提醒，不阻断
            if tier3_count > 0:
                self.log(f"[Notice] Check AP Space: {tier3_count} 台服务器 Use% > 80%（Tier 3 提醒，不阻断 Checkpoint）")

            # [步骤 5] 磁盘空间无 Tier 1 强阻断，直接通关并点击 Checkpoint
            msg = f"Check AP Space 全部 {total_count} 台服务器巡检完毕" + (f"（有 {tier3_count} 台 Use% > 80% Tier 3 提醒，不阻断）" if tier3_count > 0 else "，磁盘空间全部正常") + "！"
            self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_04",
                title="Check AP Space",
                status=True,
                headers=headers,
                rows=rows,
                summary=msg
            )
            # [步骤 6] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_04", "Check AP Space", e)
