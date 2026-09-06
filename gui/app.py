"""
================================================================================
主界面 GUI 窗口构造模块 (gui/app.py)
--------------------------------------------------------------------------------
作用:
1. 继承 CustomTkinter 主窗口 `ctk.CTk`，打造暗黑现代风格的 GUI。
2. 构造顶部【全局账号与域名控制栏】(Domain Entry + Save 按钮，op35/op38/custom 单选，账号密码输入框)。
3. 构造两大核心 Tab 选项卡:
   - Tab 1: Checkpoint 自动化巡检 (CheckpointTab)
   - Tab 2: Error Log 日志抓取导出 (ErrorLogTab)
================================================================================
"""

import customtkinter as ctk
from config import load_config, save_config
from gui.tab_checkpoint import CheckpointTab
from gui.tab_error_log import ErrorLogTab
from gui.tab_log_viewer import LogViewerTab

class UnifiedBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Automation Platform - Checkpoint & Error Log Unified Hub")
        self.geometry("1060x760")
        self.minsize(980, 680)
        
        # 设定全局暗黑暗青现代 UI 模式
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # 加载本地 JSON 配置文件
        self.config_data = load_config()
        self.account_var = ctk.StringVar(value="op35") # 默认选中的账号单选框
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()

    def build_ui(self):
        # 1. 顶部 Header Title Bar 标题栏
        header = ctk.CTkFrame(self, height=45, corner_radius=0, fg_color="#1f1f1f")
        header.pack(fill="x")
        
        title_label = ctk.CTkLabel(
            header, text="🛡️ Operations Automated Inspection & Log Analytics System v2.0",
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(side="left", padx=20, pady=8)

        # 2. 全局账号与域名控制顶栏 (Global Top Account & Domain Bar)
        login_frame = ctk.CTkFrame(self)
        login_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 关联域名 Domain / URL 行
        url_frame = ctk.CTkFrame(login_frame, fg_color="transparent")
        url_frame.pack(side="top", fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(url_frame, text="🌐 Login Domain/URL:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 5))
        self.entry_url = ctk.CTkEntry(url_frame, width=420)
        self.entry_url.pack(side="left", padx=(0, 10))
        self.entry_url.insert(0, self.config_data.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?"))

        btn_save_url = ctk.CTkButton(
            url_frame, text="💾 Save Domain", width=95, command=self.save_domain_url,
            fg_color="#17a2b8", hover_color="#138496"
        )
        btn_save_url.pack(side="left")

        # 账号模式单选按钮行 (Default op35 / Default op38 / Custom Login)
        radio_frame = ctk.CTkFrame(login_frame, fg_color="transparent")
        radio_frame.pack(side="top", anchor="w", padx=10, pady=(4, 2))

        ctk.CTkLabel(radio_frame, text="🔑 Account Mode:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))

        ctk.CTkRadioButton(
            radio_frame, text="Default (op35)", variable=self.account_var, value="op35", command=self.update_inputs
        ).pack(side="left", padx=10)

        ctk.CTkRadioButton(
            radio_frame, text="Default (op38)", variable=self.account_var, value="op38", command=self.update_inputs
        ).pack(side="left", padx=10)

        ctk.CTkRadioButton(
            radio_frame, text="Custom Login", variable=self.account_var, value="custom", command=self.update_inputs
        ).pack(side="left", padx=10)

        # 账号密码输入框行
        input_frame = ctk.CTkFrame(login_frame, fg_color="transparent")
        input_frame.pack(side="top", anchor="w", padx=10, pady=(0, 8))

        ctk.CTkLabel(input_frame, text="User:").pack(side="left", padx=(0, 5))
        self.entry_user = ctk.CTkEntry(input_frame, width=140)
        self.entry_user.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(input_frame, text="Pass:").pack(side="left", padx=(0, 5))
        self.entry_pass = ctk.CTkEntry(input_frame, width=140, show="*")
        self.entry_pass.pack(side="left")

        # 依据单选状态初始化账号密码框
        self.update_inputs()

        # 3. 核心功能选项卡控件 (Tabview)
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Tab 1: Checkpoint 自动化巡检选项卡
        tab_cp = self.tabview.add("🤖 Checkpoint Inspection")
        self.checkpoint_tab = CheckpointTab(tab_cp, self)
        self.checkpoint_tab.pack(fill="both", expand=True)

        # Tab 2: Error Log 日志抓取导出选项卡
        tab_el = self.tabview.add("📊 Error Log Exporter")
        self.error_log_tab = ErrorLogTab(tab_el, self)
        self.error_log_tab.pack(fill="both", expand=True)

        # Tab 3: 巡检日志浏览器选项卡
        tab_lv = self.tabview.add("📋 Checkpoint Log Viewer")
        self.log_viewer_tab = LogViewerTab(tab_lv, self)
        self.log_viewer_tab.pack(fill="both", expand=True)

    def save_domain_url(self):
        """[保存新域名] 将输入框中修改的 URL 持久化存入 config.json"""
        new_url = self.entry_url.get().strip()
        if new_url:
            self.config_data["LOGIN_URL"] = new_url
            save_config(self.config_data)

    def update_inputs(self):
        """[单选框事件触发] 依单选模式自动填入预置默认密码 123qwe"""
        mode = self.account_var.get()
        self.entry_user.configure(state="normal")
        self.entry_pass.configure(state="normal")

        if mode in ("op35", "op38"):
            self.entry_user.delete(0, "end")
            self.entry_user.insert(0, mode)
            self.entry_pass.delete(0, "end")
            self.entry_pass.insert(0, "123qwe")
            self.entry_user.configure(state="disabled")
            self.entry_pass.configure(state="disabled")
        else: # Custom Login
            self.entry_user.delete(0, "end")
            self.entry_pass.delete(0, "end")

    def on_close(self):
        """主窗口关闭拦截: 安全通知后台任务停止并销毁窗口"""
        try:
            if hasattr(self, 'checkpoint_tab'):
                self.checkpoint_tab.stop_requested = True
            if hasattr(self, 'error_log_tab') and getattr(self.error_log_tab, 'service', None):
                self.error_log_tab.service.stop_flag = True
        except Exception:
            pass
        self.destroy()

    def get_credentials(self):
        """[对外提供接口] 返回当前顶栏界面填写的 (username, password) 账户元组"""
        return self.entry_user.get().strip(), self.entry_pass.get().strip()

    def get_login_url(self):
        """[对外提供接口] 返回当前顶栏界面填写的 URL 域名链接"""
        return self.entry_url.get().strip()

    def notify_task_state_changed(self):
        """
        [全局双向排他互斥锁通知]
        当任何一个 Tab 启动或结束任务时，通知所有 Tab 刷新自身按钮的 Enable/Disable 状态，
        确保 Checkpoint 巡检与 Error Log 导出永远不会并发运行！
        """
        if hasattr(self, 'checkpoint_tab'):
            self.checkpoint_tab.update_button_states()
        if hasattr(self, 'error_log_tab'):
            self.error_log_tab.update_button_states()
