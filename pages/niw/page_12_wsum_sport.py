"""
================================================================================
第12站 Wsum Sport 关卡检查器 (pages/niw/page_12_wsum_sport.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面功能与抓取目标:
   - 本页面监控的是体育注单与 Wsum 统计是否完全一致 (Wsum & Wager Winloss Compare)。
   - 抓取字段: Company (公司名称), Type (体育类型如 sport), Total Wsum (总Wsum), 
     Total Betslips (总注单数), Remark (备注判定), Last Refresh (最后刷新时间)。

2. 校验与阻断标准 (Tier 1 强阻断):
   - 核心考核指标为 `Remark` 字段。
   - 正常情况下，`Total Wsum` 应等于 `Total Betslips`，Remark 显示绿字 `"Correct"`。
   - 如果 Remark 文本不等于 "Correct" (例如显示 Error 或数据不匹配)，判定为 **Tier 1 致命报错强阻断 Checkpoint**！
================================================================================
"""

import time
from core.base_checker import BaseChecker

class WsumSportChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i14text (对应 NIW 区域的 Wsum Sport 选项)
        self.log_station_header("第12站 Wsum Sport", menu_id="apy_b0i14text")
        try:
            # [步骤 2] 导航切入 Wsum Sport 页面，缓冲等待 3.5 秒让数据自动渲染
            self.navigate_to_menu("Wsum Sport", menu_id="apy_b0i14text", section="NIW")

            self.wait_for_page_loaded(seconds=1.5, max_wait=35)
            # [步骤 3] JavaScript 脚本精准抓取 Wsum Sport 表格数据
            p12_data = self.driver.execute_script("""
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

                    // 通过表头关键字段 Company, Total Wsum, Total Betslips 锁定表格
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Total Wsum") !== -1 && txt.indexOf("Total Betslips") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 5) {
                                var com = tds[0].innerText.trim();
                                var type = tds[1].innerText.trim();
                                var wsum = tds[2].innerText.trim();
                                var betslips = tds[3].innerText.trim();
                                var remark = tds[4].innerText.trim();

                                // 过滤表头行
                                if (com && com !== "Company") {
                                    // 判断 Remark 是否非 Correct (不区分大小写)
                                    var isErr = remark.toLowerCase() !== "correct";
                                    var tag = " [OK/正常绿字]";
                                    if (isErr) {
                                        result.errCount++;
                                        tag = " [ERROR/Tier 1 Remark异常阻断]";
                                        result.errList.push(com + " Remark: " + remark);
                                    }

                                    var line = com + " (" + type + "): Total Wsum = " + wsum + ", Total Betslips = " + betslips + ", Remark = " + remark + tag;
                                    result.rows.push(line);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p12_data.get("category", "RCM")
            rows = p12_data.get("rows", [])
            err_count = p12_data.get("errCount", 0)
            err_list = p12_data.get("errList", [])

            self.log_data_extracted(f"成功抓取 Wsum Sport ({cat_name}) 数据 | 监控节点: {len(rows)} 项 (异常 {err_count} 项)")
            self.log_check_method("全量校验 Wsum Sport 所有公司节点的 Remark 必须为 Correct (Tier 1 强阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【Wsum Sport 全量巡检数据明细 ({cat_name})】:"]

            if rows:
                summary_lines.append(f"--- [1. Wsum Sport 监控板块 (共 {len(rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in rows])

            self.log_data_summary(summary_lines)

            # [步骤 5] Tier 1 报错阻断判定
            # 只要存在 1 项 Remark 非 Correct，强阻断 Checkpoint
            if err_count > 0:
                self.log_check_result(False, f"Wsum Sport 巡检发现 Tier 1 致命异常: 存在 {err_count} 项 Remark 非 Correct ({', '.join(err_list)})，强阻断 Checkpoint！")
                return False
            else:
                self.log_check_result(True, "Wsum Sport 全部公司节点 Remark 均为 Correct，状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Wsum Sport 检查出现异常: {e}")
            return False
