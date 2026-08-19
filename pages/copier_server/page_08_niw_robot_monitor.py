"""
================================================================================
第08站 NIW Robot Monitor 关卡检查器 (pages/copier_server/page_08_niw_robot_monitor.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 NIW Robot Monitor (Menu ID: apy_b0i26text)
   - iFrames: 0 (数据直接在 mainFrame)
   - 表格列: Robot ID | RCM Details | Robot Interval | TimeStamp
   - 包含 RCM 与 LRCM 两个分组区域

2. 校验与阻断标准:
   - 使用 scan_red_cells() 对全页做 DOM RGB 真实颜色深度扫描
   - 若存在任何红底/红字节点 → Tier 1 致命阻断，停止 Checkpoint
   - 全部正常（无红色节点） → 点击 Checkpoint 通关

3. 打印内容:
   - 打印 RCM 与 LRCM 机器人列表摘要（仅打印前 10 条，总数一起显示）
   - 红色节点详情（如有）
================================================================================
"""

import time
from core.base_checker import BaseChecker


class NIWRobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第08站 NIW Robot Monitor", menu_id="apy_b0i26text")
        try:
            # [步骤 1] 导航切入 NIW Robot Monitor 页面
            self.navigate_to_menu("NIW Robot Monitor", menu_id="apy_b0i26text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 2] 使用 JavaScript 精准解析 rcmlist 与 lrcmlist 两个容器中的 Robot 表格
            # 包含 RCM 和 LRCM 分组，表格列: Robot ID | Details | Robot Interval | TimeStamp
            robot_data = self.driver.execute_script("""
                var result = {
                    rcmRobots: [],    // RCM 分组 Robot 列表
                    lrcmRobots: [],   // LRCM 分组 Robot 列表
                    rcmCount: 0,
                    lrcmCount: 0,
                    totalCount: 0
                };

                // 通用容器解析器
                function parseContainer(containerId, targetArray) {
                    var container = document.getElementById(containerId) || document.querySelector("#" + containerId);
                    if (!container) return;

                    var rows = container.querySelectorAll("table tr");
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
                        if (timestamp.indexOf("TimeStamp") !== -1 || details.indexOf("Details") !== -1) continue;

                        targetArray.push({
                            robotId: robotId,
                            details: details,
                            interval: interval,
                            timestamp: timestamp
                        });
                    }
                }

                // 1. 精准提取 RCM 列表 (div#rcmlist)
                parseContainer("rcmlist", result.rcmRobots);

                // 2. 精准提取 LRCM 列表 (div#lrcmlist)
                parseContainer("lrcmlist", result.lrcmRobots);

                // 3. 容错后备机制 (若 DOM ID 发生变动)
                if (result.rcmRobots.length === 0 && result.lrcmRobots.length === 0) {
                    var tables = document.querySelectorAll("table");
                    for (var t = 0; t < tables.length; t++) {
                        var txt = tables[t].innerText || "";
                        if (txt.indexOf("Robot ID") !== -1 && txt.indexOf("TimeStamp") !== -1) {
                            var target = (txt.indexOf("LRCM") !== -1) ? result.lrcmRobots : result.rcmRobots;
                            var rows = tables[t].querySelectorAll("tr");
                            for (var r = 0; r < rows.length; r++) {
                                var tds = rows[r].querySelectorAll("td");
                                if (tds.length >= 2) {
                                    var rId = tds[0].innerText.trim();
                                    var det = tds.length >= 3 ? tds[1].innerText.trim() : "-";
                                    var intv = tds.length >= 4 ? tds[2].innerText.trim() : "-";
                                    var ts = tds.length >= 4 ? tds[3].innerText.trim() : tds[1].innerText.trim();
                                    if (rId && rId !== "Robot ID") {
                                        target.push({ robotId: rId, details: det, interval: intv, timestamp: ts });
                                    }
                                }
                            }
                        }
                    }
                }

                result.rcmCount  = result.rcmRobots.length;
                result.lrcmCount = result.lrcmRobots.length;
                result.totalCount = result.rcmCount + result.lrcmCount;
                return result;
            """)

            rcm_robots  = robot_data.get("rcmRobots", [])
            lrcm_robots = robot_data.get("lrcmRobots", [])
            rcm_count   = robot_data.get("rcmCount", 0)
            lrcm_count  = robot_data.get("lrcmCount", 0)
            total_count = robot_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 NIW Robot Monitor 表格，共捕获 {total_count} 个 Robot "
                f"(RCM: {rcm_count} 个, LRCM: {lrcm_count} 个)"
            )
            self.log_check_method(
                "校验规则: scan_red_cells() DOM RGB 深度扫描全页红色节点 → Tier 1 强阻断；"
                "全部正常则点击 Checkpoint 通关。打印前 10 条 RCM/LRCM 摘要（总数一并显示）"
            )

            # [步骤 3] 打印 RCM 与 LRCM 机器人列表摘要（仅打印前 10 条）
            PREVIEW_LIMIT = 10
            summary_lines = ["【NIW Robot Monitor 全量巡检数据明细】:"]

            # RCM 摘要
            summary_lines.append(f"--- [RCM Robot 列表 (共 {rcm_count} 个，显示前 {min(PREVIEW_LIMIT, rcm_count)} 条)] ---")
            for robot in rcm_robots[:PREVIEW_LIMIT]:
                line = f"Robot ID: {robot['robotId']} | Details: {robot['details']} | Interval: {robot['interval']} | TimeStamp: {robot['timestamp']}"
                summary_lines.append(f"   * {line}")
            if rcm_count > PREVIEW_LIMIT:
                summary_lines.append(f"   * ... (共 {rcm_count} 条，已省略 {rcm_count - PREVIEW_LIMIT} 条)")

            # LRCM 摘要
            summary_lines.append(f"--- [LRCM Robot 列表 (共 {lrcm_count} 个，显示前 {min(PREVIEW_LIMIT, lrcm_count)} 条)] ---")
            for robot in lrcm_robots[:PREVIEW_LIMIT]:
                line = f"Robot ID: {robot['robotId']} | Details: {robot['details']} | Interval: {robot['interval']} | TimeStamp: {robot['timestamp']}"
                summary_lines.append(f"   * {line}")
            if lrcm_count > PREVIEW_LIMIT:
                summary_lines.append(f"   * ... (共 {lrcm_count} 条，已省略 {lrcm_count - PREVIEW_LIMIT} 条)")

            if total_count == 0:
                summary_lines.append("   * (未捕获到任何 Robot 数据，请检查页面是否正常加载)")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 全页红底/红字深度扫描
            red_items = self.scan_red_cells()

            if red_items:
                self.log(f"[Error] NIW Robot Monitor 检测到 {len(red_items)} 个红色异常节点，触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")
                self.log_check_result(
                    False,
                    f"NIW Robot Monitor 存在 {len(red_items)} 个红色异常节点，Tier 1 强阻断 Checkpoint！"
                )
                return False
            else:
                self.log_check_result(
                    True,
                    f"NIW Robot Monitor 全部 {total_count} 个 Robot 无红色异常（RCM: {rcm_count}, LRCM: {lrcm_count}），巡检通过！"
                )

            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"NIW Robot Monitor 检查出现异常: {e}")
            return False
