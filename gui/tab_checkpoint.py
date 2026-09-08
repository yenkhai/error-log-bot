"""
================================================================================
Checkpoint 自动化巡检选项卡 UI 模块 (gui/tab_checkpoint.py)
--------------------------------------------------------------------------------
作用与设计解析:
1. Checkpoint 巡检中枢核心: 串联调度 NIW 15 个业务关卡与 Copier 9 个服务器关卡。
2. 弹性执行模式:
   - 【Check All】全量贯通巡检: 先执行 NIW 1~15 关，全部通关后自动切入 Copier 1~9 关。
   - 【Check NIW】/【Check Copier】: 支持单独针对业务或服务器分区进行专项巡检。
   - 【Stop】优雅软停止: 设置停止标志位，允许当前正在执行的网页完整保存后安全退出，不破坏现场。
   - 【Resume】断点续传: 自动记录上一次发生阻断/异常的关卡索引与类型，一键从中断点原地重新尝试。
   - 【Skip】跳过打勾: 强制在当前异常关卡点击页面 Checkpoint 打勾，标记通过并推进到下一关。
3. 动态关卡勾选矩阵 (Matrix Panel):
   - 支持 24 关独立勾选，支持一键全选/全不选，支持折叠与展开以节省纵向屏幕空间。
4. 定时自动巡检引擎 (Hourly Auto-Run Scheduler):
   - 支持 30m / 45m / 60m 周期性自动巡检倒计时，动态秒级心跳驱动，关卡出错时自动暂停等待人工介入。
5. 蜂鸣警报音 (Sound Alert):
   - 检测到红色阻断异常时，自动派发后台守护线程播放 Windows 高频蜂鸣警报音。
6. 实时多色终端控制台:
   - 错误=高亮鲜红粗体、警告=暖橙粗体、成功=翠绿、标题=青蓝粗体、分隔线=暗灰，清晰直观。
================================================================================
"""

# 导入原生时间模块，用于调度倒计时计算与时间戳格式化
import time

# 导入多线程模块，用于将耗时的网页巡检逻辑置于后台线程执行，确保 GUI 视窗操作流畅不卡顿
import threading

# 导入异常堆栈格式化工具，用于在发生异常时将完整调用链输出至日志控制台
import traceback

# 导入 Windows 原生声音模块 (非 Windows 平台或受限环境降级为 None)
try:
    import winsound
except ImportError:
    winsound = None

# 导入 Tkinter 原生 GUI 核心与 CustomTkinter 现代控件库
import tkinter as tk
import customtkinter as ctk

# 导入日期时间模块，用于记录每个关卡巡检完成的精确物理时间
from datetime import datetime

# 导入浏览器核心驱动管理器，用于获取/连接 Chrome 单例
from core.browser import BrowserManager

# 导入检查器基类，用于在所有关卡通关后执行导航回到第一关、以及在 Skip 时执行通用打勾
from core.base_checker import BaseChecker

# 导入内存巡检结果存储中心，用于记录表格结构化数据与刷新浏览器列表
from core.checkpoint_store import CheckpointStore

# ── 导入所有 15 个 NIW 业务关卡检查器 ──
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

# ── 导入所有 9 个 Copier & Server 基础设施关卡检查器 ──
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
#  彩色日志标签配置字典 (LOG_TAGS)
#  结构: tag_name -> (foreground_color 十六进制色彩, is_bold 布尔值)
# ─────────────────────────────────────────────────────────────────────────────
LOG_TAGS = {
    "error":       ("#FF4D4D", True),    # 亮红粗体 — ERROR / Tier 1 / 异常 / 🔴 / 积压 / 阻断
    "warn":        ("#FFB86C", True),    # 暖橙粗体 — WARN / Tier 3 / 提醒 / 🟡 / 仅通知
    "success":     ("#50FA7B", False),   # 翠绿 — SUCCESS / OK / 通关 / 正常 / ✅
    "station":     ("#8BE9FD", True),    # 青蓝粗体 — 关卡站头 / 分区标题 / ===
    "checkpoint":  ("#50FA7B", True),    # 翠绿粗体 — CHECKPOINT 打勾成功
    "stop":        ("#FF79C6", True),    # 粉红粗体 — 用户主动点击 STOP
    "info":        ("#C9D1D9", False),   # 舒适白灰 — 普通说明与正常数据行
    "dim":         ("#555E70", False),   # 低调暗灰 — 分隔横线
    "data":        ("#D8DEE9", False),   # 干净浅灰 — 数据表格明细
}


def _classify_tag(line: str) -> str:
    """
    [智能色彩标签分类器]
    根据单行日志的文本语义特征，精确匹配返回 LOG_TAGS 中对应的色彩样式标签，
    确保致命异常 100% 呈现醒目亮红粗体，普通成功呈翠绿，标题呈青蓝。
    """
    u = line.upper()

    # 1. 错误 / 阻断 / 异常分类 (最高优先级：高亮鲜红粗体 #FF4D4D)
    if any(k in line for k in ["🔴", "红字", "红底", "异常", "积压阻断", "致命", "阻断", "超时积压", "❌"]) or \
       any(k in u for k in ["[ERROR]", "FAILED", "TIER 1", "TIER1", "[INTERRUPT]", "RED NODE", "ERROR/", "[ERROR/"]):
        return "error"

    # 2. 警告 / 仅提示分类 (暖橙粗体 #FFB86C)
    if any(k in line for k in ["🟡", "⚠️", "⚠", "警告", "提醒", "仅通知", "仅提示"]) or \
       any(k in u for k in ["[WARN]", "[NOTICE]", "TIER 3", "TIER3", "WARNING", "WARN/", "[WARN/"]):
        return "warn"

    # 3. 成功 / 正常 / 通关分类 (翠绿 #50FA7B)
    if any(k in line for k in ["✅", "🟢", "通关", "巡检通过", "全绿", "全部正常", "完全正常", "全部 0", "全 0", "[OK/正常]", "[OK]"]) or \
       any(k in u for k in ["SUCCESS", "[COMPLETE]", "CHECK RESULT] SUCCESS", "NO ERROR", "OK/"]):
        return "success"

    # 4. Checkpoint 按钮打勾成功日志
    if "CHECKPOINT" in u and ("SUCCESS" in u or "成功点击" in u):
        return "checkpoint"

    # 5. 关卡站头 / 分区标题 / 边框线 (青蓝粗体 #8BE9FD)
    if any(k in u for k in ["[STATION]", "[PIPELINE", "=== ", "===", "═══"]):
        return "station"
    if "COMPANY:" in u or "PART 1:" in u or "PART 2:" in u or "--- [" in line or ("【" in line and "明细】" in line):
        return "station"

    # 6. 用户主动中止提示 (粉红粗体)
    if "[STOP]" in u:
        return "stop"

    # 7. 纯分隔装饰线 (暗灰 #555E70)
    if set(line.strip()).issubset(set("─═=- \t")) and len(line.strip()) > 5:
        return "dim"

    # 8. 其余常规输出与数据明细 (干净浅灰 #C9D1D9)
    return "info"


class CheckpointTab(ctk.CTkFrame):
    """
    Checkpoint 自动化巡检控制中心视图类
    负责巡检线程生命周期管理、断点记录、关卡矩阵勾选、定时调度倒计时及彩色控制台渲染。
    """

    def __init__(self, parent, app):
        # 1. 显式初始化父类 CTkFrame 容器
        super().__init__(parent)

        # 2. 保存顶层应用 UnifiedBotApp 实例引用
        self.app = app

        # 3. 运行控制标志位
        self.is_running = False          # 是否有巡检正在执行 (True 时互斥锁定其他任务)
        self.stop_requested = False      # 用户是否已请求停止 (True 时当前页面跑完立即优雅退出)

        # 4. 断点续传记录变量 (记录最后一次失败阻断的关卡信息)
        self.last_failed_type = None     # "NIW" 或 "Copier"
        self.last_failed_index = 0       # 关卡在列表中的 0-based 绝对索引

        # 5. 关卡矩阵面板的显示/折叠状态 (默认展开 True)
        self.matrix_visible = True

        # 6. 本轮巡检结果元组列表 [(page_key, display_name, bool_result, timestamp)]
        self._run_results = []

        # 7. 24 个关卡的复选框布尔追踪变量列表 (默认全部打勾 True)
        self.niw_vars    = [ctk.BooleanVar(value=True) for _ in range(15)]
        self.copier_vars = [ctk.BooleanVar(value=True) for _ in range(9)]

        # 8. 定时自动巡检控制变量
        self.hourly_auto_var = ctk.BooleanVar(value=True) # 定时自动开关 (默认开启)
        self.hourly_interval_seconds = 2700               # 默认间隔 2700 秒 (45分钟)
        self.next_run_timestamp = None                    # 下一次触发的目标物理时间戳
        self.hourly_timer_id = None                       # Tkinter after 定时器 ID
        self.hourly_cycle_count = 0                       # 已完成的自动轮次计数器

        # 9. 异常声音报警开关变量 (默认开启 True)
        self.sound_alert_var = ctk.BooleanVar(value=True)

        # 10. 组装所有控件并初始化按钮状态
        self.build_ui()

    # ─────────────────────────────────────────────────────────────────
    #  UI 构建核心
    # ─────────────────────────────────────────────────────────────────
    def build_ui(self):
        """
        构建 Checkpoint 选项卡的全部控件结构:
        1. 顶层主控制按钮栏 (Check All, Check NIW, Check Copier, Stop, Resume, Skip, Collapse, Clear)
        2. 定时自动调度控制条 (Auto Schedule 开关、周期下拉菜单、Sound Alert 报警开关、状态倒计时)
        3. 关卡自定义勾选矩阵 (NIW 15 关 + Copier 9 关，支持全选/反选)
        4. 多色 Console 终端控制台 (带双向滚动条，支持标签高亮)
        """
        # ── 1. 顶层主操作按钮栏 ──
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # ▶ 【Check All】全量贯通巡检按钮 (先跑 NIW 15 关，再接 Copier 9 关)
        self.btn_run_all = ctk.CTkButton(
            top_frame,
            text="Check All",
            command=self.start_full_thread,
            fg_color="#1f538d",
            hover_color="#14375e",
            font=ctk.CTkFont(weight="bold"),
            width=105
        )
        self.btn_run_all.pack(side="left", padx=3, pady=5)

        # ▶ 【Check NIW】仅运行 NIW 业务区 15 关
        self.btn_run_niw = ctk.CTkButton(
            top_frame,
            text="Check NIW",
            command=self.start_niw_only_thread,
            fg_color="#16a085",
            hover_color="#117864",
            font=ctk.CTkFont(weight="bold"),
            width=95
        )
        self.btn_run_niw.pack(side="left", padx=3, pady=5)

        # ▶ 【Check Copier】仅运行 Copier 服务器基础设施区 9 关
        self.btn_run_copier = ctk.CTkButton(
            top_frame,
            text="Check Copier",
            command=self.start_copier_only_thread,
            fg_color="#27ae60",
            hover_color="#1e8449",
            font=ctk.CTkFont(weight="bold"),
            width=100
        )
        self.btn_run_copier.pack(side="left", padx=3, pady=5)

        # ⏹ 【Stop】停止按钮 (软停止：当前正在抓取的页面完成后立即优雅停机)
        self.btn_stop = ctk.CTkButton(
            top_frame,
            text="Stop",
            command=self.request_stop,
            fg_color="#c0392b",
            hover_color="#962d22",
            font=ctk.CTkFont(weight="bold"),
            width=75
        )
        self.btn_stop.pack(side="left", padx=3, pady=5)

        # ⏯ 【Resume】断点续传按钮 (从上次阻断处重新开始)
        self.btn_resume = ctk.CTkButton(
            top_frame,
            text="Resume",
            command=self.start_resume_thread,
            fg_color="#e67e22",
            hover_color="#d35400",
            font=ctk.CTkFont(weight="bold"),
            width=85
        )
        self.btn_resume.pack(side="left", padx=3, pady=5)

        # ⏭ 【Skip】跳过打勾按钮 (在当前中断页面强行点击 Checkpoint 并推进下一关)
        self.btn_skip = ctk.CTkButton(
            top_frame,
            text="Skip",
            command=self.start_skip_and_checkpoint_thread,
            fg_color="#8e44ad",
            hover_color="#732d91",
            font=ctk.CTkFont(weight="bold"),
            width=85
        )
        self.btn_skip.pack(side="left", padx=3, pady=5)

        # 🔽 【Collapse/Expand】折叠/展开关卡选择矩阵按钮 (靠右放置)
        self.btn_toggle_matrix = ctk.CTkButton(
            top_frame,
            text="Collapse",
            command=self.toggle_matrix_panel,
            fg_color="#34495e",
            hover_color="#2c3e50",
            font=ctk.CTkFont(weight="bold"),
            width=85
        )
        self.btn_toggle_matrix.pack(side="right", padx=3, pady=5)

        # 🗑 【Clear】一键清空日志控制台按钮
        self.btn_clear = ctk.CTkButton(
            top_frame,
            text="Clear",
            command=self.clear_log,
            width=65
        )
        self.btn_clear.pack(side="right", padx=3, pady=5)

        # ── 1.5 定时自动巡检调度控制栏 (Hourly Auto-Run Scheduler Bar) ──
        schedule_frame = ctk.CTkFrame(self, fg_color="#1a202c", corner_radius=6)
        schedule_frame.pack(fill="x", padx=10, pady=(2, 4))

        # 定时巡检开关 (绿色激活)
        self.switch_hourly = ctk.CTkSwitch(
            schedule_frame,
            text="⏰ Auto Schedule",
            variable=self.hourly_auto_var,
            command=self.toggle_hourly_auto,
            font=ctk.CTkFont(weight="bold", size=12),
            progress_color="#2ecc71"
        )
        self.switch_hourly.pack(side="left", padx=(10, 6), pady=4)

        # 巡检间隔下拉选择框 (支持 45m / 30m / 60m)
        self.opt_interval = ctk.CTkOptionMenu(
            schedule_frame,
            values=["Every 45m", "Every 30m", "Every 60m (1 hr)"],
            width=135,
            height=24,
            font=ctk.CTkFont(size=11),
            command=self._on_interval_changed
        )
        self.opt_interval.set("Every 45m")
        self.opt_interval.pack(side="left", padx=4, pady=4)

        # 异常蜂鸣报警音开关 (靠最右侧 pack，防止小分辨率下被挤压遮挡)
        self.switch_sound = ctk.CTkSwitch(
            schedule_frame,
            text="🔔 Sound Alert",
            variable=self.sound_alert_var,
            font=ctk.CTkFont(weight="bold", size=11),
            progress_color="#e74c3c",
            width=46
        )
        self.switch_sound.pack(side="right", padx=(6, 12), pady=4)

        # 调度状态动态指示标签 (展示当前倒计时、执行中轮次或暂停状态)
        self.lbl_schedule_status = ctk.CTkLabel(
            schedule_frame,
            text="[Status] ⏳ Initializing..." if self.hourly_auto_var.get() else "[Status] ⏸️ Disabled",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#FFB86C" if self.hourly_auto_var.get() else "#8892B0"
        )
        self.lbl_schedule_status.pack(side="left", padx=(10, 5), pady=4)

        # ── 2. 关卡自定义勾选矩阵 (Selection Matrix Frame) ──
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.pack(fill="x", padx=10, pady=5)

        # (1) NIW 业务关卡子区域 (15 关)
        niw_names = [
            "1.Pending Wager", "2.CCL Recover", "3.Matches Wagers", "4.Result Process",
            "5.Calculate Betslips", "6.RPT PolyMarket", "7.RPT Compare", "8.RPT AI",
            "9.RPT Compare UTC", "10.Forecast", "11.Check CCL", "12.Wsum Sport",
            "13.HG Percentages", "14.RPT CRS", "15.1 Wallet Pending"
        ]
        self._build_station_matrix(
            self.select_frame,
            title="[CONFIG] NIW Stations (Default: Select All):",
            names=niw_names,
            vars_list=self.niw_vars
        )

        # (2) Copier & Server 基础设施关卡子区域 (9 关)
        copier_names = [
            "1.Copier", "2.DB Server", "3.AP Server", "4.AP Space", "5.Error Log",
            "6.Redis", "7.Robot Monitor", "8.NIW Robot", "9.Info Robot"
        ]
        self._build_station_matrix(
            self.select_frame,
            title="[CONFIG] Copier & Server Stations (Default: Select All):",
            names=copier_names,
            vars_list=self.copier_vars
        )

        # ── 3. 彩色日志控制台 (Multicolor Tkinter Text Console) ──
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # 使用原生 tk.Text 支持丰富的行内多色文本标签，配置深色背景
        self.log_text = tk.Text(
            log_frame,
            font=("Consolas", 13),
            bg="#1E1E2E",             # 舒适暗夜黑底色
            fg="#F8F8F2",             # 默认白灰文本
            insertbackground="#F8F8F2",
            selectbackground="#44475A",
            relief="flat",
            borderwidth=0,
            wrap="none",              # 不自动换行，保证数据表格整齐对齐
            state="disabled"          # 初始只读
        )

        # 垂直滚动条
        scrollbar_y = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar_y.pack(side="right", fill="y")

        # 水平滚动条 (便于横向查看超宽数据表格)
        scrollbar_x = tk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        scrollbar_x.pack(side="bottom", fill="x")

        # 关联滚动条
        self.log_text.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        self.log_text.pack(side="left", fill="both", expand=True)

        # 注册预定义的所有色彩标签
        for tag_name, (fg_color, is_bold) in LOG_TAGS.items():
            font_weight = "bold" if is_bold else "normal"
            self.log_text.tag_configure(
                tag_name,
                foreground=fg_color,
                font=("Consolas", 13, font_weight)
            )

        # 初始调用：精确计算并初始化所有操作按钮的启用/置灰状态
        self.update_button_states()

        # 若默认开启定时自动巡检 (Auto Schedule)，初始化调度引擎并启动倒计时
        if self.hourly_auto_var.get():
            self.toggle_hourly_auto()

    # ─────────────────────────────────────────────────────────────────
    #  工具辅助方法
    # ─────────────────────────────────────────────────────────────────
    def _build_station_matrix(self, parent, title: str, names: list, vars_list: list, cols: int = 5):
        """
        [通用关卡复选框矩阵构建器]
        生成包含标题、Select All / Deselect All 按钮以及自动分行换列 CheckBox 网格的面板容器。
        """
        box = ctk.CTkFrame(parent)
        box.pack(fill="x", padx=5, pady=5)

        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=5, pady=(2, 2))
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(weight="bold")
        ).pack(side="left")

        # 全选按钮
        ctk.CTkButton(
            header, text="Select All", width=75, height=22,
            command=lambda: self.set_all_vars(vars_list, True)
        ).pack(side="left", padx=5)

        # 全不选按钮
        ctk.CTkButton(
            header, text="Deselect All", width=85, height=22,
            command=lambda: self.set_all_vars(vars_list, False)
        ).pack(side="left")

        # 复选框网格布局
        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=5, pady=(0, 5))
        for i, name in enumerate(names):
            ctk.CTkCheckBox(
                grid, text=name, variable=vars_list[i], font=ctk.CTkFont(size=11)
            ).grid(row=i // cols, column=i % cols, sticky="w", padx=4, pady=2)
    def toggle_matrix_panel(self):
        """[折叠/展开关卡矩阵] 切换矩阵面板的显隐状态，释放纵向日志视窗空间"""
        if self.matrix_visible:
            self.select_frame.pack_forget()
            self.matrix_visible = False
            self.btn_toggle_matrix.configure(text="▶ Expand")
        else:
            self.select_frame.pack(fill="x", padx=10, pady=5, before=self.log_text.master)
            self.matrix_visible = True
            self.btn_toggle_matrix.configure(text="🔽 Collapse")

    def set_all_vars(self, var_list, value: bool):
        """[批量设置复选框状态] 将布尔变量列表全设为 True 或 False"""
        for v in var_list:
            v.set(value)

    def log(self, message: str):
        """
        [多色日志追加方法]
        线程安全地向彩色日志控制台追加一行文字，自动通过 _classify_tag 分配色彩标签并滚动到最底端。
        """
        def append():
            tag = _classify_tag(message)
            self.log_text.configure(state="normal")
            # 缓冲区行数保护：若行数超过 3000 行，自动修剪前 500 行，防止长时间巡检内存暴涨
            try:
                num_lines = int(float(self.log_text.index("end-1c")))
                if num_lines > 3000:
                    self.log_text.delete("1.0", "501.0")
            except Exception:
                pass
            self.log_text.insert("end", message + "\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, append)

    def clear_log(self):
        """[清空日志] 清空当前控制台的所有历史记录"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────
    #  定时自动巡检调度方法 (Hourly Auto-Run Engine)
    # ─────────────────────────────────────────────────────────────────
    def _on_interval_changed(self, choice: str):
        """[巡检周期切换事件] 当下拉框在 30m / 45m / 60m 之间切换时重新设定计时基准"""
        if "30" in choice:
            self.hourly_interval_seconds = 1800
        elif "45" in choice:
            self.hourly_interval_seconds = 2700
        else:
            self.hourly_interval_seconds = 3600

        # 若当前定时器处于开启状态且正在倒计时中，按新间隔重新计算目标触发时间
        if self.hourly_auto_var.get() and self.next_run_timestamp is not None:
            self.next_run_timestamp = time.time() + self.hourly_interval_seconds
            self.log(f"[TIMER] ⚙️ Schedule interval switched to: {choice}")

    def toggle_hourly_auto(self):
        """[开启/关闭定时自动巡检] 开关激活后进入倒计时阶段，不立即打断正在进行的操作"""
        enabled = self.hourly_auto_var.get()
        if enabled:
            self.hourly_cycle_count = 0
            # 开启瞬间计算第一次触发的目标时间戳 (如当前时间 + 60分钟)
            self.next_run_timestamp = time.time() + self.hourly_interval_seconds
            mins = self.hourly_interval_seconds // 60
            target_time = time.strftime("%H:%M:%S", time.localtime(self.next_run_timestamp))

            self.log("══════════════════════════════════════════════════")
            self.log(f"  ⏰ Auto schedule enabled! (Interval: Every {mins} min)")
            self.log(f"  ⏳ Countdown started: Next run at {target_time} (in ~{mins} mins) for Cycle 1")
            self.log("══════════════════════════════════════════════════")

            # 清理可能存在的残余定时器并启动 1 秒心跳调度引擎
            if self.hourly_timer_id is not None:
                self.after_cancel(self.hourly_timer_id)
            self._hourly_tick()
        else:
            self.log("[TIMER] ⏹ Auto schedule disabled.")
            self.next_run_timestamp = None
            self.lbl_schedule_status.configure(text="[Status] ⏸️ Disabled", text_color="#8892B0")
            if self.hourly_timer_id is not None:
                self.after_cancel(self.hourly_timer_id)
                self.hourly_timer_id = None

    def _hourly_tick(self):
        """
        [1秒级高精度倒计时调度心跳引擎]
        每秒被 self.after 递归触发一次，计算剩余秒数，并在倒计时归零时自动唤醒全量巡检。
        保护逻辑:
        1. 若巡检正在执行中，状态展示为 Running，不重复触发。
        2. 若之前发生过 Error 阻断，状态展示为 Paused，锁定下一轮，保护现场等待人工排查。
        3. 若 Error Log 正在抓取，延后 30 秒再次检测，防止双任务碰撞。
        """
        if not self.hourly_auto_var.get():
            self.hourly_timer_id = None
            return

        now = time.time()
        if self.is_running:
            # 状态 1: 正在运行当前轮次巡检
            self.lbl_schedule_status.configure(
                text=f"[Status] 🚀 Cycle {self.hourly_cycle_count + 1} Running...",
                text_color="#50FA7B"
            )
            # 运行期间清空 next_run_timestamp，通关后再精准设定下一轮时间
            self.next_run_timestamp = None
        else:
            # 状态 2: 当前处于空闲状态
            if self.last_failed_type is not None:
                # 存在未解决的中断阻断，暂停自动巡检保护现场
                self.lbl_schedule_status.configure(
                    text=f"[Status] ⚠️ Paused ({self.last_failed_type} Error)",
                    text_color="#FF4D4D"
                )
            else:
                # 正常空闲状态
                if self.next_run_timestamp is None:
                    # 刚完成上一轮，计算下一次执行时间
                    self.hourly_cycle_count += 1
                    self.next_run_timestamp = now + self.hourly_interval_seconds
                    mins = self.hourly_interval_seconds // 60
                    target_time = time.strftime("%H:%M:%S", time.localtime(self.next_run_timestamp))
                    self.log(f"\n[TIMER] ⏳ Checkpoint completed! Auto countdown started: Next run at {target_time} (in ~{mins} mins) for Cycle {self.hourly_cycle_count + 1}")

                diff = int(self.next_run_timestamp - now)
                if diff <= 0:
                    # 倒计时归零，唤醒下一轮全量巡检
                    self.next_run_timestamp = None
                    if not self._check_cross_tab_busy():
                        self.log(f"\n[TIMER] ⏰ Countdown reached! Starting scheduled Cycle {self.hourly_cycle_count + 1}...")
                        self.start_full_thread()
                    else:
                        # 另一个 Tab 正忙，温和延后 30 秒
                        self.log("[TIMER] ⚠️ Error Log exporter is currently active. Postponing checkpoint run by 30 seconds...")
                        self.next_run_timestamp = now + 30
                else:
                    # 正常倒计时展示
                    mins = diff // 60
                    secs = diff % 60
                    target_time = time.strftime("%H:%M:%S", time.localtime(self.next_run_timestamp))
                    self.lbl_schedule_status.configure(
                        text=f"[Status] ⏳ Next: {target_time} ({mins}m {secs:02d}s) | Cycles: {self.hourly_cycle_count}",
                        text_color="#FFB86C"
                    )

        # 每隔 1 秒递归调度下一跳心跳
        self.hourly_timer_id = self.after(1000, self._hourly_tick)


    def play_error_sound(self):
        """
        [异常蜂鸣报警音触发器]
        当巡检关卡检测到红色阻断异常时调用。
        判断用户是否开启了声音报警开关 (sound_alert_var)，
        若开启，派发后台守护线程播放 Windows 原生高频蜂鸣 (1800Hz)，连续蜂鸣 3 声，不卡顿主线程。
        """
        if not self.sound_alert_var.get():
            return

        def _beep():
            if not winsound:
                return
            try:
                # 连续播放 3 声清晰的高频警报蜂鸣音 (频率 1800Hz，持续 200ms，间隔 80ms)
                for _ in range(3):
                    winsound.Beep(1800, 200)
                    time.sleep(0.08)
            except Exception:
                # 兼容非 Windows 环境或无声卡扬声器环境，静默忽略
                pass

        # 启动后台独立守护线程，避免 winsound 耗时阻塞 Tkinter 界面响应
        threading.Thread(target=_beep, daemon=True).start()

    def request_stop(self):
        """
        [用户请求停止巡检 (软停止机制)]
        设计原理:
        区别于粗暴的 kill 进程或立即中断，软停止会在当前关卡页面巡检及日志写入完整完成后才退出，
        保护浏览器与本地日志文件不处于破损不一致状态。
        """
        if not self.is_running:
            self.log("[STOP] No active inspection task running.")
            return

        # 标记停止请求为 True，正在运行的关卡循环在处理完当页后会检测此变量并退出
        self.stop_requested = True
        self.log("[STOP] ⏹ Stop request received! Halting after current page finishes...")

        # 若定时自动调度仍在运行，给予友好提示
        if self.hourly_auto_var.get():
            self.log("[STOP] Note: Auto schedule remains enabled. Toggle [⏰ Auto Schedule] switch to disable.")

    def update_button_states(self):
        """
        [全量操作按钮状态精准状态机]
        根据当前系统 4 种互斥状态，统一计算并刷新所有按钮的启用 (normal) 与禁用 (disabled):
        - 状态 1: 自身巡检正在运行中 (is_running=True) -> 仅 [Stop] 可用，其余全置灰
        - 状态 2: 另一个 Tab (Error Log) 正在运行中 -> 全部置灰 (杜绝浏览器并发竞争)
        - 状态 3: 存在阻断中断点 (last_failed_type 不为空) -> [Resume] 与 [Skip] 亮起，允许重试或跳过
        - 状态 4: 系统完全空闲 -> [Check All/NIW/Copier] 亮起，[Resume/Skip/Stop] 置灰
        """
        def apply():
            # 1. 检测 Error Log 选项卡是否处于活跃运行状态
            is_error_log_running = False
            if hasattr(self.app, 'error_log_tab') and getattr(self.app.error_log_tab, 'is_running', False):
                is_error_log_running = True

            # 2. 状态机条件分支判定
            if self.is_running:
                # 自身正在巡检中
                self.btn_run_all.configure(state="disabled")
                self.btn_run_niw.configure(state="disabled")
                self.btn_run_copier.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="normal") # 唯独 Stop 保持可用
            elif is_error_log_running:
                # 另一个 Tab 正在运行，彻底锁定本 Tab 所有执行按钮
                self.btn_run_all.configure(state="disabled")
                self.btn_run_niw.configure(state="disabled")
                self.btn_run_copier.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")
            elif self.last_failed_type is not None:
                # 存在未处理的中断点（处于待续传/待跳过状态）
                self.btn_run_all.configure(state="normal")
                self.btn_run_niw.configure(state="normal")
                self.btn_run_copier.configure(state="normal")
                self.btn_resume.configure(state="normal") # 激活 Resume 续传
                self.btn_skip.configure(state="normal")   # 激活 Skip 强制打勾
                self.btn_stop.configure(state="disabled")
            else:
                # 系统初始或已全部通关的完全空闲状态
                self.btn_run_all.configure(state="normal")
                self.btn_run_niw.configure(state="normal")
                self.btn_run_copier.configure(state="normal")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")

        # 确保在 Tkinter 主事件循环中安全更新 UI 控件
        self.after(0, apply)

    def toggle_buttons(self, enabled: bool):
        """兼容旧接口的别名方法，直接统一重定向至 update_button_states"""
        self.update_button_states()

    def reset_buttons(self):
        """
        [任务结束重置状态]
        当后台巡检子线程正常结束或异常退出时，由 finally 块回调本方法，
        清空运行标志并刷新主窗口所有 Tab 的排他互斥锁。
        """
        self.is_running = False
        self.stop_requested = False
        self._notify_state_change()

        # 确保定时自动巡检调度引擎处于活跃运行状态
        if self.hourly_auto_var.get() and self.hourly_timer_id is None:
            self._hourly_tick()

    def _notify_state_change(self):
        """[跨 Tab 状态通知辅助方法] 统一触发全局协调器或本地按钮刷新"""
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()

    def _check_cross_tab_busy(self) -> bool:
        """
        [跨 Tab 互斥锁检测]
        检查 Error Log 导出工具是否正在运行。若在运行，拒绝本次巡检请求并打印警告。
        """
        if hasattr(self.app, 'error_log_tab') and getattr(self.app.error_log_tab, 'is_running', False):
            self.log("[WARN] 🚫 Operation rejected: Error Log Exporter is currently running! Please wait or stop Error Log task.")
            return True
        return False

    # ─────────────────────────────────────────────────────────────────
    #  后台子线程启动入口 (Thread Launchers)
    # ─────────────────────────────────────────────────────────────────
    def _start_pipeline_thread(self, mode: str, niw_start: int, copier_start: int, full: bool, banner_text: str):
        """
        [内部通用流水线子线程启动器]
        统一处理排他检测、状态标记初始化、断点重置、跨 Tab 通知及守护线程拉起。
        """
        # 1. 排他锁与防抖检测
        if self.is_running or self._check_cross_tab_busy():
            return

        # 2. 设置运行状态与流水线模式
        self.current_pipeline_mode = mode
        self.is_running = True
        self.stop_requested = False
        self._run_results = []

        # 3. 若从该分区起始位置从头执行，重置历史断点记录
        if niw_start in (0, 15) and copier_start == 0:
            self.last_failed_type = None
            self.last_failed_index = 0

        # 4. 派发互斥状态变更通知
        self._notify_state_change()

        # 5. 打印醒目的开始旗标
        self.log("══════════════════════════════════════════════════")
        self.log(f"  ▶ {banner_text}")
        self.log("══════════════════════════════════════════════════")

        # 6. 创建并启动后台守护线程运行流水线
        threading.Thread(
            target=self.run_full_pipeline,
            args=(niw_start, copier_start, full),
            daemon=True
        ).start()

    def start_full_thread(self, niw_start=0, copier_start=0, full=True):
        """
        [启动全量贯通巡检子线程]
        流程: NIW 15 关全部执行通过 -> 自动衔接 Copier 9 关执行。
        """
        self._start_pipeline_thread(
            mode="FULL",
            niw_start=niw_start,
            copier_start=copier_start,
            full=full,
            banner_text="Full Checkpoint Started — NIW (15 Stations) → Copier (9 Stations)"
        )

    def start_niw_only_thread(self, niw_start=0):
        """
        [启动仅运行 NIW 业务区 15 关子线程]
        执行完第 15 关后结束，不进入 Copier 分区。
        """
        self._start_pipeline_thread(
            mode="NIW",
            niw_start=niw_start,
            copier_start=0,
            full=False,
            banner_text="Checkpoint Started — NIW Only (15 Stations)"
        )

    def start_copier_only_thread(self, copier_start=0):
        """
        [启动仅运行 Copier 基础设施区 9 关子线程]
        直接跳过 NIW 分区 (niw_start=15)，只执行 Copier 9 关。
        """
        self._start_pipeline_thread(
            mode="COPIER",
            niw_start=15,
            copier_start=copier_start,
            full=False,
            banner_text="Checkpoint Started — Copier & Server Only (9 Stations)"
        )

    def start_resume_thread(self):
        """
        [断点续传启动入口]
        读取 self.last_failed_type 与 self.last_failed_index，
        从上次发生异常中断的关卡原地重新发起检测，无需从第 1 关重新跑起。
        """
        if self.is_running or self._check_cross_tab_busy():
            return

        is_full = getattr(self, "current_pipeline_mode", "FULL") == "FULL"

        if self.last_failed_type == "Copier":
            self.log(f"[RESUME] Resuming from Copier Station {self.last_failed_index + 1}...")
            self.start_copier_only_thread(copier_start=self.last_failed_index)
        else:
            self.log(f"[RESUME] Resuming from NIW Station {self.last_failed_index + 1}...")
            if is_full:
                self.start_full_thread(niw_start=self.last_failed_index, copier_start=0, full=True)
            else:
                self.start_niw_only_thread(niw_start=self.last_failed_index)

    def start_skip_and_checkpoint_thread(self):
        """
        [跳过打勾启动入口]
        在当前停滞的页面强行点击 Checkpoint 按钮打勾，随后继续推进下一关卡。
        """
        if self.is_running or self._check_cross_tab_busy():
            return

        self.is_running = True
        self._notify_state_change()

        self.log("[SKIP] Force passing current station and moving to next...")
        threading.Thread(target=self.run_skip_and_checkpoint_pipeline, daemon=True).start()

    def _handle_all_passed(self, driver):
        """
        [全量通关善后与归位逻辑]
        清空中断指针，打印通关横幅，并将浏览器菜单导航回 NIW 第 1 关 Pending Wager。
        """
        self.last_failed_type = None
        self.last_failed_index = 0
        self.log("\n══════════════════════════════════════════════════")
        self.log("  🎉 Congratulations! All checkpoint stations passed successfully!")
        self.log("══════════════════════════════════════════════════")
        try:
            # 按照运维标准规范，所有关卡巡检完成后，自动将浏览器菜单切回 NIW 第 1 关 Pending Wager 归位
            checker = BaseChecker(driver, self.log)
            checker.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW", wait_seconds=2)
            self.log("[NAVIGATE] ✅ All stations passed. Navigated back to Pending Wager (NIW Station 1)")
        except Exception:
            pass

    def _execute_station_loop(self, section_name: str, checkers: list, page_keys: list, var_list: list, start_idx: int) -> bool:
        """
        [关卡分区执行循环引擎]
        统一执行一个分区内的各站巡检，处理跳过、结果记录、LogViewer 联动刷新、异常中断与用户停止。
        返回值: interrupted (bool) — 若遇到 Error 或收到用户 Stop 信号则返回 True，否则返回 False。
        """
        for i, (name, checker) in enumerate(checkers[start_idx:]):
            idx = start_idx + i

            # 检测该关卡是否在界面网格中被用户取消打勾
            if not var_list[idx].get():
                self.log(f"[SKIP] Skipped {name} (unchecked by user)")
                continue

            # 执行关卡检查器核心 check 逻辑
            res = checker.check()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 记录本关巡检结果
            self._run_results.append((page_keys[idx], name, res, ts))

            # 实时通知第 3 个 Tab (LogViewerTab) 刷新列表状态
            if hasattr(self.app, 'log_viewer_tab'):
                self.after(0, self.app.log_viewer_tab.refresh_list)

            # 检查结果是否发生错误 (res 为 False)
            if not res:
                self.last_failed_type = section_name
                self.last_failed_index = idx
                self.log(f"\n[INTERRUPT] ❌ {name} error detected, inspection halted!")
                self.log("  → Click [Resume] to retry current station")
                self.log("  → Click [Skip] to force pass current station and proceed")
                self.play_error_sound()
                return True # 中断当前流水线，等待用户介入

            # 检测用户是否点击了 Stop 停止按钮
            if self.stop_requested:
                self.log(f"\n[STOP] ⏹ Completed {name}. Stopping pipeline per user request.")
                return True

        return False

    # ─────────────────────────────────────────────────────────────────
    #  流水线调度核心逻辑 (Pipeline Execution Engine)
    # ─────────────────────────────────────────────────────────────────
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
            user, pwd = self.app.get_credentials()
            url = self.app.get_login_url()
            self.log(f"[CONFIG] User: {user}  |  URL: {url}")

            # 2. 连接或启动底层 Chrome WebDriver 驱动
            self.log("[BROWSER] Connecting to Chrome browser...")
            driver = BrowserManager.get_driver(url=url, user=user, pwd=pwd)
            self.log("[BROWSER] Browser ready!")
            self.log("──────────────────────────────────────────────────")

            # 3. 构造 15 个 NIW 关卡实例序列与标准存储键列表
            niw_page_keys = [f"niw_{str(i+1).zfill(2)}" for i in range(15)]
            niw_checkers = [
                ("NIW Station 01 - Pending Wager",     PendingWagerChecker(driver, self.log)),
                ("NIW Station 02 - CCL Recover",        CCLRecoverChecker(driver, self.log)),
                ("NIW Station 03 - Matches Wagers",     MatchesWagersChecker(driver, self.log)),
                ("NIW Station 04 - Result Process",     ResultProcessChecker(driver, self.log)),
                ("NIW Station 05 - Calculate Betslips", CalculateBetslipsChecker(driver, self.log)),
                ("NIW Station 06 - RPT PolyMarket",     RPTPolyMarketChecker(driver, self.log)),
                ("NIW Station 07 - RPT Compare",        RPTCompareChecker(driver, self.log)),
                ("NIW Station 08 - RPT AI",             RPTAIChecker(driver, self.log)),
                ("NIW Station 09 - RPT Compare UTC",    RPTCompareUTCChecker(driver, self.log)),
                ("NIW Station 10 - Forecast",           ForecastChecker(driver, self.log)),
                ("NIW Station 11 - Check CCL",          CheckCCLChecker(driver, self.log)),
                ("NIW Station 12 - Wsum Sport",         WsumSportChecker(driver, self.log)),
                ("NIW Station 13 - HG Percentages",     HGPercentagesChecker(driver, self.log)),
                ("NIW Station 14 - RPT CRS",            RPTCRSChecker(driver, self.log)),
                ("NIW Station 15 - 1 Wallet Pending",   OneWalletPendingChecker(driver, self.log)),
            ]

            # 4. 构造 9 个 Copier 关卡实例序列与标准存储键列表
            copier_page_keys = [f"copier_{str(i+1).zfill(2)}" for i in range(9)]
            copier_checkers = [
                ("Copier Station 01 - Copier",            CopierChecker(driver, self.log)),
                ("Copier Station 02 - DB Server Status",   DBServerStatusChecker(driver, self.log)),
                ("Copier Station 03 - AP Server Status",   APServerStatusChecker(driver, self.log)),
                ("Copier Station 04 - Check AP Space",     CheckAPSpaceChecker(driver, self.log)),
                ("Copier Station 05 - Error Log",          ErrorLogChecker(driver, self.log)),
                ("Copier Station 06 - Redis Server",       RedisServerChecker(driver, self.log)),
                ("Copier Station 07 - Robot Monitor",      RobotMonitorChecker(driver, self.log)),
                ("Copier Station 08 - NIW Robot Monitor",  NIWRobotMonitorChecker(driver, self.log)),
                ("Copier Station 09 - Info Robot Monitor", InfoRobotMonitorChecker(driver, self.log)),
            ]

            interrupted = False # 中断标志位

            # ── 5. 执行 NIW 业务分区循环 ──
            if niw_start < 15:
                self.log(f"[PIPELINE START] NIW Section — Starting from Station {niw_start+1}")
                interrupted = self._execute_station_loop("NIW", niw_checkers, niw_page_keys, self.niw_vars, niw_start)

            # ── 6. 执行 Copier & Server 基础设施分区循环 ──
            should_run_copier = (full or copier_start > 0 or getattr(self, "current_pipeline_mode", "FULL") in ["FULL", "COPIER"])
            if not interrupted and should_run_copier:
                self.log("──────────────────────────────────────────────────")
                self.log(f"[PIPELINE START] Copier & Server Section — Starting from Station {copier_start+1}")
                interrupted = self._execute_station_loop("Copier", copier_checkers, copier_page_keys, self.copier_vars, copier_start)
                if not interrupted:
                    self.log("[COMPLETE] All Copier & Server stations completed!")
            elif not interrupted and not should_run_copier and niw_start < 15:
                self.log("[COMPLETE] All NIW stations completed!")

            # ── 7. 全量通关后的善后与归位逻辑 ──
            if not interrupted:
                self._handle_all_passed(driver)

            # 最终刷新一次日志浏览器
            if hasattr(self.app, 'log_viewer_tab'):
                self.after(0, self.app.log_viewer_tab.refresh_list)

        except Exception as e:
            # 捕获致命未处理异常，输出详细堆栈并触发报警音
            self.log(f"\n[ERROR] Pipeline encountered an exception: {e}\n{traceback.format_exc()}")
            self.play_error_sound()
        finally:
            # 退出工作线程时重置所有操作按钮状态
            self.after(0, self.reset_buttons)

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

            # 1. 强行在当前页面点击 Checkpoint 打勾
            self.log("[SKIP] Forcing Checkpoint click on current page...")
            checker.click_checkpoint()
            self.log("[SKIP SUCCESS] Checkpoint checked! Preparing next station...")

            # 2. 标记当前关卡虽被跳过并强制点击 Checkpoint 打勾，但在 CheckpointStore 中维持 Error 异常状态（用户要求：被 skip 跳过的关卡不要改成 passed，维持 error 状态）
            curr_pk = f"copier_{str(self.last_failed_index + 1).zfill(2)}" if self.last_failed_type == "Copier" else f"niw_{str(self.last_failed_index + 1).zfill(2)}"
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
                self.after(0, self.app.log_viewer_tab.refresh_list)

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
                        self.after(0, self.app.log_viewer_tab.refresh_list)
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
                            self.after(0, self.app.log_viewer_tab.refresh_list)

        except Exception as e:
            self.log(f"[ERROR] Force skip encountered exception: {e}\n{traceback.format_exc()}")
        finally:
            # 若没有后续关卡推进，重置按钮状态
            if not _continuing_to_next:
                self.after(0, self.reset_buttons)


