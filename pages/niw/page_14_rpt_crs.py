"""
================================================================================
第14站 RPT CRS 关卡检查器 (pages/niw/page_14_rpt_crs.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面功能与抓取目标:
   - 本页面监控 API 与 Credit 各个历史日期跨度区间的同步核算状态 (Agency / API / Credit)。
   - 抓取字段: 包含跨月/跨期时间段（如 `01/06/2026 - 30/06/2026`）与对应的同步状态标示（如 `ok` 或 `-`）。

2. 校验与阻断标准 (Tier 1 强阻断):
   - 检查每一个时间段的同步状态。
   - 正常状态应为 `"ok"` 或 `"-"`。
   - 如果某个节点的单元格呈红底/红字，或者状态文本包含 `"error"`，判定为 **Tier 1 致命报错强阻断 Checkpoint**！
================================================================================
"""

import time
from core.base_checker import BaseChecker

class RPTCRSChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i16text (对应 NIW 区域的 RPT CRS 选项)
        self.log_station_header("第14站 RPT CRS", menu_id="apy_b0i16text")
        try:
            # [步骤 2] 导航切入 RPT CRS 页面，缓冲等待 3.5 秒让数据自动渲染
            self.navigate_to_menu("RPT CRS", menu_id="apy_b0i16text", section="NIW", wait_seconds=10)

            # [步骤 3] JavaScript 脚本精准抓取 RPT CRS 时间跨度表格数据
            p14_data = self.driver.execute_script("""
                var result = {
                    category: "RCM",
                    rows: [],
                    errCount: 0,
                    errList: []
                };

                // 获取下拉框当前选择的分区 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.category = sel.options[sel.selectedIndex].text;
                }

                // 判断颜色是否为红色警示
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110);
                    }
                    return false;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 通过关键字 Agency, API, Credit 锁定目标表格
                    if (txt.indexOf("Agency") !== -1 || txt.indexOf("API") !== -1 || txt.indexOf("Credit") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var cells = [];
                                var rowErr = false;
                                for (var i = 0; i < tds.length; i++) {
                                    var cellTxt = tds[i].innerText.trim();
                                    var bg = window.getComputedStyle(tds[i]).backgroundColor;
                                    var fg = window.getComputedStyle(tds[i]).color;

                                    // 检查单元格颜色是否偏红，或文字包含 "error"
                                    if (isRed(bg) || isRed(fg) || cellTxt.toLowerCase() === "error") {
                                        rowErr = true;
                                    }
                                    cells.push(cellTxt);
                                }

                                var lineText = cells.join(" | ");
                                // 过滤表头行
                                if (cells[0] && cells[0] !== "Agency" && cells[0] !== "API") {
                                    var tag = " [OK/正常]";
                                    if (rowErr) {
                                        result.errCount++;
                                        tag = " [ERROR/Tier 1 状态异常阻断]";
                                        result.errList.push(lineText);
                                    }

                                    result.rows.push(lineText + tag);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p14_data.get("category", "RCM")
            rows = p14_data.get("rows", [])
            err_count = p14_data.get("errCount", 0)
            err_list = p14_data.get("errList", [])

            self.log_data_extracted(f"成功抓取 RPT CRS ({cat_name}) 数据 | 监控节点: {len(rows)} 项 (异常 {err_count} 项)")
            self.log_check_method("全量校验 RPT CRS 所有 Agency/API 节点在各个日期的区间同步状态 (非 error 且无红字/Tier 1 强阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【RPT CRS 全量巡检数据明细 ({cat_name})】:"]

            if rows:
                summary_lines.append(f"--- [1. RPT CRS 监控板块 (共 {len(rows)} 个区间节点)] ---")
                summary_lines.extend([f"   * {r}" for r in rows])

            self.log_data_summary(summary_lines)

            # [步骤 5] Tier 1 报错阻断判定
            # 如果存在任意 1 项区间状态异常，阻断 Checkpoint
            if err_count > 0:
                self.log_check_result(False, f"RPT CRS 巡检发现 Tier 1 致命异常: 存在 {err_count} 项区间节点状态异常 ({', '.join(err_list)})，强阻断 Checkpoint！")
                return False
            else:
                self.log_check_result(True, "RPT CRS 全部区间节点同步状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT CRS 检查出现异常: {e}")
            return False
