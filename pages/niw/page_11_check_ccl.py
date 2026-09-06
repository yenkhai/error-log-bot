"""
================================================================================
第11站 Check CCL 关卡检查器 (pages/niw/page_11_check_ccl.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 监控的两大核心表格 (与用户截图红框完全对齐):
   - 左侧表格 (Check NIW Semi Cash CCL): 包含 20 家 Satellite 公司 (NO, Company, Type, Error, Last Cache)
   - 右侧表格 (Check Credit CCL): 包含 11 家 Credit CCL 公司 (NO, Company, Error)

2. 为什么使用 cleanNumber 清理文本？
   - 某些单元格里的数字可能被包裹在 HTML 标签中（如 `<a>0</a>` 或 `<span> 0 </span>`）。
   - 直接读取 innerText 可能会拿到带空格或换行符的字符串（如 "  0 \n"）。
   - 通过正则表达式 `txt.replace(/[^0-9]/g, "")` 可以强行把非数字字符剥离掉，确保拿到纯净的数字字符串 "0"。

3. 校验与阻断判定标准:
   - 左右任意一家公司的 Error 纯数字**必须大于 0**，或者单元格的背景/文字呈红色，才判定为异常。
   - 只要有任意 1 项异常 $\rightarrow$ 归类为 **Tier 1 致命报错阻断 Checkpoint**！
   - 只有左右全部 31 家公司的 Error 均为 0 时 $\rightarrow$ 通关并自动点击 Checkpoint。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class CheckCCLChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i13text (对应 NIW 区域的 Check CCL 选项)
        self.log_station_header("第11站 Check CCL", menu_id="apy_b0i13text")
        try:
            # [步骤 2] 导航切入 Check CCL 页面，缓冲等待 3.5 秒让左右两大表格完整渲染
            self.navigate_to_menu("Check CCL", menu_id="apy_b0i13text", section="NIW")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 3] JavaScript 脚本抓取左右两大 CCL 板块
            p11_data = self.driver.execute_script("""
                var result = {
                    leftCategory: "RCM",
                    leftRows: [],
                    leftErrCount: 0,
                    rightRows: [],
                    rightErrCount: 0
                };

                // 获取下拉框当前选择的分区 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.leftCategory = sel.options[sel.selectedIndex].text;
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

                // 字符串数字清洗器: 剥离所有空格、换行符和非数字字符
                function cleanNumber(txt) {
                    if (!txt) return "0";
                    var num = txt.replace(/[^0-9]/g, "");
                    return num === "" ? "0" : num;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 3.1 抓取左侧表格: Check NIW Semi Cash CCL (表头包含 NO, Company, Type, Error)
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Type") !== -1 && txt.indexOf("Error") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 4) {
                                var no = tds[0].innerText.trim();
                                var com = tds[1].innerText.trim();
                                var type = tds[2].innerText.trim();
                                var rawErrStr = tds[3].innerText.trim();
                                var errStr = cleanNumber(rawErrStr); // 清洗为干净的数字字符串
                                var bg = window.getComputedStyle(tds[3]).backgroundColor;
                                var fg = window.getComputedStyle(tds[3]).color;

                                // 过滤掉表头，只提取真实的公司数据行
                                if (no && no !== "NO" && com && com !== "Company") {
                                    var errVal = parseInt(errStr) || 0;
                                    var hasRed = isRed(bg) || isRed(fg);
                                    var isErr = errVal > 0 || hasRed; // Error > 0 或呈红色

                                    if (isErr) result.leftErrCount++;

                                    var tag = isErr ? " [ERROR/Tier 1 Error异常]" : " [OK/正常]";
                                    result.leftRows.push(com + " (" + type + "): Error = " + errStr + tag);
                                }
                            }
                        });
                    }

                    // 3.2 抓取右侧表格: Check Credit CCL (表头包含 NO, Company, Error，但不含 Type)
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Error") !== -1 && txt.indexOf("Type") === -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var no = tds[0].innerText.trim();
                                var com = tds[1].innerText.trim();
                                var rawErrStr = tds[2].innerText.trim();
                                var errStr = cleanNumber(rawErrStr);
                                var bg = window.getComputedStyle(tds[2]).backgroundColor;
                                var fg = window.getComputedStyle(tds[2]).color;

                                if (no && no !== "NO" && com && com !== "Company") {
                                    var errVal = parseInt(errStr) || 0;
                                    var hasRed = isRed(bg) || isRed(fg);
                                    var isErr = errVal > 0 || hasRed;

                                    if (isErr) result.rightErrCount++;

                                    var tag = isErr ? " [ERROR/Tier 1 Error异常]" : " [OK/正常]";
                                    result.rightRows.push(com + ": Error = " + errStr + tag);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p11_data.get("leftCategory", "RCM")
            left_rows = p11_data.get("leftRows", [])
            left_err_count = p11_data.get("leftErrCount", 0)
            right_rows = p11_data.get("rightRows", [])
            right_err_count = p11_data.get("rightErrCount", 0)

            self.log_data_extracted(f"成功抓取 Check CCL ({cat_name}) 数据 | 左侧 NIW Semi Cash: {len(left_rows)} 个节点 (异常 {left_err_count} 项) | 右侧 Credit CCL: {len(right_rows)} 个节点 (异常 {right_err_count} 项)")
            self.log_check_method("全量校验左侧 Check NIW Semi Cash CCL 与右侧 Check Credit CCL 节点的 Error 统计值 (需均为 0 且无红字)")

            # [步骤 4] 无条件全量打印巡检摘要
            summary_lines = [f"【Check CCL 全量巡检数据明细 ({cat_name})】:"]

            if left_rows:
                summary_lines.append(f"--- [1. 左侧 Check NIW Semi Cash CCL 板块 (共 {len(left_rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in left_rows])

            if right_rows:
                summary_lines.append(f"--- [2. 右侧 Check Credit CCL 板块 (共 {len(right_rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in right_rows])

            self.log_data_summary(summary_lines)

            # [步骤 5] Tier 1 报错阻断判定
            has_tier1_err = False
            err_reasons = []

            if left_err_count > 0:
                has_tier1_err = True
                err_reasons.append(f"左侧 NIW Semi Cash CCL 存在 {left_err_count} 项 Error 非 0 异常")

            if right_err_count > 0:
                has_tier1_err = True
                err_reasons.append(f"右侧 Credit CCL 存在 {right_err_count} 项 Error 非 0 异常")

            # 如果存在任意 Tier 1 错误，阻断 Checkpoint
            if has_tier1_err:
                self.log_check_result(False, f"Check CCL 巡检发现 Tier 1 致命异常: {'; '.join(err_reasons)}，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_11",
                    title="Check CCL",
                    status=False,
                    headers=["Left Semi Cash", "Right Credit CCL"],
                    rows=[[
                        CheckpointStore.make_cell(left_rows[i] if i < len(left_rows) else ""),
                        CheckpointStore.make_cell(right_rows[i] if i < len(right_rows) else "")
                    ] for i in range(max(len(left_rows), len(right_rows)))],
                    summary=f"Left err: {left_err_count}, Right err: {right_err_count}"
                )
                return False
            else:
                self.log_check_result(True, "Check CCL 左右两大 CCL 板块全部公司节点 Error 均为 0，状态完全正常！")

            # [步骤 6] 状态完全合格，解封并自动点击 Checkpoint
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_11",
                title="Check CCL",
                status=True,
                headers=["Left Semi Cash", "Right Credit CCL"],
                rows=[[
                    CheckpointStore.make_cell(left_rows[i] if i < len(left_rows) else ""),
                    CheckpointStore.make_cell(right_rows[i] if i < len(right_rows) else "")
                ] for i in range(max(len(left_rows), len(right_rows)))],
                summary="All CCL ok"
            )
            return True

        except Exception as e:
            self.log_check_result(False, f"Check CCL 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_11",
                title="Check CCL",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception occurred"
            )
            return False
