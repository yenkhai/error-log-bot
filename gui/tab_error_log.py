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
================================================================================
"""

import threading
import customtkinter as ctk
from services.error_log_scraper import ErrorLogScraperService

class ErrorLogTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app # 主窗口引用
        self.service = None # 抓取服务实例对象
        self.build_ui()

    def build_ui(self):
        # 1. 顶部按钮控制栏
        ctrl_frame = ctk.CTkFrame(self)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        self.btn_start = ctk.CTkButton(
            ctrl_frame, text="[RUN] 开始抓取导出 (断点续传)", command=self.start_scrape,
            fg_color="#28A745", hover_color="#218838", font=ctk.CTkFont(weight="bold")
        )
        self.btn_start.pack(side="left", padx=10, pady=5)

        self.btn_stop = ctk.CTkButton(
            ctrl_frame, text="[STOP] 停止", command=self.stop_scrape,
            fg_color="#DC3545", hover_color="#C82333", state="disabled", font=ctk.CTkFont(weight="bold"), width=80
        )
        self.btn_stop.pack(side="left", padx=5, pady=5)

        self.btn_clear = ctk.CTkButton(
            ctrl_frame, text="[CLEAR] 清空日志", command=self.clear_log, width=90
        )
        self.btn_clear.pack(side="right", padx=10, pady=5)

        # 2. 中部双日志面板 (调大字体至 14pt，大字号高清晰)
        mid_frame = ctk.CTkFrame(self)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        mid_frame.grid_columnconfigure(0, weight=3) # 左侧 Terminal 权重为 3
        mid_frame.grid_columnconfigure(1, weight=1) # 右侧 跳过警报框 权重为 1
        mid_frame.grid_rowconfigure(1, weight=1)

        # 左侧运行 Terminal 日志框 (绿色字体 14pt)
        ctk.CTkLabel(mid_frame, text="[LOG] 运行日志 (Terminal)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")
        self.txt_log = ctk.CTkTextbox(mid_frame, fg_color="#1E1E1E", text_color="#00FF00", font=ctk.CTkFont(family="Consolas", size=14))
        self.txt_log.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # 右侧 >10k 记录跳过警报框 (红色字体 14pt)
        ctk.CTkLabel(mid_frame, text="[SKIP] 已跳过 (>10k)", font=ctk.CTkFont(weight="bold"), text_color="#FF4C4C").grid(row=0, column=1, padx=10, pady=(5, 0), sticky="w")
        self.txt_skip = ctk.CTkTextbox(mid_frame, fg_color="#1E1E1E", text_color="#FF4C4C", font=ctk.CTkFont(family="Consolas", size=14))
        self.txt_skip.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="nsew")
        self.txt_skip.configure(state="disabled")

    def log(self, message: str):
        """主运行日志追加入口"""
        def append():
            self.txt_log.insert("end", message + "\n")
            self.txt_log.see("end")
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
        self.txt_log.delete("1.0", "end")
        self.txt_skip.configure(state="normal")
        self.txt_skip.delete("1.0", "end")
        self.txt_skip.configure(state="disabled")

    def start_scrape(self):
        """启动 Error Log 抓取后台任务"""
        user, pwd = self.app.get_credentials()
        if not user or not pwd:
            self.log("[WARN] 全局账号或密码为空，请输入有效的账号和密码！")
            return

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.service = ErrorLogScraperService(self.log, self.skip_log)
        threading.Thread(target=self.run_service, args=(user, pwd), daemon=True).start()

    def stop_scrape(self):
        """给后台任务发送停止信号"""
        if self.service:
            self.service.stop_flag = True
            self.log("[STOP] 正在发送停止信号...")

    def run_service(self, user, pwd):
        """服务运行线程包装"""
        try:
            self.service.run(user, pwd)
        except Exception as e:
            self.log(f"[ERROR] 运行抓取服务出错: {e}")
        finally:
            def reset():
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
            self.after(0, reset)
