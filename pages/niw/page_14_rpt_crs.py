"""
================================================================================
第14站 RPT CRS 关卡检查器 (pages/niw/page_14_rpt_crs.py)
--------------------------------------------------------------------------------
【核心功能详解与智能加载判定规则】
1. 页面特性与抓取目标:
   - 页面包含 Agency、API、Credit 等多个历史日期的区间同步核算数据。
   - 状态为异步 AJAX 加载，每个区间的状态（`ok`、`error`、`-`）会逐步填充到单元格中。
2. 智能动态轮询（Smart Wait）:
   - 拒绝盲目固定等待！每秒动态轮询 DOM，检测所有监控单元格是否已脱离空白/加载中状态。
   - 一旦全部 12 项状态完整就绪（全部填充），立即进行校验；最多轮询等待 30 秒。
3. 严格校验与阻断标准 (Tier 1 强阻断):
   - 正常通过状态: 单元格必须明确为 `"ok"` 或 `"-"`。
   - 异常阻断判定:
     * 单元格包含 `"error"` 或呈现红字/红底 -> **Tier 1 阻断**
     * 超时后单元格仍为空白 `""`（代表接口未加载完成/计算挂起）-> **Tier 1 阻断（防止放水误判）**
4. 巡检通过:
   - 只有在 100% 数据加载完毕且全部状态为 `ok` / `-` 时，才允许点击 Checkpoint！
================================================================================
"""

import time
from core.base_checker import BaseChecker


class RPTCRSChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第14站 RPT CRS", menu_id="apy_b0i16text", page_key="niw_14")
        try:
            # 1. 导航切入 RPT CRS 页面 (基础初始导航 3 秒)
            self.navigate_to_menu("RPT CRS", menu_id="apy_b0i16text", section="NIW")

            # 2. 智能动态轮询：等待所有表格中每个区间的 AJAX 状态数据完全渲染填充完毕
            max_poll_seconds = 60
            poll_interval = 1.5
            start_time = time.time()
            is_fully_loaded = False
            last_status = {}

            self.wait_for_page_loaded(seconds=2, max_wait=30)
            self.log("[WAIT] 正在动态监测 RPT CRS 所有区间 AJAX 数据加载进度 (最大等待 30 秒)...")

            while (time.time() - start_time) < max_poll_seconds:
                poll_res = self.driver.execute_script("""
                    var tables = document.querySelectorAll("table");
                    var totalCells = 0;
                    var filledCells = 0;
                    var emptyCells = 0;

                    tables.forEach(function(t) {
                        if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                        var txt = t.innerText ? t.innerText.trim() : "";
                        if (txt.indexOf("Agency") !== -1 || txt.indexOf("API") !== -1 || txt.indexOf("Credit") !== -1) {
                            var rows = t.querySelectorAll("tr");
                            rows.forEach(function(r) {
                                var tds = r.querySelectorAll("td");
                                if (tds.length >= 2) {
                                    // 检查除第 1 列日期/标题外的所有状态列
                                    for (var i = 1; i < tds.length; i++) {
                                        var cTxt = tds[i].innerText.trim();
                                        totalCells++;
                                        if (cTxt === "" || cTxt.toLowerCase().indexOf("loading") !== -1) {
                                            emptyCells++;
                                        } else {
                                            filledCells++;
                                        }
                                    }
                                }
                            });
                        }
                    });

                    return {
                        totalCells: totalCells,
                        filledCells: filledCells,
                        emptyCells: emptyCells,
                        isComplete: (totalCells > 0 && emptyCells === 0)
                    };
                """)

                last_status = poll_res
                if poll_res.get("isComplete", False):
                    is_fully_loaded = True
                    elapsed = round(time.time() - start_time, 1)
                    self.log(f"[WAIT] ✅ RPT CRS 页面数据已在 {elapsed} 秒内 100% 加载完毕 (已就绪: {poll_res.get('filledCells')}/{poll_res.get('totalCells')})！")
                    break
                else:
                    elapsed = int(time.time() - start_time)
                    filled = poll_res.get("filledCells", 0)
                    total = poll_res.get("totalCells", 0)
                    if elapsed % 3 == 0:
                        self.log(f"[WAIT] 数据计算同步中... (当前已就绪: {filled}/{total} 项，耗时 {elapsed}s)")
                    time.sleep(poll_interval)

            if not is_fully_loaded:
                self.log(f"[WARN] 动态等待超时 (30s)，当前就绪: {last_status.get('filledCells', 0)}/{last_status.get('totalCells', 0)} 项，启动严格校验！")

            # 3. 核心 JavaScript 提取全量数据并执行严格判定
            p14_data = self.driver.execute_script("""
                var result = {
                    category: "RCM",
                    sections: [],
                    allRows: [],
                    tier1ErrorCount: 0,
                    unloadedCount: 0,
                    errList: []
                };

                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.category = sel.options[sel.selectedIndex].text;
                }

                function isRed(el) {
                    if (!el) return false;
                    try {
                        var style = window.getComputedStyle(el);
                        var bg = style.backgroundColor || "";
                        var color = style.color || "";
                        if (bg.indexOf("255, 0, 0") !== -1 || bg.indexOf("red") !== -1 ||
                            color.indexOf("255, 0, 0") !== -1 || color.indexOf("red") !== -1) {
                            return true;
                        }
                    } catch(e) {}
                    return false;
                }

                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    if (txt.indexOf("Agency") !== -1 || txt.indexOf("API") !== -1 || txt.indexOf("Credit") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            if (tds.length >= 2) {
                                var cells = [];
                                var isHeader = false;
                                var hasErr = false;
                                var hasUnloaded = false;

                                for (var i = 0; i < tds.length; i++) {
                                    var cellTxt = tds[i].innerText.trim();
                                    var isCellRed = isRed(tds[i]);
                                    var lower = cellTxt.toLowerCase();

                                    if (cellTxt === "Agency" || cellTxt === "API" || cellTxt === "Credit" || cellTxt === "Date" || cellTxt === "Status") {
                                        isHeader = true;
                                    }

                                    // 检查错误与未加载项 (仅对数据行判定)
                                    if (!isHeader && i >= 1) {
                                        if (isCellRed || lower === "error" || lower.indexOf("fail") !== -1) {
                                            hasErr = true;
                                        } else if (cellTxt === "" || lower.indexOf("loading") !== -1) {
                                            hasUnloaded = true;
                                        }
                                    }

                                    cells.push(cellTxt === "" ? "[未加载/空]" : cellTxt);
                                }

                                if (!isHeader && cells.length > 0 && cells[0] !== "[未加载/空]") {
                                    var lineText = cells.join(" | ");
                                    var statusTag = " [OK/正常]";

                                    if (hasErr) {
                                        result.tier1ErrorCount++;
                                        statusTag = " 🔴[ERROR/Tier 1 状态异常阻断]";
                                        result.errList.push(lineText + " (状态报错)");
                                    } else if (hasUnloaded) {
                                        result.tier1ErrorCount++;
                                        result.unloadedCount++;
                                        statusTag = " 🔴[ERROR/Tier 1 数据未加载完成阻断]";
                                        result.errList.push(lineText + " (数据未加载)");
                                    }

                                    result.allRows.push(lineText + statusTag);
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            cat_name = p14_data.get("category", "RCM")
            all_rows = p14_data.get("allRows", [])
            tier1_errors = p14_data.get("tier1ErrorCount", 0)
            unloaded_cnt = p14_data.get("unloadedCount", 0)
            err_list = p14_data.get("errList", [])

            # 4. 组装全量巡检数据日志
            all_summary = [f"【RPT CRS 全量巡检数据明细 ({cat_name})】:"]
            all_summary.append(f"--- [RPT CRS 监控板块 (共 {len(all_rows)} 个核算节点)] ---")
            if all_rows:
                all_summary.extend([f"   * {r}" for r in all_rows])
            else:
                all_summary.append("   * 🔴[ERROR/未抓取到任何 RPT CRS 表格数据]")

            self.log_data_extracted(f"成功抓取 RPT CRS ({cat_name}) 监控指标共 {len(all_rows)} 项 (状态异常: {tier1_errors - unloaded_cnt}, 未加载空缺: {unloaded_cnt})")
            self.log_check_method("智能动态轮询等待 AJAX 100% 加载完毕 -> 严格校验每一个区间节点的同步状态 (必须为 ok 或 -，出现 error、红字或空白未加载均直接 Tier 1 阻断)")
            self.log_data_summary(all_summary)

            # 5. Checkpoint 巡检结论判定
            if tier1_errors > 0:
                if unloaded_cnt > 0:
                    self.log(f"[Error] RPT CRS 检测到 {unloaded_cnt} 项数据尚未加载完成，属于 Tier 1 致命异常，严禁放水，阻断 Checkpoint！")
                if (tier1_errors - unloaded_cnt) > 0:
                    self.log(f"[Error] RPT CRS 检测到 {tier1_errors - unloaded_cnt} 项节点状态为 error/红字异常，阻断 Checkpoint！")
                
                self.log_check_result(False, f"RPT CRS 存在 {tier1_errors} 项 Tier 1 异常 ({', '.join(err_list[:3])})，阻断 Checkpoint。")
                return False
            else:
                self.log_check_result(True, "RPT CRS 全部区间节点数据 100% 加载完毕且同步状态完全正常！")

            # 6. 巡检通过，点击 Checkpoint 提交通关
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"RPT CRS 检查出现异常: {e}")
            return False
