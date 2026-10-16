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
   - 若全部 20 家公司的 Total Unsynch 均为 0 = OK(pass)，否则视为 ERROR(Fail)
================================================================================
"""

import time

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore
from core.native_tables import capture_native_tables

class CopierChecker(BaseChecker):
    def check(self) -> bool:
        # 1. 打印关卡页头信息 (Menu ID: apy_b0i19text)
        self.log_station_header("第01站 Copier", menu_id="apy_b0i19text")
        try:
            # 2. 自动化导航切入 Copier 专属菜单页面
            self.navigate_to_menu("Copier", menu_id="apy_b0i19text", section="Copier")

            # 3. 智能等待页面载入完成
            self.wait_for_page_loaded(seconds=2, max_wait=30)

            # 4. 获取页面内所有 iframe 子窗口节点
            iframes = self.driver.find_elements("tag name", "iframe")
            # 过滤掉弹窗 frame，只保留公司 Copier Monitor 监控窗口
            company_frames = [f for f in iframes if (f.get_attribute("id") or "").startswith("f_") and "popup" not in (f.get_attribute("id") or "")]

            if not company_frames:
                raise RuntimeError("未捕获到 Copier 公司监控窗口，不能判定通过")

            self.log_data_extracted(f"成功发现 Copier 监控子窗口: 共 {len(iframes)} 个 iframe，其中 {len(company_frames)} 个公司监控窗口")
            self.log_check_method("校验规则: 逐一穿透每家公司 Copier iframe，检查 Total Unsynch (Niw_w / Niw_winc / Niw_wmulp) 必须全部为 0；Robot Last Update、Last Copy ID 和 Total Unsynch 的九格必须白底 (Tier 1 强阻断)")

            summary_lines = ["【Copier 全量巡检数据明细】:"]
            summary_lines.append(f"--- [1. Copier Monitor 子窗口板块 (共 {len(company_frames)} 家公司)] ---")

            err_count = 0
            err_list = []
            rows = []

            native_tables = []
            native_company_count = 0

            # 5. 逐一穿透每家公司的 Copier Monitor iframe，读取数据
            for frame in company_frames:
                frame_id = frame.get_attribute("id") or "Unknown"
                comp_name = frame_id.replace("f_", "").strip()  # 提取公司名称 (如 D0005)

                try:
                    # 5.1 切入该公司的 iframe 子窗口
                    frame_rect = frame.rect
                    self.driver.switch_to.frame(frame)

                    # 5.2 在 iframe 内执行 JS 读取 Total Unsynch 行 (Table[0] 第 4 行 tr[3])
                    unsynch_data = self.driver.execute_script("""
                        // RGB 真实红底检测
                        function isRed(colorStr) {
                            if (!colorStr) return false;
                            var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            if (m) {
                                return (parseInt(m[1]) >= 170 && parseInt(m[2]) <= 110 && parseInt(m[3]) <= 110);
                            }
                            return false;
                        }

                        // 纯数字转换
                        function cleanNum(txt) {
                            if (!txt || !/^[0-9,]+$/.test(txt.trim())) return null;
                            var n = parseInt(txt.replace(/[^0-9]/g, ""));
                            return isNaN(n) ? 0 : n;
                        }

                        var result = {
                            niw_w: 0,
                            niw_winc: 0,
                            niw_wmulp: 0,
                            hasRed: false,
                            colorErrors: [],
                            lastUpdate: "Unknown",
                            found: false
                        };

                        var tables = document.querySelectorAll("table");
                        if (tables.length > 0) {
                            var rows = tables[0].querySelectorAll("tr");
                            // Row 1: Robot Last Update (索引 1=niw_w, 2=niw_winc, 3=niw_wmulp)
                            if (rows.length > 1) {
                                var updateTds = rows[1].querySelectorAll("td");
                                if (updateTds.length >= 2) {
                                    result.lastUpdate = updateTds[1].innerText.trim();
                                }
                            }
                            // Nine data cells: Robot Last Update, Last Copy ID and Total Unsynch.
                            function whiteBackground(cell) {
                                let node = cell;
                                while (node) {
                                    const color = window.getComputedStyle(node).backgroundColor;
                                    const values = color.match(/[0-9.]+/g);
                                    if (values && values.length >= 3 && (values.length < 4 || +values[3] > 0)) {
                                        return +values[0] === 255 && +values[1] === 255 && +values[2] === 255 &&
                                               (values.length < 4 || +values[3] === 1);
                                    }
                                    node = node.parentElement;
                                }
                                return true; // Browser canvas defaults to white.
                            }
                            for (var ri = 1; ri <= 3; ri++) {
                                const cells = rows[ri] ? rows[ri].querySelectorAll('td') : [];
                                for (var ci = 1; ci <= 3; ci++) {
                                    if (!cells[ci] || !whiteBackground(cells[ci])) {
                                        result.colorErrors.push(['Robot Last Update', 'Last Copy ID', 'Total Unsynch'][ri-1] +
                                            ' / ' + ['Niw_w', 'Niw_winc', 'Niw_wmulp'][ci-1] + ': 非白色或缺失');
                                    }
                                }
                            }
                            // Row 3: Total Unsynch (索引 1=niw_w, 2=niw_winc, 3=niw_wmulp)
                            if (rows.length > 3) {
                                var tds = rows[3].querySelectorAll("td");
                                if (tds.length >= 4) {
                                    result.niw_w = cleanNum(tds[1].innerText.trim());
                                    result.niw_winc = cleanNum(tds[2].innerText.trim());
                                    result.niw_wmulp = cleanNum(tds[3].innerText.trim());
                                    result.found = [result.niw_w, result.niw_winc, result.niw_wmulp].every(value => value !== null);

                                    // 检查红底警示
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

                    color_errors = unsynch_data.get("colorErrors", [])

                    # Total Unsynch >0 or any of the nine status cells is non-white.
                    is_err = (niw_w > 0 or niw_winc > 0 or niw_wmulp > 0 or has_red or bool(color_errors) or not found)

                    if is_err:
                        err_count += 1
                        warn_parts = list(color_errors)
                        if not found: warn_parts.append("Total Unsynch 数据缺失")
                        if niw_w > 0: warn_parts.append(f"Niw_w={niw_w}")
                        if niw_winc > 0: warn_parts.append(f"Niw_winc={niw_winc}")
                        if niw_wmulp > 0: warn_parts.append(f"Niw_wmulp={niw_wmulp}")
                        if has_red: warn_parts.append("红色警示")
                        err_list.append(f"{comp_name} ({', '.join(warn_parts)})")

                        tag = f" 🔴[ERROR/Tier 1 强阻断: {', '.join(warn_parts)}]"
                    else:
                        tag = " [OK/正常]"

                    bg_color = "red" if is_err else "green"

                    if found:
                        line = f"{comp_name}: Total Unsynch (Niw_w={niw_w}, Niw_winc={niw_winc}, Niw_wmulp={niw_wmulp}), Last Update={last_update}{tag}"
                        rows.append([
                            comp_name,
                            CheckpointStore.make_cell(str(niw_w), bg_color),
                            CheckpointStore.make_cell(str(niw_winc), bg_color),
                            CheckpointStore.make_cell(str(niw_wmulp), bg_color),
                            last_update
                        ])
                    else:
                        line = f"{comp_name}: 无法读取 Total Unsynch 数据 (表格结构可能不同){tag}"
                        rows.append([comp_name, "N/A", "N/A", "N/A", "N/A"])

                    summary_lines.append(f"   * {line}")
                    try:
                        captured = capture_native_tables(self.driver)
                        if captured:
                            native_company_count += 1
                            for table in captured:
                                table['title'] = comp_name
                                table['source_x'] += frame_rect['x']
                                table['source_y'] += frame_rect['y']
                            native_tables.extend(captured)
                    except Exception:
                        pass

                except Exception as fe:
                    err_count += 1
                    err_list.append(f"{comp_name} (读取失败: {fe})")
                    summary_lines.append(f"   * {comp_name}: [ERR] 穿透异常: {fe}")
                    rows.append([comp_name, "ERR", "ERR", "ERR", str(fe)])
                finally:
                    # 5.3 必须切回 mainFrame 准备处理下一个公司 iframe
                    self.switch_to_main_frame()
                    time.sleep(0.3)

            if native_company_count != len(company_frames):
                native_tables = []

            # 6. 打印全量数据明细
            self.log_data_summary(summary_lines)

            headers = ["Company", "Niw_w", "Niw_winc", "Niw_wmulp", "Last Update"]

            # 7. Tier 1 报错阻断判定
            if err_count > 0:
                msg = f"Copier 巡检发现 Tier 1 致命异常: {err_count} 家公司 Total Unsynch 或背景颜色异常 ({', '.join(err_list)})，强阻断 Checkpoint！"
                self.log_check_result(False, msg)
                CheckpointStore.save(
                    page_key="copier_01",
                    title="Copier",
                    status=False,
                    tables=native_tables or None,
                    headers=headers,
                    rows=rows,
                    summary=msg
                )
                return False
            else:
                msg = f"Copier 全部 {len(company_frames)} 家公司 Total Unsynch 均为 0，Copier Monitor 运行完全正常！"
                self.log_check_result(True, msg)

            CheckpointStore.save(
                page_key="copier_01",
                title="Copier",
                status=True,
                tables=native_tables or None,
                headers=headers,
                rows=rows,
                summary=msg
            )
            return True

        except Exception as e:
            # 捕获未知异常
            return self.handle_exception("copier_01", "Copier", e)
