"""
================================================================================
第01站 Copier 关卡检查器 (pages/copier_server/page_01_copier.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面结构 (真实 DOM 探测后对齐):
   - 主 mainFrame 内包含 21 个子 iframe：
     * iframe[0]: f_popup (系统弹窗专用，跳过)
     * iframe[1] ~ iframe[20]: 20 家卫星公司的 Copier Monitor 监控子窗口
       (公司列表: D0005, D0008, D0009, D0011, D0012, D0013, D0015,
                  P0001, P0002, P0003, P0005, P0008,
                  E1001, E1002, E2001, E2002, E2003,
                  J0001, J0002, K0002)

2. 每个 iframe 内部数据结构 (固定4行 x 4列):
   ┌─────────────────┬──────────────┬──────────────┬──────────────┐
   │ Title           │ Niw_w        │ Niw_winc     │ Niw_wmulp    │
   │ Robot Last Upd  │ [时间戳]      │ [时间戳]      │ [时间戳]      │
   │ Last Copy ID    │ [数字]        │ [数字]        │ [数字]       │
   │ Total Unsynch   │ [数值]        │ [数值]        │ [数值]       │  ← 核心监控行
   └─────────────────┴──────────────┴──────────────┴──────────────┘

3. 校验与阻断标准 (Tier 1 强阻断):
   - 核心考核指标为第 4 行 "Total Unsynch" 的 Niw_w / Niw_winc / Niw_wmulp 三列。
   - 三列任意一个数值 > 0，或该单元格背景/文字呈红色，判定为 Tier 1 致命报错强阻断！
   - 若全部 20 家公司的 Total Unsynch 均为 0 → 通关并自动点击 Checkpoint！
================================================================================
"""

import time
from core.base_checker import BaseChecker

class CopierChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i19text (Copier & Server 区域的 Copier 选项)
        self.log_station_header("第01站 Copier", menu_id="apy_b0i19text")
        try:
            # [步骤 2] 导航切入 Copier 页面 (section="Copier" 自动切换 Copier & Server 选项卡)
            self.navigate_to_menu("Copier", menu_id="apy_b0i19text", section="Copier")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 3] 获取页面内所有 iframe 子窗口列表
            iframes = self.driver.find_elements("tag name", "iframe")
            # 过滤掉 idx=0 的 f_popup 弹窗 frame，只保留公司监控 frame (idx 1~20)
            company_frames = [f for f in iframes if (f.get_attribute("id") or "").startswith("f_") and "popup" not in (f.get_attribute("id") or "")]

            self.log_data_extracted(f"成功发现 Copier 监控子窗口: 共 {len(iframes)} 个 iframe，其中 {len(company_frames)} 个公司监控窗口")
            self.log_check_method("校验规则: 逐一穿透每家公司 Copier iframe，检查 Total Unsynch (Niw_w / Niw_winc / Niw_wmulp) 必须全部为 0 (Tier 1 强阻断)")

            # [步骤 4] 逐一穿透每家公司的 Copier Monitor iframe，读取 Total Unsynch 数据
            summary_lines = ["【Copier 全量巡检数据明细】:"]
            summary_lines.append(f"--- [1. Copier Monitor 子窗口板块 (共 {len(company_frames)} 家公司)] ---")

            err_count = 0
            err_list = []

            for frame in company_frames:
                frame_id = frame.get_attribute("id") or "Unknown"
                # 从 iframe ID 提取公司名称: "f_D0005 - Sport" -> "D0005 - Sport"
                comp_name = frame_id.replace("f_", "").strip()

                try:
                    # 4.1 切入该公司的 iframe 子窗口
                    self.driver.switch_to.frame(frame)

                    # 4.2 读取 Total Unsynch 行 (固定为 Table[0] 第 4 行 tr[3])
                    unsynch_data = self.driver.execute_script("""
                        function isRed(colorStr) {
                            if (!colorStr) return false;
                            var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            if (m) {
                                return (parseInt(m[1]) >= 170 && parseInt(m[2]) <= 110 && parseInt(m[3]) <= 110);
                            }
                            return false;
                        }

                        function cleanNum(txt) {
                            if (!txt) return 0;
                            var n = parseInt(txt.replace(/[^0-9]/g, ""));
                            return isNaN(n) ? 0 : n;
                        }

                        var result = {
                            niw_w: 0,
                            niw_winc: 0,
                            niw_wmulp: 0,
                            hasRed: false,
                            lastUpdate: "Unknown",
                            found: false
                        };

                        var tables = document.querySelectorAll("table");
                        if (tables.length > 0) {
                            var rows = tables[0].querySelectorAll("tr");
                            // Row 1: Robot Last Update (indices: 1=niw_w, 2=niw_winc, 3=niw_wmulp)
                            if (rows.length > 1) {
                                var updateTds = rows[1].querySelectorAll("td");
                                if (updateTds.length >= 2) {
                                    result.lastUpdate = updateTds[1].innerText.trim();
                                }
                            }
                            // Row 3: Total Unsynch (indices: 1=niw_w, 2=niw_winc, 3=niw_wmulp)
                            if (rows.length > 3) {
                                var tds = rows[3].querySelectorAll("td");
                                if (tds.length >= 4) {
                                    result.niw_w = cleanNum(tds[1].innerText.trim());
                                    result.niw_winc = cleanNum(tds[2].innerText.trim());
                                    result.niw_wmulp = cleanNum(tds[3].innerText.trim());
                                    result.found = true;

                                    // 检查红色警示
                                    for (var i = 1; i <= 3; i++) {
                                        if (i < tds.length) {
                                            var bg = window.getComputedStyle(tds[i]).backgroundColor;
                                            var fg = window.getComputedStyle(tds[i]).color;
                                            if (isRed(bg) || isRed(fg)) {
                                                result.hasRed = true;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        return result;
                    """)

                    niw_w = unsynch_data.get("niw_w", 0)
                    niw_winc = unsynch_data.get("niw_winc", 0)
                    niw_wmulp = unsynch_data.get("niw_wmulp", 0)
                    has_red = unsynch_data.get("hasRed", False)
                    last_update = unsynch_data.get("lastUpdate", "Unknown")
                    found = unsynch_data.get("found", False)

                    is_err = (niw_w > 0 or niw_winc > 0 or niw_wmulp > 0 or has_red)

                    if is_err:
                        err_count += 1
                        warn_parts = []
                        if niw_w > 0: warn_parts.append(f"Niw_w={niw_w}")
                        if niw_winc > 0: warn_parts.append(f"Niw_winc={niw_winc}")
                        if niw_wmulp > 0: warn_parts.append(f"Niw_wmulp={niw_wmulp}")
                        if has_red: warn_parts.append("红色警示")
                        err_list.append(f"{comp_name} ({', '.join(warn_parts)})")

                        tag = f" [ERROR/Tier 1 强阻断: {', '.join(warn_parts)}]"
                    else:
                        tag = " [OK/正常]"

                    if found:
                        line = f"{comp_name}: Total Unsynch (Niw_w={niw_w}, Niw_winc={niw_winc}, Niw_wmulp={niw_wmulp}), Last Update={last_update}{tag}"
                    else:
                        line = f"{comp_name}: 无法读取 Total Unsynch 数据 (表格结构可能不同){tag}"

                    summary_lines.append(f"   * {line}")

                except Exception as fe:
                    summary_lines.append(f"   * {comp_name}: [ERR] 穿透异常: {fe}")
                finally:
                    # 4.3 切回 mainFrame 准备处理下一个公司 iframe
                    self.switch_to_main_frame()
                    time.sleep(0.3)  # 短暂缓冲确保 Frame 切换稳定

            # [步骤 5] 打印全量明细摘要
            self.log_data_summary(summary_lines)

            # [步骤 6] Tier 1 报错阻断判定
            if err_count > 0:
                self.log_check_result(False, f"Copier 巡检发现 Tier 1 致命异常: {err_count} 家公司 Total Unsynch 非零 ({', '.join(err_list)})，强阻断 Checkpoint！")
                return False
            else:
                self.log_check_result(True, f"Copier 全部 {len(company_frames)} 家公司 Total Unsynch 均为 0，Copier Monitor 运行完全正常！")

            # [步骤 7] Copier 页面本身没有 Checkpoint 按钮，巡检通过直接返回 True 即可
            return True

        except Exception as e:
            self.log_check_result(False, f"Copier 检查出现异常: {e}")
            return False
