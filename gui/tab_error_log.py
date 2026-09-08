"""
================================================================================
Error Log 日志抓取与导出选项卡 UI 模块 (gui/tab_error_log.py)
--------------------------------------------------------------------------------
作用与设计解析:
1. 提供 Error Log 专属的控制界面：
   - [RUN] 开始抓取导出 (支持断点续传，自动扫描本地目录并跳过已下载的完整日志)
   - [STOP] 停止抓取 (向后台服务发出优雅停机信号，当前批次完成后安全退出)
   - [CLEAR] 一键清空双控制台日志
2. 双日志控制台布局设计 (Dual-Terminal UI):
   - 左侧 (权重 3): 绿色大字号 Consolas 14pt Terminal 实时运行与解析调试日志
   - 右侧 (权重 1): 红色大字号 Consolas 14pt 警报框，专门记录 >10,000 条被安全策略自动跳过的服务器 IP 及条数
3. 调度后台服务 ErrorLogScraperService 执行多线程日志抓取导出任务，避免阻塞 Tkinter 主事件循环。
4. 全局互斥排他支持：
   - 与 Checkpoint 自动化巡检共享底层的 Chrome 浏览器，当巡检任务运行时自动锁定，杜绝并发冲突。
================================================================================
"""

# 导入 Python 原生多线程模块，用于将耗时的网页爬虫任务放入后台守护线程运行
import threading

# 导入 CustomTkinter 现代 GUI 库，用于构建卡片式容器与高清晰度文本框
import customtkinter as ctk

# 导入 Error Log 日志抓取导出业务服务类
from services.error_log_scraper import ErrorLogScraperService


class ErrorLogTab(ctk.CTkFrame):
    """
    Error Log 错误日志导出专属选项卡视图类
    继承自 `ctk.CTkFrame`，作为 Tabview 的子页面嵌入主窗口。
    """

    def __init__(self, parent, app):
        # 1. 调用父类 CTkFrame 构造方法，初始化当前选项卡的框架容器
        super().__init__(parent)

        # 2. 保存顶层 UnifiedBotApp 根窗口的引用，用于获取顶栏账号密码/URL 以及派发互斥锁通知
        self.app = app

        # 3. 后台抓取服务实例指针，初始为 None，点击 [RUN] 时动态实例化
        self.service = None

        # 4. 当前选项卡自身任务的运行状态布尔标志 (True 表示爬虫抓取正在执行)
        self.is_running = False

        # 5. 装配组装选项卡的所有视觉控件
        self.build_ui()

    def build_ui(self):
        """
        构建 Error Log 选项卡的界面布局:
        包含顶部操作按钮控制栏与中部左右双控制台面板。
        """

        # ── 1. 顶部控制按钮栏 (Top Control Frame) ──
        # 创建一个横向通栏卡片作为顶部按钮底座
        ctrl_frame = ctk.CTkFrame(self)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        # [RUN] 启动导出按钮 (翠绿色高亮，加粗)
        # 点击后触发 self.start_scrape 方法
        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="[RUN] Start Export (Resume)",
            command=self.start_scrape,
            fg_color="#28A745",       # 鲜明绿色
            hover_color="#218838",    # 鼠标悬停暗绿色
            font=ctk.CTkFont(weight="bold")
        )
        self.btn_start.pack(side="left", padx=10, pady=5)

        # [STOP] 停止按钮 (红色高亮，初始为禁用状态 disabled)
        # 点击后触发 self.stop_scrape 方法
        self.btn_stop = ctk.CTkButton(
            ctrl_frame,
            text="[STOP] Stop",
            command=self.stop_scrape,
            fg_color="#DC3545",       # 鲜明红色
            hover_color="#C82333",    # 鼠标悬停暗红色
            state="disabled",         # 初始禁用
            font=ctk.CTkFont(weight="bold"),
            width=80
        )
        self.btn_stop.pack(side="left", padx=5, pady=5)

        # [CLEAR] 清空日志按钮 (靠右放置)
        # 点击后清空左右两个文本控制台中的所有字符
        self.btn_clear = ctk.CTkButton(
            ctrl_frame,
            text="[CLEAR] Clear Log",
            command=self.clear_log,
            width=90
        )
        self.btn_clear.pack(side="right", padx=10, pady=5)

        # ── 2. 中部双日志面板 (Dual Log Terminals) ──
        # 创建中间主容器，采用 Grid 网格布局实现左右分屏
        mid_frame = ctk.CTkFrame(self)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 配置网格权重: 第 0 列 (左侧主日志) 占比 3，第 1 列 (右侧跳过警告) 占比 1
        mid_frame.grid_columnconfigure(0, weight=3) # 左侧 Terminal 权重为 3
        mid_frame.grid_columnconfigure(1, weight=1) # 右侧 跳过警报框 权重为 1
        # 配置第 1 行 (文本框所在行) 上下撑满
        mid_frame.grid_rowconfigure(1, weight=1)

        # (1) 左侧运行 Terminal 日志框 (黑色底色，翠绿色字体，Consolas 14pt 等宽字体)
        ctk.CTkLabel(
            mid_frame,
            text="[LOG] Execution Log (Terminal)",
            font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")

        self.txt_log = ctk.CTkTextbox(
            mid_frame,
            fg_color="#1E1E1E",       # 深黑终端背景
            text_color="#00FF00",     # 翠绿黑客风字符
            font=ctk.CTkFont(family="Consolas", size=14)
        )
        self.txt_log.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.txt_log.configure(state="disabled") # 设为只读，防止用户误碰键盘敲入杂乱字符

        # (2) 右侧 >10k 记录跳过警报框 (黑色底色，亮红色字体，Consolas 14pt)
        ctk.CTkLabel(
            mid_frame,
            text="[SKIP] Skipped Servers (>10k)",
            font=ctk.CTkFont(weight="bold"),
            text_color="#FF4C4C"
        ).grid(row=0, column=1, padx=10, pady=(5, 0), sticky="w")

        self.txt_skip = ctk.CTkTextbox(
            mid_frame,
            fg_color="#1E1E1E",       # 深黑背景
            text_color="#FF4C4C",     # 醒目警示红字
            font=ctk.CTkFont(family="Consolas", size=14)
        )
        self.txt_skip.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="nsew")
        self.txt_skip.configure(state="disabled") # 初始只读

        # 初始化调用：刷新一次当前按钮的启用/禁用状态
        self.update_button_states()

    def update_button_states(self):
        """
        [按钮状态精准状态机联动]
        根据全局任务运行状态动态切换 [RUN] 与 [STOP] 按钮：
        - 状态 1: 自身正在运行 (is_running=True) -> [RUN] 禁用, [STOP] 启用
        - 状态 2: 巡检任务 CheckpointTab 正在运行 -> [RUN] 禁用, [STOP] 禁用 (全局互斥保护)
        - 状态 3: 系统完全空闲 -> [RUN] 启用, [STOP] 禁用
        """
        def apply():
            # 检查 CheckpointTab 是否正在运行
            is_checkpoint_running = False
            if hasattr(self.app, 'checkpoint_tab') and getattr(self.app.checkpoint_tab, 'is_running', False):
                is_checkpoint_running = True

            if self.is_running:
                # 自身正在抓取中
                self.btn_start.configure(state="disabled")
                self.btn_stop.configure(state="normal", text="[STOP] Stop")
            elif is_checkpoint_running:
                # 巡检正在运行，彻底锁定
                self.btn_start.configure(state="disabled")
                self.btn_stop.configure(state="disabled", text="[STOP] Stop")
            else:
                # 完全空闲
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled", text="[STOP] Stop")

        # 通过 self.after(0, apply) 确保在 Tkinter 主 UI 线程中安全更新控件属性
        self.after(0, apply)

    def _append_text(self, textbox, text: str):
        """
        [内部通用文本追加辅助方法]
        安全解锁只读 Textbox，追加文本，修剪超限历史行，并重新锁定为只读。
        """
        def append():
            textbox.configure(state="normal")
            # 缓冲区行数保护：超过 3000 行时自动修剪前 500 行，避免内存膨胀
            try:
                num_lines = int(float(textbox.index("end-1c")))
                if num_lines > 3000:
                    textbox.delete("1.0", "501.0")
            except Exception:
                pass
            textbox.insert("end", text)
            textbox.see("end")
            textbox.configure(state="disabled")
        self.after(0, append)

    def log(self, message: str):
        """
        [主运行日志追加入口]
        供后台抓取服务 ErrorLogScraperService 作为回调函数调用。
        线程安全地将日志文本追加到左侧绿色 Terminal 控制台中，并自动滚至最底端。
        """
        self._append_text(self.txt_log, message + "\n")

    def skip_log(self, ip, count):
        """
        [右侧 >10k 跳过记录追加入口]
        当后台发现某台服务器错误日志总行数超过 10,000 条并触发跳过保护时调用。
        将服务器 IP 和条数以醒目的格式记录在右侧红字警报框中。
        """
        self._append_text(self.txt_skip, f"{ip} ({count} Rec)\n")

    def clear_log(self):
        """
        [一键清空日志]
        清空左右两个文本框的所有历史打印内容。
        """
        # 清空左侧控制台
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

        # 清空右侧警报框
        self.txt_skip.configure(state="normal")
        self.txt_skip.delete("1.0", "end")
        self.txt_skip.configure(state="disabled")

    def _check_cross_tab_busy(self) -> bool:
        """
        [跨 Tab 状态互斥探针]
        检查 Checkpoint 自动化巡检是否正在运行；若正在运行，打印警告并拦截本次执行。
        """
        if hasattr(self.app, 'checkpoint_tab') and getattr(self.app.checkpoint_tab, 'is_running', False):
            self.log("[WARN] 🚫 Operation rejected: Checkpoint inspection is currently running! Please wait or stop checkpoint task.")
            return True
        return False

    def start_scrape(self):
        """
        [启动 Error Log 导出任务]
        1. 执行排他锁与参数完整性校验。
        2. 锁定按钮并通知全局状态变更。
        3. 实例化 ErrorLogScraperService 并派发后台守护线程执行。
        """
        # 1. 状态防抖校验：自身已在运行或 CheckpointTab 正在运行则直接拒绝
        if self.is_running or self._check_cross_tab_busy():
            return

        # 2. 从顶栏获取当前填写的用户名、密码及登录 URL
        user, pwd = self.app.get_credentials()
        login_url = self.app.get_login_url() if hasattr(self.app, 'get_login_url') else None

        # 3. 校验账号密码是否为空
        if not user or not pwd:
            self.log("[WARN] Account or password is empty. Please enter valid credentials!")
            return

        # 4. 标记当前处于运行状态
        self.is_running = True

        # 5. 通知全局协调器更新各 Tab 按钮状态
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()

        # 6. 构造后台导出服务实例，传入主日志回调、跳过日志回调及登录 URL
        self.service = ErrorLogScraperService(self.log, self.skip_log, login_url=login_url)

        # 7. 启动子线程执行任务，daemon=True 确保主窗口退出时子线程能随之销毁
        threading.Thread(target=self.run_service, args=(user, pwd), daemon=True).start()

    def stop_scrape(self):
        """
        [发送停止信号]
        将底层爬虫服务的 stop_flag 标志位置为 True，促使其在当前服务器日志下载完成后安全退出。
        """
        if self.service:
            self.service.stop_flag = True
            self.log("[STOP] Sending stop signal...")
            if hasattr(self, 'btn_stop'):
                self.btn_stop.configure(state="disabled", text="⏳ Stopping...")

    def run_service(self, user, pwd):
        """
        [后台线程执行体包装器]
        在独立的子线程中执行，防止抓取过程中的网络等待卡死 GUI 渲染。
        执行完毕或发生异常时，统一重置状态并刷新按钮。
        """
        try:
            # 调用抓取服务的核心 run 调度逻辑
            self.service.run(user, pwd)
        except Exception as e:
            # 捕获未处理的运行时异常并打印到日志控制台
            self.log(f"[ERROR] Error occurred during scraper execution: {e}")
        finally:
            # 无论正常结束还是发生异常，均将运行标志置为 False
            self.is_running = False

            # 通知全局协调器恢复所有被锁定的按钮
            if hasattr(self.app, 'notify_task_state_changed'):
                self.app.notify_task_state_changed()
            else:
                self.update_button_states()

