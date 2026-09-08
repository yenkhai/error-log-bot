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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class RobotMonitorChecker(BaseChecker):
    """
    Robot Monitor 机器人监控检查器类
    负责监控系统运行的各机器人进程 (Robot ID | Details | TimeStamp)，
    ⚠️ 特别注意: 本站为纯只读展示页面，无 Checkpoint 按钮，绝对不调用 click_checkpoint()。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Robot Monitor 页面 (apy_b0i25text, section="Copier")
        2. 执行前端 JavaScript 提取所有 Robot ID、Details 与 TimeStamp 状态行
        3. 调用 scan_red_cells() 扫描红色警戒节点 (若有则作为 Tier 3 提醒通报)
        4. 全量打印各 Robot 运行状态明细
        5. 保存巡检记录至 CheckpointStore 并直接 return True (本页面无 Checkpoint 按钮)
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i25text
        self.log_station_header("第07站 Robot Monitor", menu_id="apy_b0i25text")
        try:
            # [步骤 1] 导航切入 Robot Monitor 页面
            self.navigate_to_menu("Robot Monitor", menu_id="apy_b0i25text", section="Copier")
            
            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 解析 Robot Monitor 表格
            # 表格列: Robot ID | Details | TimeStamp
            robot_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    robots: [],       // 所有 Robot 状态行列表
                    totalCount: 0     // 捕获到的 Robot 总数
                };

                // 2. 遍历页面中所有 table 标签
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 3. 通过关键词 'Robot ID' 和 'TimeStamp' 定位主表
                    if ((txt.indexOf("Robot ID") !== -1 || txt.indexOf("Robot") !== -1)
                        && txt.indexOf("TimeStamp") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        // 4. 遍历每一行
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

                            // 5. 存入机器人列表
                            result.robots.push({
                                robotId: robotId,
                                details: details,
                                timestamp: timestamp
                            });
                        }
                        break;
                    }
                }

                // 6. 统计总数并返回给 Python
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
            
            headers = ["Robot ID", "Details", "TimeStamp"]
            rows = []

            for robot in robots:
                line = f"Robot ID: {robot['robotId']} | Details: {robot['details']} | TimeStamp: {robot['timestamp']}"
                summary_lines.append(f"   * {line}")
                rows.append([robot['robotId'], robot['details'], robot['timestamp']])

            if not robots:
                summary_lines.append("   * (未捕获到任何 Robot 数据，页面可能无 Robot 在运行或结构不符)")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 扫描红色节点 → Tier 3 提醒（不阻断）
            red_items = self.scan_red_cells()

            if red_items:
                self.log(f"[Notice] Robot Monitor 检测到 {len(red_items)} 个红色节点，归类为 Tier 3 提醒（不阻断）")
                for item in red_items:
                    self.log(f"   [WARN/Tier 3] {item}")
                    rows.append([CheckpointStore.make_cell(str(item), "red"), "RED NODE", ""])
                msg = f"Robot Monitor 有 {len(red_items)} 个红色节点（Tier 3 提醒，仅 Notify，不阻断）。本站无 Checkpoint，直接通过。"
                self.log_check_result(True, msg)
            else:
                msg = f"Robot Monitor 全部 {total_count} 个 Robot 无红色异常，本站无 Checkpoint，巡检正常通过！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_07",
                title="Robot Monitor",
                status=True,
                headers=headers,
                rows=rows,
                summary=msg
            )
            # ⚠️ 本站无 Checkpoint 按钮，绝对不调用 click_checkpoint()
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_07", "Robot Monitor", e)
