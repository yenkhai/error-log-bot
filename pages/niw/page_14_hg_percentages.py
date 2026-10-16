"""
================================================================================
第13站 HG Percentages 关卡检查器 (pages/niw/page_13_hg_percentages.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面功能与抓取目标:
   - 本页面监控 HG 占比及编辑器/投注同步状态。
   - 抓取字段: Company (公司代码如 s0010, k0002), Count (Editor) (编辑器计数),
     Editor (编辑器状态), Count (Betting) (投注计数), Betting (投注状态)。

2. 校验与阻断标准 (Tier 1 强阻断):
   - 核心考核指标为 `Editor` 与 `Betting` 两个状态列。
   - 要求两个状态均必须显示为绿字 `"Correct"`。
   - 如果任何一个状态不等于 "Correct"，判定为 **Tier 1 致命报错强阻断 Checkpoint**！
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class HGPercentagesChecker(BaseChecker):
    """
    HG Percentages 关卡检查器类
    负责监控各公司节点的 Editor (编辑器) 与 Betting (投注) 状态，
    严格核验两项指标是否均为 Correct。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 HG Percentages 页面 (apy_b0i15text)
        2. 执行前端 JavaScript 提取所有公司的 Editor 与 Betting 状态
        3. 严格核验两项指标是否均为 Correct (任何非 Correct 均属 Tier 1 致命异常阻断 Checkpoint)
        4. 打印全量明细日志并将数据存储至 CheckpointStore
        5. 巡检通过后点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i15text (对应 NIW 区域的 HG Percentages 选项)
        self.log_station_header("第14站 HG Percentages", menu_id="apy_b0i16text")
        try:
            # [步骤 2] 导航切入 HG Percentages 页面
            self.navigate_to_menu("HG Percentages", menu_id="apy_b0i16text", section="NIW")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)

            # [步骤 3] JavaScript 脚本精准抓取 HG Percentages 表格数据
            p13_data = self.driver.execute_script("""
                // 1. 初始化前端抓取结果字典
                var result = {
                    category: "RCM",   // 当前业务分类名称 (如 RCM / LRCM)
                    rows: [],          // 格式化文本行列表 (供日志展示)
                    rawRows: [],       // 结构化对象行列表 (供 HTML 仪表盘展示)
                    errCount: 0,       // 异常节点统计
                    errList: []        // 异常节点详细错误描述列表
                };

                // 2. 获取下拉框当前选择的分区 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.category = sel.options[sel.selectedIndex].text;
                }

                // 3. 遍历页面所有 table 标签定位目标监控表格
                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 过滤日历控件表格
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 通过表头关键字 Company, Editor, Betting 锁定目标表格
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Editor") !== -1 && txt.indexOf("Betting") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            // 确保列数充足 (至少 5 列: Company | Count(Editor) | Editor | Count(Betting) | Betting)
                            if (tds.length >= 5) {
                                var com = tds[0].innerText.trim();
                                var cEditor = tds[1].innerText.trim();
                                var editor = tds[2].innerText.trim();
                                var cBetting = tds[3].innerText.trim();
                                var betting = tds[4].innerText.trim();

                                // 过滤表头行
                                if (com && com !== "Company" && com.indexOf("Count") === -1) {
                                    // 4. 只要 Editor 或 Betting 有任何一个不是 Correct 即判定为异常
                                    var editorCount = Number(cEditor.replace(/,/g, ""));
                                    var bettingCount = Number(cBetting.replace(/,/g, ""));
                                    var isErr = editorCount > 0 || bettingCount > 0 || editor.toLowerCase() !== "correct" || betting.toLowerCase() !== "correct";
                                    var tag = " [OK/正常绿字]";
                                    if (isErr) {
                                        result.errCount++;
                                        tag = " [ERROR/Tier 1 异常阻断]";
                                        result.errList.push(com + " Count(Editor): " + cEditor + ", Editor: " + editor + ", Count(Betting): " + cBetting + ", Betting: " + betting);
                                    }

                                    // 5. 格式化日志输出字符串
                                    var line = com + ": Count(Editor) = " + cEditor + ", Editor = " + editor + ", Count(Betting) = " + cBetting + ", Betting = " + betting + tag;
                                    result.rows.push(line);

                                    // 6. 存入结构化数据列表供仪表盘展示
                                    result.rawRows.push({
                                        company: com,
                                        c_editor: cEditor,
                                        editor: editor,
                                        c_betting: cBetting,
                                        betting: betting,
                                        status: isErr ? "ERROR" : "OK",
                                        is_error: isErr
                                    });
                                }
                            }
                        });
                    }
                });

                // 将解析结果返回给 Python 执行端
                return result;
            """)

            cat_name = p13_data.get("category", "RCM")
            rows = p13_data.get("rows", [])
            raw_rows = p13_data.get("rawRows", [])
            err_count = p13_data.get("errCount", 0)
            err_list = p13_data.get("errList", [])

            if not raw_rows:
                raise RuntimeError("HG Percentages 未读取到公司数据，不能判定通过")

            self.log_data_extracted(f"成功抓取 HG Percentages ({cat_name}) 数据 | 监控节点: {len(rows)} 项 (异常 {err_count} 项)")
            self.log_check_method("全量校验 HG Percentages 所有公司节点的 两项 Count 必须为 0，Editor 与 Betting 必须为 Correct (Tier 1 强阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【HG Percentages 全量巡检数据明细 ({cat_name})】:"]

            if rows:
                summary_lines.append(f"--- [1. HG Percentages 监控板块 (共 {len(rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in rows])

            self.log_data_summary(summary_lines)

            table_headers = ["Company", "Count (Editor)", "Editor", "Count (Betting)", "Betting", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["company"]),
                    CheckpointStore.make_cell(r["c_editor"], bg="red" if float(r["c_editor"].replace(",", "") or 0) > 0 else "green"),
                    CheckpointStore.make_cell(r["editor"], bg="red" if r.get("is_error") and r["editor"].lower() != "correct" else "green"),
                    CheckpointStore.make_cell(r["c_betting"], bg="red" if float(r["c_betting"].replace(",", "") or 0) > 0 else "green"),
                    CheckpointStore.make_cell(r["betting"], bg="red" if r.get("is_error") and r["betting"].lower() != "correct" else "green"),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # [步骤 5] Tier 1 报错阻断判定
            # 只要存在 Editor 或 Betting 非 Correct，阻断 Checkpoint
            if err_count > 0:
                self.log_check_result(False, f"HG Percentages 巡检发现 Tier 1 致命异常: 存在 {err_count} 项节点 Count >0 或状态非 Correct ({', '.join(err_list)})，强阻断 Checkpoint！")
                CheckpointStore.save(
                    derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                    page_key="niw_14",
                    title="HG Percentages",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Errors: {err_count}"
                )
                return False
            else:
                self.log_check_result(True, "HG Percentages 全部公司节点 两项 Count 均为 0，Editor 与 Betting 均为 Correct，状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            CheckpointStore.save(
                derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                page_key="niw_14",
                title="HG Percentages",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary="All Correct"
            )
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("niw_14", "HG Percentages", e)
