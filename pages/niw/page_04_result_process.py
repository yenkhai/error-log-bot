"""
================================================================================
第4站 Result Process 关卡检查器 (pages/niw/page_04_result_process.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 监控 5 大表格:
   - Event Score Process
   - Syn Event
   - Result Action
   - Promotion Action
   - Satellite Score Missing
2. 判定标准:
   - 单元格文字为 'success' 且非红底/红字判定为 [OK/正常绿底]
   - 单元格文字非 success (如 fail/missing/error) 或颜色为 RGB 真实红底判定为 [ERROR/异常阻断]
   - 解决误报: 采用 RGB 三原色解析 (R>=170 & G<=110 & B<=110)，精准过滤掉白色(255,255,255)与透明色造成的伪红字误报。
3. 全表加载完成后再判定；异常公司单独重载最多两次，不重新 Search。完整数据保存在 Log Viewer。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class ResultProcessChecker(BaseChecker):
    def _extract_data(self):
        return self.driver.execute_script(r"""

                var result = {
                    dates: [],                  // 动态抓取到的表头两个日期，如 ["15/09/2026", "16/09/2026"]
                    eventScoreRows: [],         // 1. Event Score Process 节点明细列表
                    synEventRows: [],           // 2. Syn Event 节点明细列表
                    resultActionRows: [],       // 3. Result Action 节点明细列表
                    promotionActionRows: [],    // 4. Promotion Action 节点明细列表
                    missingRows: [],            // 5. Satellite Score Missing 检查节点列表

                    eventScoreDetails: [],
                    synEventDetails: [],
                    resultActionDetails: [],
                    promotionActionDetails: [],
                    missingDetails: [],
                    rawRows: [],
                    errorCount: 0
                };

                // 【辅助函数 1】: 核心 RGB 真实的红底/红字判定逻辑 (R >= 170 且 G <= 110 且 B <= 110)
                function isRed(colorStr) {
                    if (!colorStr) return false;
                    var m = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r >= 170 && g <= 110 && b <= 110);
                    }
                    return false;
                }

                // 【辅助函数 2】: 校验单元格是否属于 success/正常
                function checkSuccessCell(tdEl) {
                    if (!tdEl) return false;
                    var txt = tdEl.innerText ? tdEl.innerText.trim().toLowerCase() : "";
                    var bg = window.getComputedStyle(tdEl).backgroundColor;
                    var hasRed = isRed(bg) || isRed(window.getComputedStyle(tdEl).color); // 仅检查背景是否为红底
                    var isSuccessText = (txt === "success");

                    if (!isSuccessText || hasRed || txt.indexOf("error") !== -1 || txt.indexOf("fail") !== -1) {
                        return true; // 代表有问题 (isError = true)
                    }
                    return false; // 代表正常
                }

                // 【辅助函数 3】: 从表格精准提取两个动态日期 (如 "15/09/2026", "16/09/2026")
                function extractDates(tableEl) {
                    var ds = [];
                    // 1. 优先从 thead 的第 2 行提取 (网页标准两行表头结构)
                    var theadThs = tableEl.querySelectorAll("thead tr:nth-child(2) th");
                    if (theadThs.length >= 2) {
                        for (var i = 0; i < theadThs.length; i++) {
                            var tVal = theadThs[i].innerText.trim();
                            if (tVal.indexOf("/") !== -1) ds.push(tVal);
                        }
                    }
                    // 2. 备选方案：遍历前 3 行 tr，查找包含 "/" 且格式类似 dd/mm/yyyy 的单元格
                    if (ds.length < 2) {
                        var trs = tableEl.querySelectorAll("tr");
                        for (var r = 0; r < Math.min(trs.length, 3); r++) {
                            var cells = trs[r].querySelectorAll("th, td");
                            var rowDates = [];
                            for (var c = 0; c < cells.length; c++) {
                                var cText = cells[c].innerText.trim();
                                if (cText.indexOf("/") !== -1 && cText.length >= 8 && cText.length <= 12) {
                                    rowDates.push(cText);
                                }
                            }
                            if (rowDates.length >= 2) {
                                ds = [rowDates[0], rowDates[1]];
                                break;
                            }
                        }
                    }
                    return ds;
                }

                // 【辅助函数 4】: 通用独立板块表格解析
                function parseSectionTable(t, sectionName, targetRows, targetDetails) {
                    var ds = extractDates(t);
                    if (ds.length >= 2 && result.dates.length < 2) {
                        result.dates = ds;
                    }

                    var rows = t.querySelectorAll("tr");
                    for (var r = 0; r < rows.length; r++) {
                        if (rows[r].closest("table") !== t) continue;
                        var tds = Array.from(rows[r].children).filter(c => /^(TD|TH)$/.test(c.tagName));
                        if (tds.length >= 3) {
                            var sat = tds[0].innerText.trim();
                            var d1 = tds[1].innerText.trim();
                            var d2 = tds[2].innerText.trim();
                            // 排除表头行（Satellite、板块名、含有日期的行）
                            if (sat && sat !== "Satellite" && sat.indexOf(sectionName) === -1 && d1.indexOf("/") === -1) {
                                var isErr1 = checkSuccessCell(tds[1]);
                                var isErr2 = checkSuccessCell(tds[2]);
                                var isErr = (isErr1 || isErr2);

                                if (isErr) result.errorCount++;
                                var tag = isErr ? " [ERROR]" : " [OK]";
                                targetDetails.push(sat + " -> D1: " + d1 + ", D2: " + d2 + tag);
                                var item = {
                                    section: sectionName,
                                    satellite: sat,
                                    d1: d1,
                                    d2: d2,
                                    status: isErr ? "ERROR" : "OK",
                                    d1_error: isErr1,
                                    d2_error: isErr2,
                                    is_error: isErr
                                };
                                targetRows.push(item);
                                result.rawRows.push(item);
                            }
                        }
                    }
                }

                var tables = document.querySelectorAll("table");

                tables.forEach(function(t) {
                    // 过滤掉日历控件表格 ui-datepicker
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // ── 板块 1. Event Score Process ──
                    if (txt.indexOf("Event Score Process") !== -1) {
                        parseSectionTable(t, "Event Score Process", result.eventScoreRows, result.eventScoreDetails);
                    }
                    // ── 板块 2. Syn Event ──
                    else if (txt.indexOf("Syn Event") !== -1) {
                        parseSectionTable(t, "Syn Event", result.synEventRows, result.synEventDetails);
                    }
                    // ── 板块 3. Result Action ──
                    else if (txt.indexOf("Result Action") !== -1) {
                        parseSectionTable(t, "Result Action", result.resultActionRows, result.resultActionDetails);
                    }
                    // ── 板块 4. Promotion Action ──
                    else if (txt.indexOf("Promotion Action") !== -1) {
                        parseSectionTable(t, "Promotion Action", result.promotionActionRows, result.promotionActionDetails);
                    }
                    // ── 板块 5. Satellite Score Missing ──
                    else if (txt.indexOf("Satellite Score Missing") !== -1) {
                        var ds = extractDates(t);
                        if (ds.length >= 2 && result.dates.length < 2) {
                            result.dates = ds;
                        }
                        var rows = t.querySelectorAll("tr");
                        for (var r = 0; r < rows.length; r++) {
                            if (rows[r].closest("table") !== t) continue;
                        var tds = Array.from(rows[r].children).filter(c => /^(TD|TH)$/.test(c.tagName));
                            if (tds.length >= 2) {
                                var d1 = tds[0].innerText.trim();
                                var d2 = tds[1].innerText.trim();
                                if (d1 && d1 !== "Satellite Score Missing" && d1.indexOf("/") === -1) {
                                    var isErr1 = checkSuccessCell(tds[0]);
                                    var isErr2 = checkSuccessCell(tds[1]);
                                    var isErr = (isErr1 || isErr2);

                                    if (isErr) result.errorCount++;
                                    var tag = isErr ? " [ERROR]" : " [OK]";
                                    result.missingDetails.push("Score Missing Check -> D1: " + d1 + ", D2: " + d2 + tag);
                                    var item = {
                                        section: "Satellite Score Missing",
                                        satellite: "Missing Check",
                                        d1: d1,
                                        d2: d2,
                                        status: isErr ? "ERROR" : "OK",
                                        d1_error: isErr1,
                                    d2_error: isErr2,
                                    is_error: isErr
                                    };
                                    result.missingRows.push(item);
                                    result.rawRows.push(item);
                                }
                            }
                        }
                    }
                });

                return result;

        """)

    def _wait_for_all_data(self, timeout=90):
        import re
        import time
        from selenium.webdriver.support.ui import WebDriverWait
        previous = None
        stable_since = None
        groups = ('eventScoreRows', 'synEventRows', 'resultActionRows', 'promotionActionRows', 'missingRows')

        def ready(driver):
            nonlocal previous, stable_since
            data = self._extract_data()
            idle = driver.execute_script("return document.readyState === 'complete' && (typeof jQuery === 'undefined' || jQuery.active === 0);")
            rows = data.get('rawRows', [])
            loaded = all(data.get(key) for key in groups) and all(
                str(row.get(key, '')).strip() and not re.search(r'loading|please wait|加载中', str(row[key]), re.I)
                for row in rows for key in ('d1', 'd2')
            )
            if not idle or not rows or not loaded:
                previous, stable_since = None, None
                return False
            signature = repr((data.get('dates'), rows))
            now = time.monotonic()
            if previous != signature or stable_since is None:
                previous, stable_since = signature, now
                return False
            return data if now - stable_since >= 1.0 else False

        return WebDriverWait(self.driver, timeout, poll_frequency=0.5).until(
            ready, message='Result Process: all five sections must finish loading before inspection'
        )

    def _click_company(self, section, company):
        return bool(self.driver.execute_script(r"""
            var section = arguments[0], company = arguments[1];
            for (var table of document.querySelectorAll('table')) {
                if (!table.innerText.includes(section)) continue;
                for (var row of table.querySelectorAll('tr')) {
                    if (row.closest('table') !== table) continue;
                    var cell = row.children[0];
                    if (!cell || cell.innerText.trim() !== company) continue;
                    var target = cell.matches('a,[onclick],button') ? cell : cell.querySelector('a,[onclick],button');
                    if (!target) continue;
                    target.click();
                    return true;
                }
            }
            return false;
        """, section, company))

    def check(self) -> bool:
        # 1. 记录当前关卡页头日志 (Menu ID: apy_b0i5text)
        self.log_station_header("第4站 Result Process", menu_id="apy_b0i5text")
        try:
            # 2. 自动化导航切入 Result Process 专属菜单页面
            self.navigate_to_menu("Result Process", menu_id="apy_b0i5text", section="NIW")

            # Wait for every section before deciding which companies need a reload.
            p4_data = self._wait_for_all_data()
            attempts = {}
            while True:
                candidates = [row for row in p4_data.get("rawRows", [])
                              if row.get("is_error") and row.get("satellite") != "Missing Check"
                              and attempts.get(row.get("satellite"), 0) < 2]
                if not candidates:
                    break
                row = candidates[0]
                company, section = row["satellite"], row["section"]
                attempts[company] = attempts.get(company, 0) + 1
                self.log(f"[RELOAD] {section} / {company} 重载 ({attempts[company]}/2)")
                if not self._click_company(section, company):
                    self.log(f"[WARN] {section} / {company} 找不到可点击的公司链接，保留错误。")
                    attempts[company] = 2
                    continue
                p4_data = self._wait_for_all_data()

            # 5. 在 Python 侧解构 JS 返回的数据字段
            event_details = p4_data.get("eventScoreDetails", [])
            syn_details = p4_data.get("synEventDetails", [])
            result_details = p4_data.get("resultActionDetails", [])
            promo_details = p4_data.get("promotionActionDetails", [])
            missing_details = p4_data.get("missingDetails", [])
            raw_rows = p4_data.get("rawRows", [])

            event_rows = p4_data.get("eventScoreRows", [])
            syn_rows = p4_data.get("synEventRows", [])
            result_rows = p4_data.get("resultActionRows", [])
            promo_rows = p4_data.get("promotionActionRows", [])
            missing_rows = p4_data.get("missingRows", [])

            # 动态表头日期：从网页中提取实际抓取到的两个日期 (如 "15/09/2026", "16/09/2026")
            dates = p4_data.get("dates", [])
            date1 = dates[0] if len(dates) >= 1 else "Date 1"
            date2 = dates[1] if len(dates) >= 2 else "Date 2"

            error_count = p4_data.get("errorCount", 0)
            total_items = len(raw_rows)

            self.log_data_extracted(f"成功抓取 Result Process 全局表格共 {total_items} 项节点数据 (异常发现数: {error_count})，动态巡检日期: [{date1} ~ {date2}]")
            self.log_check_method(f"校验 4 大监控表格 (日期: {date1}, {date2}) 所有节点单元格是否为 success 以及 RGB 正常绿底")

            # 6. 无论是否有 Error，全量明细无条件透明化打印在 Log 控制台中
            all_summary = [f"【Result Process 全量巡检数据明细 (日期: {date1} ~ {date2})】:"]

            if event_details:
                all_summary.append("--- [1. Event Score Process 板块] ---")
                all_summary.extend([f"   * {line}" for line in event_details])

            if syn_details:
                all_summary.append("--- [2. Syn Event 板块] ---")
                all_summary.extend([f"   * {line}" for line in syn_details])

            if result_details:
                all_summary.append("--- [3. Result Action 板块] ---")
                all_summary.extend([f"   * {line}" for line in result_details])

            if promo_details:
                all_summary.append("--- [4. Promotion Action 板块] ---")
                all_summary.extend([f"   * {line}" for line in promo_details])

            if missing_details:
                all_summary.append("--- [5. Satellite Score Missing 板块] ---")
                all_summary.extend([f"   * {line}" for line in missing_details])

            self.log_data_summary(all_summary)

            # 7. 构筑 CheckpointStore 4 个独立子表格数据结构 (动态日期表头)
            def build_subtable(title: str, items: list) -> dict:
                headers = ["Satellite", date1, date2, "Status"]
                rows = [
                    [
                        CheckpointStore.make_cell(r["satellite"]),
                        CheckpointStore.make_cell(r["d1"], bg="red" if r.get("d1_error", r.get("is_error")) else "green"),
                        CheckpointStore.make_cell(r["d2"], bg="red" if r.get("d2_error", r.get("is_error")) else "green"),
                        CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                    ]
                    for r in items
                ]
                return {
                    "title": title,
                    "header_bg": "#C8D7A6",
                    "headers": headers,
                    "derived_status_columns": [3],
                    "rows": rows
                }

            subtables = []
            if event_rows:
                subtables.append(build_subtable("Event Score Process", event_rows))
            if syn_rows:
                subtables.append(build_subtable("Syn Event", syn_rows))
            if result_rows:
                subtables.append(build_subtable("Result Action", result_rows))
            if promo_rows:
                subtables.append(build_subtable("Promotion Action", promo_rows))

            if missing_rows:
                subtables.append({
                    "title": "Satellite Score Missing",
                    "header_bg": "#C8D7A6",
                    "headers": [date1, date2, "Status"],
                    "derived_status_columns": [2],
                    "rows": [
                        [
                            CheckpointStore.make_cell(r["d1"], bg="red" if r.get("d1_error", r.get("is_error")) else "green"),
                            CheckpointStore.make_cell(r["d2"], bg="red" if r.get("d2_error", r.get("is_error")) else "green"),
                            CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                        ]
                        for r in missing_rows
                    ]
                })

            # 8. Checkpoint 巡检结论判定
            if error_count > 0:
                # 存在异常非 success 项：阻断 Checkpoint
                self.log(f"[Error] Result Process 检测到 {error_count} 项非 success 或红底异常，阻断 Checkpoint！")
                self.log_check_result(False, f"Result Process 存在 {error_count} 项状态异常，阻断 Checkpoint。")
                CheckpointStore.save(
                    page_key="niw_04",
                    title="Result Process",
                    status=False,
                    tables=subtables,
                    summary=f"{error_count} 项异常 (共 {total_items} 项, {date1} ~ {date2})"
                )
                return False
            else:
                # 状态全部正常通过
                self.log_check_result(True, f"Result Process 4 大表格状态全部为 success 且绿底正常 ({date1} ~ {date2})，巡检通过！")

            # 9. 巡检通过后解封并点击 Checkpoint 按钮打勾提交
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            CheckpointStore.save(
                page_key="niw_04",
                title="Result Process",
                status=True,
                tables=subtables,
                summary=f"全部 {total_items} 项节点状态全部绿底 success ({date1} ~ {date2})"
            )
            return True

        except Exception as e:
            # 捕获未知运行异常
            return self.handle_exception("niw_04", "Result Process", e)
