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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class NIWRobotMonitorChecker(BaseChecker):
    """
    NIW Robot Monitor 机器人监控检查器类
    负责监控 RCM 与 LRCM 两个分组区域的各机器人状态 (Robot ID | Details | Interval | TimeStamp)，
    并通过 scan_red_cells() 进行 DOM RGB 真实颜色深度扫描 (Tier 1 强阻断规则)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 NIW Robot Monitor 页面 (apy_b0i26text, section="Copier")
        2. 执行前端 JavaScript 分别解析 rcmlist 与 lrcmlist 容器中的机器人表格
        3. 检测 TimeStamp 单元格背景是否呈红色预警
        4. 打印 RCM 与 LRCM 前 10 条摘要与总数
        5. 调用 scan_red_cells() 全页扫描，无红色异常则保存快照并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i26text
        self.log_station_header("第08站 NIW Robot Monitor", menu_id="apy_b0i26text")
        try:
            # [步骤 1] 导航切入 NIW Robot Monitor 页面
            self.navigate_to_menu("NIW Robot Monitor", menu_id="apy_b0i26text", section="Copier")
            
            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 精准解析 rcmlist 与 lrcmlist 两个容器中的 Robot 表格
            # 包含 RCM 和 LRCM 分组，表格列: Robot ID | Details | Robot Interval | TimeStamp
            robot_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    rcmRobots: [],    // RCM 分组 Robot 列表
                    lrcmRobots: [],   // LRCM 分组 Robot 列表
                    rcmCount: 0,      // RCM 机器人总数
                    lrcmCount: 0,     // LRCM 机器人总数
                    totalCount: 0     // 两个分组合计总数
                };

                // 2. 通用容器解析器函数: 提取指定容器内表格的数据
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

                        // 获取时间戳单元格并检查其是否为红底
                        var tsCell = tds.length >= 4 ? tds[3] : (tds.length >= 3 ? tds[2] : tds[1]);
                        var cellBg = window.getComputedStyle(tsCell).backgroundColor;
                        var isRed = (cellBg.indexOf("255") !== -1 && cellBg.indexOf("0, 0") !== -1);

                        // 存入对应分组数组
                        targetArray.push({
                            robotId: robotId,
                            details: details,
                            interval: interval,
                            timestamp: timestamp,
                            isRed: isRed
                        });
                    }
                }

                // 3. 精准提取 RCM 列表 (div#rcmlist)
                parseContainer("rcmlist", result.rcmRobots);

                // 4. 精准提取 LRCM 列表 (div#lrcmlist)
                parseContainer("lrcmlist", result.lrcmRobots);

                // 5. 容错后备机制 (若 DOM ID 发生变动则通过关键词匹配定位)
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
                                    var tsCell2 = tds.length >= 4 ? tds[3] : tds[1];
                                    var cBg = window.getComputedStyle(tsCell2).backgroundColor;
                                    var isR = (cBg.indexOf("255") !== -1 && cBg.indexOf("0, 0") !== -1);
                                    if (rId && rId !== "Robot ID") {
                                        target.push({ robotId: rId, details: det, interval: intv, timestamp: ts, isRed: isR });
                                    }
                                }
                            }
                        }
                    }
                }

                // 6. 统计总数并返回给 Python
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

            # 构筑 1:1 还原企业网页的两张原生独立子表 (RCM Details 与 LRCM Details)
            subtables = [
                {
                    "title": "RCM Details",
                    "header_bg": "#5B9BD5",
                    "headers": ["Robot ID", "RCM Details", "Robot Interval", "TimeStamp"],
                    "rows": [
                        [
                            CheckpointStore.make_cell(r["robotId"]),
                            CheckpointStore.make_cell(r["details"]),
                            CheckpointStore.make_cell(r["interval"]),
                            CheckpointStore.make_cell(r["timestamp"], bg="red" if r.get("isRed") else "white")
                        ]
                        for r in rcm_robots
                    ]
                },
                {
                    "title": "LRCM Details",
                    "header_bg": "#5B9BD5",
                    "headers": ["Robot ID", "LRCM Details", "Robot Interval", "TimeStamp"],
                    "rows": [
                        [
                            CheckpointStore.make_cell(r["robotId"]),
                            CheckpointStore.make_cell(r["details"]),
                            CheckpointStore.make_cell(r["interval"]),
                            CheckpointStore.make_cell(r["timestamp"], bg="red" if r.get("isRed") else "white")
                        ]
                        for r in lrcm_robots
                    ]
                }
            ]

            # [步骤 4] scan_red_cells() 全页红底/红字深度扫描 (Check Logic 原生不变)
            red_items = self.scan_red_cells()

            if red_items:
                self.log(f"[Error] NIW Robot Monitor 检测到 {len(red_items)} 个红色异常节点，触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")
                msg = f"NIW Robot Monitor 存在 {len(red_items)} 个红色异常节点，Tier 1 强阻断 Checkpoint！"
                self.log_check_result(False, msg)
                CheckpointStore.save(
                    page_key="copier_08",
                    title="NIW Robot Monitor",
                    status=False,
                    tables=subtables,
                    summary=msg
                )
                return False
            else:
                msg = f"NIW Robot Monitor 全部 {total_count} 个 Robot 无红色异常（RCM: {rcm_count}, LRCM: {lrcm_count}），巡检通过！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_08",
                title="NIW Robot Monitor",
                status=True,
                tables=subtables,
                summary=msg
            )
            # [步骤 5] 巡检通过，点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_08", "NIW Robot Monitor", e)
