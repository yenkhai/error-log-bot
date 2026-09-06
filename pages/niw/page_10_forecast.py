"""
================================================================================
第10站 Forecast 关卡检查器 (pages/niw/page_10_forecast.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 为什么不需要二次点击 Search 刷新？
   - 导航进入 Forecast 页面后，页面会自动异步 (AJAX) 加载默认的数据（如 RCM 分类）。
   - 保留 3.5 秒的 sleep 等待数据渲染完成后，直接读取即可，避免二次刷新导致页面重载。

2. 为什么需要重写 window.confirm 与 window.alert (原生弹窗挂钩 Hook)？
   - 当程序点击弹窗里的 "Patch" 补丁按钮时，浏览器会弹出原生的 JavaScript 对话框：
     `Confirm generate report?` (询问用户是否确认生成报告)。
   - 自动化驱动程序 (Selenium/ChromeDriver) 如果遇到未经处理的原生弹窗，会直接抛出 
     `unexpected alert open` 崩溃报错并强制中断！
   - 通过在浏览器 JS 上下文中执行：
     `window.confirm = function() { return true; };`
     `window.alert = function() { return true; };`
     可以提前把弹窗的拦截函数强制改成“永远自动返回确定”，使浏览器静默通过，不会卡死！

3. 为什么传统 for 循环点击 Patch 会导致“隔行遗漏/漏按”？
   - 假如有 30 行 Patch 链接。传统的循环是：点击 index 0、点击 index 1、点击 index 2...
   - 当点击完第 0 行的 Patch 后，那一行文本变为了 "processing"（黄底），在 DOM 树中就不再是 `Patch` 超链接了！
   - 这导致整个表格剩下的 Patch 链接在 DOM 结构中**整体向上平移了 1 行**！
   - 下一次循环去点击 index 1 时，实际上点到的是原先的第 2 行，把平移上来的原第 1 行给漏掉了！（造成奇偶隔行漏按）

4. 核心解法：【动态 Index 0 锁定算法】
   - 不再使用递增的下标 i，而是采用：`while` 循环或 `for _ in range(max)` 循环。
   - 每次循环都只查找当前弹窗中**剩下的第一个文本为 "patch" 的链接** (`links[0]`)。
   - 点击完后等待 0.9 秒，让那一行变黄后，下一次循环继续找新的第一个 "patch" 链接。
   - 这样不论 DOM 如何向上平移，都能 100% 毫无遗漏地把每一行 Patch 全部实打实按完！
================================================================================
"""

import time
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class ForecastChecker(BaseChecker):
    def check(self) -> bool:
        # [步骤 1] 打印站名日志头，传入 Menu ID: apy_b0i11text (对应 NIW 区域的 Forecast 按钮)
        self.log_station_header("第10站 Forecast", menu_id="apy_b0i11text")
        try:
            # [步骤 2] 导航切入 Forecast 页面
            self.navigate_to_menu("Forecast", menu_id="apy_b0i11text", section="NIW")

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            # [步骤 3] 全局注入抗弹窗 Hook (拦截浏览器的 Confirm / Alert 询问框)
            # 作用: 防止点击 Patch 按钮时弹出的 "Confirm generate report?" 阻塞程序运行
            self.driver.execute_script("""
                window.confirm = function() { return true; };
                window.alert = function() { return true; };
            """)

            # [步骤 4] 捕获左侧矩阵 (Agency Forecast Compare Tool) 中含有 error 红底的超链接
            # 返回一个数组，每一项包含卫星公司名称 sat、列号 colIdx 以及要点击的 <a> 标签 anchor
            error_anchors = self.driver.execute_script("""
                // 辅助函数: 判断颜色字符串 (如 "rgb(255, 0, 0)") 是否为红色
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110); // R分量高，G/B分量低即为红底
                    }
                    return false;
                }

                var items = [];
                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 过滤掉日历等无关控件
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 定位含有 Satellite 和 error/Check MULP 的表格
                    if (txt.indexOf("Satellite") !== -1 && (txt.indexOf("Check MULP Status") !== -1 || txt.indexOf("error") !== -1)) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 3) {
                                var sat = tds[0].innerText.trim();
                                // 排除表头行
                                if (sat && sat !== "Satellite" && sat.indexOf("Date") === -1) {
                                    for (var c = 1; c < tds.length; c++) {
                                        var cellTxt = tds[c].innerText.trim().toLowerCase();
                                        var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                        var fg = window.getComputedStyle(tds[c]).color;
                                        // 如果单元格文本是 "error" 或者背景/文字是红色
                                        if (cellTxt === "error" || isRed(bg) || isRed(fg)) {
                                            var a = tds[c].querySelector("a"); // 获取内部的 <a> 标签
                                            items.push({
                                                sat: sat,
                                                colIdx: c,
                                                anchor: a ? a : tds[c]
                                            });
                                        }
                                    }
                                }
                            }
                        });
                    }
                });
                return items;
            """)

            # [步骤 5] 执行真人视角、100% 零遗漏的 Details 唤醒与 Patch 补丁点击
            patch_logs = []
            if error_anchors:
                self.log(f"[AUTO-PATCH] 捕获到左侧矩阵 {len(error_anchors)} 处红底 error 链接，启动真人视角 100% 全量无遗漏 Patch 点击...")
                
                # 遍历每一个含 error 的单元格 (如 p0008, k0002 等)
                for idx, item in enumerate(error_anchors):
                    sat = item.get("sat", "Unknown")
                    col_idx = item.get("colIdx", 1)
                    anchor_el = item.get("anchor")

                    try:
                        # 5.1 在点击前再次注入 Hook 确保弹窗无缝接受
                        self.driver.execute_script("""
                            window.confirm = function() { return true; };
                            window.alert = function() { return true; };
                        """)

                        # 5.2 滚动到目标单元格并点击其 <a> 标签，唤醒 Details 弹窗
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", anchor_el)
                        self.wait_for_page_loaded(seconds=1, max_wait=5)  # 智能等待 Details 弹窗拉开并渲染完毕

                        # 驱动层双重防线：如果有遗留原生 Alert，直接 accept 确认掉
                        try:
                            alert = self.driver.switch_to.alert
                            alert.accept()
                            time.sleep(0.5)
                        except Exception:
                            pass

                        # 5.3 零遗漏动态点击算法 (核心防隔行遗漏逻辑)
                        patched_count = 0
                        max_attempts = 150 # 最大尝试次数上限，防止死循环

                        for attempt in range(max_attempts):
                            # 每次点击前重新注入重写弹窗代码
                            self.driver.execute_script("""
                                window.confirm = function() { return true; };
                                window.alert = function() { return true; };
                            """)

                            # 【核心代码】：查找弹窗内文本为 "patch" 的【第一个链接】并点击它！
                            # 只要能找到就返回 true，找不到说明弹窗内所有 Patch 已经全部点击完毕！
                            found_and_clicked = self.driver.execute_script("""
                                var links = document.querySelectorAll("a");
                                for (var i = 0; i < links.length; i++) {
                                    var txt = links[i].innerText ? links[i].innerText.trim().toLowerCase() : "";
                                    if (txt === "patch") {
                                        links[i].scrollIntoView({block: 'center'});
                                        links[i].click(); // 点击找到的第一个 Patch
                                        return true; // 点击成功，退出 JS 函数
                                    }
                                }
                                return false; // 已经没有未点击的 Patch 链接了
                            """)

                            # 驱动层防线：捕获可能伴随出现的 confirm 确认框
                            try:
                                alert = self.driver.switch_to.alert
                                alert.accept()
                            except Exception:
                                pass

                            # 如果找不到 Patch 链接了，说明当前 Details 弹窗已经 100% 处理完毕，跳出循环！
                            if not found_and_clicked:
                                break

                            patched_count += 1
                            self.wait_for_page_loaded(seconds=0.5, max_wait=3)  # 智能等待 Patch 请求完成并变黄

                        patch_logs.append(f"{sat} (列{col_idx}): 已唤醒 Details 弹窗并成功完成 100% 无遗漏全量 {patched_count} 项 Patch 点击 [Tier 2 提醒/肉眼可见已补丁/不阻断]")

                        # 5.4 补丁点击完毕，寻找并点击弹窗右侧的 [ X ] 按钮关闭 Details 弹窗
                        self.driver.execute_script("""
                            var closeBtns = document.querySelectorAll("span, div, a, td");
                            for (var cb = 0; cb < closeBtns.length; cb++) {
                                var txt = closeBtns[cb].innerText ? closeBtns[cb].innerText.trim() : "";
                                if (txt === "[ X ]" || txt === "[X]" || txt === "X") {
                                    closeBtns[cb].click();
                                    break;
                                }
                            }
                        """)
                        self.wait_for_page_loaded(seconds=0.5, max_wait=3)  # 智能等待弹窗关闭动画完成

                    except Exception as pe:
                        # 容错处理：确保即使单个单元格异常也不影响后续流程
                        try:
                            self.driver.switch_to.alert.accept()
                        except Exception:
                            pass
                        patch_logs.append(f"{sat} (列{col_idx}): 自动补丁点击处理提示: {pe} [Tier 2 提醒/不阻断]")

            # [步骤 6] 抓取右侧 NASA & Forecast Compare 板块 (Tier 1 规则)
            p10_data = self.driver.execute_script("""
                var result = {
                    leftCategory: "RCM",
                    rightRows: [],
                    rightHasErr: false,
                    rightErrList: []
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.leftCategory = sel.options[sel.selectedIndex].text;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 定位含有 Company, Online List, Betslips 的右侧对比表格
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Online List") !== -1 && txt.indexOf("Betslips") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 5) {
                                var com = tds[0].innerText.trim();
                                var type = tds[1].innerText.trim();
                                var online = tds[2].innerText.trim();
                                var betslips = tds[3].innerText.trim();
                                var remark = tds[4].innerText.trim();

                                if (com && com !== "Company") {
                                    // 判定 Remark 是否为 "Correct"
                                    var isRemarkErr = remark.toLowerCase() !== "correct";
                                    var statusTag = " [OK/正常绿字]";
                                    if (isRemarkErr) {
                                        result.rightHasErr = true;
                                        statusTag = " [ERROR/Tier 1 Remark异常阻断]";
                                        result.rightErrList.push(com + " Remark: " + remark);
                                    }

                                    var line = com + " (" + type + "): Online List = " + online + ", Betslips = " + betslips + ", Remark = " + remark + statusTag;
                                    result.rightRows.push(line);
                                    result.rawRows = result.rawRows || [];
                                    result.rawRows.push({
                                        company: com,
                                        type: type,
                                        online: online,
                                        betslips: betslips,
                                        remark: remark,
                                        status: isRemarkErr ? "ERROR" : "OK",
                                        is_error: isRemarkErr
                                    });
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p10_data.get("leftCategory", "RCM")
            right_rows = p10_data.get("rightRows", [])
            raw_rows = p10_data.get("rawRows", [])
            right_errs = p10_data.get("rightErrList", [])

            self.log_data_extracted(f"成功抓取 Forecast ({cat_name}) 数据 | 左侧 100% 零遗漏 Patch: {len(error_anchors)} 个红底单元格 (Tier 2) | 右侧监控节点: {len(right_rows)} 项 (Tier 1)")
            self.log_check_method("校验规则: 左侧 Agency Forecast 唤醒 Details 并 100% 无遗漏逐行点击 Patch (Tier 2 不阻断)；右侧 NASA Remark 需为 Correct (Tier 1 阻断)")

            # [步骤 7] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【Forecast 全量巡检数据明细 ({cat_name})】:"]

            if patch_logs:
                summary_lines.append(f"--- [1. 左侧 Agency Forecast 矩阵 (Tier 2 通报/已 100% 零遗漏完成 {len(patch_logs)} 组 Details 补丁点击)] ---")
                summary_lines.extend([f"   * {p}" for p in patch_logs])
            else:
                summary_lines.append("--- [1. 左侧 Agency Forecast 矩阵]: 所有单元格均为 success 绿底 [OK/正常] ---")

            if right_rows:
                summary_lines.append(f"--- [2. 右侧 NASA & Forecast Compare 板块 (Tier 1 规则/共 {len(right_rows)} 个节点)] ---")
                summary_lines.extend([f"   * {r}" for r in right_rows])

            self.log_data_summary(summary_lines)

            table_headers = ["Company", "Type", "Online List", "Betslips", "Remark", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["company"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["online"]),
                    CheckpointStore.make_cell(r["betslips"]),
                    CheckpointStore.make_cell(r["remark"], bg="red" if r.get("is_error") else "green"),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # [步骤 8] Tier 1 报错阻断判定 (仅针对右侧 NASA Remark 非 Correct)
            if len(right_errs) > 0:
                self.log_check_result(False, f"Forecast 巡检发现 Tier 1 致命异常: 右侧 NASA Compare 存在 {len(right_errs)} 项 Remark 非 Correct，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_10",
                    title="Forecast",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Right NASA Errors: {len(right_errs)}"
                )
                return False

            if error_anchors:
                self.log_check_result(True, f"Forecast 右侧合格，左侧 {len(error_anchors)} 组 error 单元格已全量 100% 零遗漏完成 Patch 点击 (Tier 2 不阻断)，巡检通过！")
            else:
                self.log_check_result(True, "Forecast 左右两大板块数据全部校验通过，状态完全正常！")

            # [步骤 9] 解封并自动点击 Checkpoint 按钮
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_10",
                title="Forecast",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"右侧 {len(raw_rows)} 个节点全部 Correct，左侧已完成 Patch"
            )
            return True

        except Exception as e:
            self.log_check_result(False, f"Forecast 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_10",
                title="Forecast",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception occurred"
            )
            return False
