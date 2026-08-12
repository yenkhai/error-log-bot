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

import time
from core.base_checker import BaseChecker


class InfoRobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第09站 Info Robot Monitor", menu_id="apy_b0i27text")
        try:
            # [步骤 1] 导航切入 Info Robot Monitor 页面
            self.navigate_to_menu("Info Robot Monitor", menu_id="apy_b0i27text", section="Copier", wait_seconds=3.5)

            # [步骤 2] 使用 JavaScript 精准解析 Info Robot Monitor 表格
            # 表格列: Robot ID | Details | Robot Interval | TimeStamp
            # 特别注意: 同时检测每行 TimeStamp 单元格是否呈红色背景（长时间未运行的 Robot）
            robot_data = self.driver.execute_script("""
                var result = {
                    robots: [],        // 所有 Robot 状态行
                    redRobots: [],     // 含红色时间戳的 Robot 列表（长时间未运行）
                    totalCount: 0,
                    redCount: 0
                };

                function isRedColor(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        return (parseInt(m[1]) >= 170 && parseInt(m[2]) <= 110 && parseInt(m[3]) <= 110);
                    }
                    return false;
                }

                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 通过关键词 'Robot ID' / 'Robot' 和 'TimeStamp' 定位主表
                    if ((txt.indexOf("Robot ID") !== -1 || txt.indexOf("Robot") !== -1)
                        && txt.indexOf("TimeStamp") !== -1) {

                        var rows = tables[t].querySelectorAll("tr");

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

                            // 检测 TimeStamp 单元格是否有红色背景/红字
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

                            // 检测行内任意单元格是否有红色
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

            for robot in robots:
                line = (
                    f"Robot ID: {robot['robotId']} | Details: {robot['details']} | "
                    f"Interval: {robot['interval']} | TimeStamp: {robot['timestamp']}{robot['tag']}"
                )
                summary_lines.append(f"   * {line}")

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
                self.log(f"[Error] Info Robot Monitor 检测到 {len(red_items)} 个红色异常节点（含红色时间戳），触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")
                self.log_check_result(
                    False,
                    f"Info Robot Monitor 存在 {len(red_items)} 个红色异常节点（红色时间戳代表 Robot 长时间未运行），Tier 1 强阻断 Checkpoint！"
                )
                return False
            else:
                self.log_check_result(
                    True,
                    f"Info Robot Monitor 全部 {total_count} 个 Robot 无红色异常，所有 Robot 运行正常，巡检通过！"
                )

            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Info Robot Monitor 检查出现异常: {e}")
            return False
