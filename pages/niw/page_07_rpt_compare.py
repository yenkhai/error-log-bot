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
        """
        [辅助方法: 模拟点击卫星公司链接触发刷新]
        在页面表格中搜索卫星公司代号 (如 p0008, d0005)，定位后点击超链接以发起重新计算请求。
        """
        return self.driver.execute_script("""
            // 获取传入的卫星公司代码参数
            var sat = arguments[0];

            // 1. 优先在所有表格超链接 <a> 中精确查找文字匹配的公司名
            var links = document.querySelectorAll("table a");
            for (var i = 0; i < links.length; i++) {
                var txt = links[i].innerText ? links[i].innerText.trim() : "";
                if (txt === sat) {
                    // 模拟原生点击事件触发刷新
                    links[i].click();
                    return true;
                }
            }

            // 2. 兜底方案: 若超链接未包裹 <a>，尝试在普通 <td> 单元格中查找并点击
            var cells = document.querySelectorAll("table td");
            for (var j = 0; j < cells.length; j++) {
                if (cells[j].innerText && cells[j].innerText.trim() === sat) {
                    cells[j].click();
                    return true;
                }
            }

            // 未找到对应节点返回 false
            return false;
        """, sat_code)

    def _extract_page7_data(self) -> dict:
        """
        [前端 DOM 提取脚本]
        执行 JavaScript，深度解析当前页面上全部 4 大区域的表格结构与计算样式。
        """
        return self.driver.execute_script("""
            // 初始化返回数据结构字典
            var result = {
                categoryName: "RCM",       // 下拉框当前选中的分类名 (默认 RCM)
                rptCompleteInfo: "",        // 区域1: Rpt Complete 状态文字
                rptCompleteHasErr: false,   // 区域1: Rpt Complete 是否异常
                resetLogTotal: 0,           // 区域1: Reset Log 累加总数 (需为 0)
                matrixSatellitesCount: 0,   // 区域2: 主矩阵中解析到的卫星公司数量
                matrixTotalOk: 0,           // 区域2: 状态为 'ok' 的单元格总数
                matrixErrList: [],          // 区域2: 仅存放真正的红色错误 / Error 单元格 (Tier 1)
                matrixWagerCalList: [],     // 区域2: 存放黄色 Wager Cal 单元格及对应卫星公司 (Tier 3)
                punterRows: [],             // 区域3: Punter 文本行
                punterErrList: [],          // 区域3: Punter 异常行
                aiPunterRows: [],           // 区域4: AI Punter 文本行
                aiPunterErrList: [],        // 区域4: AI Punter 异常行
                mainTableHeaders: [],       // 主矩阵表头结构
                mainTableRows: [],          // 主矩阵数据行结构 (带颜色标记)
                punterList: [],             // 结构化 Punter 列表
                aiPunterList: []            // 结构化 AI Punter 列表
            };

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
                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        // 过滤列数不足的主表行
                        if (tds.length >= 10) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            // (1) 提取表头结构
                            if (result.mainTableHeaders.length === 0 && (lineTxt.indexOf("Satellite") !== -1 || lineTxt.indexOf("Rpt Complete") !== -1)) {
                                result.mainTableHeaders = txts;
                            }

                            // (2) 提取 Rpt Complete 状态与背景颜色
                            if (lineTxt.indexOf("Complete") !== -1 && !result.rptCompleteInfo) {
                                for (var i = 0; i < tds.length; i++) {
                                    var cellVal = tds[i].innerText.trim();
                                    if (cellVal.indexOf("Complete") !== -1) {
                                        var bg = window.getComputedStyle(tds[i]).backgroundColor;
                                        // 检查是否呈红底 (RGB 255, 0, 0)
                                        var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);
                                        result.rptCompleteInfo = cellVal;
                                        if (isRed) result.rptCompleteHasErr = true;
                                        break;
                                    }
                                }
                            }

                            // (3) 提取卫星行数据 (以包含 'sport' 作为关键标记)
                            var sportIdx = txts.indexOf("sport");
                            if (sportIdx !== -1) {
                                result.matrixSatellitesCount++;
                                var sat = txts[sportIdx - 1]; // 卫星公司代号 (如 p0001)
                                var resetLog = txts[sportIdx - 2] || "0"; // Reset Log 数量
                                result.resetLogTotal += parseInt(resetLog) || 0;

                                var rowCells = [];
                                for (var c = 0; c < tds.length; c++) {
                                    var rawCellText = tds[c].innerText.trim();
                                    var cellText = rawCellText.toLowerCase();
                                    var cellBg = window.getComputedStyle(tds[c]).backgroundColor;

                                    // 判定是否为红底或 Error 文本 (只有红色的 Error 才是 Tier 1)
                                    var isRedCell = (cellBg.indexOf("255") !== -1 && cellBg.indexOf("0, 0") !== -1) || cellText === "error" || cellText.indexOf("error") !== -1;

                                    // 判定是否为黄色 Wager Cal 警告
                                    var isYellowCell = (cellText.indexOf("wager cal") !== -1 || cellBg.indexOf("255, 255") !== -1 || cellBg.indexOf("yellow") !== -1);

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
                            }
                        }
                    });
                }

                // ── 3.2 下方 Generate Punter / AI Punter (区域 3 与区域 4) ──
                var pRows = t.querySelectorAll("tr");
                pRows.forEach(function(r) {
                    var tds = r.querySelectorAll("td, th");
                    if (tds.length >= 2) {
                        var robotId = tds[0].innerText.trim();
                        var rptDate = tds[1].innerText.trim();
                        var fn = tds[2] ? tds[2].innerText.trim() : "";

                        var dateCell = tds[1];
                        var dateBg = window.getComputedStyle(dateCell).backgroundColor;
                        // 判定日期单元格是否呈红底或包含 Pending 挂起状态
                        var isRedDate = (dateBg.indexOf("255") !== -1 && dateBg.indexOf("0, 0") !== -1) || fn.indexOf("Pending") !== -1;

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

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        串联执行导航、点击搜索、初始数据抽取、Wager Cal 2次重试刷新、全量日志输出及 Tier 1/3 评判闭环。
        """
        # 1. 输出关卡站头日志
        self.log_station_header("第7站 RPT Compare", menu_id="apy_b0i8text")
        try:
            # 2. 导航切入 RPT Compare 菜单 (Menu ID: apy_b0i8text)
            self.navigate_to_menu("RPT Compare", menu_id="apy_b0i8text", section="NIW")

            # 3. 触发网页前端 search_data() 函数并智能等待加载完成
            self.driver.execute_script("""
                if (typeof search_data === "function") search_data();
            """)
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)

            # 4. 初始全量抓取页面数据
            p7_data = self._extract_page7_data()

            # ── 5. 用户专属核心机制: 黄色 Wager Cal 智能刷新 ──
            # 如果发现黄色的 Wager Cal，先点击相应的卫星公司名称进行刷新，最多尝试 2 次
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

                    # 每次刷新后等待网页重绘并再次调用 search_data()
                    self.wait_for_page_loaded(seconds=2.0, max_wait=25)
                    self.driver.execute_script("if (typeof search_data === 'function') search_data();")
                    self.wait_for_page_loaded(seconds=2.0, max_wait=25)

                    # 重新抓取数据核验 Wager Cal 是否消除
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
            self.log_check_method("校验规则: 只有红色的 Error / Reset Log > 0 才是 Tier 1 阻断；黄底 Wager Cal 与 Generate Punter 挂起为 Tier 3 仅通知提醒")

            # 7. 全量打印结构化巡检明细日志
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

            # 9. 严格执行 Tier 1 报错阻断判定 (唯独红色 Error、Reset Log > 0、Rpt Complete 异常会阻断)
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

            # 10. Tier 3 提醒汇总 (不阻断通关)
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

            # 11. 执行 Check Point 打勾并持久化数据到内存 Store
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
            # 异常兜底保护
            return self.handle_exception("niw_07", "RPT Compare", e)
