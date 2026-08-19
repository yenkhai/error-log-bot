"""
================================================================================
Checkpoint 自动化巡检选项卡 UI 模块 (gui/tab_checkpoint.py)
--------------------------------------------------------------------------------
作用:
1. 构造 Checkpoint 选项卡页面：顶层控制按钮栏、关卡自定义选择矩阵、彩色日志控制台。
2. 单按钮【▶ 开始全量巡检】: 先跑 NIW 15 关，完成后接 Copier 9 关。
3. 提供【⏹ 停止】按钮: 当前页跑完即停止，不强行中断。
4. 提供【⏯️ 断点续传】与【⏭️ 跳过打勾】关键控制逻辑。
5. 彩色日志显示: ERROR=红, SUCCESS=绿, WARN=黄, STATION=蓝, 其余=灰白。
6. 每完成一个关卡，调用 PageLogger 写入 Desktop\\CheckpointLogs\\ 对应文件。
================================================================================
"""

import time
import threading
import traceback
import tkinter as tk
import customtkinter as ctk
from core.browser import BrowserManager
from core.base_checker import BaseChecker
from core.page_logger import PageLogger

# 导入所有 15 个 NIW 关卡
from pages.niw.page_01_pending_wager import PendingWagerChecker
from pages.niw.page_02_ccl_recover import CCLRecoverChecker
from pages.niw.page_03_matches_wagers import MatchesWagersChecker
from pages.niw.page_04_result_process import ResultProcessChecker
from pages.niw.page_05_calculate_betslips import CalculateBetslipsChecker
from pages.niw.page_06_rpt_polymarket import RPTPolyMarketChecker
from pages.niw.page_07_rpt_compare import RPTCompareChecker
from pages.niw.page_08_rpt_ai import RPTAIChecker
from pages.niw.page_09_rpt_compare_utc import RPTCompareUTCChecker
from pages.niw.page_10_forecast import ForecastChecker
from pages.niw.page_11_check_ccl import CheckCCLChecker
from pages.niw.page_12_wsum_sport import WsumSportChecker
from pages.niw.page_13_hg_percentages import HGPercentagesChecker
from pages.niw.page_14_rpt_crs import RPTCRSChecker
from pages.niw.page_15_one_wallet_pending import OneWalletPendingChecker

# 导入 9 个 Copier & Server 关卡
from pages.copier_server.page_01_copier import CopierChecker
from pages.copier_server.page_02_db_server_status import DBServerStatusChecker
from pages.copier_server.page_03_ap_server_status import APServerStatusChecker
from pages.copier_server.page_04_check_ap_space import CheckAPSpaceChecker
from pages.copier_server.page_05_error_log import ErrorLogChecker
from pages.copier_server.page_06_redis_server import RedisServerChecker
from pages.copier_server.page_07_robot_monitor import RobotMonitorChecker
from pages.copier_server.page_08_niw_robot_monitor import NIWRobotMonitorChecker
from pages.copier_server.page_09_info_robot_monitor import InfoRobotMonitorChecker


# ─────────────────────────────────────────────────────────────────────────────
#  彩色日志标签配置
#  tag_name → (foreground_color, bold)
# ─────────────────────────────────────────────────────────────────────────────
LOG_TAGS = {
    "error":       ("#FF4D4D", True),    # 亮红粗体 — ERROR / Tier 1 / 异常 / 🔴 / 积压 / 阻断
    "warn":        ("#FFB86C", True),    # 暖橙粗体 — WARN / Tier 3 / 提醒 / 🟡 / 仅通知
    "success":     ("#50FA7B", False),   # 翠绿 — SUCCESS / OK / 通关 / 正常 / ✅
    "station":     ("#8BE9FD", True),    # 青蓝粗体 — 关卡站头 / 分区标题 / ===
    "checkpoint":  ("#50FA7B", True),    # 翠绿粗体 — CHECKPOINT 打勾成功
    "stop":        ("#FF79C6", True),    # 粉红粗体 — 用户 STOP
    "info":        ("#C9D1D9", False),   # 舒适白灰 — 普通文本
    "dim":         ("#555E70", False),   # 低调暗灰 — 分隔横线
    "data":        ("#D8DEE9", False),   # 干净浅灰 — 数据表格
}


def _classify_tag(line: str) -> str:
    """根据日志行内容自动判断颜色标签，确保有错的地方 100% 呈高亮红色"""
    u = line.upper()

    # 1. 错误 / 阻断 / 异常 (最优先：高亮鲜红粗体 #FF4D4D)
    if any(k in line for k in ["🔴", "红字", "红底", "异常", "积压阻断", "致命", "阻断", "超时积压", "❌"]) or \
       any(k in u for k in ["[ERROR]", "FAILED", "TIER 1", "TIER1", "[INTERRUPT]", "RED NODE", "ERROR/", "[ERROR/"]):
        return "error"

    # 2. 警告 / 提示 (暖橙粗体 #FFB86C)
    if any(k in line for k in ["🟡", "⚠️", "⚠", "警告", "提醒", "仅通知", "仅提示"]) or \
       any(k in u for k in ["[WARN]", "[NOTICE]", "TIER 3", "TIER3", "WARNING", "WARN/", "[WARN/"]):
        return "warn"

    # 3. 成功 / 正常 / 通关 (翠绿 #50FA7B)
    if any(k in line for k in ["✅", "🟢", "通关", "巡检通过", "全绿", "全部正常", "完全正常", "全部 0", "全 0", "[OK/正常]", "[OK]"]) or \
       any(k in u for k in ["SUCCESS", "[COMPLETE]", "CHECK RESULT] SUCCESS", "NO ERROR", "OK/"]):
        return "success"

    # 4. Checkpoint 按钮打勾
    if "CHECKPOINT" in u and ("SUCCESS" in u or "成功点击" in u):
        return "checkpoint"

    # 5. 关卡站头 / 区域标题 (青蓝粗体 #8BE9FD)
    if any(k in u for k in ["[STATION]", "[PIPELINE", "=== ", "===", "═══"]):
        return "station"
    if "COMPANY:" in u or "PART 1:" in u or "PART 2:" in u or "--- [" in line or ("【" in line and "明细】" in line):
        return "station"

    # 6. 用户停止
    if "[STOP]" in u:
        return "stop"

    # 7. 纯分隔线 (暗灰 #555E70)
    if set(line.strip()).issubset(set("─═=- \t")) and len(line.strip()) > 5:
        return "dim"

    # 8. 其余数据行 (干净浅灰 #C9D1D9，不再全部涂成刺眼的黄色)
    return "info"


class CheckpointTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.is_running = False          # 是否有巡检正在执行
        self.stop_requested = False      # 用户请求停止（跑完当前页即停）

        # 断点记录
        self.last_failed_type = None     # "NIW" 或 "Copier"
        self.last_failed_index = 0      # 0-based 关卡索引

        # 关卡选择面板展开状态
        self.matrix_visible = True

        # 本轮巡检结果汇总（用于写 INDEX.txt）
        self._run_results = []

        # 缓存日志行（用于写入文件）
        self._page_log_buffer = []

        # 关卡勾选控制变量列表 (默认全部 True)
        self.niw_vars    = [ctk.BooleanVar(value=True) for _ in range(15)]
        self.copier_vars = [ctk.BooleanVar(value=True) for _ in range(9)]

        # 每小时自动巡检控制变量
        self.hourly_auto_var = ctk.BooleanVar(value=False)
        self.hourly_interval_seconds = 3600  # 默认 3600 秒 (1小时)
        self.next_run_timestamp = None
        self.hourly_timer_id = None
        self.hourly_cycle_count = 0

        # 异常声音报警开关 (默认开启)
        self.sound_alert_var = ctk.BooleanVar(value=True)

        self.build_ui()

    # ─────────────────────────────────────────────────────────────────
    #  UI 构建
    # ─────────────────────────────────────────────────────────────────
    def build_ui(self):
        # 1. 顶层按钮控制栏
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # ▶ 运行全量 (NIW → Copier 依次执行)
        self.btn_run_all = ctk.CTkButton(
            top_frame, text="Check All", command=self.start_full_thread,
            fg_color="#1f538d", hover_color="#14375e",
            font=ctk.CTkFont(weight="bold"), width=105
        )
        self.btn_run_all.pack(side="left", padx=3, pady=5)

        # ▶ 仅运行 NIW
        self.btn_run_niw = ctk.CTkButton(
            top_frame, text="Check NIW", command=self.start_niw_only_thread,
            fg_color="#16a085", hover_color="#117864",
            font=ctk.CTkFont(weight="bold"), width=95
        )
        self.btn_run_niw.pack(side="left", padx=3, pady=5)

        # ▶ 仅运行 Copier
        self.btn_run_copier = ctk.CTkButton(
            top_frame, text="Check Copier", command=self.start_copier_only_thread,
            fg_color="#27ae60", hover_color="#1e8449",
            font=ctk.CTkFont(weight="bold"), width=100
        )
        self.btn_run_copier.pack(side="left", padx=3, pady=5)

        # ⏹ 停止（跑完当前页停止）
        self.btn_stop = ctk.CTkButton(
            top_frame, text="Stop", command=self.request_stop,
            fg_color="#c0392b", hover_color="#962d22",
            font=ctk.CTkFont(weight="bold"), width=75
        )
        self.btn_stop.pack(side="left", padx=3, pady=5)

        # ⏯ 断点续传
        self.btn_resume = ctk.CTkButton(
            top_frame, text="Resume", command=self.start_resume_thread,
            fg_color="#e67e22", hover_color="#d35400",
            font=ctk.CTkFont(weight="bold"), width=85
        )
        self.btn_resume.pack(side="left", padx=3, pady=5)

        # ⏭ 跳过打勾
        self.btn_skip = ctk.CTkButton(
            top_frame, text="skip", command=self.start_skip_and_checkpoint_thread,
            fg_color="#8e44ad", hover_color="#732d91",
            font=ctk.CTkFont(weight="bold"), width=85
        )
        self.btn_skip.pack(side="left", padx=3, pady=5)

        # 🔽 折叠/展开
        self.btn_toggle_matrix = ctk.CTkButton(
            top_frame, text="Collapse", command=self.toggle_matrix_panel,
            fg_color="#34495e", hover_color="#2c3e50",
            font=ctk.CTkFont(weight="bold"), width=85
        )
        self.btn_toggle_matrix.pack(side="right", padx=3, pady=5)

        # 🗑 清空日志
        self.btn_clear = ctk.CTkButton(
            top_frame, text="Clear", command=self.clear_log, width=65
        )
        self.btn_clear.pack(side="right", padx=3, pady=5)

        # 📁 打开日志文件夹
        self.btn_open_logs = ctk.CTkButton(
            top_frame, text="Logs", command=self.open_log_folder, width=65
        )
        self.btn_open_logs.pack(side="right", padx=3, pady=5)

        # 1.5 定时自动巡检调度控制栏 (Hourly Auto-Run Scheduler)
        schedule_frame = ctk.CTkFrame(self, fg_color="#1a202c", corner_radius=6)
        schedule_frame.pack(fill="x", padx=10, pady=(2, 4))

        self.switch_hourly = ctk.CTkSwitch(
            schedule_frame, text="⏰ 定时自动巡检", variable=self.hourly_auto_var,
            command=self.toggle_hourly_auto, font=ctk.CTkFont(weight="bold", size=12),
            progress_color="#2ecc71"
        )
        self.switch_hourly.pack(side="left", padx=(10, 8), pady=4)

        self.opt_interval = ctk.CTkOptionMenu(
            schedule_frame, values=["每 60 分钟 (1小时)", "每 30 分钟", "每 120 分钟 (2小时)"],
            width=140, height=24, font=ctk.CTkFont(size=11),
            command=self._on_interval_changed
        )
        self.opt_interval.set("每 60 分钟 (1小时)")
        self.opt_interval.pack(side="left", padx=5, pady=4)

        self.lbl_schedule_status = ctk.CTkLabel(
            schedule_frame, text="[状态] ⏸️ 未开启自动巡检",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#8892B0"
        )
        self.lbl_schedule_status.pack(side="left", padx=(15, 10), pady=4)

        self.switch_sound = ctk.CTkSwitch(
            schedule_frame, text="🔔 报警音", variable=self.sound_alert_var,
            font=ctk.CTkFont(weight="bold", size=11), progress_color="#e74c3c", width=65
        )
        self.switch_sound.pack(side="right", padx=(5, 12), pady=4)

        # 2. 关卡自定义勾选矩阵
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.pack(fill="x", padx=10, pady=5)

        # NIW 子区域
        niw_box = ctk.CTkFrame(self.select_frame)
        niw_box.pack(fill="x", padx=5, pady=5)
        niw_header = ctk.CTkFrame(niw_box, fg_color="transparent")
        niw_header.pack(fill="x", padx=5, pady=(2, 2))
        ctk.CTkLabel(niw_header, text="[CONFIG] NIW 关卡定制 (默认全选):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(niw_header, text="全选", width=50, height=22,
                      command=lambda: self.set_all_vars(self.niw_vars, True)).pack(side="left", padx=5)
        ctk.CTkButton(niw_header, text="全不选", width=55, height=22,
                      command=lambda: self.set_all_vars(self.niw_vars, False)).pack(side="left")

        niw_grid = ctk.CTkFrame(niw_box, fg_color="transparent")
        niw_grid.pack(fill="x", padx=5, pady=(0, 5))
        niw_names = [
            "1.Pending Wager", "2.CCL Recover", "3.Matches Wagers", "4.Result Process",
            "5.Calculate Betslips", "6.RPT PolyMarket", "7.RPT Compare", "8.RPT AI",
            "9.RPT Compare UTC", "10.Forecast", "11.Check CCL", "12.Wsum Sport",
            "13.HG Percentages", "14.RPT CRS", "15.1 Wallet Pending"
        ]
        for i, name in enumerate(niw_names):
            ctk.CTkCheckBox(niw_grid, text=name, variable=self.niw_vars[i],
                            font=ctk.CTkFont(size=11)).grid(
                row=i // 5, column=i % 5, sticky="w", padx=4, pady=2)

        # Copier 子区域
        copier_box = ctk.CTkFrame(self.select_frame)
        copier_box.pack(fill="x", padx=5, pady=5)
        copier_header = ctk.CTkFrame(copier_box, fg_color="transparent")
        copier_header.pack(fill="x", padx=5, pady=(2, 2))
        ctk.CTkLabel(copier_header, text="[CONFIG] Copier & Server 关卡定制 (默认全选):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(copier_header, text="全选", width=50, height=22,
                      command=lambda: self.set_all_vars(self.copier_vars, True)).pack(side="left", padx=5)
        ctk.CTkButton(copier_header, text="全不选", width=55, height=22,
                      command=lambda: self.set_all_vars(self.copier_vars, False)).pack(side="left")

        copier_grid = ctk.CTkFrame(copier_box, fg_color="transparent")
        copier_grid.pack(fill="x", padx=5, pady=(0, 5))
        copier_names = [
            "1.Copier", "2.DB Server", "3.AP Server", "4.AP Space", "5.Error Log",
            "6.Redis", "7.Robot Monitor", "8.NIW Robot", "9.Info Robot"
        ]
        for i, name in enumerate(copier_names):
            ctk.CTkCheckBox(copier_grid, text=name, variable=self.copier_vars[i],
                            font=ctk.CTkFont(size=11)).grid(
                row=i // 5, column=i % 5, sticky="w", padx=4, pady=2)

        # 3. 彩色日志控制台 (tkinter.Text 支持多色标签)
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = tk.Text(
            log_frame,
            font=("Consolas", 13),
            bg="#1E1E2E",       # 深色背景
            fg="#F8F8F2",       # 默认白灰文字
            insertbackground="#F8F8F2",
            selectbackground="#44475A",
            relief="flat",
            borderwidth=0,
            wrap="none",        # 不自动换行（数据表格不要乱拆）
            state="disabled"
        )

        # 垂直滚动条
        scrollbar_y = tk.Scrollbar(log_frame, orient="vertical",
                                    command=self.log_text.yview)
        scrollbar_y.pack(side="right", fill="y")

        # 水平滚动条（便于查看宽表格）
        scrollbar_x = tk.Scrollbar(log_frame, orient="horizontal",
                                    command=self.log_text.xview)
        scrollbar_x.pack(side="bottom", fill="x")

        self.log_text.configure(yscrollcommand=scrollbar_y.set,
                                xscrollcommand=scrollbar_x.set)
        self.log_text.pack(side="left", fill="both", expand=True)

        # 注册颜色标签
        for tag_name, (fg_color, is_bold) in LOG_TAGS.items():
            font_weight = "bold" if is_bold else "normal"
            self.log_text.tag_configure(
                tag_name,
                foreground=fg_color,
                font=("Consolas", 13, font_weight)
            )

        # 初始调用：精确初始化所有按钮的状态
        self.update_button_states()

    # ─────────────────────────────────────────────────────────────────
    #  工具方法
    # ─────────────────────────────────────────────────────────────────
    def toggle_matrix_panel(self):
        if self.matrix_visible:
            self.select_frame.pack_forget()
            self.matrix_visible = False
            self.btn_toggle_matrix.configure(text="▶ 展开定制")
        else:
            self.select_frame.pack(fill="x", padx=10, pady=5, before=self.log_text.master)
            self.matrix_visible = True
            self.btn_toggle_matrix.configure(text="🔽 折叠定制")

    def set_all_vars(self, var_list, value: bool):
        for v in var_list:
            v.set(value)

    def log(self, message: str):
        """线程安全地向彩色日志控制台追加一行，自动根据内容分配颜色标签"""
        # 同时缓存到页面日志 buffer
        self._page_log_buffer.append(message)

        def append():
            tag = _classify_tag(message)
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, append)

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def open_log_folder(self):
        """打开桌面 CheckpointLogs 文件夹"""
        import os, subprocess
        from core.page_logger import LOG_ROOT
        PageLogger.ensure_dirs()
        try:
            subprocess.Popen(f'explorer "{LOG_ROOT}"')
            self.log(f"[LOG] 已打开日志文件夹: {LOG_ROOT}")
        except Exception as e:
            self.log(f"[WARN] 打开文件夹失败: {e}")

    # ─────────────────────────────────────────────────────────────────
    #  定时自动巡检调度方法 (Hourly Auto-Run Engine)
    # ─────────────────────────────────────────────────────────────────
    def _on_interval_changed(self, choice: str):
        """周期下拉框选择事件"""
        if "30" in choice:
            self.hourly_interval_seconds = 1800
        elif "120" in choice:
            self.hourly_interval_seconds = 7200
        else:
            self.hourly_interval_seconds = 3600
        
        # 若当前正在等待倒计时中，重新计算下一次执行目标时间
        if self.hourly_auto_var.get() and self.next_run_timestamp is not None:
            self.next_run_timestamp = time.time() + self.hourly_interval_seconds
            self.log(f"[TIMER] ⚙️ 巡检周期已切换为: {choice}")

    def toggle_hourly_auto(self):
        """开启 / 关闭 定时自动巡检开关 (开启后进入倒计时，不立即触发)"""
        enabled = self.hourly_auto_var.get()
        if enabled:
            self.hourly_cycle_count = 0
            # 开启时直接从当前时间开始计算下次执行时间 (例如 60 分钟后)
            self.next_run_timestamp = time.time() + self.hourly_interval_seconds
            mins = self.hourly_interval_seconds // 60
            target_time = time.strftime("%H:%M:%S", time.localtime(self.next_run_timestamp))
            
            self.log("══════════════════════════════════════════════════")
            self.log(f"  ⏰ 已开启定时自动巡检！(周期: 每 {mins} 分钟)")
            self.log(f"  ⏳ 倒计时开始：将在 {target_time} (约 {mins} 分钟后) 自动执行第 1 轮巡检")
            self.log("══════════════════════════════════════════════════")
            
            if self.hourly_timer_id is not None:
                self.after_cancel(self.hourly_timer_id)
            self._hourly_tick()
        else:
            self.log("[TIMER] ⏹ 已关闭定时自动巡检模式。")
            self.next_run_timestamp = None
            self.lbl_schedule_status.configure(text="[状态] ⏸️ 未开启自动巡检", text_color="#8892B0")
            if self.hourly_timer_id is not None:
                self.after_cancel(self.hourly_timer_id)
                self.hourly_timer_id = None

    def _hourly_tick(self):
        """每秒驱动一次的倒计时调度引擎"""
        if not self.hourly_auto_var.get():
            return

        now = time.time()
        if self.is_running:
            # 正在运行巡检任务
            self.lbl_schedule_status.configure(
                text=f"[状态] 🚀 正在执行第 {self.hourly_cycle_count + 1} 轮巡检中...",
                text_color="#50FA7B"
            )
            # 运行期间清空 next_run_timestamp，等全量通关后再精确设定下一次时间
            self.next_run_timestamp = None
        else:
            # 当前未在运行
            if self.last_failed_type is not None:
                # 存在 Error 中断，暂停下一轮，保护现场等待人工介入
                self.lbl_schedule_status.configure(
                    text=f"[状态] ⚠️ 上一轮在 {self.last_failed_type} 遇错中断！已暂停，等待处理",
                    text_color="#FF4D4D"
                )
            else:
                # 正常空闲状态
                if self.next_run_timestamp is None:
                    # 刚刚完成一轮，计算下一次执行目标时间戳
                    self.hourly_cycle_count += 1
                    self.next_run_timestamp = now + self.hourly_interval_seconds

                diff = int(self.next_run_timestamp - now)
                if diff <= 0:
                    # 倒计时归零，自动唤醒触发下一轮全量巡检
                    self.next_run_timestamp = None
                    if not self._check_cross_tab_busy():
                        self.log(f"\n[TIMER] ⏰ 倒计时结束，自动唤醒执行第 {self.hourly_cycle_count + 1} 轮全量巡检！")
                        self.start_full_thread()
                    else:
                        self.log("[TIMER] ⚠️ 检测到 Error Log 工具正在运行，延后 30 秒再次尝试唤醒巡检...")
                        self.next_run_timestamp = now + 30
                else:
                    mins = diff // 60
                    secs = diff % 60
                    target_time = time.strftime("%H:%M:%S", time.localtime(self.next_run_timestamp))
                    self.lbl_schedule_status.configure(
                        text=f"[状态] ⏳ 下次巡检: {target_time} (还剩 {mins}分{secs:02d}秒) | 已完成: {self.hourly_cycle_count}轮",
                        text_color="#FFB86C"
                    )

        # 关键：每隔 1 秒递归调度下一跳，驱动倒计时动态减少与自动触发
        self.hourly_timer_id = self.after(1000, self._hourly_tick)

    def play_error_sound(self):
        """异常发生时触发 Windows 蜂鸣报警音 (后台守护线程执行，不阻塞 UI)"""
        if not self.sound_alert_var.get():
            return
        def _beep():
            try:
                import winsound
                # 连续播放 3 声清晰的高频警报音 (1800Hz, 200ms)
                for _ in range(3):
                    winsound.Beep(1800, 200)
                    time.sleep(0.08)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()

    def request_stop(self):
        """用户点击停止 — 设置标志，当前页跑完后停止"""
        if not self.is_running:
            self.log("[STOP] 当前没有正在运行的巡检任务。")
            return
        self.stop_requested = True
        self.log("[STOP] ⏹ 已收到停止指令！将在当前页面完成后停止，请稍候...")
        if self.hourly_auto_var.get():
            self.log("[STOP] 提示: 定时巡检仍处于开启状态；如需完全停止定时，请关闭上方【⏰ 定时自动巡检】开关。")

    def update_button_states(self):
        """
        根据当前巡检状态及跨 Tab 互斥状态精细化控制所有按钮的 Enable / Disable 状态：
        - 自身运行中 (is_running=True): 所有启动、续传、跳过按钮变灰禁用，仅 [STOP] 启用
        - 另一个 Tab (Error Log) 运行中: 所有启动、续传、跳过、STOP 全部变灰禁用
        - 有中断 (last_failed_type 不为空 且空闲): [全量/NIW/Copier]、[续传]、[跳过] 全部启用，[STOP] 变灰
        - 空闲/完成 (无中断): [全量/NIW/Copier] 启用，[续传]、[跳过]、[STOP] 变灰
        """
        def apply():
            is_error_log_running = False
            if hasattr(self.app, 'error_log_tab') and getattr(self.app.error_log_tab, 'is_running', False):
                is_error_log_running = True

            if self.is_running:
                # 自身运行中
                self.btn_run_all.configure(state="disabled")
                self.btn_run_niw.configure(state="disabled")
                self.btn_run_copier.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="normal")
            elif is_error_log_running:
                # 另一个 Tab 运行中，彻底锁定本 Tab 所有执行按钮
                self.btn_run_all.configure(state="disabled")
                self.btn_run_niw.configure(state="disabled")
                self.btn_run_copier.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")
            elif self.last_failed_type is not None:
                # 存在中断点（待续传/跳过）
                self.btn_run_all.configure(state="normal")
                self.btn_run_niw.configure(state="normal")
                self.btn_run_copier.configure(state="normal")
                self.btn_resume.configure(state="normal")
                self.btn_skip.configure(state="normal")
                self.btn_stop.configure(state="disabled")
            else:
                # 初始或全部完成空闲状态
                self.btn_run_all.configure(state="normal")
                self.btn_run_niw.configure(state="normal")
                self.btn_run_copier.configure(state="normal")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")

        self.after(0, apply)

    def toggle_buttons(self, enabled: bool):
        """兼容旧接口，统一调度 update_button_states"""
        self.update_button_states()

    def reset_buttons(self):
        self.is_running = False
        self.stop_requested = False
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()

    def _check_cross_tab_busy(self) -> bool:
        """检查 Error Log 导出工具是否正在运行"""
        if hasattr(self.app, 'error_log_tab') and getattr(self.app.error_log_tab, 'is_running', False):
            self.log("[WARN] 🚫 拒绝执行：Error Log 日志导出工具正在运行中！为了防止冲突，请等待或停止 Error Log 任务。")
            return True
        return False

    # ─────────────────────────────────────────────────────────────────
    #  线程启动入口
    # ─────────────────────────────────────────────────────────────────
    def start_full_thread(self, niw_start=0, copier_start=0, full=True):
        """▶ 开始全量巡检: NIW 15 站 → Copier 9 站"""
        if self.is_running or self._check_cross_tab_busy():
            return
        self.current_pipeline_mode = "FULL"
        self.is_running = True
        self.stop_requested = False
        self._run_results = []
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()
        self.log("══════════════════════════════════════════════════")
        self.log("  ▶ 全量巡检启动 — NIW (15站) → Copier (9站)")
        self.log("══════════════════════════════════════════════════")
        threading.Thread(
            target=self.run_full_pipeline,
            args=(niw_start, copier_start, True),
            daemon=True
        ).start()

    def start_niw_only_thread(self, niw_start=0):
        """▶ 仅运行 NIW (15 站)"""
        if self.is_running or self._check_cross_tab_busy():
            return
        self.current_pipeline_mode = "NIW"
        self.is_running = True
        self.stop_requested = False
        self._run_results = []
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()
        self.log("══════════════════════════════════════════════════")
        self.log("  ▶ 巡检启动 — 仅 NIW (15站)")
        self.log("══════════════════════════════════════════════════")
        threading.Thread(
            target=self.run_full_pipeline,
            args=(niw_start, 0, False),
            daemon=True
        ).start()

    def start_copier_only_thread(self, copier_start=0):
        """▶ 仅运行 Copier & Server (9 站)"""
        if self.is_running or self._check_cross_tab_busy():
            return
        self.current_pipeline_mode = "COPIER"
        self.is_running = True
        self.stop_requested = False
        self._run_results = []
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()
        self.log("══════════════════════════════════════════════════")
        self.log("  ▶ 巡检启动 — 仅 Copier & Server (9站)")
        self.log("══════════════════════════════════════════════════")
        threading.Thread(
            target=self.run_full_pipeline,
            args=(15, copier_start, False),
            daemon=True
        ).start()

    def start_resume_thread(self):
        """⏯ 断点续传 — 从上次中断位置重新开始"""
        if self.is_running or self._check_cross_tab_busy():
            return
        is_full = getattr(self, "current_pipeline_mode", "FULL") == "FULL"
        if self.last_failed_type == "Copier":
            self.log(f"[RESUME] 从 Copier 第 {self.last_failed_index + 1} 站续传...")
            self.start_copier_only_thread(copier_start=self.last_failed_index)
        else:
            self.log(f"[RESUME] 从 NIW 第 {self.last_failed_index + 1} 站续传...")
            if is_full:
                self.start_full_thread(niw_start=self.last_failed_index, copier_start=0, full=True)
            else:
                self.start_niw_only_thread(niw_start=self.last_failed_index)

    def start_skip_and_checkpoint_thread(self):
        """⏭ 强制跳过打勾 — 在当前中断页面点击 Checkpoint 后进入下一关"""
        if self.is_running or self._check_cross_tab_busy():
            return
        self.is_running = True
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()
        self.log("[SKIP] 强制打勾跳过当前页，进入下一关...")
        threading.Thread(target=self.run_skip_and_checkpoint_pipeline, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────
    #  流水线核心逻辑
    # ─────────────────────────────────────────────────────────────────
    def run_full_pipeline(self, niw_start=0, copier_start=0, full=True):
        """
        全量巡检流水线: NIW → Copier
        - 每完成一站，写入 Desktop\\CheckpointLogs\\ 对应文件
        - 每完成一站后检查 stop_requested 标志
        """
        try:
            user, pwd = self.app.get_credentials()
            url = self.app.get_login_url()
            self.log(f"[CONFIG] 账号: {user}  |  域名: {url}")

            self.log("[BROWSER] 正在连接 Chrome 浏览器...")
            driver = BrowserManager.get_driver(url=url, user=user, pwd=pwd)
            self.log("[BROWSER] 浏览器就绪！")
            self.log("──────────────────────────────────────────────────")

            # NIW 关卡列表
            niw_page_keys = [f"niw_{str(i+1).zfill(2)}" for i in range(15)]
            niw_checkers = [
                ("NIW 第1站  Pending Wager",    PendingWagerChecker(driver, self.log)),
                ("NIW 第2站  CCL Recover",       CCLRecoverChecker(driver, self.log)),
                ("NIW 第3站  Matches Wagers",    MatchesWagersChecker(driver, self.log)),
                ("NIW 第4站  Result Process",    ResultProcessChecker(driver, self.log)),
                ("NIW 第5站  Calculate Betslips",CalculateBetslipsChecker(driver, self.log)),
                ("NIW 第6站  RPT PolyMarket",    RPTPolyMarketChecker(driver, self.log)),
                ("NIW 第7站  RPT Compare",       RPTCompareChecker(driver, self.log)),
                ("NIW 第8站  RPT AI",            RPTAIChecker(driver, self.log)),
                ("NIW 第9站  RPT Compare UTC",   RPTCompareUTCChecker(driver, self.log)),
                ("NIW 第10站 Forecast",          ForecastChecker(driver, self.log)),
                ("NIW 第11站 Check CCL",         CheckCCLChecker(driver, self.log)),
                ("NIW 第12站 Wsum Sport",        WsumSportChecker(driver, self.log)),
                ("NIW 第13站 HG Percentages",    HGPercentagesChecker(driver, self.log)),
                ("NIW 第14站 RPT CRS",           RPTCRSChecker(driver, self.log)),
                ("NIW 第15站 1 Wallet Pending",  OneWalletPendingChecker(driver, self.log)),
            ]

            # Copier 关卡列表
            copier_page_keys = [f"copier_{str(i+1).zfill(2)}" for i in range(9)]
            copier_checkers = [
                ("Copier 第1站 Copier",           CopierChecker(driver, self.log)),
                ("Copier 第2站 DB Server Status",  DBServerStatusChecker(driver, self.log)),
                ("Copier 第3站 AP Server Status",  APServerStatusChecker(driver, self.log)),
                ("Copier 第4站 Check AP Space",    CheckAPSpaceChecker(driver, self.log)),
                ("Copier 第5站 Error Log",         ErrorLogChecker(driver, self.log)),
                ("Copier 第6站 Redis Server",      RedisServerChecker(driver, self.log)),
                ("Copier 第7站 Robot Monitor",     RobotMonitorChecker(driver, self.log)),
                ("Copier 第8站 NIW Robot Monitor", NIWRobotMonitorChecker(driver, self.log)),
                ("Copier 第9站 Info Robot Monitor",InfoRobotMonitorChecker(driver, self.log)),
            ]

            interrupted = False

            # ── NIW 区域 ──
            if niw_start < 15:
                self.log(f"[PIPELINE START] NIW 区域 — 从第 {niw_start+1} 站开始")
                for i, (name, checker) in enumerate(niw_checkers[niw_start:]):
                    idx = niw_start + i

                    if not self.niw_vars[idx].get():
                        self.log(f"[SKIP] 已跳过 {name}（用户未勾选）")
                        continue

                    # 清空页面日志 buffer
                    self._page_log_buffer = []

                    res = checker.check()
                    ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # 写入桌面日志文件
                    try:
                        PageLogger.write_page_log(
                            page_key=niw_page_keys[idx],
                            station_name=name,
                            is_success=res,
                            raw_lines=list(self._page_log_buffer)
                        )
                    except Exception as log_err:
                        self.log(f"[WARN] 写入日志文件失败: {log_err}")

                    self._run_results.append((niw_page_keys[idx], name, res, ts))

                    if not res:
                        self.last_failed_type = "NIW"
                        self.last_failed_index = idx
                        self.log(f"\n[INTERRUPT] ❌ {name} 检测到异常，巡检中断！")
                        self.log("  → 点击 [⏯ 断点续传] 重试当前站")
                        self.log("  → 点击 [⏭ 跳过打勾] 强行通关当前站进入下一站")
                        self.play_error_sound()
                        interrupted = True
                        break

                    # 检查 STOP 标志
                    if self.stop_requested:
                        self.log(f"\n[STOP] ⏹ 已完成 {name}，依据用户指令停止巡检。")
                        interrupted = True
                        break

            # ── Copier 区域（NIW 全部通过且未停止，或处于 FULL / COPIER 模式才继续）──
            should_run_copier = (full or copier_start > 0 or getattr(self, "current_pipeline_mode", "FULL") in ["FULL", "COPIER"])
            if not interrupted and should_run_copier:
                self.log("──────────────────────────────────────────────────")
                self.log(f"[PIPELINE START] Copier & Server 区域 — 从第 {copier_start+1} 站开始")
                for i, (name, checker) in enumerate(copier_checkers[copier_start:]):
                    idx = copier_start + i

                    if not self.copier_vars[idx].get():
                        self.log(f"[SKIP] 已跳过 {name}（用户未勾选）")
                        continue

                    self._page_log_buffer = []

                    res = checker.check()
                    ts = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    try:
                        PageLogger.write_page_log(
                            page_key=copier_page_keys[idx],
                            station_name=name,
                            is_success=res,
                            raw_lines=list(self._page_log_buffer)
                        )
                    except Exception as log_err:
                        self.log(f"[WARN] 写入日志文件失败: {log_err}")

                    self._run_results.append((copier_page_keys[idx], name, res, ts))

                    if not res:
                        self.last_failed_type = "Copier"
                        self.last_failed_index = idx
                        self.log(f"\n[INTERRUPT] ❌ {name} 检测到异常，巡检中断！")
                        self.log("  → 点击 [⏯ 断点续传] 重试当前站")
                        self.log("  → 点击 [⏭ 跳过打勾] 强行通关当前站进入下一站")
                        self.play_error_sound()
                        interrupted = True
                        break

                    if self.stop_requested:
                        self.log(f"\n[STOP] ⏹ 已完成 {name}，依据用户指令停止巡检。")
                        interrupted = True
                        break

            if not interrupted:
                self.last_failed_type = None
                self.last_failed_index = 0
                self.log("\n══════════════════════════════════════════════════")
                self.log("  🎉 恭喜！巡检关卡全部顺畅通关！")
                self.log("══════════════════════════════════════════════════")
                # 仅在全部成功通关时，才自动跳回 NIW 第1站 Pending Wager
                try:
                    checker = BaseChecker(driver, self.log)
                    checker.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW", wait_seconds=2)
                    self.log("[NAVIGATE] ✅ 巡检全部顺利完成，已自动跳回 Pending Wager (NIW 第1站) 页面")
                except Exception:
                    pass

            # 更新 INDEX.txt 汇总
            if self._run_results:
                try:
                    PageLogger.update_index(self._run_results)
                    self.log(f"[LOG] 巡检记录已保存至桌面 CheckpointLogs\\")
                except Exception as e:
                    self.log(f"[WARN] 写入 INDEX.txt 失败: {e}")

        except Exception as e:
            self.log(f"\n[ERROR] 巡检过程出现异常: {e}\n{traceback.format_exc()}")
            self.play_error_sound()
        finally:
            self.after(0, self.reset_buttons)

    def run_skip_and_checkpoint_pipeline(self):
        """
        强制在当前中断页面点击 Checkpoint 打勾，然后进入下一关。
        """
        _continuing_to_next = False
        try:
            driver = BrowserManager.get_driver()
            checker = BaseChecker(driver, self.log)
            self.log("[SKIP] 正在强制点击当前页面 Checkpoint...")
            checker.click_checkpoint()
            self.log("[SKIP SUCCESS] Checkpoint 打勾完成！准备进入下一关...")

            next_index = self.last_failed_index + 1
            is_full = getattr(self, "current_pipeline_mode", "FULL") == "FULL"

            if self.last_failed_type == "Copier":
                if next_index < 9:
                    _continuing_to_next = True
                    self.log(f"[SKIP] 继续从 Copier 第 {next_index + 1} 站执行...")
                    self.run_full_pipeline(niw_start=15, copier_start=next_index, full=False)
                else:
                    self.log("[COMPLETE] Copier & Server 全部关卡已巡检完毕！")
                    try:
                        checker.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW", wait_seconds=2)
                        self.log("[NAVIGATE] ✅ 已自动跳回 Pending Wager (NIW 第1站) 页面")
                    except Exception:
                        pass
            else:
                if next_index < 15:
                    _continuing_to_next = True
                    self.log(f"[SKIP] 继续从 NIW 第 {next_index + 1} 站执行...")
                    self.run_full_pipeline(niw_start=next_index, copier_start=0, full=is_full)
                else:
                    if is_full:
                        _continuing_to_next = True
                        self.log("[SKIP] NIW 已全部完成，自动接续 Copier & Server 巡检...")
                        self.run_full_pipeline(niw_start=15, copier_start=0, full=True)
                    else:
                        self.log("[COMPLETE] NIW 全部关卡已巡检完毕！")
                        try:
                            checker.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW", wait_seconds=2)
                            self.log("[NAVIGATE] ✅ 已自动跳回 Pending Wager (NIW 第1站) 页面")
                        except Exception:
                            pass

        except Exception as e:
            self.log(f"[ERROR] 强制跳过过程异常: {e}\n{traceback.format_exc()}")
        finally:
            if not _continuing_to_next:
                self.after(0, self.reset_buttons)

