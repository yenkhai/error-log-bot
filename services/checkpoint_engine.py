"""Checkpoint execution engine; UI provides logging and state callbacks."""
import traceback
from core.native_tables import capture_native_tables, prefer_native_tables, forecast_right_tables
from core.compact_log import issue_details
from core.browser import BrowserManager
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore
from core.stations import STATIONS, build_checkers

NOON_FAST_PAGE_KEYS = frozenset({"niw_03", "niw_05", "niw_07", "niw_08", "niw_12"})

# 午间快速通关需自动导航并点击 Checkpoint 的关卡菜单映射 (关卡名, 菜单 ID)
NOON_FAST_MENUS = {
    "niw_05": ("Calculate Betslips", "apy_b0i6text"),
    "niw_08": ("RPT AI", "apy_b0i9text"),
    "niw_12": ("Wsum Sport", "apy_b0i14text"),
}


CHECKPOINT_ONLY_MENUS = {'niw_01': ('Pending Wager', 'apy_b0i2text'),
 'niw_02': ('CCL Recover', 'apy_b0i3text'),
 'niw_03': ('Matches & Wagers', 'apy_b0i4text'),
 'niw_04': ('Result Process', 'apy_b0i5text'),
 'niw_05': ('Calculate Betslips', 'apy_b0i6text'),
 'niw_06': ('RPT PolyMarket', 'apy_b0i7text'),
 'niw_07': ('RPT Compare', 'apy_b0i8text'),
 'niw_08': ('RPT AI', 'apy_b0i9text'),
 'niw_09': ('RPT Compare UTC', 'apy_b0i10text'),
 'niw_10': ('Forecast', 'apy_b0i11text'),
 'niw_11': ('Check CCL', 'apy_b0i13text'),
 'niw_12': ('Wsum Sport', 'apy_b0i14text'),
 'niw_13': ('RPT CRS', 'apy_b0i15text'),
 'niw_14': ('HG Percentages', 'apy_b0i16text'),
 'niw_15': ('1 Wallet Pending', 'apy_b0i17text'),
 'copier_01': ('Copier', 'apy_b0i19text'),
 'copier_02': ('DB Server Status', 'apy_b0i20text'),
 'copier_03': ('AP Server Status', 'apy_b0i21text'),
 'copier_04': ('Check AP Space', 'apy_b0i22text'),
 'copier_05': ('Error Log', 'apy_b0i23text'),
 'copier_06': ('Redis Server', 'apy_b0i24text'),
 'copier_07': ('Robot Monitor', 'apy_b0i25text'),
 'copier_08': ('NIW Robot Monitor', 'apy_b0i26text'),
 'copier_09': ('Info Robot Monitor', 'apy_b0i27text')}


class CheckpointEngine:
    def _checkpoint_only_station(self, checker, page_key, name, section):
        self.log(f"[BYPASS] {name}: 已选择仅 Checkpoint，未检查页面数据")
        try:
            menu, menu_id = CHECKPOINT_ONLY_MENUS[page_key]
            checker.navigate_to_menu(menu, menu_id=menu_id, section=section)
            if page_key != "copier_07" and not checker.click_checkpoint():
                raise RuntimeError("Checkpoint 提交未确认")
            summary = "未检查：用户选择仅 Checkpoint" if page_key != "copier_07" else "未检查：此页无 Checkpoint，已跳过"
            CheckpointStore.save(page_key, name, True, summary=summary, has_warn=True)
            return True
        except Exception as exc:
            return checker.handle_exception(page_key, name, exc)

    def _fast_checkpoint_station(self, checker, page_key: str, name: str) -> bool:
        """
        [午间快速通关单站处理]
        针对 12:00-14:00 美东结算期间受影响的关卡 (05, 07, 08, 12)：
        导航至该页面，尝试点击 Checkpoint 按钮，记录通过状态并直接推进下一站。
        """
        self.log(f"\n[NOON FAST] ⚡ {name} (12-2pm EDT settlement bypass active)")
        try:
            menu_info = NOON_FAST_MENUS.get(page_key)
            if menu_info:
                menu_name, menu_id = menu_info
                checker.log_station_header(f"{name} [⚡ Noon Fast Mode]", menu_id=menu_id, page_key=page_key)
                checker.navigate_to_menu(menu_name, menu_id=menu_id, section="NIW", wait_seconds=1.5)

            # 尝试在页面上查找并点击 Checkpoint 按钮
            click_success = False
            try:
                click_success = checker.click_checkpoint()
            except Exception as ex:
                self.log(f"[NOON FAST] ⚠️ Checkpoint click note for {name}: {ex}")

            if not click_success:
                raise RuntimeError("Checkpoint submission failed")

            CheckpointStore.save(
                page_key=page_key,
                title=name,
                status=True,
                tables=[],
                headers=["Station", "Mode", "Checkpoint Action", "Status"],
                rows=[[
                    CheckpointStore.make_cell(name),
                    CheckpointStore.make_cell("Noon Fast Mode (12-2pm EDT)"),
                    CheckpointStore.make_cell("Clicked" if click_success else "Bypassed", bg="green"),
                    CheckpointStore.make_cell("Passed (Noon Fast)", bg="green")
                ]],
                summary="[Noon Fast Passed] 12:00-14:00 EDT settlement bypass"
            )
            self.log(f"[NOON FAST] ✅ {name} passed under Noon Fast Mode!")
            return True
        except Exception as e:
            self.log(f"[NOON FAST] ⚠️ Fast pass encountered exception for {name}: {e}")
            return checker.handle_exception(page_key, name, e)


    def _execute_station_loop(self, section_name: str, checkers: list, page_keys: list, var_list: list, start_idx: int) -> bool:
        """
        [关卡分区执行循环引擎]
        统一执行一个分区内的各站巡检，处理跳过、结果记录、LogViewer 联动刷新、异常中断与用户停止。
        支持 12:00-14:00 美东结算期快速通关模式 (自动跳过未结赛事阻断关卡并自动打勾推进)。
        返回值: interrupted (bool) — 若遇到 Error 或收到用户 Stop 信号则返回 True，否则返回 False。
        """
        for i, (name, checker) in enumerate(checkers[start_idx:]):
            idx = start_idx + i
            page_key = page_keys[idx] if idx < len(page_keys) else ""

            if not hasattr(self, "run_results"):
                self.run_results = {}

            # 检测该关卡是否在界面网格中被用户取消打勾
            if not (var_list[idx].get() if hasattr(var_list[idx], "get") else var_list[idx]):
                self.run_results[page_key] = "skipped"
                continue

            # 只在关卡边界暂停，记录下一项实际会执行的关卡。
            # 未勾选项已在上面跳过；最后一站完成则正常结束，无需再 Resume。
            if self.stop_requested:
                self.paused_station = (section_name, idx)
                self.last_failed_type = None
                self.log(f"\n[STOP] ⏸ Inspection paused before {name}. Click [Resume] to continue.")
                return True

            offset = 15 if section_name == "Copier" else 0
            self.log(f"[PROGRESS] [{offset + idx + 1}/24] {name.split(' - ', 1)[-1]} 检查中")
            self.last_failed_type, self.last_failed_index = section_name, idx

            # 检测是否处于美东午间快速通关模式 (12:00-14:00)
            noon_fast_active = self.is_noon_fast_mode_active()
            settings = getattr(self, "run_settings", {})
            bypass_flags = settings.get("checkpoint_only_" + section_name.lower(), [])
            checkpoint_only = idx < len(bypass_flags) and bypass_flags[idx]
            if checkpoint_only:
                res = self._checkpoint_only_station(checker, page_key, name, section_name)
            elif noon_fast_active and page_key in NOON_FAST_PAGE_KEYS:
                if page_key == "niw_03":
                    # 第 3 站 Matches & Wagers: 运行真实审查以判定是否可提前结束午间快速模式
                    self.log("\n[NOON FAST] ⚡ Station 03 Matches & Wagers — Inspecting uncompleted scores/wagers...")
                    res = checker.check()
                    if res:
                        # 审查通过：说明昨天的未结算赛事和注单已全部结清！提前结束午间快速模式
                        self.noon_early_exit_today = True
                        self.log("[NOON FAST] 🌟 Page 03 Matches & Wagers has 0 backlog! Yesterday's settlement is complete. Noon Fast Mode ended early for today!")
                    else:
                        # 审查未通过：属于美东中午正常的未结赛事积压，自动打勾并通过
                        self.log("[NOON FAST] ⚡ Station 03 has uncompleted bets/scores (EDT settlement in progress). Clicking Checkpoint & auto-passing per Noon Fast schedule...")
                        try:
                            if not checker.click_checkpoint():
                                raise RuntimeError("Checkpoint submission failed")
                        except Exception as ex:
                            checker.handle_exception(page_key, name, ex)
                            self.last_failed_type, self.last_failed_index = section_name, idx
                            return True

                        curr_data = CheckpointStore.get("niw_03")
                        orig_summary = curr_data.get("summary", "") if curr_data else "Matches & Wagers pending EDT settlement"
                        CheckpointStore.save(
                            page_key="niw_03",
                            title="Matches & Wagers",
                            status=True,
                            tables=curr_data.get("tables", []) if curr_data else [],
                            headers=curr_data.get("headers", []) if curr_data else [],
                            rows=curr_data.get("rows", []) if curr_data else [],
                            summary=f"[Noon Fast Passed] {orig_summary}"
                        )
                        res = True # 标记为通过，不阻断流水线
                elif page_key == "niw_07":
                    # 第 7 站 RPT Compare: 运行真实审查，但美东跨日结算未 release 报表期间允许 Rpt Complete 与 Reset Log 红字
                    self.log("\n[NOON FAST] ⚡ Station 07 RPT Compare — Running inspection (Rpt Complete & Reset Log tolerated while noon fast mode is active)...")
                    res = checker.check(is_noon_fast=True)
                else:
                    # 第 5, 8, 12 站：直接快速通关并点击 Checkpoint 按钮
                    res = self._fast_checkpoint_station(checker, page_key, name)
            else:
                # 执行关卡检查器核心 check 逻辑 (非午间快速模式或已提早退出，is_noon_fast 为 False)
                if page_key == "niw_07":
                    res = checker.check(is_noon_fast=False)
                else:
                    res = checker.check()

            stored = CheckpointStore.get(page_key) or {}
            # These pages leave a complete table view in the current frame.
            # Company-by-company and multi-frame collectors keep their aggregated tables.
            if not checkpoint_only and stored and page_key not in {"niw_01", "niw_05", "niw_13", "niw_15", "copier_01", "copier_04", "copier_05", "copier_06", "copier_07", "copier_08", "copier_09"} and hasattr(checker, "driver"):
                try:
                    native = capture_native_tables(checker.driver)
                    if page_key in ("copier_08", "copier_09"):
                        native = [table for table in native if any("timestamp" in str(h).lower() for h in table.get("headers", []))]
                    if page_key == "niw_10":
                        native = forecast_right_tables(native)
                    if prefer_native_tables(stored, native):
                        CheckpointStore.save(page_key, stored['title'], stored['status'],
                            tables=native, summary=stored.get('summary', ''), has_warn=stored.get('has_warn'))
                        stored = CheckpointStore.get(page_key)
                except Exception:
                    pass  # Display-only capture must never change an inspection outcome.

            outcome = "failed" if not res else ("warning" if stored.get("has_warn") else "passed")
            self.run_results[page_key] = outcome
            icon = {"failed": "❌", "warning": "⚠️", "passed": "✅"}[outcome]
            details = issue_details(stored, "red" if outcome == "failed" else "yellow") if outcome != "passed" else []
            reason = stored.get("summary", "") if outcome != "passed" else "通过"
            if outcome == "warning" and details:
                reason = "检查通过，有提醒（不阻断）"
            self.log(f"[RESULT] {icon} {name.split(' - ', 1)[-1]}：{reason or ('检查失败' if not res else '警告')}")
            for detail in details:
                self.log(f"[DETAIL] {icon} {detail}")
            if res:
                self.last_failed_type = None

            # 实时通知第 3 个 Tab (LogViewerTab) 刷新列表状态
            if hasattr(self.app, 'log_viewer_tab'):
                self.app.post_ui(self.app.log_viewer_tab.refresh_list)

            # 检查结果是否发生错误 (res 为 False)
            if not res:
                self.last_failed_type = section_name
                self.last_failed_index = idx
                self.log(f"\n[INTERRUPT] ❌ {name} error detected, inspection halted!")
                self.log("  → Click [Resume] to retry current station")
                self.log("  → Click [Skip] to force pass current station and proceed")
                self.play_error_sound()
                return True # 中断当前流水线，等待用户介入


        return False


    def run_full_pipeline(self, niw_start=0, copier_start=0, full=True):
        """
        [核心流水线主调度器 (后台工作线程)]
        参数:
        - niw_start: NIW 起始关卡索引 (0~14，默认 0；为 15 表示跳过 NIW)
        - copier_start: Copier 起始关卡索引 (0~8，默认 0)
        - full: 是否为贯通模式 (True 表示 NIW 跑完后继续跑 Copier)
        """
        try:
            # 1. 获取当前主界面顶栏填写的账号、密码与登录域名
            user, pwd = self.run_settings["credentials"]
            url = self.run_settings["url"]
            self.log(f"[CONFIG] User: {user}  |  URL: {url}")

            # 2. 连接或启动底层 Chrome WebDriver 驱动
            self.log("[BROWSER] Connecting to Chrome browser...")
            driver = BrowserManager.get_driver(url=url, user=user, pwd=pwd)
            self.log("[BROWSER] Browser ready!")
            self.log("──────────────────────────────────────────────────")

            # 3. 构造 15 个 NIW 关卡实例序列与标准存储键列表
            niw_page_keys = [key for key, _, _ in STATIONS if key.startswith("niw_")]
            niw_checkers = build_checkers("niw", driver, self.log)

            # 4. 构造 9 个 Copier 关卡实例序列与标准存储键列表
            copier_page_keys = [key for key, _, _ in STATIONS if key.startswith("copier_")]
            copier_checkers = build_checkers("copier", driver, self.log)

            interrupted = False # 中断标志位

            # ── 5. 执行 NIW 业务分区循环 ──
            if niw_start < 15:
                self.log(f"[PIPELINE START] NIW Section — Starting from Station {niw_start+1}")
                interrupted = self._execute_station_loop("NIW", niw_checkers, niw_page_keys, self.run_settings["niw"], niw_start)

            # ── 6. 执行 Copier & Server 基础设施分区循环 ──
            should_run_copier = (full or copier_start > 0 or getattr(self, "current_pipeline_mode", "FULL") in ["FULL", "COPIER"])
            if not interrupted and should_run_copier:
                self.log("──────────────────────────────────────────────────")
                self.log(f"[PIPELINE START] Copier & Server Section — Starting from Station {copier_start+1}")
                interrupted = self._execute_station_loop("Copier", copier_checkers, copier_page_keys, self.run_settings["copier"], copier_start)
                if not interrupted:
                    self.log("[COMPLETE] All Copier & Server stations completed!")
            elif not interrupted and not should_run_copier and niw_start < 15:
                self.log("[COMPLETE] All NIW stations completed!")

            # ── 7. 全量通关后的善后与归位逻辑 ──
            if not interrupted:
                self._handle_all_passed(driver)

            # 最终刷新一次日志浏览器
            if hasattr(self.app, 'log_viewer_tab'):
                self.app.post_ui(self.app.log_viewer_tab.refresh_list)

        except Exception as e:
            if self.last_failed_type is None:
                self.paused_station = ("NIW", niw_start) if niw_start < 15 else ("Copier", copier_start)
            # 捕获致命未处理异常，输出详细堆栈并触发报警音
            self.log(f"\n[ERROR] Pipeline encountered an exception: {e}\n{traceback.format_exc()}")
            self.play_error_sound()
        finally:
            # 退出工作线程时重置所有操作按钮状态
            self.app.post_ui(self.reset_buttons)


    def run_skip_and_checkpoint_pipeline(self):
        """
        [强制跳过打勾执行体]
        在当前停留的阻断异常页面上：
        1. 强制找到 Checkpoint 按钮并点击打勾。
        2. 将内存 CheckpointStore 中该关卡的状态维持为 False (Error)，附加 [Skipped & Checked] 标识。
        3. 刷新日志浏览器。
        4. 自动拉起下一关卡继续向下执行流水线。
        """
        _continuing_to_next = False
        try:
            driver = BrowserManager.get_driver()
            checker = BaseChecker(driver, self.log)

            # Robot Monitor is read-only and has no Checkpoint button.
            no_checkpoint = self.last_failed_type == "Copier" and self.last_failed_index == 6
            if no_checkpoint:
                self.log("[SKIP] Robot Monitor 无 Checkpoint，跳过检查并继续下一关。")
            else:
                self.log("[SKIP] Forcing Checkpoint click on current page...")
                if not checker.click_checkpoint():
                    raise RuntimeError("Checkpoint submission failed; station remains blocked")
                self.log("[SKIP SUCCESS] Checkpoint checked! Preparing next station...")

            # 2. 标记当前关卡虽被跳过并强制点击 Checkpoint 打勾，但在 CheckpointStore 中维持 Error 异常状态（用户要求：被 skip 跳过的关卡不要改成 passed，维持 error 状态）
            curr_pk = f"copier_{str(self.last_failed_index + 1).zfill(2)}" if self.last_failed_type == "Copier" else f"niw_{str(self.last_failed_index + 1).zfill(2)}"
            if not hasattr(self, "run_results"):
                self.run_results = {}
            self.run_results[curr_pk] = "skipped"
            curr_data = CheckpointStore.get(curr_pk)
            if curr_data:
                orig_summary = curr_data.get("summary", "")
                CheckpointStore.save(
                    page_key=curr_pk,
                    title=curr_data.get("title", ""),
                    status=False,
                    tables=curr_data.get("tables", []),
                    headers=curr_data.get("headers", []),
                    rows=curr_data.get("rows", []),
                    summary=f"[Skipped & Checked] {orig_summary}" if orig_summary else "Skipped & Checked by user"
                )
            else:
                title = f"{self.last_failed_type} Station {self.last_failed_index + 1}"
                CheckpointStore.save(
                    page_key=curr_pk,
                    title=title,
                    status=False,
                    summary="[Skipped & Checked] Station skipped by user after error"
                )

            # 3. 刷新列表展示
            if hasattr(self.app, 'log_viewer_tab'):
                self.app.post_ui(self.app.log_viewer_tab.refresh_list)

            # 4. 计算下一关卡索引
            next_index = self.last_failed_index + 1
            is_full = getattr(self, "current_pipeline_mode", "FULL") == "FULL"

            # 5. 分支推进逻辑
            if self.last_failed_type == "Copier":
                if next_index < 9:
                    # Copier 还有后续关卡
                    _continuing_to_next = True
                    self.log(f"[SKIP] Proceeding from Copier Station {next_index + 1}...")
                    self.run_full_pipeline(niw_start=15, copier_start=next_index, full=False)
                else:
                    # Copier 最后一关已跳过，全量完成
                    self.log("[COMPLETE] All Copier & Server stations completed!")
                    self._handle_all_passed(driver)
                    if hasattr(self.app, 'log_viewer_tab'):
                        self.app.post_ui(self.app.log_viewer_tab.refresh_list)
            else:
                # 中断在 NIW 关卡
                if next_index < 15:
                    # NIW 还有后续关卡
                    _continuing_to_next = True
                    self.log(f"[SKIP] Proceeding from NIW Station {next_index + 1}...")
                    self.run_full_pipeline(niw_start=next_index, copier_start=0, full=is_full)
                else:
                    # NIW 15 关全部结束
                    if is_full:
                        # 全量模式下自动切入 Copier 第 1 关
                        _continuing_to_next = True
                        self.log("[SKIP] NIW section completed! Continuing to Copier & Server...")
                        self.run_full_pipeline(niw_start=15, copier_start=0, full=True)
                    else:
                        # 仅 NIW 模式结束
                        self.log("[COMPLETE] All NIW stations completed!")
                        self._handle_all_passed(driver)
                        if hasattr(self.app, 'log_viewer_tab'):
                            self.app.post_ui(self.app.log_viewer_tab.refresh_list)

        except Exception as e:
            self.log(f"[ERROR] Force skip encountered exception: {e}\n{traceback.format_exc()}")
        finally:
            # 若没有后续关卡推进，重置按钮状态
            if not _continuing_to_next:
                self.app.post_ui(self.reset_buttons)
