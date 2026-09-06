"""
================================================================================
Error Log 日志抓取与导出选项卡 UI 模块 (gui/tab_error_log.py)
--------------------------------------------------------------------------------
作用:
1. 提供 Error Log 专属的控制界面：[RUN] 开始抓取导出 (断点续传)、[STOP] 停止、[CLEAR] 清空日志。
2. 双日志区域显示：
   - 左侧: 绿色大字号 Terminal 实时运行调试日志。
   - 右侧: 红色大字号 >10,000 条记录自动跳过记录警报框。
3. 调度后台服务 ErrorLogScraperService 执行多线程日志抓取导出任务。
4. 全局互斥锁支持：当 Checkpoint 巡检在运行时，自动禁用并阻止抓取，防止浏览器冲突。
================================================================================
"""

import threading
import customtkinter as ctk
from services.error_log_scraper import ErrorLogScraperService


class ErrorLogTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app               # 主窗口引用
        self.service = None          # 抓取服务实例对象
        self.is_running = False      # 运行状态标识
        self.build_ui()

    def build_ui(self):
        # 1. 顶部按钮控制栏
        ctrl_frame = ctk.CTkFrame(self)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        self.btn_start = ctk.CTkButton(
            ctrl_frame, text="[RUN] Start Export (Resume)", command=self.start_scrape,
            fg_color="#28A745", hover_color="#218838", font=ctk.CTkFont(weight="bold")
        )
        self.btn_start.pack(side="left", padx=10, pady=5)

        self.btn_stop = ctk.CTkButton(
            ctrl_frame, text="[STOP] Stop", command=self.stop_scrape,
            fg_color="#DC3545", hover_color="#C82333", state="disabled", font=ctk.CTkFont(weight="bold"), width=80
        )
        self.btn_stop.pack(side="left", padx=5, pady=5)

        self.btn_clear = ctk.CTkButton(
            ctrl_frame, text="[CLEAR] Clear Log", command=self.clear_log, width=90
        )
        self.btn_clear.pack(side="right", padx=10, pady=5)

        # 2. 中部双日志面板 (调大字体至 14pt，大字号高清晰)
        mid_frame = ctk.CTkFrame(self)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        mid_frame.grid_columnconfigure(0, weight=3) # 左侧 Terminal 权重为 3
        mid_frame.grid_columnconfigure(1, weight=1) # 右侧 跳过警报框 权重为 1
        mid_frame.grid_rowconfigure(1, weight=1)

        # 左侧运行 Terminal 日志框 (绿色字体 14pt)
        ctk.CTkLabel(mid_frame, text="[LOG] Execution Log (Terminal)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")
        self.txt_log = ctk.CTkTextbox(mid_frame, fg_color="#1E1E1E", text_color="#00FF00", font=ctk.CTkFont(family="Consolas", size=14))
        self.txt_log.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.txt_log.configure(state="disabled")

        # 右侧 >10k 记录跳过警报框 (红色字体 14pt)
        ctk.CTkLabel(mid_frame, text="[SKIP] Skipped Servers (>10k)", font=ctk.CTkFont(weight="bold"), text_color="#FF4C4C").grid(row=0, column=1, padx=10, pady=(5, 0), sticky="w")
        self.txt_skip = ctk.CTkTextbox(mid_frame, fg_color="#1E1E1E", text_color="#FF4C4C", font=ctk.CTkFont(family="Consolas", size=14))
        self.txt_skip.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="nsew")
        self.txt_skip.configure(state="disabled")

        # 初始调用更新按钮状态
        self.update_button_states()

    def update_button_states(self):
        """
        根据全局互斥状态更新按钮状态：
        - 自身运行中 (is_running=True): [RUN] 禁用, [STOP] 启用
        - 另一个 Tab (Checkpoint) 运行中: [RUN] 禁用, [STOP] 禁用
        - 均空闲: [RUN] 启用, [STOP] 禁用
        """
        def apply():
            is_checkpoint_running = False
            if hasattr(self.app, 'checkpoint_tab') and getattr(self.app.checkpoint_tab, 'is_running', False):
                is_checkpoint_running = True

            if self.is_running:
                self.btn_start.configure(state="disabled")
                self.btn_stop.configure(state="normal")
            elif is_checkpoint_running:
                self.btn_start.configure(state="disabled")
                self.btn_stop.configure(state="disabled")
            else:
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")

        self.after(0, apply)

    def log(self, message: str):
        """主运行日志追加入口"""
        def append():
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", message + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        self.after(0, append)

    def skip_log(self, ip, count):
        """右侧 >10k 跳过记录追加入口"""
        def append():
            self.txt_skip.configure(state="normal")
            self.txt_skip.insert("end", f"{ip} ({count} Rec)\n")
            self.txt_skip.see("end")
            self.txt_skip.configure(state="disabled")
        self.after(0, append)

    def clear_log(self):
        """清空双控制台"""
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")
        self.txt_skip.configure(state="normal")
        self.txt_skip.delete("1.0", "end")
        self.txt_skip.configure(state="disabled")

    def _check_cross_tab_busy(self) -> bool:
        """检查 Checkpoint 自动化巡检是否正在运行"""
        if hasattr(self.app, 'checkpoint_tab') and getattr(self.app.checkpoint_tab, 'is_running', False):
            self.log("[WARN] 🚫 Operation rejected: Checkpoint inspection is currently running! Please wait or stop checkpoint task.")
            return True
        return False

    def start_scrape(self):
        """启动 Error Log 抓取后台任务"""
        if self.is_running or self._check_cross_tab_busy():
            return

        user, pwd = self.app.get_credentials()
        login_url = self.app.get_login_url() if hasattr(self.app, 'get_login_url') else None
        if not user or not pwd:
            self.log("[WARN] Account or password is empty. Please enter valid credentials!")
            return

        self.is_running = True
        if hasattr(self.app, 'notify_task_state_changed'):
            self.app.notify_task_state_changed()
        else:
            self.update_button_states()

        self.service = ErrorLogScraperService(self.log, self.skip_log, login_url=login_url)
        threading.Thread(target=self.run_service, args=(user, pwd), daemon=True).start()

    def stop_scrape(self):
        """给后台任务发送停止信号"""
        if self.service:
            self.service.stop_flag = True
            self.log("[STOP] Sending stop signal...")

    def run_service(self, user, pwd):
        """服务运行线程包装"""
        try:
            self.service.run(user, pwd)
        except Exception as e:
            self.log(f"[ERROR] Error occurred during scraper execution: {e}")
        finally:
            self.is_running = False
            if hasattr(self.app, 'notify_task_state_changed'):
                self.app.notify_task_state_changed()
            else:
                self.update_button_states()
