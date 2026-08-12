"""
================================================================================
第07站 Robot Monitor 关卡检查器 (pages/copier_server/page_07_robot_monitor.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 Robot Monitor (Menu ID: apy_b0i25text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格列: Robot ID | Details | TimeStamp

2. 校验与阻断标准:
   ⚠️ 本站无 Checkpoint 按钮！绝对不调用 click_checkpoint()
   - 使用 scan_red_cells() 扫描全页红底/红字节点
   - 若存在红色节点 → 归类为 Tier 3 提醒（仅 Notify 通知，不阻断，仍 return True）
   - 无红色节点 → 正常
   - 无论如何都直接 return True（本站无 Checkpoint 页面）

3. 打印内容:
   - 打印当前运行中的所有 Robot ID 与最后更新时间（TimeStamp）
   - 红色节点详情（如有）
================================================================================
"""

import time
from core.base_checker import BaseChecker


class RobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第07站 Robot Monitor", menu_id="apy_b0i25text")
        try:
            # [步骤 1] 导航切入 Robot Monitor 页面
            self.navigate_to_menu("Robot Monitor", menu_id="apy_b0i25text", section="Copier", wait_seconds=3.5)

            # [步骤 2] 使用 JavaScript 解析 Robot Monitor 表格
            # 表格列: Robot ID | Details | TimeStamp
            robot_data = self.driver.execute_script("""
                var result = {
                    robots: [],       // 所有 Robot 状态行
                    totalCount: 0
                };

                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 通过关键词 'Robot ID' 和 'TimeStamp' 定位主表
                    if ((txt.indexOf("Robot ID") !== -1 || txt.indexOf("Robot") !== -1)
                        && txt.indexOf("TimeStamp") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");

                            // 至少需要 2 列: Robot ID | TimeStamp
                            if (tds.length < 2) continue;

                            var robotId   = tds[0].innerText.trim();
                            var details   = tds.length >= 3 ? tds[1].innerText.trim() : "-";
                            var timestamp = tds.length >= 3 ? tds[2].innerText.trim() : tds[1].innerText.trim();

                            // 跳过表头行
                            if (!robotId || robotId === "Robot ID" || robotId === "Robot" || robotId === "") continue;
                            if (timestamp === "TimeStamp") continue;

                            result.robots.push({
                                robotId: robotId,
                                details: details,
                                timestamp: timestamp
                            });
                        }
                        break;
                    }
                }

                result.totalCount = result.robots.length;
                return result;
            """)

            robots      = robot_data.get("robots", [])
            total_count = robot_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 Robot Monitor 表格，共捕获 {total_count} 个 Robot 运行状态行"
            )
            self.log_check_method(
                "校验规则: scan_red_cells() 扫描红色节点 → Tier 3 提醒（不阻断）。"
                "⚠️ 本站无 Checkpoint 按钮，无论结果如何均 return True"
            )

            # [步骤 3] 打印所有 Robot ID 与最后更新时间
            summary_lines = ["【Robot Monitor 全量巡检数据明细】:"]
            summary_lines.append(f"--- [Robot 运行状态列表 (共 {total_count} 个)] ---")

            for robot in robots:
                line = f"Robot ID: {robot['robotId']} | Details: {robot['details']} | TimeStamp: {robot['timestamp']}"
                summary_lines.append(f"   * {line}")

            if not robots:
                summary_lines.append("   * (未捕获到任何 Robot 数据，页面可能无 Robot 在运行或结构不符)")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 扫描红色节点 → Tier 3 提醒（不阻断）
            red_items = self.scan_red_cells()

            if red_items:
                self.log(f"[Notice] Robot Monitor 检测到 {len(red_items)} 个红色节点，归类为 Tier 3 提醒（不阻断）")
                for item in red_items:
                    self.log(f"   [WARN/Tier 3] {item}")
                self.log_check_result(
                    True,
                    f"Robot Monitor 有 {len(red_items)} 个红色节点（Tier 3 提醒，仅 Notify，不阻断）。本站无 Checkpoint，直接通过。"
                )
            else:
                self.log_check_result(
                    True,
                    f"Robot Monitor 全部 {total_count} 个 Robot 无红色异常，本站无 Checkpoint，巡检正常通过！"
                )

            # ⚠️ 本站无 Checkpoint 按钮，绝对不调用 click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Robot Monitor 检查出现异常: {e}")
            return False
