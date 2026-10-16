"""
================================================================================
第03站 AP Server Status 关卡检查器 (pages/copier_server/page_03_ap_server_status.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构:
   - 导航至 AP Server Status (Menu ID: apy_b0i21text)
   - iFrames: 0 (数据直接在 mainFrame，无子 Frame 嵌套)
   - 页面以 IP 地址列举 AP 服务器 (如 10.101.10.59, 10.101.10.69, 10.16.10.49 等)

2. 校验与阻断标准:
   - 使用 scan_red_cells() 对全页做 DOM RGB 真实颜色深度扫描
   - 若存在任何红底/红字节点（代表 AP 服务器状态异常）→ Tier 1 致命阻断
   - 全部正常（无红色节点） → 点击 Checkpoint 通关

3. 打印内容:
   - 无条件打印所有捕获到的服务器 IP 列表
   - 明确标注红色项（如有）
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class APServerStatusChecker(BaseChecker):
    """
    AP Server Status 应用服务器状态检查器类
    负责监控所有 10.x.x.x 内网 AP 服务器的运行状态，
    并通过 scan_red_cells() 进行 DOM RGB 真实颜色深度扫描。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 AP Server Status 页面 (apy_b0i21text, section="Copier")
        2. 执行前端 JavaScript 正则捕获页面中所有 10.x.x.x 的 AP 服务器 IP
        3. 检查每个 IP 所在单元格的背景与文字颜色是否呈红底/红字
        4. 调用 scan_red_cells() 全页扫描，存在任何红色异常即触发 Tier 1 强阻断
        5. 全部正常则保存快照并点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i21text
        self.log_station_header("第03站 AP Server Status", menu_id="apy_b0i21text")
        try:
            # [步骤 1] 导航切入 AP Server Status 页面
            self.navigate_to_menu("AP Server Status", menu_id="apy_b0i21text", section="Copier")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=2, max_wait=30)

            # [步骤 2] 使用 JavaScript 解析页面中所有 AP 服务器 IP 地址
            # AP 服务器 IP 格式: 10.xxx.xxx.xxx，通过正则匹配文本节点提取
            ap_data = self.driver.execute_script("""
                // 1. 初始化存储结果的数据结构
                var result = {
                    ipList: [],       // 所有捕获到的 IP 地址列表
                    totalCount: 0     // 捕获到的 IP 总数
                };

                // 2. 在所有 td、div、span、font 节点中匹配 IP 地址格式
                var elements = document.querySelectorAll("td, div, span, font, p");
                var ipPattern = /\\b(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})\\b/g;
                var seen = {};

                for (var i = 0; i < elements.length; i++) {
                    var el = elements[i];
                    // 跳过不可见节点
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) continue;

                    var txt = el.innerText ? el.innerText.trim() : "";
                    if (!txt) continue;

                    // 3. 仅匹配以 10. 开头的内网 IP（排除外部域名 IP 噪音）
                    var matches = txt.match(ipPattern);
                    if (matches) {
                        for (var m = 0; m < matches.length; m++) {
                            var ip = matches[m];
                            if (ip.indexOf("10.") === 0 && !seen[ip]) {
                                seen[ip] = true;

                                // 4. 检查该元素是否呈红色警示
                                var style = window.getComputedStyle(el);
                                var bg = style.backgroundColor;
                                var fg = style.color;

                                var isRedBg = false, isRedFg = false;
                                var bgM = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                if (bgM && parseInt(bgM[1]) >= 170 && parseInt(bgM[2]) <= 110 && parseInt(bgM[3]) <= 110) isRedBg = true;
                                var fgM = fg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                                if (fgM && parseInt(fgM[1]) >= 170 && parseInt(fgM[2]) <= 110 && parseInt(fgM[3]) <= 110) isRedFg = true;

                                // 5. 记录 IP 及其色彩状态与上下文文本
                                result.ipList.push({
                                    ip: ip,
                                    isRed: isRedBg || isRedFg,
                                    context: txt.substring(0, 80)
                                });
                            }
                        }
                    }
                }

                // 6. 统计总数并返回给 Python
                result.totalCount = result.ipList.length;
                return result;
            """)

            ip_list     = ap_data.get("ipList", [])
            total_count = ap_data.get("totalCount", 0)

            self.log_data_extracted(
                f"成功解析 AP Server Status 页面，共捕获 {total_count} 个 AP 服务器 IP 地址"
            )
            self.log_check_method(
                "校验规则: scan_red_cells() DOM RGB 深度扫描全页红色节点 → Tier 1 强阻断；"
                "全部正常则点击 Checkpoint 通关"
            )

            # [步骤 3] 组装全量数据摘要
            summary_lines = ["【AP Server Status 全量巡检数据明细】:"]
            summary_lines.append(f"--- [AP 服务器 IP 列表 (共 {total_count} 台)] ---")

            red_ips = []
            for item in ip_list:
                tag = " [RED/红色警示]" if item["isRed"] else " [OK/正常]"
                summary_lines.append(f"   * {item['ip']}{tag}")
                if item["isRed"]:
                    red_ips.append(item["ip"])

            if not ip_list:
                summary_lines.append("   * (未捕获到任何 AP 服务器 IP，请检查页面是否正常加载)")

            self.log_data_summary(summary_lines)

            # [步骤 4] scan_red_cells() 全页红底/红字深度扫描（双重确认）
            red_items = self.scan_red_cells()

            headers = ["IP", "Status", "Context"]
            rows = []
            for item in ip_list:
                bg = "red" if item["isRed"] else "green"
                rows.append([
                    item["ip"],
                    CheckpointStore.make_cell("Error" if item["isRed"] else "OK", bg),
                    item["context"]
                ])

            if red_items:
                for item in red_items:
                    rows.append([CheckpointStore.make_cell(str(item), "red"), "Error", "RED NODE"])

            if red_items:
                self.log(f"[Error] AP Server Status 检测到 {len(red_items)} 个红色异常节点，触发 Tier 1 致命阻断！")
                for item in red_items:
                    self.log(f"   [RED NODE] {item}")

                msg = f"AP Server Status 存在 {len(red_items)} 个红色异常节点（含红色 IP: {red_ips}），Tier 1 强阻断 Checkpoint！"
                self.log_check_result(False, msg)
                CheckpointStore.save(
                    derived_status_columns=tuple(i for i, h in enumerate(headers) if h == "Status"),
                    page_key="copier_03",
                    title="AP Server Status",
                    status=False,
                    headers=headers,
                    rows=rows,
                    summary=msg
                )
                return False
            else:
                msg = f"AP Server Status 全部 {total_count} 台服务器无红色异常，巡检通过！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                derived_status_columns=tuple(i for i, h in enumerate(headers) if h == "Status"),
                page_key="copier_03",
                title="AP Server Status",
                status=True,
                headers=headers,
                rows=rows,
                summary=msg
            )
            # [步骤 5] 巡检通过，点击 Checkpoint
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("copier_03", "AP Server Status", e)
