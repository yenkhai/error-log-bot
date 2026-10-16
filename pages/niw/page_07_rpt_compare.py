"""
================================================================================
第7站 RPT Compare 关卡检查器 (pages/niw/page_07_rpt_compare.py)
--------------------------------------------------------------------------------
全量日志与判定规则 (遵循用户最新业务规范):
1. 抓取与对齐网页上的全部 4 大核心监控区域:
   - 区域 1 (左侧状态栏): Rpt Complete (需为 Complete 绿底) 与 Reset Log (需为 0) [Tier 1 核心]；
   - 区域 2 (主对比大矩阵): 26 家 Satellite 卫星公司在 6 个日期及 7 大子列 (Lg, Com, Ag, Mem, Cy, Evt, Pro) 下的状态；
   - 区域 3 (左下 Generate Punter): 检查各 Robot ID 报表生成状态 [Tier 3 仅通知不阻断]；
   - 区域 4 (右下 Generate AI Punter): 检查各 AI Robot ID 报表生成状态 [Tier 3 仅通知不阻断]；

2. 黄色 Wager Cal 智能刷新与判定规则 (系统专属自动化机制):
   - 如果发现黄色的 'Wager Cal' 单元格，优先点击相应卫星公司名称进行刷新触发重算；
   - 最多循环点击刷新 2 次，每次点击后等待并重新获取最新数据；
   - 若点击 2 次后仍显示 Wager Cal，则归类为 Tier 3 提醒 (Log 提示，不阻断 Checkpoint 打勾)；
   - 若刷新后 Wager Cal 恢复为 ok 绿底，则视为完全合格。

3. 判定标准:
   - 只有红色的 Error 才是 Tier 1 (致命阻断):
     * 主对比矩阵中真正呈红底或显式标记为 'error' 的单元格；
     * Reset Log > 0 或 Rpt Complete 状态异常；
     * 发现此类红色错误强阻断 Checkpoint！
   - Tier 3 通报提醒 (不阻断 Checkpoint 打勾):
     * 刷新 2 次后依然存在的黄色 'Wager Cal'；
     * Generate Punter / Generate AI Punter 包含 Pending 挂起或红底；
     * 仅做 Log 通报提醒，正常点击 Checkpoint 通关！
================================================================================
"""

# 导入原生时间模块，用于动作之间的休眠等待
import time

# 导入基类 BaseChecker 与内存数据存储单例 CheckpointStore
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class RPTCompareChecker(BaseChecker):
    """
    RPT Compare 报表对比检查器类
    负责分析主矩阵报表一致性、自动触发 Wager Cal 刷新、以及校验 Punter 生成状态。
    """

    def _click_satellite_company(self, sat_code: str) -> bool:
        """Only click the company cell in its sport matrix row."""
        return bool(self.driver.execute_script(r"""
            var sat = arguments[0].toLowerCase();
            for (var row of document.querySelectorAll('tr')) {
                var cells = Array.from(row.children).filter(c => /^(TD|TH)$/.test(c.tagName));
                var sport = cells.findIndex(c => c.innerText.trim().toLowerCase() === 'sport');
                if (sport < 1 || cells[sport-1].innerText.trim().toLowerCase() !== sat) continue;
                var cell = cells[sport-1];
                var target = cell.matches('a,[onclick],button') ? cell : cell.querySelector('a,[onclick],button');
                if (!target) return false;
                target.click();
                return true;
            }
            return false;
        """, sat_code))

    def _matrix_load_state(self) -> dict:
        """Read readiness from every company row, including white empty cells."""
        return self.driver.execute_script(r"""
            var rows = [];
            var pending = 0;
            for (var row of document.querySelectorAll('tr')) {
                var cells = Array.from(row.children).filter(c => /^(TD|TH)$/.test(c.tagName));
                var sport = cells.findIndex(c => c.innerText.trim().toLowerCase() === 'sport');
                if (sport < 1 || cells.length <= sport + 1) continue;
                var company = cells[sport-1].innerText.trim();
                var values = cells.slice(sport+1).map(function(c) {
                    var text = c.innerText.trim();
                    var color = getComputedStyle(c).backgroundColor;
                    // Empty white/transparent cells have not returned data yet.
                    var rgb = color.match(/[\d.]+/g) || [];
                    var colored = rgb.length >= 3 && (Math.max(+rgb[0],+rgb[1],+rgb[2]) - Math.min(+rgb[0],+rgb[1],+rgb[2]) > 80) && !(rgb.length > 3 && +rgb[3] === 0);
                    if ((!text && !colored) || /loading|please wait|加载中/i.test(text)) pending++;
                    return text + ':' + color;
                });
                rows.push(company + '|' + values.join('|'));
            }
            return {rows: rows.length, pending: pending,
                idle: document.readyState === 'complete' && (typeof jQuery === 'undefined' || jQuery.active === 0),
                signature: rows.join('\n')};
        """)

    def _wait_for_matrix_loaded(self, timeout=90):
        """Wait for all rows to fill and settle; a timeout must not pass inspection."""
        from selenium.webdriver.support.ui import WebDriverWait
        signature = None
        stable_since = None

        def ready(_):
            nonlocal signature, stable_since
            state = self._matrix_load_state()
            if not state.get('rows') or state.get('pending') or not state.get('idle'):
                signature, stable_since = None, None
                return False
            current = state.get('signature')
            now = time.monotonic()
            if current != signature or stable_since is None:
                signature, stable_since = current, now
                return False
            return now - stable_since >= 1.0

        WebDriverWait(self.driver, timeout, poll_frequency=0.5).until(
            ready, message='RPT Compare matrix still contains unloaded company data'
        )

    def _extract_page7_data(self) -> dict:
        """
        [前端 DOM 提取脚本]
        执行 JavaScript，深度解析当前页面上全部 4 大区域的表格结构与计算样式。
        """
        return self.driver.execute_script(r"""
            // 初始化返回数据结构字典
            var result = {
                categoryName: "RCM",       // 下拉框当前选中的分类名 (默认 RCM)
                rptCompleteInfo: "",        // 区域1: Rpt Complete 状态文字
                rptCompleteHasErr: false,   // 区域1: Rpt Complete 是否异常
                resetLogTotal: 0,           // 区域1: Reset Log 累加总数 (需为 0)
                resetLogHasErr: false,      // 区域1: Reset Log 是否红底
                matrixSatellitesCount: 0,   // 区域2: 主矩阵中解析到的卫星公司数量
                matrixTotalOk: 0,           // 区域2: 状态为 'ok' 的单元格总数
                matrixErrList: [],          // 区域2: 仅存放真正的红色错误 / Error 单元格 (Tier 1)
                matrixWagerCalList: [],     // 区域2: 存放黄色 Wager Cal 单元格及对应卫星公司 (Tier 3)
                punterRows: [],             // 区域3: Punter 文本行
                punterErrList: [],          // 区域3: Punter 异常行
                aiPunterRows: [],           // 区域4: AI Punter 文本行
                aiPunterErrList: [],        // 区域4: AI Punter 异常行
                mainTableHeaders: [],       // 主矩阵表头结构
                mainTableSpans: [],
                mainTableRows: [],          // 主矩阵数据行结构 (带颜色标记)
                punterList: [],             // 结构化 Punter 列表
                aiPunterList: []            // 结构化 AI Punter 列表
            };

            // 颜色判定辅助函数 (安全解析 rgb 分量，杜绝将纯白误判为黄色，杜绝漏判深红)
            function parseRGB(c) {
                if (!c) return null;
                var p1 = c.indexOf("("), p2 = c.indexOf(")");
                if (p1 !== -1 && p2 !== -1) {
                    var parts = c.substring(p1 + 1, p2).split(",");
                    if (parts.length >= 3) {
                        return { r: parseInt(parts[0]), g: parseInt(parts[1]), b: parseInt(parts[2]) };
                    }
                }
                return null;
            }
            function isRedColor(c) {
                if (!c) return false;
                if (c.indexOf("red") !== -1) return true;
                var rgb = parseRGB(c);
                return rgb ? (rgb.r >= 180 && rgb.g <= 100 && rgb.b <= 100) : false;
            }
            function isYellowColor(c) {
                if (!c) return false;
                if (c.indexOf("yellow") !== -1) return true;
                var rgb = parseRGB(c);
                // 黄色特征: 高红、高绿、低蓝 (排除纯白 rgb(255,255,255) 和灰色)
                return rgb ? (rgb.r >= 200 && rgb.g >= 200 && rgb.b <= 120) : false;
            }

            // 1. 获取当前下拉框选中的分类名称
            var sel = document.getElementById("com_select") || document.querySelector("select");
            if (sel && sel.selectedIndex >= 0) {
                result.categoryName = sel.options[sel.selectedIndex].text;
            }

            // 2. 遍历页面所有 table 标签分别解析
            var tables = document.querySelectorAll("table");
            tables.forEach(function(t) {
                // 排除日历控件内部的小表格
                if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                var txt = t.innerText ? t.innerText.trim() : "";

                // ── 3.1 上方主表 (区域 1 与区域 2) ──
                if (txt.indexOf("Satellite") !== -1 || txt.indexOf("Rpt Complete") !== -1 || txt.indexOf("Reset Log") !== -1) {
                    // Expand native rowspan/colspan into stable logical coordinates.
                    var rows = Array.from(t.querySelectorAll("tr")).filter(r => r.closest("table") === t);
                    var grid = [];
                    rows.forEach(function(row, ri) {
                        grid[ri] = grid[ri] || [];
                        var ci = 0;
                        Array.from(row.children).filter(c => /^(TD|TH)$/.test(c.tagName)).forEach(function(cell) {
                            while (grid[ri][ci]) ci++;
                            var rs = cell.rowSpan === 0 ? rows.length-ri : Math.max(cell.rowSpan || 1, 1);
                            var cs = Math.max(cell.colSpan || 1, 1);
                            for (var rr=ri; rr<Math.min(ri+rs, rows.length); rr++) {
                                grid[rr] = grid[rr] || [];
                                for (var cc=ci; cc<ci+cs; cc++) grid[rr][cc] = cell;
                            }
                            ci += cs;
                        });
                    });
                    var bodyCells = [];
                    var headerCells = [];
                    var resetSeen = new Set();
                    grid.forEach(function(tds, rowIndex) {
                        var own = Array.from(rows[rowIndex].children).filter(c => /^(TD|TH)$/.test(c.tagName));
                        // Browser HTML contains empty rows and label-only rowspan rows.
                        // They have no visible data and must not become extra header rows.
                        if (!own.length || (own.length === 1 && own[0].rowSpan > 1 && tds.length < grid[0].length)) return;
                        if (tds.length >= 10 && tds.every(Boolean)) {
                            var txts = tds.map(c => c.innerText.trim());
                            var lineTxt = txts.join(" ");

                            // (3) 提取卫星行数据 (以包含 'sport' 作为关键标记)
                            var sportIdx = txts.indexOf("sport");
                            if (sportIdx !== -1) {
                                bodyCells.push(tds);
                                result.matrixSatellitesCount++;
                                var sat = txts[sportIdx - 1]; // 卫星公司代号 (如 p0001)
                                var resetLog = txts[sportIdx - 2] || "0"; // Reset Log 数量
                                if (!resetSeen.has(tds[sportIdx-2])) {
                                    result.resetLogTotal += parseInt(resetLog) || 0;
                                    resetSeen.add(tds[sportIdx-2]);
                                }

                                // 检查 Reset Log 单元格是否为红底/红字
                                if (sportIdx - 2 >= 0) {
                                    var rCell = tds[sportIdx - 2];
                                    var rBg = window.getComputedStyle(rCell).backgroundColor;
                                    var rFg = window.getComputedStyle(rCell).color;
                                    if (isRedColor(rBg) || isRedColor(rFg)) {
                                        result.resetLogHasErr = true;
                                    }
                                }

                                // 优先从第一行的对应列提取 Rpt Complete 单元格
                                if (sportIdx - 3 >= 0) {
                                    var rptCell = tds[sportIdx - 3];
                                    var rptTxt = rptCell.innerText.trim();
                                    if (rptTxt && !result.rptCompleteInfo) result.rptCompleteInfo = rptTxt;
                                    var rptBg = window.getComputedStyle(rptCell).backgroundColor;
                                    var rptFg = window.getComputedStyle(rptCell).color;
                                    if (isRedColor(rptBg) || isRedColor(rptFg) ||
                                        rptTxt.toLowerCase().indexOf("incomplete") !== -1 ||
                                        rptTxt.toLowerCase().indexOf("uncomplete") !== -1 ||
                                        (rptBg.indexOf("255") !== -1 && rptBg.indexOf("0, 0") !== -1)) {
                                        result.rptCompleteHasErr = true;
                                    }
                                }

                                var rowCells = [];
                                for (var c = 0; c < tds.length; c++) {
                                    var rawCellText = tds[c].innerText.trim();
                                    var cellText = rawCellText.toLowerCase();
                                    var cellBg = window.getComputedStyle(tds[c]).backgroundColor;

                                     // 判定是否为红底或 Error 文本 (只有红色的 Error 才是 Tier 1)
                                     var isRedCell = isRedColor(cellBg) || cellText === "error" || cellText.indexOf("error") !== -1;

                                     // 判定是否为黄色 Wager Cal 警告 (通过 RGB 分量精准判断，排除纯白色背景)
                                     var isYellowCell = (cellText.indexOf("wager cal") !== -1 || isYellowColor(cellBg));

                                     // 判定是否为绿底或 OK 正常
                                     var isGreenCell = !isRedCell && !isYellowCell && (cellBg.indexOf("0, 128") !== -1 || cellBg.indexOf("0, 204") !== -1 || cellBg.indexOf("0, 230") !== -1 || cellBg.indexOf("0, 255") !== -1 || cellText === "ok");

                                     // 赋予颜色标签
                                     var bgTag = isRedCell ? "red" : (isYellowCell ? "yellow" : (isGreenCell ? "green" : "white"));
                                    rowCells.push({ text: rawCellText, bg: bgTag });

                                    // 对比列 (位于 sport 列之后) 进行详细状态收集
                                    if (c > sportIdx) {
                                        if (isRedCell) {
                                            result.matrixErrList.push(sat + " (列" + c + "): " + rawCellText + " [RED ERROR]");
                                        } else if (isYellowCell) {
                                            result.matrixWagerCalList.push({
                                                sat: sat,
                                                col: c,
                                                text: rawCellText
                                            });
                                        } else if (cellText === "ok") {
                                            result.matrixTotalOk++;
                                        } else if (cellText !== "") {
                                            // 其他非空且非 OK 的未知文本也需记录
                                            result.matrixErrList.push(sat + " (列" + c + "): " + rawCellText);
                                        }
                                    }
                                }
                                result.mainTableRows.push(rowCells);
                            } else if (!bodyCells.length) {
                                headerCells.push(tds);
                            }
                        }
                    });
                    if (bodyCells.length) {
                        var width = bodyCells[0].length;
                        result.mainTableHeaders = Array.from({length:width}, function(_, col) {
                            var parts = [];
                            var seen = new Set();
                            headerCells.forEach(function(row) {
                                var cell = row[col];
                                if (cell && !seen.has(cell)) {
                                    var text = cell.innerText.trim();
                                    if (text) parts.push(text);
                                    seen.add(cell);
                                }
                            });
                            return parts.join('\n') || ('Col ' + (col+1));
                        });
                        var seenBody = new Set();
                        bodyCells.forEach(function(row, ri) {
                            row.forEach(function(cell, ci) {
                                if (seenBody.has(cell)) return;
                                seenBody.add(cell);
                                var rs=1, cs=1;
                                while (ri+rs<bodyCells.length && bodyCells[ri+rs][ci]===cell) rs++;
                                while (ci+cs<row.length && row[ci+cs]===cell) cs++;
                                if (rs>1 || cs>1) result.mainTableSpans.push({row:ri,col:ci,rowspan:rs,colspan:cs});
                            });
                        });
                    }
                }

                // ── 3.2 下方 Generate Punter / AI Punter (区域 3 与区域 4) ──
                var pRows = t.querySelectorAll("tr");
                pRows.forEach(function(r) {
                    if (r.closest("table") !== t) return;
                        var tds = Array.from(r.children).filter(c => /^(TD|TH)$/.test(c.tagName));
                    if (tds.length >= 2) {
                        var robotId = tds[0].innerText.trim();
                        var rptDate = tds[1].innerText.trim();
                        var fn = tds[2] ? tds[2].innerText.trim() : "";

                        var dateCell = tds[1];
                        var dateBg = window.getComputedStyle(dateCell).backgroundColor;
                        // 判定日期单元格是否呈红底或包含 Pending 挂起状态
                        var isRedDate = isRedColor(dateBg) || fn.indexOf("Pending") !== -1;

                        // 校验是否为合法机器人 ID (纯数字且日期字符串完整)
                        if (robotId && !isNaN(parseInt(robotId)) && rptDate.length >= 8) {
                            var robotNum = parseInt(robotId);
                            var statusTag = " [OK/正常绿底]";
                            if (isRedDate) statusTag = " [Tier 3 提醒/不阻断]";

                            var line = "Robot " + robotId + ": Rpt Date = " + rptDate + (fn ? (", Function = " + fn) : "") + statusTag;
                            var pItem = { robotId: robotId, rptDate: rptDate, fn: fn, isRed: isRedDate };

                            // Robot ID >= 800 属于 AI Punter，其余属于普通 Punter
                            if (robotNum >= 800) {
                                result.aiPunterRows.push(line);
                                result.aiPunterList.push(pItem);
                                if (isRedDate) result.aiPunterErrList.push(line);
                            } else {
                                result.punterRows.push(line);
                                result.punterList.push(pItem);
                                if (isRedDate) result.punterErrList.push(line);
                            }
                        }
                    }
                });
            });

            return result;
        """)

    def check(self, is_noon_fast: bool = False) -> bool:
        """
        [关卡主巡检方法]
        串联执行导航、点击搜索、初始数据抽取、Wager Cal 2次重试刷新、全量日志输出及 Tier 1/3 评判闭环。
        参数:
        - is_noon_fast (bool): 是否处于 12:00-14:00 午间快速通关窗口。若为 True，因未对外 release 昨日报表，
          沿用调度器根据 Matches & Wagers 整页结果确定的午间模式，Rpt Complete / Reset Log 暂不阻断；若为 False（超时或提前结束），则依然按 Tier 1 严格阻断。
        """
        # 1. 输出关卡站头日志
        header_title = "第7站 RPT Compare" + (" [⚡ Noon Fast Mode]" if is_noon_fast else "")
        self.log_station_header(header_title, menu_id="apy_b0i8text", page_key="niw_07")
        try:
            # 2. 导航切入 RPT Compare 菜单 (Menu ID: apy_b0i8text)
            self.navigate_to_menu("RPT Compare", menu_id="apy_b0i8text", section="NIW")

            # 3. 触发网页前端 search_data() 函数并智能等待加载完成
            self.driver.execute_script(r"""
                if (typeof search_data === "function") search_data();
            """)
            self.log("[LOAD] Waiting for every company row to finish loading...")
            self._wait_for_matrix_loaded()

            # 4. 初始全量抓取页面数据
            p7_data = self._extract_page7_data()

            # Only the initial Search loads the full matrix. Retries click company links.
            attempts = {}
            while True:
                pending = sorted({item["sat"] for item in p7_data.get("matrixWagerCalList", [])})
                candidates = [sat for sat in pending if attempts.get(sat, 0) < 2]
                if not candidates:
                    break
                for sat in candidates:
                    # A previous company's refresh may already have cleared this company.
                    current = {item["sat"] for item in p7_data.get("matrixWagerCalList", [])}
                    if sat not in current:
                        continue
                    attempts[sat] = attempts.get(sat, 0) + 1
                    self.log(f"[Wager Cal] Reload company [{sat}] ({attempts[sat]}/2); no Search.")
                    if not self._click_satellite_company(sat):
                        raise RuntimeError(f"Company [{sat}] refresh link not found; no Search fallback")
                    # Finish this company's reload before touching any other company.
                    self._wait_for_matrix_loaded()
                    p7_data = self._extract_page7_data()
            remaining = sorted({item["sat"] for item in p7_data.get("matrixWagerCalList", [])})
            if remaining:
                self.log(f"[Tier 3] Wager Cal remains after two company reloads: {', '.join(remaining)}")

            # 6. 读取各区域最终汇总指标
            cat_name = p7_data.get("categoryName", "RCM")
            rpt_comp = p7_data.get("rptCompleteInfo", "Complete")
            sat_count = p7_data.get("matrixSatellitesCount", 0)
            total_ok = p7_data.get("matrixTotalOk", 0)
            reset_sum = p7_data.get("resetLogTotal", 0)
            matrix_errs = p7_data.get("matrixErrList", [])
            punter_rows = p7_data.get("punterRows", [])
            punter_errs = p7_data.get("punterErrList", [])
            ai_punter_rows = p7_data.get("aiPunterRows", [])
            ai_punter_errs = p7_data.get("aiPunterErrList", [])

            final_wager_items = p7_data.get("matrixWagerCalList", [])
            final_wager_sats = sorted(list(set(item["sat"] for item in final_wager_items)))

            self.log_data_extracted(f"成功抓取 RPT Compare ({cat_name}) 数据矩阵 ({sat_count} 个卫星节点) | 'ok' 单元格: {total_ok} 个 | Rpt Complete: {rpt_comp} | Reset Log: {reset_sum}")
            self.log_check_method("校验规则: 红色 Error / Reset Log > 0 为 Tier 1 阻断 (午间模式由 Matches & Wagers 整页结果决定；模式生效时 Rpt Complete / Reset Log 暂不阻断)；黄底 Wager Cal 与 Generate Punter 为 Tier 3 提醒")

            # 7. 全量打印结构化巡检明细日志
            rpt_has_err = p7_data.get("rptCompleteHasErr", False)
            reset_is_err = reset_sum > 0 or p7_data.get("resetLogHasErr", False)
            rpt_comp_tag = "[Noon Fast/正常]" if (rpt_has_err and is_noon_fast) else ("[ERROR/异常]" if rpt_has_err else "[OK/正常]")
            reset_tag = "[Noon Fast/正常]" if (reset_is_err and is_noon_fast) else ("[ERROR/异常]" if reset_is_err else "[OK/正常]")

            summary_lines = [
                f"【RPT Compare 全量巡检数据明细 ({cat_name})】:",
                f"   * [1. 状态栏]: Rpt Complete = {rpt_comp} {rpt_comp_tag} | Reset Log = {reset_sum} {reset_tag}",
                f"   * [2. 主对比矩阵]: 成功校验 {sat_count} 个 Satellite 卫星节点，包含 {total_ok} 个 'ok' 绿底单元格 [OK/正常]"
            ]

            if final_wager_sats:
                summary_lines.append(f"   * [2.1 Wager Cal (Tier 3 提醒)]: 包含 {len(final_wager_items)} 处 Wager Cal (公司: {', '.join(final_wager_sats)}) [点击刷新2次后仍显示，仅通知不阻断]")

            if punter_rows:
                summary_lines.append("   * [3. Generate Punter 机器人状态 (Tier 3 通报提醒)]:")
                summary_lines.extend([f"      -> {p}" for p in punter_rows])

            if ai_punter_rows:
                summary_lines.append("   * [4. Generate AI Punter 机器人状态 (Tier 3 通报提醒)]:")
                summary_lines.extend([f"      -> {p}" for p in ai_punter_rows])

            self.log_data_summary(summary_lines)

            # 8. 构造 1:1 仿真多子表供 CheckpointStore 存储
            subtables = []
            main_rows = p7_data.get("mainTableRows", [])
            main_headers = p7_data.get("mainTableHeaders", [])
            if main_rows:
                if not main_headers:
                    first_len = len(main_rows[0])
                    main_headers = ["Col " + str(i+1) for i in range(first_len)]
                    if first_len >= 5:
                        main_headers[0:5] = ["NIW", "Rpt Complete", "Reset Log", "Satellite", "Type"]
                subtables.append({
                    "title": f"RPT Compare Matrix ({cat_name})",
                    "header_bg": "#C8D7A6",
                    "headers": main_headers,
                    "cell_spans": p7_data.get("mainTableSpans", []),
                    "rows": main_rows
                })

            p_list = p7_data.get("punterList", [])
            if p_list:
                subtables.append({
                    "title": "Generate Punter",
                    "header_bg": "#C8D7A6",
                    "headers": ["Robot ID", "Rpt Date", "Function"],
                    "rows": [
                        [
                            p["robotId"],
                            CheckpointStore.make_cell(p["rptDate"], "red" if p.get("isRed") else "white"),
                            CheckpointStore.make_cell(p["fn"], is_link="Generate" in p.get("fn", ""))
                        ]
                        for p in p_list
                    ]
                })

            ai_p_list = p7_data.get("aiPunterList", [])
            if ai_p_list:
                subtables.append({
                    "title": "Generate AI Punter",
                    "header_bg": "#C8D7A6",
                    "headers": ["Robot ID", "Rpt Date", "Function"],
                    "rows": [
                        [
                            p["robotId"],
                            CheckpointStore.make_cell(p["rptDate"], "red" if p.get("isRed") else "white"),
                            CheckpointStore.make_cell(p["fn"], is_link="Generate" in p.get("fn", ""))
                        ]
                        for p in ai_p_list
                    ]
                })

            # 9. 严格执行 Tier 1 报错阻断判定
            has_tier1_err = False
            err_reasons = []

            # Reset Log 判定: 午间快速通关期间未 release 报表属于正常现象不阻断；超时或提前结束后红字/大于0依然强阻断
            reset_has_err = (reset_sum > 0) or p7_data.get("resetLogHasErr", False)
            if reset_is_err:
                if is_noon_fast:
                    self.log(f"[NOON FAST] ⚡ Reset Log={reset_sum} (中午 12:00-14:00 跨日结算未 release 报表期间属于正常现象，暂不阻断)")
                else:
                    has_tier1_err = True
                    err_reasons.append(f"Reset Log 异常 (数量={reset_sum} 或 红底)")

            # Rpt Complete 判定: 午间快速通关期间未 release 报表属于正常现象不阻断；超时或提前结束后红字依然强阻断
            if p7_data.get("rptCompleteHasErr"):
                if is_noon_fast:
                    self.log("[NOON FAST] ⚡ Rpt Complete 红色（午间快速模式仍生效，暂不阻断）")
                else:
                    has_tier1_err = True
                    err_reasons.append("Rpt Complete 红色/未完成（午间快速模式未生效或已结束）")

            # 主对比矩阵判定: 任何时段存在主矩阵红色 Error 均强阻断
            if len(matrix_errs) > 0:
                has_tier1_err = True
                err_reasons.append(f"主对比矩阵存在 {len(matrix_errs)} 处红色 Error 异常单元格")

            if has_tier1_err:
                self.log_check_result(False, f"RPT Compare 巡检发现 Tier 1 红色致命异常: {'; '.join(err_reasons)}，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_07",
                    title="RPT Compare",
                    status=False,
                    tables=subtables,
                    summary="; ".join(err_reasons)
                )
                return False

            # 10. Tier 3 提醒汇总 (不阻断通关)
            tier3_msg = []
            if is_noon_fast:
                if reset_is_err:
                    tier3_msg.append(f"[Noon Fast] Reset Log={reset_sum} 正常")
                if p7_data.get("rptCompleteHasErr"):
                    tier3_msg.append("[Noon Fast] Rpt Complete 红色未完成暂时允许")

            if final_wager_sats:
                tier3_msg.append(f"Wager Cal 卫星公司: {', '.join(final_wager_sats)} (共 {len(final_wager_items)} 处，已尝试刷新2次)")
            if len(punter_errs) > 0:
                tier3_msg.append(f"Generate Punter 包含 {len(punter_errs)} 项 Pending 挂起")
            if len(ai_punter_errs) > 0:
                tier3_msg.append(f"Generate AI Punter 包含 {len(ai_punter_errs)} 项 Pending 挂起")

            if is_noon_fast and (reset_is_err or p7_data.get("rptCompleteHasErr")):
                self.log_check_result(True, f"RPT Compare 巡检通过！(午间规则允许的项目不阻断" + (f" | 提醒: {'; '.join(tier3_msg)}" if tier3_msg else "") + ")")
            elif tier3_msg:
                self.log_check_result(True, f"RPT Compare 主矩阵无红色 Error，发现 Tier 3 提醒 ({'; '.join(tier3_msg)})，根据规则仅做 Log 通报，通过！")
            else:
                self.log_check_result(True, "RPT Compare 所有区域全部合格，通过！")

            # 11. 执行 Check Point 打勾并持久化数据到内存 Store
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            CheckpointStore.save(
                page_key="niw_07",
                title="RPT Compare",
                status=True,
                tables=subtables,
                summary="; ".join(tier3_msg) if tier3_msg else "All tables OK",
                has_warn=bool(tier3_msg)
            )
            return True

        except Exception as e:
            # 异常兜底保护
            return self.handle_exception("niw_07", "RPT Compare", e)
