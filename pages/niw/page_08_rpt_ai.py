"""
================================================================================
第8站 RPT AI 关卡检查器 (pages/niw/page_08_rpt_ai.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐网页核心矩阵 (RPT Compare AI Tool):
   - 包含 24 家 Satellite 卫星公司 (d0005, d0008, d0009... 到 eq001)；
   - 包含多日期梯度 (10/08/2026, 11/08/2026...) 下的 3 大子列:
     1. Satellite Wager (卫星注单状态)
     2. RPT Punter (会员报表状态)
     3. RPT Punter IP (会员 IP 报表状态)
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 逐行打印 24 家 Satellite 卫星公司在各个日期下 3 大子列的 ok / 异常状态；
3. 判定标准 (Tier 1 致命报错阻断):
   - 若任何单元格出现非 ok、error 或红底，判定为 Tier 1 报错强阻断 Checkpoint 打勾！
4. 自动接入内存 CheckpointStore 存储与仿真实体表格可视化。
================================================================================
"""

# 导入基类 BaseChecker 与数据存储中心 CheckpointStore
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class RPTAIChecker(BaseChecker):
    """
    RPT AI 报表智能对比检查器类
    负责全面核对 Satellite 卫星节点在多个日期下 3 大子列的数据一致性。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        负责进入页面、执行前端 DOM 抽取、全量打印 24 家卫星公司明细、并执行 Tier 1 异常阻断判定。
        """
        # 1. 打印关卡页头日志
        self.log_station_header("第8站 RPT AI", menu_id="apy_b0i9text")
        try:
            # 2. 导航切入 RPT AI 页面菜单 (Menu ID: apy_b0i9text)
            self.navigate_to_menu("RPT AI", menu_id="apy_b0i9text", section="NIW")

            # 3. 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)

            # 4. 执行核心前端 JavaScript 脚本，提取 24 家 Satellite 卫星节点数据矩阵
            p8_data = self.driver.execute_script("""
                // 初始化前端解析结果字典
                var result = {
                    categoryName: "RCM",       // 下拉框分类名 (默认 RCM)
                    satellitesCount: 0,        // 抓取到的卫星公司总数
                    totalOkCount: 0,           // 处于 'ok' 绿底状态的单元格总数
                    errList: [],               // 错误单元格明细列表
                    satelliteRows: [],         // 文本摘要行
                    rawRows: [],               // 扁平结构化行
                    mainTableHeaders: [],      // 主矩阵原生表头
                    mainTableRows: [],         // 主矩阵原生带色彩数据行
                    punterList: [],            // Punter 列表
                    aiPunterList: []           // AI Punter 列表
                };

                // 1. 获取当前下拉框选中的分类名称 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                // 2. 遍历页面所有 table 标签定位主矩阵
                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 排除日期选择器插件的日历表格
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";
                    // 必须包含 Satellite 或 RPT Punter 等关键词才视为主表格
                    if (txt.indexOf("Satellite") === -1 && txt.indexOf("RPT Punter") === -1 && txt.indexOf("Punter IP") === -1) return;

                    var rows = t.querySelectorAll("tr");

                    rows.forEach(function(r) {
                        var tds = r.querySelectorAll("td, th");
                        // 过滤列数不足的数据行 (主矩阵列数通常在 5 列以上)
                        if (tds.length >= 5) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            // (1) 提取表头
                            if (result.mainTableHeaders.length === 0 && (lineTxt.indexOf("Satellite") !== -1 || lineTxt.indexOf("Date") !== -1)) {
                                result.mainTableHeaders = txts;
                            }

                            // 忽略子表头或说明装饰行
                            if (lineTxt.indexOf("Satellite Wager") !== -1 || lineTxt.indexOf("RPT Punter IP") !== -1 || lineTxt.indexOf("Date") !== -1) return;

                            var sat = "";
                            var dateStartIdx = 2;

                            // (2) 识别卫星节点代号 (如 nv01, d0005, eq001)
                            if (txts[0] === "RCM" || txts[0] === "LRCM" || txts[0] === "NIW") {
                                sat = txts[1];
                                dateStartIdx = 2; // 日期列从第 2 列开始
                            } else {
                                sat = txts[0];
                                dateStartIdx = 1; // 日期列从第 1 列开始
                            }

                            // 校验是否为合法卫星公司代码
                            if (sat && sat !== "Satellite" && sat.indexOf("Satellite") === -1) {
                                result.satellitesCount++;
                                var cellStatuses = [];
                                var rowHasErr = false;

                                var rowCells = [];
                                // 遍历该行所有单元格提取计算颜色
                                for (var c = 0; c < tds.length; c++) {
                                    var cellText = tds[c].innerText.trim().toLowerCase();
                                    var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                    // 检查是否红底 (RGB 255, 0, 0)
                                    var isRed = (bg.indexOf("255") !== -1 && bg.indexOf("0, 0") !== -1);
                                    // 检查是否绿底或文本为 'ok'
                                    var isGreen = (bg.indexOf("0, 128") !== -1 || bg.indexOf("0, 204") !== -1 || bg.indexOf("0, 230") !== -1 || bg.indexOf("0, 255") !== -1 || cellText === "ok");

                                    var bgTag = isRed ? "red" : (isGreen ? "green" : "white");
                                    rowCells.push({ text: tds[c].innerText.trim(), bg: bgTag });

                                    // 对日期数据列进行状态检验
                                    if (c >= dateStartIdx) {
                                        if (cellText === "ok" && !isRed) {
                                            result.totalOkCount++;
                                            cellStatuses.push("col" + (c - dateStartIdx + 1) + ":ok");
                                        } else if (cellText !== "") {
                                            // 出现非 ok 或红底单元格，触发异常标志
                                            rowHasErr = true;
                                            result.errList.push(sat + " (列" + c + "): " + cellText);
                                            cellStatuses.push("col" + (c - dateStartIdx + 1) + ":" + cellText + "[Tier 1 报错]");
                                        }
                                    }
                                }
                                result.mainTableRows.push(rowCells);

                                // 组装单行日志状态标签
                                var statusTag = " [OK/正常绿底]";
                                if (rowHasErr) statusTag = " [ERROR/Tier 1 异常阻断]";

                                var line = sat + ": 单元格状态(" + cellStatuses.length + "项) " + statusTag;
                                result.satelliteRows.push(line);
                                result.rawRows.push({
                                    satellite: sat,
                                    sub_cols: "Wager / Punter / IP",
                                    total_items: cellStatuses.length,
                                    errors: rowHasErr ? "Has Errors" : "0",
                                    status: rowHasErr ? "ERROR" : "OK",
                                    is_error: rowHasErr
                                });
                            }
                        }
                    });
                });

                // 3. 尝试抓取 Generate Punter / AI Punter 表格 (若存在)
                tables.forEach(function(t) {
                    var txt = t.innerText ? t.innerText.trim() : "";
                    if (txt.indexOf("Robot ID") !== -1 && (txt.indexOf("Rpt Date") !== -1 || txt.indexOf("Function") !== -1)) {
                        var pRows = t.querySelectorAll("tr");
                        pRows.forEach(function(r) {
                            var tds = r.querySelectorAll("td");
                            if (tds.length >= 2) {
                                var robotId = tds[0].innerText.trim();
                                var rptDate = tds[1].innerText.trim();
                                var fn = tds[2] ? tds[2].innerText.trim() : "";
                                var dateBg = window.getComputedStyle(tds[1]).backgroundColor;
                                var isRedDate = (dateBg.indexOf("255") !== -1 && dateBg.indexOf("0, 0") !== -1) || fn.indexOf("Pending") !== -1;
                                if (robotId && !isNaN(parseInt(robotId)) && rptDate.length >= 8) {
                                    var num = parseInt(robotId);
                                    var item = { robotId: robotId, rptDate: rptDate, fn: fn, isRed: isRedDate };
                                    if (num >= 800) {
                                        result.aiPunterList.push(item);
                                    } else {
                                        result.punterList.push(item);
                                    }
                                }
                            }
                        });
                    }
                });

                return result;
            """)

            # 5. 读取解析数据指标
            cat_name = p8_data.get("categoryName", "RCM")
            sat_count = p8_data.get("satellitesCount", 0)
            total_ok = p8_data.get("totalOkCount", 0)
            err_list = p8_data.get("errList", [])
            sat_rows = p8_data.get("satelliteRows", [])
            raw_rows = p8_data.get("rawRows", [])

            self.log_data_extracted(f"成功抓取 RPT AI ({cat_name}) 数据矩阵 ({sat_count} 个卫星节点) | 'ok' 单元格: {total_ok} 个 | 异常单元格: {len(err_list)} 个")
            self.log_check_method("全量核对 Satellite 卫星节点在各个日期下 3 大子列 (Satellite Wager, RPT Punter, RPT Punter IP) 状态 ( Tier 1 阻断规则 )")

            # 6. 无条件全量打印明细 (全量巡检数据明细)
            summary_lines = [f"【RPT AI 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in sat_rows])
            self.log_data_summary(summary_lines)

            # 7. 构筑 1:1 原生企业表格结构供 CheckpointStore 存储
            subtables = []
            main_rows = p8_data.get("mainTableRows", [])
            main_headers = p8_data.get("mainTableHeaders", [])
            if main_rows:
                if not main_headers:
                    first_len = len(main_rows[0])
                    main_headers = ["Col " + str(i+1) for i in range(first_len)]
                subtables.append({
                    "title": f"RPT AI Satellite Matrix ({cat_name})",
                    "header_bg": "#C8D7A6",
                    "headers": main_headers,
                    "rows": main_rows
                })
            else:
                table_headers = ["Satellite", "3 Sub-Columns", "Total Checks", "Errors", "Status"]
                table_rows = [
                    [
                        CheckpointStore.make_cell(r["satellite"]),
                        CheckpointStore.make_cell(r["sub_cols"]),
                        CheckpointStore.make_cell(str(r["total_items"])),
                        CheckpointStore.make_cell(r["errors"], bg="red" if r.get("is_error") else "green"),
                        CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                    ]
                    for r in raw_rows
                ]
                subtables.append({
                    "title": f"RPT AI Satellite Matrix ({cat_name})",
                    "header_bg": "#C8D7A6",
                    "headers": table_headers,
                    "rows": table_rows
                })

            p_list = p8_data.get("punterList", [])
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

            ai_p_list = p8_data.get("aiPunterList", [])
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

            # 8. Tier 1 报错阻断判定 (若有任何异常单元格强阻断 Checkpoint)
            if len(err_list) > 0:
                self.log_check_result(False, f"RPT AI 巡检发现 {len(err_list)} 处非 ok/红底异常单元格，强阻断 Checkpoint！")
                CheckpointStore.save(
                    page_key="niw_08",
                    title="RPT AI",
                    status=False,
                    tables=subtables,
                    summary=f"{len(err_list)} error(s) found in {sat_count} satellites"
                )
                return False
            else:
                self.log_check_result(True, f"RPT AI 全部 {sat_count} 个 Satellite 卫星节点所有子列均显示 'ok' 绿底，巡检合格！")

            # 9. 点击 Check Point 打勾通关
            self.click_checkpoint()
            CheckpointStore.save(
                page_key="niw_08",
                title="RPT AI",
                status=True,
                tables=subtables,
                summary=f"全部 {sat_count} 个 Satellite 节点全部绿底 ok"
            )
            return True

        except Exception as e:
            # 异常兜底保护
            return self.handle_exception("niw_08", "RPT AI", e)
