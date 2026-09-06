"""
================================================================================
第7站 RPT Compare 关卡检查器 (pages/niw/page_07_rpt_compare.py)
--------------------------------------------------------------------------------
全量日志与判定规则 (遵循用户最新指令):
1. 抓取与对齐用户截图圈出的全部 4 大区域:
   - 区域 1 (左侧状态): Rpt Complete (需为 Complete 绿底) 与 Reset Log (需为 0) [Tier 1]；
   - 区域 2 (主对比矩阵): 26 家 Satellite 卫星公司在 6 个日期及 7 大子列 (Lg, Com, Ag, Mem, Cy, Evt, Pro) 下的状态；
   - 区域 3 (左下 Generate Punter): 检查 Robot ID 状态 [Tier 3 仅通知不阻断]；
   - 区域 4 (右下 Generate AI Punter): 检查 AI Robot ID 状态 [Tier 3 仅通知不阻断]；

2. 黄色 Wager Cal 智能刷新与判定规则 (用户专属规则):
   - 如果发现黄色的 'Wager Cal' 单元格，优先点击相应卫星公司进行刷新计算；
   - 大概点击刷新 2 次，每次点击后等待并重新获取数据；
   - 若点击 2 次后仍显示 Wager Cal，则归类为 Tier 3 提醒（Notify 提示，不阻断 Checkpoint）；
   - 若刷新后 Wager Cal 恢复为 ok 绿底，则视为完全合格。

3. 判定标准:
   - 只有红色的 Error 才是 Tier 1 (致命阻断):
     * 主对比矩阵中真正呈红底或显式标记为 'error' 的单元格；
     * Reset Log > 0 或 Rpt Complete 状态异常；
     * 发现此类红色错误强阻断 Checkpoint！
   - Tier 3 通报提醒 (不阻断 Checkpoint):
     * 刷新 2 次后依然存在的黄色 'Wager Cal'；
     * Generate Punter / Generate AI Punter 包含 Pending/红底；
     * 仅做 Log 通报提醒，正常点击 Checkpoint 通关！
================================================================================
"""

import time
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTCompareChecker(BaseChecker):

    def _click_satellite_company(self, sat_code: str) -> bool:
        """尝试在表格中定位并点击指定卫星公司 (如 p0008) 的链接触发刷新"""
        return self.driver.execute_script("""
            var sat = arguments[0];
            var links = document.querySelectorAll("table a");
            for (var i = 0; i < links.length; i++) {
                var txt = links[i].innerText ? links[i].innerText.trim() : "";
                if (txt === sat) {
                    links[i].click();
                    return true;
                }
            }
            var cells = document.querySelectorAll("table td");
            for (var j = 0; j < cells.length; j++) {
                if (cells[j].innerText && cells[j].innerText.trim() === sat) {
                    cells[j].click();
                    return true;
                }
            }
            return false;
        """, sat_code)

    def _extract_page7_data(self) -> dict:
        """执行前端 JavaScript，提取 RPT Compare 当前页面的全量数据"""
        return self.driver.execute_script("""
            var result = {
                categoryName: "RCM",
                rptCompleteInfo: "",
                rptCompleteHasErr: false,
                resetLogTotal: 0,
                matrixSatellitesCount: 0,
                matrixTotalOk: 0,
                matrixErrList: [],         // 仅存放真正的红色错误 / Error 单元格 (Tier 1)
                matrixWagerCalList: [],    // 存放黄色 Wager Cal 单元格及对应卫星公司 (Tier 3)
                punterRows: [],
                punterErrList: [],
                aiPunterRows: [],
                aiPunterErrList: [],
                mainTableHeaders: [],
                mainTableRows: [],
                punterList: [],
                aiPunterList: []
            };

            var sel = document.getElementById("com_select") || document.querySelector("select");
            if (sel && sel.selectedIndex >= 0) {
                result.categoryName = sel.options[sel.selectedIndex].text;
            }

            var tables = document.querySelectorAll("table");
            tables.forEach(function(t) {
                if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                var txt = t.innerText ? t.innerText.trim() : "";

                // 3.1 上方主表 (Red Box 1 & 2)
                if (txt.indexOf("Satellite") !== -1 || txt.indexOf("Rpt Complete") !== -1 || txt.indexOf("Reset Log") !== -1) {
                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        if (tds.length >= 10) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            if (result.mainTableHeaders.length === 0 && (lineTxt.indexOf("Satellite") !== -1 || lineTxt.indexOf("Rpt Complete") !== -1)) {
                                result.mainTableHeaders = txts;
                            }

                            if (lineTxt.indexOf("Complete") !== -1 && !result.rptCompleteInfo) {
                                for (var i = 0; i < tds.length; i++) {
                                    var cellVal = tds[i].innerText.trim();
                                    if (cellVal.indexOf("Complete") !== -1) {
                                        var bg = window.getComputedStyle(tds[i]).backgroundColor;
                                        var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);
                                        result.rptCompleteInfo = cellVal;
                                        if (isRed) result.rptCompleteHasErr = true;
                                        break;
                                    }
                                }
                            }

                            var sportIdx = txts.indexOf("sport");
                            if (sportIdx !== -1) {
                                result.matrixSatellitesCount++;
                                var sat = txts[sportIdx - 1];
                                var resetLog = txts[sportIdx - 2] || "0";
                                result.resetLogTotal += parseInt(resetLog) || 0;

                                var rowCells = [];
                                for (var c = 0; c < tds.length; c++) {
                                    var rawCellText = tds[c].innerText.trim();
                                    var cellText = rawCellText.toLowerCase();
                                    var cellBg = window.getComputedStyle(tds[c]).backgroundColor;

                                    // 判定是否为红底或 Error 文本 (只有红色的 Error 才是 Tier 1)
                                    var isRedCell = (cellBg.indexOf("255") !== -1 && cellBg.indexOf("0, 0") !== -1) || cellText === "error" || cellText.indexOf("error") !== -1;

                                    // 判定是否为黄色 Wager Cal
                                    var isYellowCell = (cellText.indexOf("wager cal") !== -1 || cellBg.indexOf("255, 255") !== -1 || cellBg.indexOf("yellow") !== -1);

                                    // 判定是否为绿底或 OK 正常
                                    var isGreenCell = !isRedCell && !isYellowCell && (cellBg.indexOf("0, 128") !== -1 || cellBg.indexOf("0, 204") !== -1 || cellBg.indexOf("0, 230") !== -1 || cellBg.indexOf("0, 255") !== -1 || cellText === "ok");

                                    var bgTag = isRedCell ? "red" : (isYellowCell ? "yellow" : (isGreenCell ? "green" : "white"));
                                    rowCells.push({ text: rawCellText, bg: bgTag });

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
                                            // 其他非空且非 OK 的未知文本
                                            result.matrixErrList.push(sat + " (列" + c + "): " + rawCellText);
                                        }
                                    }
                                }
                                result.mainTableRows.push(rowCells);
                            }
                        }
                    });
                }

                // 3.2 下方 Generate Punter / AI Punter (Red Box 3 & 4 - Tier 3 规则)
                var pRows = t.querySelectorAll("tr");
                pRows.forEach(function(r) {
                    var tds = r.querySelectorAll("td, th");
                    if (tds.length >= 2) {
                        var robotId = tds[0].innerText.trim();
                        var rptDate = tds[1].innerText.trim();
                        var fn = tds[2] ? tds[2].innerText.trim() : "";

                        var dateCell = tds[1];
                        var dateBg = window.getComputedStyle(dateCell).backgroundColor;
                        var isRedDate = (dateBg.indexOf("255") !== -1 && dateBg.indexOf("0, 0") !== -1) || fn.indexOf("Pending") !== -1;

                        if (robotId && !isNaN(parseInt(robotId)) && rptDate.length >= 8) {
                            var robotNum = parseInt(robotId);
                            var statusTag = " [OK/正常绿底]";
                            if (isRedDate) statusTag = " [Tier 3 提醒/不阻断]";

                            var line = "Robot " + robotId + ": Rpt Date = " + rptDate + (fn ? (", Function = " + fn) : "") + statusTag;
                            var pItem = { robotId: robotId, rptDate: rptDate, fn: fn, isRed: isRedDate };

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

    def check(self) -> bool:
        self.log_station_header("第7站 RPT Compare", menu_id="apy_b0i8text")
        try:
            # 1. 导航切入 RPT Compare 菜单
            self.navigate_to_menu("RPT Compare", menu_id="apy_b0i8text", section="NIW")

            # 2. 触发 search_data() 并动态智能轮询等待 Loading 动画消失与数据计算完毕
            self.driver.execute_script("""
                if (typeof search_data === "function") search_data();
            """)
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)

            # 3. 初始抓取全页 4 大区域数据
            p7_data = self._extract_page7_data()

            # ── 用户特别指令: 黄色 Wager Cal 刷新机制 ──
            # 如果有显示黄色的 Wager Cal，先点击相应的公司进行刷新校验，大概点击 2 次
            wager_cal_items = p7_data.get("matrixWagerCalList", [])
            wager_cal_sats = sorted(list(set(item["sat"] for item in wager_cal_items)))

            if wager_cal_sats:
                self.log(f"\n[Wager Cal 监测] 发现 {len(wager_cal_sats)} 家公司显示黄底 'Wager Cal': {', '.join(wager_cal_sats)}")
                self.log("   -> 根据操作指令: 优先点击相应公司进行刷新计算 (最多点击 2 次)")

                for attempt in range(1, 3):
                    if not wager_cal_sats:
                        break
                    self.log(f"\n   [刷新尝试 {attempt}/2] 正在点击对应卫星公司链接进行刷新计算...")
                    for sat in wager_cal_sats:
                        clicked = self._click_satellite_company(sat)
                        if clicked:
                            self.log(f"      -> 已触发公司 [{sat}] 刷新点击")
                        else:
                            self.log(f"      -> 尝试点击公司 [{sat}]")
                        time.sleep(1.0)

                    # 等待片刻并触发 search_data() 确保前端重绘最新结果
                    self.wait_for_page_loaded(seconds=2.0, max_wait=25)
                    self.driver.execute_script("if (typeof search_data === 'function') search_data();")
                    self.wait_for_page_loaded(seconds=2.0, max_wait=25)

                    # 重新抓取并核验最新状态
                    p7_data = self._extract_page7_data()
                    wager_cal_items = p7_data.get("matrixWagerCalList", [])
                    remaining_sats = sorted(list(set(item["sat"] for item in wager_cal_items)))

                    cleared = [s for s in wager_cal_sats if s not in remaining_sats]
                    if cleared:
                        self.log(f"      -> ✅ 公司 {', '.join(cleared)} 刷新后 Wager Cal 已消除！")

                    wager_cal_sats = remaining_sats
                    if not wager_cal_sats:
                        self.log("   -> 🎉 全部 Wager Cal 经刷新后均已恢复正常 (OK)！")
                        break

                if wager_cal_sats:
                    self.log(f"\n[Tier 3 提醒] 卫星公司 {', '.join(wager_cal_sats)} 点击刷新 2 次后仍显示 Wager Cal，根据规则判定为 Tier 3 提醒 (不阻断 Checkpoint)")

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
            self.log_check_method("校验规则: 只有红色的 Error / Reset Log > 0 才是 Tier 1 阻断；黄底 Wager Cal 与 Generate Punter 挂起为 Tier 3 仅通知提醒")

            # 4. 无条件全量打印明细 (全量巡检数据明细)
            summary_lines = [
                f"【RPT Compare 全量巡检数据明细 ({cat_name})】:",
                f"   * [1. 状态栏 (Tier 1)]: Rpt Complete = {rpt_comp} | Reset Log = {reset_sum} [OK/正常]",
                f"   * [2. 主对比矩阵 (Tier 1)]: 成功校验 {sat_count} 个 Satellite 卫星节点，包含 {total_ok} 个 'ok' 绿底单元格 [OK/正常]"
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

            table_headers = ["Section", "Satellite / Robot", "Type / Date", "Function / Reset Log", "Status"]
            table_rows = []

            # 1. Overview
            table_rows.append([
                CheckpointStore.make_cell("Status Overview"),
                CheckpointStore.make_cell(cat_name),
                CheckpointStore.make_cell(rpt_comp, bg="red" if p7_data.get("rptCompleteHasErr") else "green"),
                CheckpointStore.make_cell(f"Reset Log: {reset_sum}", bg="red" if reset_sum > 0 else "green"),
                CheckpointStore.make_cell("ERROR" if reset_sum > 0 else "OK", bg="red" if reset_sum > 0 else "green")
            ])

            # 2. Main Matrix
            table_rows.append([
                CheckpointStore.make_cell("RPT Matrix"),
                CheckpointStore.make_cell(f"{sat_count} Satellites"),
                CheckpointStore.make_cell(f"{total_ok} OK cells"),
                CheckpointStore.make_cell(f"{len(matrix_errs)} errors" if matrix_errs else "No Error"),
                CheckpointStore.make_cell("ERROR" if matrix_errs else "OK", bg="red" if matrix_errs else "green")
            ])

            # 2.1 Wager Cal 独立概览行 (如果有)
            if final_wager_sats:
                table_rows.append([
                    CheckpointStore.make_cell("Wager Cal"),
                    CheckpointStore.make_cell(", ".join(final_wager_sats)),
                    CheckpointStore.make_cell(f"{len(final_wager_items)} cells", bg="yellow"),
                    CheckpointStore.make_cell("Refreshed 2x"),
                    CheckpointStore.make_cell("TIER 3", bg="yellow")
                ])

            # 3. Punter rows
            for p in punter_rows:
                is_p_err = "Tier 3" in p or "Pending" in p
                table_rows.append([
                    CheckpointStore.make_cell("Generate Punter"),
                    CheckpointStore.make_cell(p.split(":")[0].strip() if ":" in p else p),
                    CheckpointStore.make_cell(p.split("Rpt Date = ")[1].split(",")[0].strip() if "Rpt Date = " in p else "-"),
                    CheckpointStore.make_cell(p.split("Function = ")[1].split("[")[0].strip() if "Function = " in p else "-"),
                    CheckpointStore.make_cell("PENDING" if is_p_err else "OK", bg="red" if is_p_err else "green")
                ])

            # 4. AI Punter rows
            for p in ai_punter_rows:
                is_p_err = "Tier 3" in p or "Pending" in p
                table_rows.append([
                    CheckpointStore.make_cell("Generate AI Punter"),
                    CheckpointStore.make_cell(p.split(":")[0].strip() if ":" in p else p),
                    CheckpointStore.make_cell(p.split("Rpt Date = ")[1].split(",")[0].strip() if "Rpt Date = " in p else "-"),
                    CheckpointStore.make_cell(p.split("Function = ")[1].split("[")[0].strip() if "Function = " in p else "-"),
                    CheckpointStore.make_cell("PENDING" if is_p_err else "OK", bg="red" if is_p_err else "green")
                ])

            # 构筑 1:1 还原企业网页原生大表与子表结构
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

            if not subtables:
                subtables = [{"title": "RPT Compare Overview", "header_bg": "#C8D7A6", "headers": table_headers, "rows": table_rows}]

            # 5. Tier 1 报错阻断判定 (只有红色的 Error 才是 Tier 1)
            has_tier1_err = False
            err_reasons = []

            if reset_sum > 0:
                has_tier1_err = True
                err_reasons.append(f"Reset Log 总数 = {reset_sum} > 0")

            if p7_data.get("rptCompleteHasErr"):
                has_tier1_err = True
                err_reasons.append("Rpt Complete 状态异常 (非绿底/红底)")

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

            # 6. Tier 3 提醒判定 (Wager Cal 刷新后仍存在、Punter & AI Punter 存在 Pending 均不阻断)
            tier3_msg = []
            if final_wager_sats:
                tier3_msg.append(f"Wager Cal 卫星公司: {', '.join(final_wager_sats)} (共 {len(final_wager_items)} 处，已尝试刷新2次)")
            if len(punter_errs) > 0:
                tier3_msg.append(f"Generate Punter 包含 {len(punter_errs)} 项 Pending 挂起")
            if len(ai_punter_errs) > 0:
                tier3_msg.append(f"Generate AI Punter 包含 {len(ai_punter_errs)} 项 Pending 挂起")

            if tier3_msg:
                self.log_check_result(True, f"RPT Compare 主矩阵无红色 Error，发现 Tier 3 提醒 ({'; '.join(tier3_msg)})，根据规则仅做 Log 通报，通过！")
            else:
                self.log_check_result(True, "RPT Compare 所有区域全部合格，通过！")

            # 7. 解封并点击 Checkpoint 按钮
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_07",
                title="RPT Compare",
                status=True,
                tables=subtables,
                summary="; ".join(tier3_msg) if tier3_msg else "All tables OK"
            )
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT Compare 检查出现异常: {e}")
            CheckpointStore.save(
                page_key="niw_07",
                title="RPT Compare",
                status=False,
                headers=["Error"],
                rows=[[CheckpointStore.make_cell(str(e), bg="red")]],
                summary="Exception during check"
            )
            return False
