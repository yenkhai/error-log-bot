from config import save_config
from core.stations import STATION_LIST
"""
================================================================================
Checkpoint 自动化巡检选项卡 UI 模块 (gui/tab_checkpoint.py)
--------------------------------------------------------------------------------
作用与设计解析:
1. Checkpoint 巡检中枢核心: 串联调度 NIW 15 个业务关卡与 Copier 9 个服务器关卡。
2. 弹性执行模式:
   - 【Check】按勾选项巡检: 先执行勾选的 NIW 关卡，再执行勾选的 Copier 关卡。
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
from datetime import datetime

# 导入浏览器核心驱动管理器，用于获取/连接 Chrome 单例
from core.compact_log import compact_message
from core.browser import BrowserManager

# 导入检查器基类，用于在所有关卡通关后执行导航回到第一关、以及在 Skip 时执行通用打勾
from core.base_checker import BaseChecker

# 导入内存巡检结果存储中心，用于记录表格结构化数据与刷新浏览器列表
from core.checkpoint_store import CheckpointStore

# ── 导入所有 15 个 NIW 业务关卡检查器 ──
from services.checkpoint_engine import CheckpointEngine
from core.stations import STATIONS
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
    "noon_fast":   ("#F1FA8C", True),    # 明黄粗体 — 美东午间快速通关提示
    "info":        ("#C9D1D9", False),   # 舒适白灰 — 普通说明与正常数据行
    "dim":         ("#555E70", False),   # 低调暗灰 — 分隔横线
}


def _classify_tag(line: str) -> str:
    """
    [智能色彩标签分类器]
    根据单行日志的文本语义特征，精确匹配返回 LOG_TAGS 中对应的色彩样式标签，
    确保致命异常 100% 呈现醒目亮红粗体，普通成功呈翠绿，标题呈青蓝。
    """
    # Structured outcomes take priority over words such as "Tier 1 = 0" or "不阻断".
    if line.startswith(("[RESULT]", "[DETAIL]")):
        if "❌" in line:
            return "error"
        if "⚠" in line:
            return "warn"
        if "✅" in line:
            return "success"
    u = line.upper()

    # 1. 错误 / 阻断 / 异常分类 (最高优先级：高亮鲜红粗体 #FF4D4D)
    if any(k in line for k in ["🔴", "红字", "红底", "异常", "积压阻断", "致命", "阻断", "超时积压", "❌"]) or \
       any(k in u for k in ["[ERROR]", "FAILED", "TIER 1", "TIER1", "[INTERRUPT]", "RED NODE", "ERROR/", "[ERROR/"]):
        return "error"

    # 2. 美东午间快速通关分类 (明黄粗体 #F1FA8C)
    if "[NOON FAST]" in u or "NOON FAST" in u:
        return "noon_fast"

    # 3. 警告 / 仅提示分类 (暖橙粗体 #FFB86C)
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


class CheckpointTab(ctk.CTkFrame, CheckpointEngine):
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
        self.paused_station = None       # 手动暂停位置 (section, index)，与失败断点独立
        self.last_failed_index = 0       # 关卡在列表中的 0-based 绝对索引

        # 5. 关卡矩阵面板的显示/折叠状态 (默认展开 True)
        self.matrix_visible = True

        # 6. 本轮巡检流水线执行模式 (FULL/NIW/COPIER)
        self.current_pipeline_mode = "FULL"

        # 7. 24 个关卡的复选框布尔追踪变量列表 (默认全部打勾 True)
        self.niw_vars    = [ctk.BooleanVar(value=True) for _ in range(15)]
        self.copier_vars = [ctk.BooleanVar(value=True) for _ in range(9)]
        self.niw_checkpoint_only_vars = [ctk.BooleanVar(value=False) for _ in range(15)]
        self.copier_checkpoint_only_vars = [ctk.BooleanVar(value=False) for _ in range(9)]
        bypass = self.app.config_data.get("CHECKPOINT_ONLY", {})
        self.checkpoint_only_enabled = ctk.BooleanVar(value=bool(bypass.get("enabled", False)))
        selected_keys = set(bypass.get("pages", []))
        for index, (key, _) in enumerate(STATION_LIST):
            variables = self.niw_checkpoint_only_vars if index < 15 else self.copier_checkpoint_only_vars
            variables[index if index < 15 else index - 15].set(key in selected_keys)
        self._checkpoint_only_dialog = None

        # 8. 定时自动巡检控制变量
        self.hourly_auto_var = ctk.BooleanVar(value=True) # 定时自动开关 (默认开启)
        self.hourly_interval_seconds = 2700               # 默认间隔 2700 秒 (45分钟)
        self.next_run_timestamp = None                    # 下一次触发的目标物理时间戳
        self.hourly_timer_id = None                       # Tkinter after 定时器 ID
        self.hourly_cycle_count = 0                       # 已完成的自动轮次计数器

        # 9. 异常声音报警开关变量 (默认开启 True)
        self.sound_alert_var = ctk.BooleanVar(value=True)

        # 10. 美东午间快速通关控制变量 (12:00-14:00 自动跳过未结关卡，默认开启 True)
        self.noon_fast_mode_var = ctk.BooleanVar(value=True)
        self.noon_early_exit_today = False
        self.last_noon_check_date = None

        # 11. 组装所有控件并初始化按钮状态
        self.build_ui()

    # ─────────────────────────────────────────────────────────────────
    #  UI 构建核心
    # ─────────────────────────────────────────────────────────────────
    def build_ui(self):
        """
        构建 Checkpoint 选项卡的全部控件结构:
        1. 顶层主控制按钮栏 (Check, Stop, Resume, Skip, Collapse, Clear)
        2. 定时自动调度控制条 (Auto Schedule 开关、周期下拉菜单、Sound Alert 报警开关、状态倒计时)
        3. 关卡自定义勾选矩阵 (NIW 15 关 + Copier 9 关，支持全选/反选)
        4. 多色 Console 终端控制台 (带双向滚动条，支持标签高亮)
        """
        # ── 1. 顶层主操作按钮栏 ──
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 按下方勾选项执行，顺序为 NIW → Copier。
        self.btn_check = ctk.CTkButton(
            top_frame,
            text="Check",
            command=self.start_full_thread,
            fg_color="#1f538d",
            hover_color="#14375e",
            font=ctk.CTkFont(weight="bold"),
            width=105
        )
        self.btn_check.pack(side="left", padx=3, pady=5)

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
        ctk.CTkSwitch(top_frame, text="仅 Checkpoint", variable=self.checkpoint_only_enabled,
                      command=self._toggle_checkpoint_only, progress_color="#d48806", width=120).pack(side="left", padx=(12, 4))
        ctk.CTkButton(top_frame, text="设置", width=48, command=self._open_checkpoint_only_dialog).pack(side="left", padx=3)

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

        # 美东午间快速通关开关 (12:00-14:00 自动开启，默认开启，支持随时手动启闭)
        self.switch_noon_fast = ctk.CTkSwitch(
            schedule_frame,
            text="⚡ Noon Fast (12-2pm)",
            variable=self.noon_fast_mode_var,
            command=self._on_noon_fast_toggle,
            font=ctk.CTkFont(weight="bold", size=11),
            progress_color="#f39c12",
            width=46
        )
        self.switch_noon_fast.pack(side="right", padx=(6, 6), pady=4)

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
        niw_names = [key.rsplit("_", 1)[1] + ". " + title.split(" - ", 1)[1] for key, title, _ in STATIONS if key.startswith("niw_")]
        self._build_station_matrix(
            self.select_frame,
            title="[CONFIG] NIW Stations (Default: Select All):",
            names=niw_names,
            vars_list=self.niw_vars
        )

        # (2) Copier & Server 基础设施关卡子区域 (9 关)
        copier_names = [key.rsplit("_", 1)[1] + ". " + title.split(" - ", 1)[1] for key, title, _ in STATIONS if key.startswith("copier_")]
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
            ctk.CTkCheckBox(grid, text=name, variable=vars_list[i], font=ctk.CTkFont(size=11)).grid(
                row=i // cols, column=i % cols, sticky="w", padx=4, pady=2)

    def _save_checkpoint_only(self, enabled, pages):
        updated = {**self.app.config_data, "CHECKPOINT_ONLY": {"enabled": enabled, "pages": pages}}
        if not save_config(updated):
            self.log("[ERROR] 无法保存仅 Checkpoint 设置，请重试。")
            return False
        self.app.config_data = updated
        self.checkpoint_only_enabled.set(enabled)
        for index, (key, _) in enumerate(STATION_LIST):
            variables = self.niw_checkpoint_only_vars if index < 15 else self.copier_checkpoint_only_vars
            variables[index if index < 15 else index - 15].set(key in pages)
        self.log(f"[SETTINGS] 仅 Checkpoint {'开启' if enabled else '关闭'}，已保存 {len(pages)} 个页面；下次启动检查时应用。")
        return True

    def _toggle_checkpoint_only(self):
        if self.checkpoint_only_enabled.get():
            self._open_checkpoint_only_dialog()
        else:
            pages = self.app.config_data.get("CHECKPOINT_ONLY", {}).get("pages", [])
            if not self._save_checkpoint_only(False, pages):
                self.checkpoint_only_enabled.set(True)

    def _open_checkpoint_only_dialog(self):
        if self._checkpoint_only_dialog and self._checkpoint_only_dialog.winfo_exists():
            self._checkpoint_only_dialog.focus()
            return
        saved = self.app.config_data.get("CHECKPOINT_ONLY", {})
        dialog = ctk.CTkToplevel(self)
        self._checkpoint_only_dialog = dialog
        dialog.title("选择仅 Checkpoint 的页面")
        owner = self.winfo_toplevel()
        owner.update_idletasks()
        width, height = 660, 640
        x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
        x = max(0, min(x, owner.winfo_screenwidth() - width))
        y = max(0, min(y, owner.winfo_screenheight() - height))
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.transient(owner)
        ctk.CTkLabel(dialog, text="勾选的页面不检查数据，只提交 Checkpoint", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 4))
        ctk.CTkLabel(dialog, text="保存后每次手动／自动检查都应用，直到关闭总开关。", text_color="#f0ad4e").pack(pady=(0, 10))
        body = ctk.CTkScrollableFrame(dialog)
        body.pack(fill="both", expand=True, padx=16)
        choices = {}
        for index, (key, title) in enumerate(STATION_LIST):
            if index in (0, 15):
                ctk.CTkLabel(body, text="NIW" if index == 0 else "Copier & Server", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(12, 5))
            variable = ctk.BooleanVar(value=key in saved.get("pages", []))
            choices[key] = variable
            ctk.CTkCheckBox(body, text=title, variable=variable).pack(anchor="w", padx=8, pady=4)
        def cancel():
            self.checkpoint_only_enabled.set(bool(self.app.config_data.get("CHECKPOINT_ONLY", {}).get("enabled", False)))
            dialog.destroy()
            self._checkpoint_only_dialog = None
        def confirm():
            pages = [key for key, variable in choices.items() if variable.get()]
            if self._save_checkpoint_only(True, pages):
                dialog.destroy()
                self._checkpoint_only_dialog = None
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(buttons, text="Deselect All", width=105,
                      command=lambda: self.set_all_vars(list(choices.values()), False)).pack(side="left", padx=5)
        ctk.CTkButton(buttons, text="取消", width=90, fg_color="#555555", command=cancel).pack(side="right", padx=5)
        ctk.CTkButton(buttons, text="确定并保存", width=120, command=confirm).pack(side="right", padx=5)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.after(100, dialog.grab_set)

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
        message = compact_message(message)
        if message is None:
            return

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
        self.app.post_ui(append)

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
            if self.last_failed_type is not None or self.paused_station is not None:
                # 存在未解决的中断阻断，暂停自动巡检保护现场
                self.lbl_schedule_status.configure(
                    text=f"[Status] ⚠️ Paused ({self.last_failed_type + ' Error' if self.last_failed_type else 'Stopped by user'})",
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

    # ─────────────────────────────────────────────────────────────────
    #  美东午间快速通关核心逻辑 (Noon Fast Checkpoint Mode: 12:00 - 14:00)
    # ─────────────────────────────────────────────────────────────────
    def is_noon_fast_mode_active(self) -> bool:
        """
        [美东午间快速通关激活判定]
        判定当前是否处于 12:00-14:00 快速通关时间窗口：
        1. 用户开关必须为开启状态 (self.noon_fast_mode_var.get() == True)
        2. 当前时间处于中午 12:00 至 14:00 之间 (12 <= now.hour < 14)
        3. 今日尚未因 Matches & Wagers 0 积压而提前结束 (not self.noon_early_exit_today)
        """
        if not self.run_settings["noon_fast"]:
            return False

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 每日跨天自动重置提前退出状态
        if self.last_noon_check_date != today_str:
            self.last_noon_check_date = today_str
            self.noon_early_exit_today = False

        # 仅在 12:00:00 至 13:59:59 期间生效
        if not (12 <= now.hour < 14):
            return False

        # 若今日 Matches & Wagers 审查已确认无积压，提早结束
        if self.noon_early_exit_today:
            return False

        return True

    def _on_noon_fast_toggle(self):
        """[午间快速通关开关手动切换回调]"""
        enabled = self.noon_fast_mode_var.get()
        if enabled:
            self.noon_early_exit_today = False  # 用户手动重新打开时重置提前退出状态
            now = datetime.now()
            in_window = 12 <= now.hour < 14
            status_text = "Active now (12-2pm window)" if in_window else "Scheduled (auto active between 12:00-14:00)"
            self.log(f"[NOON FAST] ⚡ Noon Fast Mode ENABLED — {status_text}")
        else:
            self.log("[NOON FAST] ⏸️ Noon Fast Mode DISABLED by user.")


    def play_error_sound(self):
        """
        [异常蜂鸣报警音触发器]
        当巡检关卡检测到红色阻断异常时调用。
        判断用户是否开启了声音报警开关 (sound_alert_var)，
        若开启，派发后台守护线程播放 Windows 原生高频蜂鸣 (1800Hz)，连续蜂鸣 3 声，不卡顿主线程。
        """
        if not self.run_settings["sound"]:
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
        self.update_button_states()
        self.log("[STOP] ⏹ Pause requested. Current page will finish; click Resume to continue afterwards.")

        # 若定时自动调度仍在运行，给予友好提示
        if self.hourly_auto_var.get():
            self.log("[STOP] Auto schedule will wait while this inspection is paused.")

    def update_button_states(self):
        """
        [全量操作按钮状态精准状态机]
        根据当前系统 4 种互斥状态，统一计算并刷新所有按钮的启用 (normal) 与禁用 (disabled):
        - 状态 1: 自身巡检正在运行中 (is_running=True) -> 仅 [Stop] 可用，其余全置灰
        - 状态 2: 另一个 Tab (Error Log) 正在运行中 -> 全部置灰 (杜绝浏览器并发竞争)
        - 状态 3: 存在阻断中断点 (last_failed_type 不为空) -> [Resume] 与 [Skip] 亮起，允许重试或跳过
        - 状态 4: 系统完全空闲 -> [Check] 亮起，[Resume/Skip/Stop] 置灰
        """
        def apply():
            # 1. 检测 Error Log 选项卡是否处于活跃运行状态
            is_error_log_running = False
            if hasattr(self.app, 'error_log_tab') and getattr(self.app.error_log_tab, 'is_running', False):
                is_error_log_running = True

            # 2. 状态机条件分支判定
            if self.is_running:
                # 自身正在巡检中
                self.btn_check.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled" if self.stop_requested else "normal")
            elif is_error_log_running or getattr(self.app, "is_logging_in", False) or getattr(self.app, "closing", False):
                # 另一个 Tab 正在运行，彻底锁定本 Tab 所有执行按钮
                self.btn_check.configure(state="disabled")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")
            elif self.last_failed_type is not None or self.paused_station is not None:
                # 存在未处理的中断点（处于待续传/待跳过状态）
                self.btn_check.configure(state="normal")
                self.btn_resume.configure(state="normal") # 激活 Resume 续传
                self.btn_skip.configure(state="normal" if self.last_failed_type is not None else "disabled")
                self.btn_stop.configure(state="disabled")
            else:
                # 系统初始或已全部通关的完全空闲状态
                self.btn_check.configure(state="normal")
                self.btn_resume.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.btn_stop.configure(state="disabled")

        # 确保在 Tkinter 主事件循环中安全更新 UI 控件
        self.app.post_ui(apply)

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
        if getattr(self.app, 'closing', False) or getattr(self.app, 'is_logging_in', False):
            self.log("[WARN] Browser is busy logging in or the application is closing.")
            return True
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

        user, pwd = self.app.get_credentials()
        if not user or not pwd:
            self.log("[WARN] Account and password are required.")
            return
        bypass = self.app.config_data.get("CHECKPOINT_ONLY", {})
        bypass_pages = set(bypass.get("pages", [])) if bypass.get("enabled", False) else set()
        self.run_settings = {
            "credentials": (user, pwd), "url": self.app.get_login_url(),
            "niw": [v.get() for v in self.niw_vars],
            "copier": [v.get() for v in self.copier_vars],
            "noon_fast": self.noon_fast_mode_var.get(),
            "sound": self.sound_alert_var.get(),
            "checkpoint_only_niw": [key in bypass_pages for key, _ in STATION_LIST[:15]],
            "checkpoint_only_copier": [key in bypass_pages for key, _ in STATION_LIST[15:]],
        }
        if not any(self.run_settings["niw"]) and not any(self.run_settings["copier"]):
            self.log("[WARN] Please select at least one checkpoint station below.")
            return
        if niw_start == 0 and copier_start == 0 and self.paused_station is None and self.last_failed_type is None:
            self.run_results = {}
        # 2. 设置运行状态与流水线模式
        self.paused_station = None
        self.current_pipeline_mode = mode
        self.is_running = True
        self.stop_requested = False

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
        if niw_start == 0 and copier_start == 0:
            self.run_results = {}
        self._start_pipeline_thread(
            mode="FULL",
            niw_start=niw_start,
            copier_start=copier_start,
            full=full,
            banner_text="Checkpoint Started — Selected Stations (NIW → Copier)"
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

        if self.paused_station is not None:
            section, index = self.paused_station
            mode = self.current_pipeline_mode
            self.log(f"[RESUME] Continuing from {section} Station {index + 1}...")
            self._start_pipeline_thread(
                mode=mode,
                niw_start=index if section == "NIW" else 15,
                copier_start=index if section == "Copier" else 0,
                full=mode == "FULL",
                banner_text="Checkpoint Resumed"
            )
            return
        if self.last_failed_type is None:
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

        if self.last_failed_type is None:
            return

        self.is_running = True
        self._notify_state_change()

        self.stop_requested = False
        self.log("[SKIP] Force passing current station and moving to next...")
        threading.Thread(target=self.run_skip_and_checkpoint_pipeline, daemon=True).start()

    def _handle_all_passed(self, driver):
        """
        [全量通关善后与归位逻辑]
        清空中断指针，打印通关横幅，并将浏览器菜单导航回 NIW 第 1 关 Pending Wager。
        """
        self.last_failed_type = None
        self.paused_station = None
        self.last_failed_index = 0
        self.log("\n══════════════════════════════════════════════════")
        self.log("══════════════════════════════════════════════════")
        try:
            # 按照运维标准规范，所有关卡巡检完成后，自动将浏览器菜单切回 NIW 第 1 关 Pending Wager 归位
            checker = BaseChecker(driver, self.log)
            checker.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW", wait_seconds=2)
            self.log("[NAVIGATE] ✅ All stations passed. Navigated back to Pending Wager (NIW Station 1)")
        except Exception:
            pass


    # ─────────────────────────────────────────────────────────────────
    #  流水线调度核心逻辑 (Pipeline Execution Engine)
    # ─────────────────────────────────────────────────────────────────
