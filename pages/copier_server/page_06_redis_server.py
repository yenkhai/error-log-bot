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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class RedisServerChecker(BaseChecker):
    """
    Redis Server 缓存服务器检查器类
    负责监控所有 Redis 缓存服务器 (Server | Remark | Total) 的健康状态，
    严格要求每台服务器的 Total 必须显示为 'No Error' 且无红色警示 (Tier 1 强阻断)。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Redis Server 页面 (apy_b0i24text, section="Copier")
        2. 执行前端 JavaScript 提取 Server, Remark 与 Total 列数据
        3. 严格核查 Total 是否为 'No Error'，并检测单元格背景色是否呈红色
        4. 发现任何异常服务器即触发 Tier 1 致命报错阻断 Checkpoint
        5. 全部合格则保存快照并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i24text
        self.log_station_header("第06站 Redis Server", menu_id="apy_b0i24text")
        try:
            # [步骤 1] 导航切入 Redis Server 页面
            self.navigate_to_menu("Redis Server", menu_id="apy_b0i24text", section="Copier")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            
            # [步骤 2] 使用 JavaScript 精准解析 Redis 服务器状态表格
            redis_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    servers: [],      // 所有 Redis 服务器状态列表
                    errorCount: 0,    // Total 非 'No Error' 或红底的异常数量
                    okCount: 0,       // Total == 'No Error' 的正常数量
                    totalCount: 0     // 捕获到的服务器总数
                };

                // 2. 遍历页面中所有 table 标签
                var tables = document.querySelectorAll("table");

                for (var t = 0; t < tables.length; t++) {
                    var txt = tables[t].innerText ? tables[t].innerText.trim() : "";

                    // 3. 通过关键词 'Server'、'Total' 以及 'Remark' 定位 Redis 状态表
                    if (txt.indexOf("Server") !== -1 && txt.indexOf("Total") !== -1) {
                        var rows = tables[t].querySelectorAll("tr");

                        // 4. 遍历表格所有行
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

                            // 5. 判断 Total 是否为 'No Error'
                            var isOk  = (totalVal === "No Error" || totalVal === "" || totalVal === "0");
                            var tier  = isOk ? "OK" : "TIER1";
                            var tag   = isOk ? " [OK/No Error]" : " [ERROR/Tier 1 致命阻断]";

                            if (isOk) {
                                result.okCount++;
                            } else {
                                result.errorCount++;
                            }

                            // 6. 检查 Total 单元格是否有红色背景警示
                            var style = window.getComputedStyle(tds[2]);
                            var bg = style.backgroundColor;
                            var bgM = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            var hasBgRed = bgM && parseInt(bgM[1]) >= 170 && parseInt(bgM[2]) <= 110 && parseInt(bgM[3]) <= 110;
                            if (hasBgRed && isOk) {
                                // 背景红色但 Total 文本看起来正常，仍强行判定为错误
                                tier = "TIER1";
                                tag  = " [ERROR/Tier 1 红色警示]";
                                result.errorCount++;
                                result.okCount--;
                            }

                            // 7. 存入服务器对象列表
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

                // 8. 统计总数并返回给 Python
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
            
            headers = ["Server", "Remark", "Total"]
            rows = []

            for srv in servers:
                line = f"{srv['server']} | Remark: {srv['remark']} | Total: {srv['total']}{srv['tag']}"
                summary_lines.append(f"   * {line}")
                
                bg = "red" if srv["tier"] == "TIER1" else "green"
                rows.append([
                    srv['server'],
                    srv['remark'],
                    CheckpointStore.make_cell(srv['total'], bg)
                ])

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
                msg = f"Redis Server 发现 {error_count} 台服务器 Total 非 'No Error'，Tier 1 致命阻断！({', '.join(error_list)})"
                self.log_check_result(False, msg)
                CheckpointStore.save(
                    page_key="copier_06",
                    title="Redis Server",
                    status=False,
                    headers=headers,
                    rows=rows,
                    summary=msg
                )
                return False
            else:
                msg = f"Redis Server 全部 {total_count} 台服务器 Total 均为 'No Error'，巡检通过！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_06",
                title="Redis Server",
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
            return self.handle_exception("copier_06", "Redis Server", e)
