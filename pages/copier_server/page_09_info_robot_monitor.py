"""
================================================================================
第09站 Info Robot Monitor 关卡检查器 (pages/copier_server/page_09_info_robot_monitor.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 Info Robot Monitor (Menu ID: apy_b0i27text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格列: Robot ID | Details | Robot Interval | TimeStamp

2. 已知问题:
   - 页面存在红色时间戳（如 '2026-08-12 17:48:50' 显示红底）
   - 红色时间戳代表该 Robot 长时间未运行，属于严重异常

3. 校验与阻断标准:
   - 使用 scan_red_cells() 对全页做 DOM RGB 真实颜色深度扫描
   - 若存在任何红底/红字节点（如红色时间戳代表 Robot 长时间未运行）→ Tier 1 致命阻断
   - 全部正常（无红色节点） → 点击 Checkpoint 通关

4. 打印内容:
   - 无条件打印所有 Robot 状态（Robot ID + Details + Interval + TimeStamp）
   - 红色节点详情（如有，特别标注为红色时间戳异常）
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class InfoRobotMonitorChecker(BaseChecker):
    """
    Info Robot Monitor 机器人监控检查器类
    负责监控所有 Info 机器人的运行状态 (Robot ID | Details | Interval | TimeStamp)，
    特别检测每行 TimeStamp 单元格是否出现红底 (代表机器人长时间挂起未运行，属于 Tier 1 强阻断)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Info Robot Monitor 页面 (apy_b0i27text, section="Copier")
        2. 执行前端 JavaScript 解析表格并检查每个机器人的 TimeStamp 是否呈现红底
        3. 全量打印所有机器人的状态明细与红色时间戳异常列表
        4. 调用 scan_red_cells() 进行全页扫描，存在红色异常立即触发 Tier 1 致命阻断
        5. 全部正常时保存巡检结果至 CheckpointStore 并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i27text
        self.log_station_header("第09站 Info Robot Monitor", menu_id="apy_b0i27text")
        try:
            # [步骤 1] 导航切入 Info Robot Monitor 页面
            self.navigate_to_menu("Info Robot Monitor", menu_id="apy_b0i27text", section="Copier")          
            
            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 精准解析 Info Robot Monitor 表格
            # 表格列: Robot ID | Details | Robot Interval | TimeStamp
            # 特别注意: 同时检测每行 TimeStamp 单元格是否呈红色背景（长时间未运行的 Robot）
            robot_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    robots: [],        // 所有 Robot 状态行列表
                    redRobots: [],     // 含红色时间戳的 Robot 列表（长时间未运行）
                    totalCount: 0,     // 机器人总数
                    redCount: 0        // 红色时间戳异常机器人总数
                };

                // 2. 辅助函数: 判断 RGB 颜色字符串是否呈红色
                function isRedColor(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        return (parseInt(m[1]) >= 170 && parseInt(m[2]) <= 110 && parseInt(m[3]) <= 110);
                    }
                    return false;
                }

                // 3. 遍历页面所有 table 标签
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 4. 通过关键词 'Robot ID' / 'Robot' 和 'TimeStamp' 定位主表
                    if ((txt.indexOf("Robot ID") !== -1 || txt.indexOf("Robot") !== -1)
                        && txt.indexOf("TimeStamp") !== -1) {

                        var rows = tables[t].querySelectorAll("tr");

                        // 5. 遍历表格所有行
                        for (var r = 0; r < rows.length; r++) {
                            var tds = rows[r].querySelectorAll("td");
                            if (tds.length < 2) continue;

                            var robotId   = tds[0].innerText.trim();
                            var details   = tds.length >= 3 ? tds[1].innerText.trim() : "-";
                            var interval  = tds.length >= 4 ? tds[2].innerText.trim() : "-";
                            var timestamp = tds.length >= 4 ? tds[3].innerText.trim() :
                                           (tds.length >= 3 ? tds[2].innerText.trim() : tds[1].innerText.trim());

                            // 跳过表头行
                            if (!robotId || robotId === "Robot ID" || robotId === "Robot" || robotId === "") continue;
                            if (timestamp === "TimeStamp" || details === "Details") continue;

                            // 6. 检测 TimeStamp 单元格是否有红色背景/红字
                            var tsTd = null;
                            if (tds.length >= 4) {
                                tsTd = tds[3];
                            } else if (tds.length >= 3) {
                                tsTd = tds[2];
                            } else {
                                tsTd = tds[1];
                            }

                            var tsRedBg = false, tsRedFg = false;
                            if (tsTd) {
                                var tsStyle = window.getComputedStyle(tsTd);
                                tsRedBg = isRedColor(tsStyle.backgroundColor);
                                tsRedFg = isRedColor(tsStyle.color);
                            }

                            // 7. 检测行内任意单元格是否有红色
                            var rowHasRed = tsRedBg || tsRedFg;
                            if (!rowHasRed) {
                                for (var c = 0; c < tds.length; c++) {
                                    var cs = window.getComputedStyle(tds[c]);
                                    if (isRedColor(cs.backgroundColor) || isRedColor(cs.color)) {
                                        rowHasRed = true;
                                        break;
                                    }
                                }
                            }

                            var tag = rowHasRed ? " [ERROR/Tier 1 红色时间戳异常-长时间未运行]" : " [OK/正常]";

                            // 8. 存入机器人员工记录
                            var entry = {
                                robotId: robotId,
                                details: details,
                                interval: interval,
                                timestamp: timestamp,
                                hasRedTimestamp: rowHasRed,
                                tag: tag
                            };

                            result.robots.push(entry);
                            if (rowHasRed) {
                                result.redRobots.push(robotId + " (TS: " + timestamp + ")");
                            }
                        }
                        break; // 找到主表即停止
                    }
                }

                // 9. 统计总数并返回给 Python
                result.totalCount = result.robots.length;
                result.redCount   = result.redRobots.length;
                return result;
            """)

            robots      = robot_data.get("robots", [])
            red_robots  = robot_data.get("redRobots", [])
            total_count = robot_data.get("totalCount", 0)
            red_count   = robot_data.get("redCount", 0)

            self.log_data_extracted(
                f"成功解析 Info Robot Monitor 表格，共捕获 {total_count} 个 Robot 运行状态 "
                f"(红色时间戳异常: {red_count} 个)"
            )
            self.log_check_method(
                "校验规则: scan_red_cells() DOM RGB 深度扫描全页红色节点（含红色时间戳代表 Robot 长时间未运行）"
                " → Tier 1 强阻断；全部正常则点击 Checkpoint 通关"
            )

            # [步骤 3] 无条件打印所有 Robot 状态（包含红色时间戳标注）
            summary_lines = ["【Info Robot Monitor 全量巡检数据明细】:"]
            summary_lines.append(f"--- [Robot 运行状态列表 (共 {total_count} 个)] ---")
            
            headers = ["Robot ID", "Details", "Interval", "TimeStamp"]
            rows = []

            for robot in robots:
                line = (
                    f"Robot ID: {robot['robotId']} | Details: {robot['details']} | "
                    f"Interval: {robot['interval']} | TimeStamp: {robot['timestamp']}{robot['tag']}"
                )
                summary_lines.append(f"   * {line}")
                
                bg = "red" if robot['hasRedTimestamp'] else "green"
                rows.append([
                    robot['robotId'],
                    robot['details'],
                    robot['interval'],
                    CheckpointStore.make_cell(robot['timestamp'], bg)
                ])

            if not robots:
                summary_lines.append("   * (未捕获到任何 Robot 数据，请检查页面是否正常加载)")

            if red_robots:
                summary_lines.append(f"--- [红色时间戳异常汇总 (共 {red_count} 个 Robot 长时间未运行)] ---")
                for item in red_robots:
                    summary_lines.append(f"   [RED TIMESTAMP] {item}")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 全页红底/红字深度扫描（双重确认）
            red_items = self.scan_red_cells()
            
            if red_items:
                for item in red_items:
                    rows.append([CheckpointStore.make_cell(str(item), "red"), "RED NODE", "-", "-"])

            if red_items:
                self.log(f"[Error] Info Robot Monitor 检测到 {len(red_items)} 个红色异常节点（含红色时间戳），触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")
                msg = f"Info Robot Monitor 存在 {len(red_items)} 个红色异常节点（红色时间戳代表 Robot 长时间未运行），Tier 1 强阻断 Checkpoint！"
                self.log_check_result(False, msg)
                CheckpointStore.save(
                    page_key="copier_09",
                    title="Info Robot Monitor",
                    status=False,
                    headers=headers,
                    rows=rows,
                    summary=msg
                )
                return False
            else:
                msg = f"Info Robot Monitor 全部 {total_count} 个 Robot 无红色异常，所有 Robot 运行正常，巡检通过！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_09",
                title="Info Robot Monitor",
                status=True,
                headers=headers,
                rows=rows,
                summary=msg
            )
            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_09", "Info Robot Monitor", e)
