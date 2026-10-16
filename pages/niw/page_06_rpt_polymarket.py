"""
================================================================================
第6站 RPT PolyMarket 关卡检查器 (pages/niw/page_06_rpt_polymarket.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户工控系统 1:1 原生报表设计:
   - 表头动态化: 去除 NIW 分区列与冗余 Type 列，按系统原生顺序展示:
     [Reset Log] | [Satellite] | [日期 1] | [日期 2] | ... | [日期 7]
   - 动态识别页面真实的 7 天 RPT 日期跨度 (如 22/09/2026 ~ 28/09/2026)，拆解为 7 个独立数据列；
2. 单元格 1:1 仿真配色:
   - Reset Log 列: 0 呈现翠绿底，>0 呈现亮红底；
   - Satellite 列: 呈现蓝色超链接样式；
   - 7 天日期状态列: ok 呈现翠绿底，异常/红底/非 ok 呈现亮红底；
3. 级别划分 (Tier 1 报错阻断 Checkpoint):
   - 若 Reset Log > 0 或某日期状态不为 ok (如 error 或红底)，直接判定为 Tier 1 报错阻断 Checkpoint！
   - 全部 Reset Log 为 0 且 7 天状态全为 ok 时，巡检通过并点击 Checkpoint 按钮打勾。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTPolyMarketChecker(BaseChecker):
    def check(self) -> bool:
        # 1. 记录当前关卡页头日志 (Menu ID: apy_b0i7text)
        self.log_station_header("第6站 RPT PolyMarket", menu_id="apy_b0i7text")
        try:
            # 2. 自动化导航切入 RPT PolyMarket 专属菜单页面
            self.navigate_to_menu("RPT PolyMarket", menu_id="apy_b0i7text", section="NIW")

            # 3. 智能等待页面载入完成
            self.wait_for_page_loaded(seconds=0.5, max_wait=30)

            # 4. 核心 JavaScript 脚本：精准抓取 Reset Log、Satellite 与动态 7 天日期矩阵
            p6_data = self.driver.execute_script("""
                // 初始化抓取容器
                var result = {
                    categoryName: "RCM",
                    dates: [],
                    satelliteRows: [],
                    rawRows: [],
                    totalOkCount: 0,
                    errCount: 0,
                    resetLogTotal: 0
                };

                // 1. 颜色判断辅助函数 (识别各种 RGB/RGBA 格式的红色)
                function isRedColor(colStr) {
                    if (!colStr) return false;
                    var m = colStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                    if (m) {
                        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                        return (r > 180 && g < 100 && b < 100);
                    }
                    return false;
                }

                // 2. 获取下拉框当前选择的分区/公司名称 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text.trim();
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 隔离防护：过滤日历控件及嵌套表格
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null || t.querySelector("table") !== null) return;

                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Reset Log") === -1 && txt.indexOf("Satellite") === -1) return;

                    // 3. 动态提取 7 天日期表头列表 (匹配 DD/MM/YYYY 或 DD/MM)
                    var dateRegex = /\\b(\\d{1,2}\\/\\d{1,2}(?:\\/\\d{2,4})?)\\b/;
                    var foundDates = [];
                    var allHeaderRows = t.querySelectorAll("tr");
                    for (var rIdx = 0; rIdx < Math.min(allHeaderRows.length, 3); rIdx++) {
                        var cells = allHeaderRows[rIdx].querySelectorAll("th, td");
                        var rowDates = [];
                        cells.forEach(function(c) {
                            var cTxt = c.innerText ? c.innerText.trim() : "";
                            var m = cTxt.match(dateRegex);
                            if (m) {
                                rowDates.push(m[1]);
                            }
                        });
                        if (rowDates.length >= 2) {
                            foundDates = rowDates;
                            break;
                        }
                    }

                    // 兜底策略：若表头未能直接匹配到连续日期，从页面 Date 输入框中推导
                    if (foundDates.length < 2) {
                        var dateInputs = document.querySelectorAll("input");
                        var inputDates = [];
                        dateInputs.forEach(function(inp) {
                            var v = (inp.value || "").trim();
                            var m = v.match(dateRegex);
                            if (m) inputDates.push(m[1]);
                        });
                        if (inputDates.length >= 2) {
                            try {
                                var parts = inputDates[0].split("/");
                                if (parts.length === 3) {
                                    var d = parseInt(parts[0], 10), m = parseInt(parts[1], 10) - 1, y = parseInt(parts[2], 10);
                                    var cur = new Date(y, m, d);
                                    for (var i = 0; i < 7; i++) {
                                        var dd = String(cur.getDate()).padStart(2, '0');
                                        var mm = String(cur.getMonth() + 1).padStart(2, '0');
                                        var yy = cur.getFullYear();
                                        foundDates.push(dd + "/" + mm + "/" + yy);
                                        cur.setDate(cur.getDate() + 1);
                                    }
                                }
                            } catch(e) {}
                        }
                    }
                    result.dates = foundDates;

                    // 4. 遍历数据行并按列抓取各指标
                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length < 5) return;

                        var txts = [];
                        tds.forEach(function(c) { txts.push(c.innerText ? c.innerText.trim() : ""); });

                        // 以 'sport' 标志列作为精准定位基准点
                        var sportIdx = txts.indexOf("sport");
                        if (sportIdx !== -1 && sportIdx >= 2) {
                            var sat = txts[sportIdx - 1];
                            var resetLog = txts[sportIdx - 2];
                            var dateStartIdx = sportIdx + 1;

                            if (sat && sat !== "Satellite" && sat.indexOf("Satellite") === -1) {
                                var rCell = tds[sportIdx - 2];
                                var rLogNum = parseInt(resetLog, 10) || 0;
                                result.resetLogTotal += rLogNum;

                                var rBg = rCell ? window.getComputedStyle(rCell).backgroundColor : "";
                                var rFg = rCell ? window.getComputedStyle(rCell).color : "";
                                var isResetErr = (rLogNum > 0 || isRedColor(rBg) || isRedColor(rFg));

                                var rowHasErr = isResetErr;
                                var dateItems = [];
                                var dateLogStatuses = [];

                                var dateCount = foundDates.length > 0 ? foundDates.length : (tds.length - dateStartIdx);
                                for (var i = 0; i < dateCount; i++) {
                                    var cIdx = dateStartIdx + i;
                                    if (cIdx >= tds.length) break;

                                    var cell = tds[cIdx];
                                    var cellText = cell.innerText ? cell.innerText.trim() : "";
                                    var cellLower = cellText.toLowerCase();

                                    var cBg = window.getComputedStyle(cell).backgroundColor;
                                    var cFg = window.getComputedStyle(cell).color;

                                    var isCellErr = false;
                                    if (cellLower !== "ok" || isRedColor(cBg) || isRedColor(cFg)) {
                                        isCellErr = true;
                                        rowHasErr = true;
                                        result.errCount++;
                                    } else {
                                        result.totalOkCount++;
                                    }

                                    var dHeader = (foundDates && foundDates[i]) ? foundDates[i] : ("Day " + (i + 1));
                                    dateItems.push({
                                        date: dHeader,
                                        text: cellText || "ok",
                                        isErr: isCellErr
                                    });
                                    dateLogStatuses.push(dHeader + ":" + cellText + (isCellErr ? "[Tier 1 报错]" : ""));
                                }

                                var statusTag = rowHasErr ? "[ERROR/Tier 1]" : " [OK]";
                                var logLine = sat + ": Reset Log=" + resetLog + " | " + dateLogStatuses.join(", ") + " " + statusTag;
                                result.satelliteRows.push(logLine);

                                result.rawRows.push({
                                    satellite: sat,
                                    resetLog: resetLog,
                                    resetLogIsErr: isResetErr,
                                    datesData: dateItems,
                                    isRowErr: rowHasErr
                                });
                            }
                        }
                    });
                });

                return result;
            """)

            # 5. 在 Python 侧解构 JS 返回的字段变量
            cat_name = p6_data.get("categoryName", "RCM")
            sat_rows = p6_data.get("satelliteRows", [])
            raw_rows = p6_data.get("rawRows", [])
            dates = p6_data.get("dates", [])
            total_ok = p6_data.get("totalOkCount", 0)
            total_err = p6_data.get("errCount", 0)
            reset_sum = p6_data.get("resetLogTotal", 0)

            # 动态表头: 去除 NIW 与 Type 列，按系统原生顺序展示: Reset Log, Satellite, 各日期
            if not dates and raw_rows and raw_rows[0].get("datesData"):
                dates = [d.get("date", f"Day {i+1}") for i, d in enumerate(raw_rows[0]["datesData"])]
            if not dates:
                dates = [f"Day {i+1}" for i in range(7)]

            table_headers = ["Reset Log", "Satellite"] + dates

            self.log_data_extracted(f"成功抓取 RPT PolyMarket ({cat_name}) 数据矩阵 ({len(sat_rows)} 个卫星节点, {len(dates)} 天) | 'ok' 单元格: {total_ok} 个 | Reset Log 总数: {reset_sum}")
            self.log_check_method("全量核对 Satellite 卫星节点 Reset Log 及 7 天 RPT 日期状态 ( Tier 1 规则: Reset Log > 0 或非 ok 状态为 Tier 1 报错阻断 )")

            # 6. 无条件全量打印明细 (全量巡检数据明细)
            summary_lines = [f"【RPT PolyMarket 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in sat_rows])
            self.log_data_summary(summary_lines)

            # 构筑 1:1 仿真表格数据行 (Reset Log 绿/红底、Satellite 超链接、各日期 ok 绿底/异常红底)
            table_rows = []
            for r in raw_rows:
                r_log_val = r.get("resetLog", "0")
                is_r_err = r.get("resetLogIsErr", False)
                sat_code = r.get("satellite", "")

                row = [
                    CheckpointStore.make_cell(r_log_val, bg="red" if is_r_err else "green"),
                    CheckpointStore.make_cell(sat_code, is_link=True),
                ]

                # 动态填充各日期单元格
                for d_info in r.get("datesData", []):
                    c_txt = d_info.get("text", "ok")
                    c_err = d_info.get("isErr", False)
                    row.append(CheckpointStore.make_cell(c_txt, bg="red" if c_err else "green"))

                table_rows.append(row)

            subtables = [{
                "title": f"RPT PolyMarket ({cat_name})",
                "headers": table_headers,
                "rows": table_rows
            }]

            # 7. Tier 1 阻断逻辑判定
            if total_err > 0 or reset_sum > 0:
                self.log_check_result(False, f"RPT PolyMarket 发现 {total_err} 项日期异常或 Reset Log={reset_sum} > 0，判定为 Tier 1 报错，阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_06",
                    title="RPT PolyMarket",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    tables=subtables,
                    summary=f"异常: {total_err} 项日期异常, Reset Log={reset_sum}"
                )
                return False
            else:
                self.log_check_result(True, "RPT PolyMarket 所有 Satellite 卫星节点 Reset Log 均为 0 且日期状态全为 ok，巡检合格！")

            # 8. 巡检合格，解封并点击 Checkpoint 按钮打勾提交
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            CheckpointStore.save(
                page_key="niw_06",
                title="RPT PolyMarket",
                status=True,
                headers=table_headers,
                rows=table_rows,
                tables=subtables,
                summary=f"全部 {len(raw_rows)} 个 Satellite 节点 {len(dates)} 天全部正常"
            )
            return True

        except Exception as e:
            # 捕获未知异常
            return self.handle_exception("niw_06", "RPT PolyMarket", e)
