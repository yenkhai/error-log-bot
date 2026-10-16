"""
================================================================================
第9站 RPT Compare UTC 关卡检查器 (pages/niw/page_09_rpt_compare_utc.py)
--------------------------------------------------------------------------------
全量日志与判定规则:
1. 抓取与对齐用户截图圈出的红框矩阵 (RPT Compare UTC Tool):
   - 包含 24 小时时间行 (Hour 00 到 Hour 23)；
   - 包含多日期 (06/08/2026 ~ 12/08/2026) 及多 Satellite 卫星 (tq001, eq001...)；
   - 包含每个 Satellite 下的 3 大子列 (UTC Curr, UTC PL, UTC Odd)；
2. 无条件全量明细打印 (Unconditional Line-by-Line Log):
   - 逐行打印 24 小时 (00 ~ 23) 在各个日期下所有子列的 ok / 异常校验结论；
3. 判定标准 (Tier 1 致命报错阻断):
   - 若任何单元格出现非 ok、error 或红底，判定为 Tier 1 报错阻断 Checkpoint！
4. 自动接入 24h 滚动历史存档与 HTML 仪表盘 (dashboard.html)。
================================================================================
"""

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class RPTCompareUTCChecker(BaseChecker):
    """
    RPT Compare UTC 报表对比检查器类
    负责全面核对 24 小时时间行 (00~23) 在多个日期与 Satellite 节点下的 UTC Curr, PL, Odd 子列状态。
    """

    def _extract_data(self):
        return self.driver.execute_script(r"""

                // 1. 初始化返回给 Python 的数据容器
                var result = {
                    categoryName: "RCM",   // 当前分类名称 (默认 RCM)
                    pendingCells: 0,
                    uniqueHours: [],
                    hoursCount: 0,          // 抓取到的时间段总数 (正常为 24 小时 00~23)
                    totalOkCount: 0,        // 状态为 'ok' 绿底的单元格总数
                    errList: [],            // 异常单元格详细记录列表
                    hourRows: [],           // 格式化的文本摘要日志行
                    rawRows: []             // 结构化数据行 (供 HTML 仪表盘展示)
                };

                // 2. 获取当前下拉菜单中选中的分类名称 (如 RCM / LRCM)
                var sel = document.getElementById("com_select") || document.querySelector("select");
                if (sel && sel.selectedIndex >= 0) {
                    result.categoryName = sel.options[sel.selectedIndex].text;
                }

                // 3. 获取并遍历页面中所有的 <table> 标签
                var tables = document.querySelectorAll("table");
                tables.forEach(function(t) {
                    // 过滤掉日历控件的表格 (避免被干扰)
                    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null) return;

                    // 获取当前表格的完整纯文本
                    var txt = t.innerText ? t.innerText.trim() : "";
                    // 只有包含 'Hour' 或 'UTC' 关键词的表格才是我们要抓取的主矩阵表格
                    if (txt.indexOf("Hour") === -1 && txt.indexOf("UTC") === -1) return;

                    // 4. 获取表格中的所有数据行 <tr>
                    var rows = t.querySelectorAll("tr");
                    rows.forEach(function(r) {
                        // 获取当前行的所有单元格 (td 或 th)
                        if (r.closest("table") !== t) return;
                        var tds = Array.from(r.children).filter(c => /^(TD|TH)$/.test(c.tagName));
                        // 矩阵行通常拥有较多列 (至少 5 列以上)
                        if (tds.length >= 5) {
                            var txts = [];
                            tds.forEach(function(c) { txts.push(c.innerText.trim()); });
                            var lineTxt = txts.join(" ");

                            // 排除表头行 (包含 Hour, Type, UTC PL 等列名)
                            if (lineTxt.indexOf("Hour") !== -1 || lineTxt.indexOf("Type") !== -1 || lineTxt.indexOf("UTC PL") !== -1) return;

                            var hourVal = "";        // 小时字段值 (如 00, 01, ..., 23)
                            var typeVal = "";        // 类型字段值 (如 sport)
                            var dateStartIdx = 2;    // 数据列起始索引 (默认从第 2 列开始)

                            // 判断是否有前置公司标识 (如 RCM, LRCM, NIW)
                            if (txts[0] === "RCM" || txts[0] === "LRCM" || txts[0] === "NIW") {
                                hourVal = txts[1];       // 第 1 列为小时数
                                typeVal = txts[2];       // 第 2 列为类型
                                dateStartIdx = 3;        // 数据状态列从第 3 列开始
                            } else {
                                hourVal = txts[0];       // 第 0 列为小时数
                                typeVal = txts[1];       // 第 1 列为类型
                                dateStartIdx = 2;        // 数据状态列从第 2 列开始
                            }

                            // 5. 确保提取到有效的小时字段，且类型为有效业务类型
                            if (/^(?:[01]?\d|2[0-3])$/.test(hourVal) && typeVal.toLowerCase() === "sport") {
                                var hourNumber = parseInt(hourVal, 10);
                                if (result.uniqueHours.indexOf(hourNumber) === -1) result.uniqueHours.push(hourNumber);
                                result.hoursCount++;     // 统计有效小时行计数
                                var rowHasPending = false;
                                var rowHasErr = false;   // 标记当前行是否存在异常单元格

                                // 6. 遍历当前行的所有数据列单元格
                                for (var c = dateStartIdx; c < tds.length; c++) {
                                    var cellText = tds[c].innerText.trim().toLowerCase();
                                    // 获取单元格计算后的背景色样式
                                    var bg = window.getComputedStyle(tds[c]).backgroundColor;
                                    // 判定是否为红底 (RGB 中含有 255 且包含 0, 0 即红色预警)
                                    var rgb = bg.match(/[\d.]+/g) || [];
                                    var isRed = rgb.length >= 3 && +rgb[0] >= 170 && +rgb[1] <= 110 && +rgb[2] <= 110;
                                    var loadingImage = Array.from(tds[c].querySelectorAll("img")).some(img => img.getClientRects().length > 0);
                                    var pending = !isRed && (!cellText || /loading|please wait|加载中/.test(cellText) || loadingImage);
                                    if (pending) {
                                        result.pendingCells++;
                                        rowHasPending = true;
                                        continue;
                                    }

                                    // 正常情况：文本为 'ok' 且不是红底
                                    if (cellText === "ok" && !isRed) {
                                        result.totalOkCount++;
                                    } else {
                                        // 异常情况：单元格有文本但不是 ok，或者呈现红底
                                        rowHasErr = true;
                                        result.errList.push("Hour " + hourVal + " (列" + c + "): " + cellText);
                                    }
                                }

                                // 7. 拼接当前小时行的巡检状态标签
                                var statusTag = " [OK/正常绿底]";
                                if (rowHasErr) statusTag = " [ERROR/Tier 1 异常阻断]";

                                var line = "Hour " + hourVal + " (" + typeVal + "): 单元格校验通过 " + statusTag;
                                result.hourRows.push(line);

                                // 8. 存入供仪表盘呈现的结构化数据字典
                                result.rawRows = result.rawRows || [];
                                result.rawRows.push({
                                    hour: "Hour " + hourVal,
                                    type: typeVal,
                                    status: rowHasErr ? "ERROR" : (rowHasPending ? "LOADING" : "OK"),
                                    is_error: rowHasErr
                                });
                            }
                        }
                    });
                });

                // 将解析提取的结果对象返回给 Python
                return result;

        """)

    def _wait_for_matrix_loaded(self, timeout=120):
        import time
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException
        previous = None
        stable_since = None
        last_notice = time.monotonic()
        last_state = {}
        self.log("[LOAD] RPT Compare UTC：等待 00–23 时全部数据，加载图标和空白不算通过。")

        def ready(driver):
            nonlocal previous, stable_since, last_notice, last_state
            state = self._extract_data()
            last_state = state
            idle = driver.execute_script("return document.readyState === 'complete' && (typeof jQuery === 'undefined' || jQuery.active === 0);")
            now = time.monotonic()
            complete = len(set(state.get('uniqueHours', []))) == 24 and state.get('pendingCells', 0) == 0 and state.get('hoursCount', 0) >= 24
            if now - last_notice >= 15:
                self.log(f"[LOAD] UTC：已找到 {len(set(state.get('uniqueHours', [])))}/24 小时，仍有 {state.get('pendingCells', 0)} 格加载中。")
                last_notice = now
            if not idle or not complete:
                previous, stable_since = None, None
                return False
            signature = repr(state)
            if previous != signature or stable_since is None:
                previous, stable_since = signature, now
                return False
            return state if now - stable_since >= 1.0 else False

        try:
            return WebDriverWait(self.driver, timeout, poll_frequency=0.5).until(ready)
        except TimeoutException as exc:
            hours = len(set(last_state.get('uniqueHours', [])))
            pending = last_state.get('pendingCells', 0)
            raise RuntimeError(f"UTC 数据加载超时（{timeout}秒）：{hours}/24 小时，{pending} 格仍加载中；尚未检查数据或点击 Checkpoint，请 Resume 重试。") from exc

    def check(self) -> bool:
        """
        [关卡主巡检方法]
        1. 导航进入 RPT Compare UTC 页面 (apy_b0i10text)
        2. 点击 Search 按钮获取最新数据
        3. 执行前端 JavaScript 深度抓取 24 小时时间段矩阵
        4. 打印全量明细日志并进行 Tier 1 报错阻断校验 (任何红底或非 ok 均阻断)
        5. 存储结果至 CheckpointStore 并点击关卡 Checkpoint 按钮
        """
        # 1. 打印第 9 站日志头信息
        self.log_station_header("第9站 RPT Compare UTC", menu_id="apy_b0i10text")
        try:
            # 2. 导航切入 RPT Compare UTC 页面 (Menu ID: apy_b0i10text)
            self.navigate_to_menu("RPT Compare UTC", menu_id="apy_b0i10text", section="NIW")

            # 3. 点击 Search 触发最新查询
            if not self.click_search_button():
                raise RuntimeError("RPT Compare UTC：找不到 Search 按钮，未开始查询")

            # Loading icons/blank cells are pending data, never evidence of OK.
            try:
                p9_data = self._wait_for_matrix_loaded(timeout=120)
            except RuntimeError as exc:
                if "UTC 数据加载超时" not in str(exc):
                    raise
                self.log("[WARN] UTC 加载超过 120 秒，重新点击一次 Search 后再等待 120 秒。")
                if not self.click_search_button():
                    raise RuntimeError("UTC 加载超时后无法重新点击 Search，巡检暂停。") from exc
                try:
                    p9_data = self._wait_for_matrix_loaded(timeout=120)
                except RuntimeError as retry_exc:
                    if "UTC 数据加载超时" not in str(retry_exc):
                        raise
                    raise RuntimeError("UTC 首次等待 120 秒并重新 Search 一次后，再等 120 秒仍未加载完成，巡检暂停；请检查系统后 Resume 重试。") from retry_exc

            # 6. 从前端返回的字典中解析各项指标
            cat_name = p9_data.get("categoryName", "RCM")
            hours_count = p9_data.get("hoursCount", 0)
            total_ok = p9_data.get("totalOkCount", 0)
            err_list = p9_data.get("errList", [])
            hour_rows = p9_data.get("hourRows", [])
            raw_rows = p9_data.get("rawRows", [])

            # 7. 打印数据提取日志与巡检逻辑方法说明
            self.log_data_extracted(f"成功抓取 RPT Compare UTC ({cat_name}) 数据矩阵 ({hours_count} 个时间段 00~23) | 'ok' 单元格: {total_ok} 个 | 异常单元格: {len(err_list)} 个")
            self.log_check_method("全量核对 24 小时 (00~23) 在各个日期与 Satellite 节点下 UTC Curr, PL, Odd 子列状态 ( Tier 1 阻断规则 )")

            # 8. 无条件全量明细打印 (全量巡检数据明细)
            summary_lines = [f"【RPT Compare UTC 矩阵数据明细 ({cat_name})】:"]
            summary_lines.extend([f"   * {row}" for row in hour_rows])
            self.log_data_summary(summary_lines)

            # 9. 构建存储中心 (CheckpointStore) 表头与表格行
            table_headers = ["Hour Segment", "Type", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["hour"]),
                    CheckpointStore.make_cell(r["type"]),
                    CheckpointStore.make_cell(r["status"], bg="red" if r.get("is_error") else "green")
                ]
                for r in raw_rows
            ]

            # 10. Tier 1 致命报错阻断判定
            if len(err_list) > 0:
                # 存在异常单元格，判定失败，阻断当前关卡
                self.log_check_result(False, f"RPT Compare UTC 巡检发现 {len(err_list)} 处非 ok/红底异常单元格，强阻断 Checkpoint！")
                CheckpointStore.save(
                    derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                    page_key="niw_09",
                    title="RPT Compare UTC",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"Total OK: {total_ok} | Errors: {len(err_list)}"
                )
                return False
            else:
                # 全部 24 个时间段均为绿底 ok，判定合格
                self.log_check_result(True, f"RPT Compare UTC 全部 24 个时间段 (00~23) 跨度下所有子列均显示 'ok' 绿底，巡检合格！")

            # 11. 解封并点击页面底部的 Checkpoint 按钮
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")

            # 12. 保存成功记录至 CheckpointStore
            CheckpointStore.save(
                derived_status_columns=tuple(i for i, h in enumerate(table_headers) if h == "Status"),
                page_key="niw_09",
                title="RPT Compare UTC",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全部 24 个时间段 (00~23) 全部绿底 ok"
            )
            return True

        except Exception as e:
            # 捕获运行过程中的任何异常并记录失败状态
            return self.handle_exception("niw_09", "RPT Compare UTC", e)
