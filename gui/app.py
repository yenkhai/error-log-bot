"""
================================================================================
主界面 GUI 窗口构造模块 (gui/app.py)
--------------------------------------------------------------------------------
作用与设计解析:
1. 继承 CustomTkinter 主窗口 `ctk.CTk`，打造深色暗黑现代扁平化科技风格的 GUI 窗口。
2. 构造顶部【全局账号与域名控制栏】(Global Top Account & Domain Bar):
   - 域名/URL 输入框 (支持持久化存入 config.json)
   - 账号预设单选框 (op35 / op38 / custom 自定义输入)
   - 账号与密码输入框 (预设模式下自动填入并锁定，自定义模式下放开编辑)
   - 【🔑 Login Only 仅登录】按钮: 启动或连接底层 Chrome 并执行登录，但不跑任何自动化任务
3. 构造三大核心 Tab 选项卡 (Tabview):
   - Tab 1: Checkpoint 自动化巡检 (CheckpointTab) — 24 关全量/单段自动化巡检与定时调度
   - Tab 2: Error Log 日志抓取导出 (ErrorLogTab) — 自动化断点续传导出错误日志
   - Tab 3: Checkpoint Log Viewer 巡检日志浏览器 (LogViewerTab) — 内存全量巡检表格彩色渲染
4. 全局双向排他互斥调度中心 (`notify_task_state_changed`):
   - 负责协调各 Tab 之间及仅登录按钮之间的并发冲突，确保底层单浏览器驱动实例不会发生资源碰撞。
================================================================================
"""

# 导入 Python 原生多线程模块，用于异步启动仅登录等网络 IO 耗时任务，防止卡死 GUI 主事件循环
import threading
import queue

# 导入 CustomTkinter 现代 GUI 控件库 (基于 Tkinter 深度二次封装，原生支持圆角与暗黑主题)
import customtkinter as ctk

# 导入本地配置读写接口，用于读取和持久化保存登录 URL、默认凭证等设置
from config import load_config, save_config

# 导入浏览器核心驱动管理器，用于驱动单例 Chrome 进行快速仅登录操作
from core.browser import BrowserManager

# 导入 Tab 1 自动化巡检选项卡视图组件
from gui.tab_checkpoint import CheckpointTab

# 导入 Tab 2 错误日志抓取导出选项卡视图组件
from gui.tab_error_log import ErrorLogTab

# 导入 Tab 3 巡检结果可视化浏览器选项卡视图组件
from gui.tab_log_viewer import LogViewerTab


class UnifiedBotApp(ctk.CTk):
    """
    运维自动化集成平台主桌面窗口类
    继承自 `ctk.CTk` (CustomTkinter 根窗口)，负责整个应用程序的生命周期与组件装配。
    """

    def __init__(self):
        # 1. 显式调用父类 CTk 的构造函数，完成底层的 Tk 引擎与视窗环境初始化
        super().__init__()

        # 2. 设置主窗口顶部标题栏文字
        self.title("Automation Platform - Checkpoint & Error Log Unified Hub")

        # 3. 设置窗口默认启动尺寸: 宽度 1060 像素，高度 760 像素
        self.geometry("1060x760")

        # 4. 设置窗口允许缩放的最小边界值 (防止视窗被缩得过小导致控件挤压重叠)
        self.minsize(980, 680)

        # 5. 全局登录中互斥状态标志位
        self.closing = False
        self._ui_queue = queue.Queue()
        self.after(30, self._drain_ui_queue)
        self.is_logging_in = False

        # 5. 设定全局 UI 主题模式为深色模式 ("Dark")
        ctk.set_appearance_mode("Dark")

        # 6. 设定默认的主题强调色板为科技蓝 ("blue")
        ctk.set_default_color_theme("blue")

        # 7. 从本地磁盘 config.json 读取配置字典 (若不存在则回退至内置默认字典)
        self.config_data = load_config()

        # 8. 定义账号选择单选框的字符串追踪变量，默认值为 "op35"
        self.account_var = ctk.StringVar(value="op35")

        # 9. 绑定操作系统级窗口关闭事件 (右上角红叉 WM_DELETE_WINDOW)，拦截并执行安全退出清理
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 10. 执行界面各布局区块的具体组装构造
        self.build_ui()

    def build_ui(self):
        """
        组装主窗口的所有 UI 控件结构:
        分为 3 大垂直分块:
        - 顶部 Header 科技风系统标题栏
        - 中上部全局账号与域名控制栏
        - 主体区域三大核心功能 Tabview 选项卡
        """

        # ── 1. 顶部 Header Title Bar 标题栏 ──
        # 构造顶栏 Frame 容器，高度 45px，深黑底色 (#1f1f1f)，直角边框
        header = ctk.CTkFrame(self, height=45, corner_radius=0, fg_color="#1f1f1f")
        header.pack(fill="x") # 横向撑满整个窗口宽度

        # 在标题栏内部放置醒目的系统主标题标签
        title_label = ctk.CTkLabel(
            header,
            text="🛡️ Operations Automated Inspection & Log Analytics System v2.0",
            font=("Segoe UI", 16, "bold") # 现代 Segoe UI 字体，16号字，加粗
        )
        # 将标签靠左排列，左右边距 20px，上下边距 8px
        title_label.pack(side="left", padx=20, pady=8)

        # ── 2. 全局账号与域名控制顶栏 (Global Top Account & Domain Bar) ──
        # 创建一个圆角卡片容器包裹所有的登录输入控件，视觉上与背景形成层次
        login_frame = ctk.CTkFrame(self)
        login_frame.pack(fill="x", padx=10, pady=(10, 5))

        # (1) 域名与 URL 输入控制行
        url_frame = ctk.CTkFrame(login_frame, fg_color="transparent") # 透明背景，融入外层卡片
        url_frame.pack(side="top", fill="x", padx=10, pady=(6, 2))

        # "Login Domain/URL" 提示标签
        ctk.CTkLabel(
            url_frame,
            text="🌐 Login Domain/URL:",
            font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=(0, 5))

        # URL 文本输入框，宽度 420px，便于容纳长链接
        self.entry_url = ctk.CTkEntry(url_frame, width=420)
        self.entry_url.pack(side="left", padx=(0, 10))

        # 从配置中取出 LOGIN_URL 并自动填入输入框，默认回退到标准入口链接
        self.entry_url.insert(0, self.config_data.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?"))

        # 保存域名按钮: 用户修改了 URL 后，点击此按钮可持久化保存到 config.json，避免下次重复输入
        self.btn_save_url = ctk.CTkButton(
            url_frame,
            text="💾 Save Domain",
            width=95,
            command=self.save_domain_url,
            fg_color="#17a2b8",       # 青蓝色按钮
            hover_color="#138496"     # 鼠标悬停变深青色
        )
        self.btn_save_url.pack(side="left")

        # (2) 账号预设模式单选按钮行 (Default op35 / Default op38 / Custom Login)
        radio_frame = ctk.CTkFrame(login_frame, fg_color="transparent")
        radio_frame.pack(side="top", anchor="w", padx=10, pady=(4, 2))

        # 单选提示标签
        ctk.CTkLabel(
            radio_frame,
            text="🔑 Account Mode:",
            font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=(0, 10))

        # op35 常用预设单选按钮
        ctk.CTkRadioButton(
            radio_frame,
            text="Default (op35)",
            variable=self.account_var,
            value="op35",
            command=self.update_inputs # 切换时自动触发输入框内容刷新
        ).pack(side="left", padx=10)

        # op38 备用预设单选按钮
        ctk.CTkRadioButton(
            radio_frame,
            text="Default (op38)",
            variable=self.account_var,
            value="op38",
            command=self.update_inputs # 切换时自动触发输入框内容刷新
        ).pack(side="left", padx=10)

        # Custom 自定义账号密码单选按钮
        ctk.CTkRadioButton(
            radio_frame,
            text="Custom Login",
            variable=self.account_var,
            value="custom",
            command=self.update_inputs # 切换时解锁输入框
        ).pack(side="left", padx=10)

        # (3) 账号、密码输入框与仅登录触发按钮行
        input_frame = ctk.CTkFrame(login_frame, fg_color="transparent")
        input_frame.pack(side="top", anchor="w", padx=10, pady=(0, 8))

        # 账号 User 提示标签
        ctk.CTkLabel(input_frame, text="User:").pack(side="left", padx=(0, 5))
        # 账号输入框
        self.entry_user = ctk.CTkEntry(input_frame, width=130)
        self.entry_user.pack(side="left", padx=(0, 15))

        # 密码 Pass 提示标签
        ctk.CTkLabel(input_frame, text="Pass:").pack(side="left", padx=(0, 5))
        # 密码输入框 (show="*" 实现星号掩码安全保护)
        self.entry_pass = ctk.CTkEntry(input_frame, width=130, show="*")
        self.entry_pass.pack(side="left", padx=(0, 15))

        # 【🔑 Login 仅登录】按钮
        # 允许运维工程师单独启动/连接浏览器并登录进入系统内部，不触发任何巡检或导出，便于人工核对
        self.btn_login_only = ctk.CTkButton(
            input_frame,
            text="Login",
            width=115,
            command=self.do_login_only,
            fg_color="#28a745",       # 鲜明绿色按钮
            hover_color="#218838",
            font=ctk.CTkFont(weight="bold")
        )
        self.btn_login_only.pack(side="left", padx=(0, 10))

        # 登录状态提示标签 (如 "Connecting...", "✅ Logged in!", "❌ Login failed")
        self.lbl_login_status = ctk.CTkLabel(
            input_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.lbl_login_status.pack(side="left", padx=(0, 5))

        # 依据单选框默认值 ("op35") 初始化账号密码框内容并设为禁用状态
        self.update_inputs()

        # ── 3. 核心功能选项卡控件 (Tabview) ──
        # 创建 CustomTkinter 选项卡容器，上下撑满剩余的所有视窗空间
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Tab 1: Checkpoint 自动化巡检选项卡 (装配 CheckpointTab 实例)
        tab_cp = self.tabview.add("🤖 Checkpoint Inspection")
        self.checkpoint_tab = CheckpointTab(tab_cp, self)
        self.checkpoint_tab.pack(fill="both", expand=True)

        # Tab 2: Error Log 日志抓取导出选项卡 (装配 ErrorLogTab 实例)
        tab_el = self.tabview.add("📊 Error Log Exporter")
        self.error_log_tab = ErrorLogTab(tab_el, self)
        self.error_log_tab.pack(fill="both", expand=True)

        # Tab 3: 巡检日志浏览器选项卡 (装配 LogViewerTab 实例，展示内存全量表格)
        tab_lv = self.tabview.add("📋 Checkpoint Log Viewer")
        self.log_viewer_tab = LogViewerTab(tab_lv, self)
        self.log_viewer_tab.pack(fill="both", expand=True)

    def save_domain_url(self):
        """
        [保存新域名]
        将当前 URL 输入框中的最新字符串写入内存配置，并持久化刷盘存入本地 config.json。
        """
        new_url = self.entry_url.get().strip()
        if new_url:
            # 1. 更新内存配置字典
            updated = {**self.config_data, "LOGIN_URL": new_url}
            if not save_config(updated):
                self.lbl_login_status.configure(text="❌ 保存失败，请检查目录写入权限", text_color="#FF4C4C")
                return
            self.config_data = updated
            # 3. 界面视觉反馈：临时将按钮变更为已保存并在 1.5 秒后还原
            if hasattr(self, 'btn_save_url'):
                orig_text = self.btn_save_url.cget("text")
                self.btn_save_url.configure(text="✅ Saved!")
                self.after(1500, lambda: self.btn_save_url.configure(text=orig_text))

    def update_inputs(self):
        """
        [单选框联动事件]
        根据用户在 op35 / op38 / custom 之间的切换，自动填充或清空账号密码，
        并在预设模式下将输入框设为只读以防误触，自定义模式下放开编辑。
        """
        mode = self.account_var.get()

        # 先将输入框恢复为 normal 状态，以便能够清空或写入字符
        self.entry_user.configure(state="normal")
        self.entry_pass.configure(state="normal")

        if mode in ("op35", "op38"):
            # 1. 填充账号名
            self.entry_user.delete(0, "end")
            self.entry_user.insert(0, mode)

            # 2. 填充系统统一默认初始密码 123qwe
            self.entry_pass.delete(0, "end")
            self.entry_pass.insert(0, "123qwe")

            # 3. 将输入框置为 disabled 禁用状态，防止运维键盘误碰篡改
            self.entry_user.configure(state="disabled")
            self.entry_pass.configure(state="disabled")
        else:
            # Custom 自定义模式: 清空输入框并保持 normal 可编辑状态，供工程师手动键入特定账号
            self.entry_user.delete(0, "end")
            self.entry_pass.delete(0, "end")

    def post_ui(self, callback, *args):
        """Workers enqueue callbacks without touching Tk."""
        self._ui_queue.put((callback, args))

    def _drain_ui_queue(self):
        for _ in range(200):
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:
                import traceback
                traceback.print_exc()
        self.after(30, self._drain_ui_queue)

    def on_close(self):
        if self.closing:
            return
        self.closing = True
        self.lbl_login_status.configure(text="Stopping tasks safely...", text_color="#FFCC00")
        self.checkpoint_tab.hourly_auto_var.set(False)
        self.checkpoint_tab.stop_requested = True
        if self.checkpoint_tab.hourly_timer_id is not None:
            self.checkpoint_tab.after_cancel(self.checkpoint_tab.hourly_timer_id)
            self.checkpoint_tab.hourly_timer_id = None
        if self.error_log_tab.service:
            self.error_log_tab.service.stop_flag = True
        self.notify_task_state_changed()
        self._wait_for_shutdown()

    def _wait_for_shutdown(self):
        if self.is_any_task_running:
            self.after(100, self._wait_for_shutdown)
            return
        if not hasattr(self, '_browser_cleanup'):
            self._browser_cleanup = threading.Thread(target=BrowserManager.quit_driver, daemon=True)
            self._browser_cleanup.start()
        if self._browser_cleanup.is_alive():
            self.after(100, self._wait_for_shutdown)
            return
        self.destroy()

    def get_credentials(self):
        """
        [对外提供接口]
        安全获取当前顶栏输入框填写的 (username, password) 账号密码元组。
        供 Checkpoint 巡检模块与 Error Log 导出模块共用。
        """
        return self.entry_user.get().strip(), self.entry_pass.get().strip()

    def get_login_url(self):
        """
        [对外提供接口]
        安全获取当前顶栏输入框填写的登录 URL 地址。
        """
        return self.entry_url.get().strip()

    @property
    def is_any_task_running(self) -> bool:
        """
        [全局任务活跃度探测属性]
        检查 Checkpoint 选项卡、Error Log 选项卡或正在执行仅登录中是否有任一任务进行。
        """
        is_cp = hasattr(self, 'checkpoint_tab') and getattr(self.checkpoint_tab, 'is_running', False)
        is_el = hasattr(self, 'error_log_tab') and getattr(self.error_log_tab, 'is_running', False)
        is_log = getattr(self, 'is_logging_in', False)
        return is_cp or is_el or is_log

    def notify_task_state_changed(self):
        """
        [全局任务互斥总调度中心]
        业务背景:
        底层 Chrome WebDriver 属于单例独占式浏览器实例，
        若 Checkpoint 巡检与 Error Log 导出同时运行，会导致页面疯狂互相跳转、Session 错乱崩溃。
        安全设计: 内部统一通过 self.post_ui(...) 派发回主事件循环，杜绝子线程直接操作 UI 组件。
        """
        def _apply():
            if hasattr(self, 'checkpoint_tab'):
                self.checkpoint_tab.update_button_states()
            if hasattr(self, 'error_log_tab'):
                self.error_log_tab.update_button_states()
            if hasattr(self, 'btn_login_only'):
                self.btn_login_only.configure(state="disabled" if self.is_any_task_running else "normal")
        self.post_ui(_apply)

    def do_login_only(self):
        """
        [仅登录] 快速连接或启动浏览器并执行系统登录。
        特点: 不执行任何 Checkpoint 关卡巡检、不做任何日志抓取，登录完成后浏览器保持在前台供人工操作。
        """
        # 1. 读取当前填写的账号密码与目标域名
        user, pwd = self.get_credentials()
        url = self.get_login_url()

        # 2. 参数健全性校验
        if not user or not pwd:
            self.lbl_login_status.configure(text="⚠️ Please enter user & pass!", text_color="#FFCC00")
            return

        # 3. 检查是否有后台任务正在执行
        if self.closing or self.is_any_task_running:
            self.lbl_login_status.configure(text="⚠️ Task currently running!", text_color="#FFCC00")
            return

        # 4. 标记登录状态并全局锁定按钮
        self.is_logging_in = True
        self.notify_task_state_changed()
        self.btn_login_only.configure(state="disabled", text="⏳ Logging in...")
        self.lbl_login_status.configure(text="Connecting to browser...", text_color="#17a2b8")

        # 5. 定义后台执行工作线程，避免 Selenium 网络连接阻塞 Tkinter GUI 渲染
        def _worker():
            try:
                # 在 CheckpointTab 控制台同步打印操作日志
                if hasattr(self, 'checkpoint_tab'):
                    self.checkpoint_tab.log(f"\n[LOGIN ONLY] Connecting to browser for user '{user}'...")

                # 调用底层驱动引擎执行仅登录逻辑
                BrowserManager.login_only(url=url, user=user, pwd=pwd)

                if hasattr(self, 'checkpoint_tab'):
                    self.checkpoint_tab.log(f"[LOGIN ONLY] ✅ Successfully logged in as '{user}'! (No inspection triggered)")

                # 登录成功回调：更新 UI 标签
                self.post_ui(lambda: self.lbl_login_status.configure(text="✅ Logged in!", text_color="#28a745"))
            except Exception as e:
                err_msg = str(e)
                if hasattr(self, 'checkpoint_tab'):
                    self.checkpoint_tab.log(f"[LOGIN ONLY] ❌ Login failed: {err_msg}")

                # 登录失败回调：更新失败提示红字
                self.post_ui(lambda: self.lbl_login_status.configure(text="❌ Login failed", text_color="#FF4C4C"))
            finally:
                # 释放登录锁定状态，刷新全局互斥按钮
                self.is_logging_in = False
                self.notify_task_state_changed()
                self.post_ui(lambda: self.btn_login_only.configure(text="Login"))

        # 6. 启动后台守护线程运行 worker
        threading.Thread(target=_worker, daemon=True).start()
