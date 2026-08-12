"""
================================================================================
第5站 Calculate Betslips 关卡检查器 (pages/niw/page_05_calculate_betslips.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 自动循环遍历所有下拉公司选项 (全量扫描 Dropdown 中的 32 家 RCM 与 LRCM 公司):
   - 绝不漏过任何一家子公司/分支公司！
2. 视觉渲染与 AJAX 网络响应保障 (Visual Sleep & DOM Re-paint):
   - 在 Python 循环中加入显式 `time.sleep(0.8)` 缓冲让 Chrome 浏览器主线程让出控制权，确保人眼能够清晰地看到每一家公司下拉框切换与数据渲染过程，绝无“未加载完就跳过”的假装画面！
3. 严密过滤日历控件 (ui-datepicker-calendar 隔离防护):
   - 自动排除 Datepicker 弹出的日历表格，避免把日历日期 (26, 27, 28...) 误判为玩法和 Uncalculate 报错！
4. 判定标准 (Tier 1 致命阻断):
   - Uncalculate (未计算单数) > 0  --> 判定为 Tier 1 报错阻断！
   - Recalculate (重算状态) != OK (非 OK 或红底)  --> 判定为 Tier 1 报错阻断！
   - Cancel/Reject (废单数) 不阻断，仅做记录。
   - No Data (无数据) 为正常合格状态！
5. 【只打印有问题的公司与明细】:
   - 全量扫描完毕后，仅当发现有问题的公司时，精准打印该公司的全量异常 Bettype 玩法明细！
================================================================================
"""

import time
from selenium.webdriver.common.by import By
from core.base_checker import BaseChecker

class CalculateBetslipsChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第5站 Calculate Betslips", menu_id="apy_b0i6text")
        try:
            # 1. 导航切入 Calculate Betslips 菜单
            self.navigate_to_menu("Calculate Betslips", menu_id="apy_b0i6text", section="NIW", wait_seconds=3)

            # 2. 获取下拉框中所有的公司列表 (RCM 与 LRCM)
            companies = self.driver.execute_script("""
                var sel = document.getElementById("company") || document.querySelector("select[name='company']");
                if (!sel) return [];
                var list = [];
                for (var i = 0; i < sel.options.length; i++) {
                    var opt = sel.options[i];
                    if (opt.value && opt.value !== "") {
                        list.push({ index: i, value: opt.value, text: opt.text });
                    }
                }
                return list;
            """)

            if not companies:
                self.log_check_result(False, "Calculate Betslips 未能找到任何 Company 下拉选项！")
                return False

            self.log(f"[COMPANY DISCOVERY] 成功搜索到 {len(companies)} 家公司选项，启动全量循环扫描...")

            problem_companies_summary = []
            total_uncalc_all = 0
            total_recalc_err_all = 0
            has_any_tier1_error = False

            # 3. 自动循环遍历所有下拉公司选项逐一扫描
            for comp in companies:
                comp_idx = comp['index']
                comp_val = comp['value']
                comp_text = comp['text']

                # 3.1 切换公司并触发计算
                self.driver.execute_script("""
                    var sel = document.getElementById("company") || document.querySelector("select[name='company']");
                    if (sel) {
                        sel.selectedIndex = arguments[0];
                        sel.dispatchEvent(new Event('change'));
                    }
                    var btn = document.getElementById("btnCalculate") || document.querySelector("input[value='Calculate']");
                    if (btn) btn.click();
                    if (typeof callCalcuate === "function") callCalcuate(1);
                """, comp_idx)

                # 3.2 显式 Python visual sleep，确保 Chrome 完成 UI 视觉渲染重绘与 AJAX 响应
                time.sleep(10)

                # 3.3 提取当前公司的数据 (包含 ui-datepicker 日历表隔离防护)
                comp_data = self.driver.execute_script("""
                    var targetVal = arguments[0];
                    var targetText = arguments[1];
                    var result = {
                        companyName: targetText,
                        companyVal: targetVal,
                        problemDetails: [],
                        uncalculateTotal: 0,
                        recalculateErrTotal: 0,
                        hasTier1Error: false
                    };

                    var tables = document.querySelectorAll("table");

                    tables.forEach(function(t) {
                        // 核心隔离: 过滤 Datepicker 日历控件与嵌套表
                        if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null || t.querySelector("table") !== null) {
                            return;
                        }
                        var txt = t.innerText ? t.innerText.trim() : "";
                        if (txt.indexOf("Normal Bettype") === -1 && txt.indexOf("Bettype") === -1) {
                            return;
                        }

                        var currentSection = "Normal Bettype";
                        var rows = t.querySelectorAll("tr");

                        rows.forEach(function(r) {
                            var textAll = r.innerText.trim();
                            if (textAll.indexOf("Running Bettype") !== -1) {
                                currentSection = "Running Bettype";
                            }

                            var tds = r.querySelectorAll("td");
                            if (tds.length >= 8) {
                                var bettype = tds[0].innerText.trim();

                                // 排除表头与 No Data 行
                                if (bettype && bettype !== "Bettype" && bettype.indexOf("Bettype") === -1 && bettype.indexOf("Member") === -1 && bettype.indexOf("Total") === -1 && textAll.indexOf("No Data") === -1) {
                                    var cancel = tds[tds.length - 3] ? tds[tds.length - 3].innerText.trim() : "0";
                                    var uncalc = tds[tds.length - 2] ? tds[tds.length - 2].innerText.trim() : "0";
                                    var recalcTd = tds[tds.length - 1];
                                    var recalc = recalcTd ? recalcTd.innerText.trim() : "OK";
                                    var bg = recalcTd ? window.getComputedStyle(recalcTd).backgroundColor : "";

                                    var uCnt = parseInt(uncalc) || 0;
                                    var isUncalcErr = uCnt > 0;
                                    function isRed(colorStr) {
                                        if (!colorStr) return false;
                                        var m = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                                        if (m) {
                                            var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                                            return (r >= 170 && g <= 110 && b <= 110);
                                        }
                                        return false;
                                    }
                                    var isRecalcErr = recalc.toUpperCase() !== "OK" || isRed(bg);

                                    if (isUncalcErr) {
                                        result.uncalculateTotal += uCnt;
                                        result.hasTier1Error = true;
                                    }
                                    if (isRecalcErr) {
                                        result.recalculateErrTotal++;
                                        result.hasTier1Error = true;
                                    }

                                    if (isUncalcErr || isRecalcErr) {
                                        var detailLine = currentSection + " -> " + bettype + ": Cancel/Reject=" + cancel + ", Uncalculate=" + uncalc + ", Recalculate=" + recalc + " [ERROR/Tier 1 异常阻断]";
                                        result.problemDetails.push(detailLine);
                                    }
                                }
                            }
                        });
                    });

                    return result;
                """, comp_val, comp_text)

                if comp_data.get("hasTier1Error"):
                    has_any_tier1_error = True
                    u_sum = comp_data.get("uncalculateTotal", 0)
                    r_err_sum = comp_data.get("recalculateErrTotal", 0)
                    total_uncalc_all += u_sum
                    total_recalc_err_all += r_err_sum

                    comp_err_lines = [
                        f"【Calculate Betslips 异常公司: {comp_text}】:",
                        f"   * Tier 1 报错统计: Uncalculate 未计算总数 = {u_sum}, Recalculate 非OK数 = {r_err_sum}",
                        "   * 具体问题 Bettype 玩法明细如下:"
                    ]
                    comp_err_lines.extend([f"      -> {p}" for p in comp_data.get("problemDetails", [])])
                    problem_companies_summary.extend(comp_err_lines)

            # 4. 日志合成输出
            self.log_data_extracted(f"成功完成全部 {len(companies)} 家公司的全量巡检扫描！")
            self.log_check_method("全量公司遍历 + 显式视觉渲染等待 (0.8s) + Datepicker 日历表隔离 -> 校验 Uncalculate > 0 或 Recalculate != OK 为 Tier 1 报错阻断")

            if has_any_tier1_error:
                self.log_data_summary(problem_companies_summary)
                self.log_check_result(False, f"Calculate Betslips 巡检中发现异常公司，存在 Uncalculate 未计算或 Recalculate 异常，阻断 Checkpoint！")
                return False
            else:
                self.log_data_summary([f"Calculate Betslips 全部 {len(companies)} 家公司巡检完毕: 所有公司的 Uncalculate 均为 0 且 Recalculate 均为 OK 绿底！[全部正常]"])
                self.log_check_result(True, f"Calculate Betslips 全部 {len(companies)} 家公司巡检通过！")

            # 5. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Calculate Betslips 检查出现异常: {e}")
            return False
