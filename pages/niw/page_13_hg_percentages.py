"""
================================================================================
第13站 HG Percentages 关卡检查器 (pages/niw/page_13_hg_percentages.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面功能与抓取目标:
   - 本页面监控 HG 占比及编辑器/投注同步状态。
   - 抓取字段: Company (公司代码如 s0010, k0002), Count (Editor) (编辑器计数), 
     Editor (编辑器状态), Count (Betting) (投注计数), Betting (投注状态)。

2. 校验与阻断标准 (Tier 1 强阻断):
   - 核心考核指标为 `Editor` 与 `Betting` 两个状态列。
   - 要求两个状态均必须显示为绿字 `"Correct"`。
   - 如果任何一个状态不等于 "Correct"，判定为 **Tier 1 致命报错强阻断 Checkpoint**！
================================================================================
"""

import time
from core.base_checker import BaseChecker

class HGPercentagesChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i15text (对应 NIW 区域的 HG Percentages 选项)
        self.log_station_header("第13站 HG Percentages", menu_id="apy_b0i15text")
        try:
            # [步骤 2] 导航切入 HG Percentages 页面，缓冲等待 3.5 秒让数据自动渲染
            self.navigate_to_menu("HG Percentages", menu_id="apy_b0i15text", section="NIW")


            self.wait_for_page_loaded(seconds=1.5, max_wait=35)
            # [步骤 3] JavaScript 脚本精准抓取 HG Percentages 表格数据
            p13_data = self.driver.execute_script("""
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

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 通过表头关键字 Company, Editor, Betting 锁定目标表格
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Editor") !== -1 && txt.indexOf("Betting") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 5) {
                                var com = tds[0].innerText.trim();
                                var cEditor = tds[1].innerText.trim();
                                var editor = tds[2].innerText.trim();
                                var cBetting = tds[3].innerText.trim();
                                var betting = tds[4].innerText.trim();

                                // 过滤表头行
                                if (com && com !== "Company" && com.indexOf("Count") === -1) {
                                    // 只要 Editor 或 Betting 有任何一个不是 Correct 即为报错
                                    var isErr = editor.toLowerCase() !== "correct" || betting.toLowerCase() !== "correct";
                                    var tag = " [OK/正常绿字]";
                                    if (isErr) {
                                        result.errCount++;
                                        tag = " [ERROR/Tier 1 异常阻断]";
                                        result.errList.push(com + " Editor: " + editor + ", Betting: " + betting);
                                    }

                                    var line = com + ": Count(Editor) = " + cEditor + ", Editor = " + editor + ", Count(Betting) = " + cBetting + ", Betting = " + betting + tag;
                                    result.rows.push(line);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p13_data.get("category", "RCM")
            rows = p13_data.get("rows", [])
            err_count = p13_data.get("errCount", 0)
            err_list = p13_data.get("errList", [])

            self.log_data_extracted(f"成功抓取 HG Percentages ({cat_name}) 数据 | 监控节点: {len(rows)} 项 (异常 {err_count} 项)")
            self.log_check_method("全量校验 HG Percentages 所有公司节点的 Editor 与 Betting 必须为 Correct (Tier 1 强阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【HG Percentages 全量巡检数据明细 ({cat_name})】:"]

            if rows:
                summary_lines.append(f"--- [1. HG Percentages 监控板块 (共 {len(rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in rows])

            self.log_data_summary(summary_lines)

            # [步骤 5] Tier 1 报错阻断判定
            # 只要存在 Editor 或 Betting 非 Correct，阻断 Checkpoint
            if err_count > 0:
                self.log_check_result(False, f"HG Percentages 巡检发现 Tier 1 致命异常: 存在 {err_count} 项节点状态非 Correct ({', '.join(err_list)})，强阻断 Checkpoint！")
                return False
            else:
                self.log_check_result(True, "HG Percentages 全部公司节点 Editor 与 Betting 均为 Correct，状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"HG Percentages 检查出现异常: {e}")
            return False
