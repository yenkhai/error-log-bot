"""
================================================================================
第12站 Wsum Sport 关卡检查器 (pages/niw/page_12_wsum_sport.py)
--------------------------------------------------------------------------------
【核心功能详解与学习指南】
1. 页面功能与抓取目标:
   - 本页面监控的是体育注单与 Wsum 统计是否完全一致 (Wsum & Wager Winloss Compare)。
   - 抓取字段: Company (公司名称), Type (体育类型如 sport), Total Wsum (总Wsum),
     Total Betslips (总注单数), Remark (备注判定), Last Refresh (最后刷新时间)。

2. 校验与阻断标准 (Tier 1 强阻断):
   - 核心考核指标为 `Remark` 字段。
   - 正常情况下，`Total Wsum` 应等于 `Total Betslips`，Remark 显示绿字 `"Correct"`。
   - 如果 Remark 文本不等于 "Correct" (例如显示 Error 或数据不匹配)，判定为 **Tier 1 致命报错强阻断 Checkpoint**！
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class WsumSportChecker(BaseChecker):
    """
    Wsum Sport 体育注单总计核查检查器类
    负责监控 Wsum 统计与注单数的一致性，核验所有节点的 Remark 是否为 Correct。
    """

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 Wsum Sport 页面 (apy_b0i14text)
        2. 执行前端 JavaScript 提取所有公司的 Wsum、Betslips 与 Remark 字段
        3. 严格核验 Remark 是否为 Correct (任何非 Correct 均属 Tier 1 致命异常阻断 Checkpoint)
        4. 打印全量明细日志并将数据存储至 CheckpointStore
        5. 巡检通过后点击关卡 Checkpoint 按钮
        """
        # [步骤 1] 打印站头，传入 Target Menu ID: apy_b0i14text (对应 NIW 区域的 Wsum Sport 选项)
        self.log_station_header("第12站 Wsum Sport", menu_id="apy_b0i14text")
        try:
            # [步骤 2] 导航切入 Wsum Sport 页面
            self.navigate_to_menu("Wsum Sport", menu_id="apy_b0i14text", section="NIW")

            # 智能等待页面数据加载完毕
            self.wait_for_page_loaded(seconds=1.5, max_wait=35)

            # [步骤 3] JavaScript 脚本精准抓取 Wsum Sport 表格数据
            p12_data = self.driver.execute_script("""
                // 1. 初始化解析结果对象
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
                    // 过滤日历插件控件
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;
                    var txt = t.innerText ? t.innerText.trim() : "";

                    // 通过表头关键字段 Company, Total Wsum, Total Betslips 锁定表格
                    if (txt.indexOf("Company") !== -1 && txt.indexOf("Total Wsum") !== -1 && txt.indexOf("Total Betslips") !== -1) {
                        var rows = t.querySelectorAll("tr");
                        rows.forEach(function(r) {
                            var tds = r.querySelectorAll("td, th");
                            // 确保列数充足 (至少 5 列: Company | Type | Total Wsum | Total Betslips | Remark)
                            if (tds.length >= 5) {
                                var com = tds[0].innerText.trim();
                                var type = tds[1].innerText.trim();
                                var wsum = tds[2].innerText.trim();
                                var betslips = tds[3].innerText.trim();
                                var remark = tds[4].innerText.trim();

                                // 过滤表头行
                                if (com && com !== "Company") {
                                    // 4. 判断 Remark 是否非 Correct (不区分大小写)
                                    var isErr = remark.toLowerCase() !== "correct";
                                    var tag = " [OK/正常绿字]";
                                    if (isErr) {
                                        result.errCount++;
                                        tag = " [ERROR/Tier 1 Remark异常阻断]";
                                        result.errList.push(com + " Remark: " + remark);
                                    }

                                    // 5. 格式化日志输出字符串
                                    var line = com + " (" + type + "): Total Wsum = " + wsum + ", Total Betslips = " + betslips + ", Remark = " + remark + tag;
                                    result.rows.push(line);

                                    // 6. 存入结构化数据列表
                                    result.rawRows.push({
                                        company: com,
                                        type: type,
                                        wsum: wsum,
                                        betslips: betslips,
                                        remark: remark,
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

            cat_name = p12_data.get("category", "RCM")
            rows = p12_data.get("rows", [])
            raw_rows = p12_data.get("rawRows", [])
            err_count = p12_data.get("errCount", 0)
            err_list = p12_data.get("errList", [])

            if not raw_rows:
                raise RuntimeError("Wsum Sport 未读取到公司数据，不能判定通过")

            self.log_data_extracted(f"成功抓取 Wsum Sport ({cat_name}) 数据 | 监控节点: {len(rows)} 项 (异常 {err_count} 项)")
            self.log_check_method("全量校验 Wsum Sport 所有公司节点的 Remark 必须为 Correct (Tier 1 强阻断)")

            # [步骤 4] 无条件全量明细打印 (生成完整的文本格式巡检报告)
            summary_lines = [f"【Wsum Sport 全量巡检数据明细 ({cat_name})】:"]

            if rows:
                summary_lines.append(f"--- [1. Wsum Sport 监控板块 (共 {len(rows)} 个公司节点)] ---")
                summary_lines.extend([f"   * {r}" for r in rows])

            self.log_data_summary(summary_lines)

            table_headers = ["Company", "Type", "Total Wsum", "Total Betslips", "Remark", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["company"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["wsum"]),
                    CheckpointStore.make_cell(r["betslips"]),
                    CheckpointStore.make_cell(r["remark"], bg="red" if r.get("is_error") else "green"),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # [步骤 5] Tier 1 报错阻断判定
            # 只要存在 1 项 Remark 非 Correct，强阻断 Checkpoint
            if err_count > 0:
                self.log_check_result(False, f"Wsum Sport 巡检发现 Tier 1 致命异常: 存在 {err_count} 项 Remark 非 Correct ({', '.join(err_list)})，强阻断 Checkpoint！")
                CheckpointStore.save(
                    derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                    page_key="niw_12",
                    title="Wsum Sport",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Errors: {err_count}"
                )
                return False
            else:
                self.log_check_result(True, "Wsum Sport 全部公司节点 Remark 均为 Correct，状态完全正常！")

            # [步骤 6] 解封并自动点击 Checkpoint
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            CheckpointStore.save(
                derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                page_key="niw_12",
                title="Wsum Sport",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary="All remarks Correct"
            )
            return True

        except Exception as e:
            # 捕获未知异常并自动记录 CheckpointStore
            return self.handle_exception("niw_12", "Wsum Sport", e)
