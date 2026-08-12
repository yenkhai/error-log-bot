"""
================================================================================
第02站 DB Server Status 关卡检查器 (pages/copier_server/page_02_db_server_status.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 DB Server Status (Menu ID: apy_b0i20text)
   - 页面含 1 个 iFrame，但数据实际位于 mainFrame 的 Table 中（无需切入子 Frame）
   - 表格列: No. | Host | Remarks | Th_connected | ratio | Partition Event | Function | Company | Product

2. 数据样例:
   1 | rcm-db-write.uvinter.link | RCM : niw | S,X,At | 5 | 99.81 % | ON | Show Process

3. 校验与阻断标准:
   - 使用 scan_red_cells() 对全页做 DOM RGB 真实颜色深度扫描
   - 若存在任何红底/红字节点 → Tier 1 致命阻断，停止 Checkpoint
   - 全部正常（无红色节点） → 点击 Checkpoint 通关

4. 打印内容:
   - 无条件打印所有 DB 服务器节点行（Host + ratio + Remarks）
   - 红色扫描结果详情（如有）
================================================================================
"""

import time
from core.base_checker import BaseChecker


class DBServerStatusChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第02站 DB Server Status", menu_id="apy_b0i20text")
        try:
            # [步骤 1] 导航切入 DB Server Status 页面 (section="Copier" 切换 Copier & Server 选项卡)
            self.navigate_to_menu("DB Server Status", menu_id="apy_b0i20text", section="Copier", wait_seconds=3.5)

            # [步骤 2] 使用 JavaScript 精准解析 mainFrame 内的 DB 服务器节点表格
            # 表格列顺序: No. | Host | Remarks | Th_connected | ratio | Partition Event | Function | Company | Product
            db_data = self.driver.execute_script("""
                var result = {
                    servers: [],      // 所有 DB 服务器节点行数据
                    totalCount: 0     // 捕获到的服务器总数
                };

                // 获取页面所有 <table> 节点
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 通过关键列标题 "Host" 和 "ratio" 定位 DB 服务器状态主表
                    if (txt.indexOf("Host") !== -1 && txt.indexOf("ratio") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");

                            // 至少需要 5 列 (No. | Host | Remarks | Th_connected | ratio)
                            if (tds.length >= 5) {
                                var no       = tds[0].innerText.trim();
                                var host     = tds[1].innerText.trim();
                                var remarks  = tds[2].innerText.trim();
                                var thConn   = tds[3].innerText.trim();
                                var ratio    = tds[4].innerText.trim();

                                // 跳过表头行
                                if (!no || no === "No." || host === "Host" || host === "") continue;

                                // 提取可选列
                                var partEvent = tds.length > 5 ? tds[5].innerText.trim() : "-";
                                var func      = tds.length > 6 ? tds[6].innerText.trim() : "-";

                                result.servers.push({
                                    no: no,
                                    host: host,
                                    remarks: remarks,
                                    thConnected: thConn,
                                    ratio: ratio,
                                    partitionEvent: partEvent,
                                    function: func
                                });
                            }
                        }
                        break; // 找到主表后即停止遍历
                    }
                }

                result.totalCount = result.servers.length;
                return result;
            """)

            servers      = db_data.get("servers", [])
            total_count  = db_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 DB Server Status 表格，共捕获 {total_count} 个 DB 服务器节点行"
            )
            self.log_check_method(
                "双重校验: (1) scan_red_cells() DOM RGB 深度扫描全页红色节点 → Tier 1 强阻断；"
                "(2) 全部正常则点击 Checkpoint 通关"
            )

            # [步骤 3] 组装全量数据摘要并打印
            summary_lines = ["【DB Server Status 全量巡检数据明细】:"]
            summary_lines.append(f"--- [DB 服务器节点列表 (共 {total_count} 台)] ---")

            for srv in servers:
                line = (
                    f"No.{srv['no']} | {srv['host']} | Remarks: {srv['remarks']} | "
                    f"Th_connected: {srv['thConnected']} | ratio: {srv['ratio']} | "
                    f"Partition Event: {srv['partitionEvent']} | Function: {srv['function']}"
                )
                summary_lines.append(f"   * {line}")

            if not servers:
                summary_lines.append("   * (未捕获到任何服务器节点，请检查页面是否正常加载)")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 全页红底/红字深度扫描
            red_items = self.scan_red_cells()

            if red_items:
                self.log(f"[Error] DB Server Status 检测到 {len(red_items)} 个红色异常节点，触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")
                self.log_check_result(
                    False,
                    f"DB Server Status 存在 {len(red_items)} 个红色异常节点，Tier 1 强阻断 Checkpoint！"
                )
                return False
            else:
                self.log_check_result(
                    True,
                    f"DB Server Status 全部 {total_count} 个节点无红色异常，巡检通过！"
                )

            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"DB Server Status 检查出现异常: {e}")
            return False
