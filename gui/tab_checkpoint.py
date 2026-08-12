"""
================================================================================
Checkpoint 自动化巡检选项卡 UI 模块 (gui/tab_checkpoint.py)
--------------------------------------------------------------------------------
作用:
1. 构造 Checkpoint 选项卡页面：顶层控制按钮栏、关卡自定义选择矩阵、大字号 14pt 实时 Terminal 控制台。
2. 调度执行 NIW 15 大关卡与 Copier 9 大关卡的后台多线程巡检。
3. 提供【🔄 从中断关卡续传】与【⏭️ 跳过当前页打勾去下一页】核心控制逻辑。
4. 提供【[CONFIG] 🔽 折叠 关卡定制】交互按钮，一键收起/展开复选框矩阵提升控制台高度。
================================================================================
"""

import time
import threading
import traceback
import customtkinter as ctk
from core.browser import BrowserManager
from core.base_checker import BaseChecker

# 导入所有 15 个 NIW 关卡 (严格匹配真实文件名与关卡编号)
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

class CheckpointTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app # 主窗口引用
        self.is_running = False # 巡检多线程运行状态标识
        
        # 记录上次中断的位置，供【断点续传】与【强制跳过】精准读取
        self.last_failed_type = None  # "NIW" 或 "Copier"
        self.last_failed_index = 0    # 0-based 关卡索引

        # 关卡勾选面板展开/折叠状态标记
        self.matrix_visible = True

        # 关卡勾选控制变量列表 (默认全部初始化为 True 全选)
        self.niw_vars = [ctk.BooleanVar(value=True) for _ in range(15)]
        self.copier_vars = [ctk.BooleanVar(value=True) for _ in range(9)]
        
        self.build_ui()

    def build_ui(self):
        # 1. 顶层操作按钮控制栏 (精简尺寸与间距，彻底解决右侧被截断拥挤问题)
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.btn_run_niw = ctk.CTkButton(
            top_frame, text="▶ 运行 NIW", command=self.start_niw_thread,
            fg_color="#1f538d", hover_color="#14375e", font=ctk.CTkFont(weight="bold"), width=110
        )
        self.btn_run_niw.pack(side="left", padx=3, pady=5)

        self.btn_run_copier = ctk.CTkButton(
            top_frame, text="▶ 运行 Copier", command=self.start_copier_thread,
            fg_color="#2fa572", hover_color="#1e6b49", font=ctk.CTkFont(weight="bold"), width=125
        )
        self.btn_run_copier.pack(side="left", padx=3, pady=5)

        self.btn_resume = ctk.CTkButton(
            top_frame, text="⏯️ 断点续传", command=self.start_resume_thread,
            fg_color="#e67e22", hover_color="#d35400", font=ctk.CTkFont(weight="bold"), width=105
        )
        self.btn_resume.pack(side="left", padx=3, pady=5)

        self.btn_skip = ctk.CTkButton(
            top_frame, text="⏭️ 跳过并打勾", command=self.start_skip_and_checkpoint_thread,
            fg_color="#8e44ad", hover_color="#732d91", font=ctk.CTkFont(weight="bold"), width=115
        )
        self.btn_skip.pack(side="left", padx=3, pady=5)

        self.btn_open_dashboard = ctk.CTkButton(
            top_frame, text="📊 HTML 仪表盘", command=self.open_dashboard,
            fg_color="#0C63AF", hover_color="#1e88e5", font=ctk.CTkFont(weight="bold"), width=125
        )
        self.btn_open_dashboard.pack(side="left", padx=3, pady=5)

        # 关卡定制矩阵展开/折叠按钮
        self.btn_toggle_matrix = ctk.CTkButton(
            top_frame, text="🔽 折叠定制", command=self.toggle_matrix_panel,
            fg_color="#34495e", hover_color="#2c3e50", font=ctk.CTkFont(weight="bold"), width=105
        )
        self.btn_toggle_matrix.pack(side="right", padx=3, pady=5)

        self.btn_clear = ctk.CTkButton(
            top_frame, text="🗑️ 清空日志", command=self.clear_log, width=85
        )
        self.btn_clear.pack(side="right", padx=3, pady=5)

        # 2. 关卡自定义勾选矩阵面板
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.pack(fill="x", padx=10, pady=5)

        # NIW 勾选子区域
        niw_box = ctk.CTkFrame(self.select_frame)
        niw_box.pack(fill="x", padx=5, pady=5)

        niw_header = ctk.CTkFrame(niw_box, fg_color="transparent")
        niw_header.pack(fill="x", padx=5, pady=(2, 2))
        ctk.CTkLabel(niw_header, text="[CONFIG] NIW 关卡定制 (默认全选):", font=ctk.CTkFont(weight="bold")).pack(side="left")
        
        ctk.CTkButton(niw_header, text="全选", width=50, height=22, command=lambda: self.set_all_vars(self.niw_vars, True)).pack(side="left", padx=5)
        ctk.CTkButton(niw_header, text="全不选", width=55, height=22, command=lambda: self.set_all_vars(self.niw_vars, False)).pack(side="left")

        niw_grid = ctk.CTkFrame(niw_box, fg_color="transparent")
        niw_grid.pack(fill="x", padx=5, pady=(0, 5))

        niw_names = [
            "1.Pending Wager", "2.CCL Recover", "3.Matches Wagers", "4.Result Process", "5.Calculate Betslips",
            "6.RPT PolyMarket", "7.RPT Compare", "8.RPT AI", "9.RPT Compare UTC", "10.Forecast",
            "11.Check CCL", "12.Wsum Sport", "13.HG Percentages", "14.RPT CRS", "15.1 Wallet Pending"
        ]

        for i, name in enumerate(niw_names):
            col = i % 5
            row = i // 5
            ctk.CTkCheckBox(
                niw_grid, text=name, variable=self.niw_vars[i], font=ctk.CTkFont(size=11)
            ).grid(row=row, column=col, sticky="w", padx=4, pady=2)

        # Copier & Server 勾选子区域
        copier_box = ctk.CTkFrame(self.select_frame)
        copier_box.pack(fill="x", padx=5, pady=(0, 5))

        copier_header = ctk.CTkFrame(copier_box, fg_color="transparent")
        copier_header.pack(fill="x", padx=5, pady=(2, 2))
        ctk.CTkLabel(copier_header, text="[CONFIG] Copier & Server 关卡定制 (默认全选):", font=ctk.CTkFont(weight="bold")).pack(side="left")

        ctk.CTkButton(copier_header, text="全选", width=50, height=22, command=lambda: self.set_all_vars(self.copier_vars, True)).pack(side="left", padx=5)
        ctk.CTkButton(copier_header, text="全不选", width=55, height=22, command=lambda: self.set_all_vars(self.copier_vars, False)).pack(side="left")

        copier_grid = ctk.CTkFrame(copier_box, fg_color="transparent")
        copier_grid.pack(fill="x", padx=5, pady=(0, 5))

        copier_names = [
            "1.Copier", "2.DB Server Status", "3.AP Server Status", "4.Check AP Space", "5.Error Log",
            "6.Redis Server", "7.Robot Monitor", "8.NIW Robot Monitor", "9.Info Robot Monitor"
        ]

        for i, name in enumerate(copier_names):
            col = i % 5
            row = i // 5
            ctk.CTkCheckBox(
                copier_grid, text=name, variable=self.copier_vars[i], font=ctk.CTkFont(size=11)
            ).grid(row=row, column=col, sticky="w", padx=4, pady=2)

        # 3. 实时日志控制台 (调大字体至 14pt，大字号清晰控制台)
        self.log_text = ctk.CTkTextbox(self, font=("Consolas", 14))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def toggle_matrix_panel(self):
        """
        [展开/折叠面板控制] 随时收起/显示关卡勾选复选框矩阵，提升控制台可视区域
        """
        if self.matrix_visible:
            self.select_frame.pack_forget() # 隐藏复选框面板
            self.matrix_visible = False
            self.btn_toggle_matrix.configure(text="▶ 展开定制")
        else:
            self.select_frame.pack(fill="x", padx=10, pady=5, before=self.log_text) # 重新显示面板
            self.matrix_visible = True
            self.btn_toggle_matrix.configure(text="🔽 折叠定制")

    def set_all_vars(self, var_list, value: bool):
        """全选 / 全不选 批量操作"""
        for v in var_list:
            v.set(value)

    def log(self, message: str):
        """线程安全地在 UI 文本框追加日志并自动滚动到底部"""
        def append():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        self.after(0, append)

    def clear_log(self):
        """清空日志控制台"""
        self.log_text.delete("1.0", "end")

    def open_dashboard(self):
        """[开启 HTML 仪表盘] 唤醒系统默认浏览器打开高保真实时 HTML 仪表盘"""
        try:
            from core.report_manager import ReportManager
            ReportManager.open_dashboard()
            self.log("[REPORT] 已成功调用默认浏览器打开 HTML 巡检仪表盘 (dashboard.html)！")
        except Exception as e:
            self.log(f"[WARN] 打开 HTML 仪表盘提示: {e}")

    def start_niw_thread(self, start_index=0):
        """启动 NIW 巡检后台线程"""
        if self.is_running: return
        self.is_running = True
        self.toggle_buttons(False)
        self.log(f"[START] 已触发 NIW 巡检 (起始关卡: 第 {start_index + 1} 关)...")
        threading.Thread(target=self.run_niw_pipeline, args=(start_index,), daemon=True).start()

    def start_copier_thread(self, start_index=0):
        """启动 Copier & Server 巡检后台线程"""
        if self.is_running: return
        self.is_running = True
        self.toggle_buttons(False)
        self.log(f"[START] 已触发 Copier & Server 巡检 (起始关卡: 第 {start_index + 1} 关)...")
        threading.Thread(target=self.run_copier_pipeline, args=(start_index,), daemon=True).start()

    def start_resume_thread(self):
        """[断点续传] 读取 self.last_failed_index 从上次中断的关卡重新检测并继续流转"""
        if self.is_running: return
        if self.last_failed_type == "Copier":
            self.log(f"[RESUME] 启动断点续传: 从 Copier & Server 第 {self.last_failed_index + 1} 关开始继续巡检...")
            self.start_copier_thread(start_index=self.last_failed_index)
        else:
            self.log(f"[RESUME] 启动断点续传: 从 NIW 第 {self.last_failed_index + 1} 关开始继续巡检...")
            self.start_niw_thread(start_index=self.last_failed_index)

    def start_skip_and_checkpoint_thread(self):
        """[强制打勾跳过] 在当前中断的页面强制点击 Checkpoint 按钮打勾，然后进入下一关"""
        if self.is_running: return
        self.is_running = True
        self.toggle_buttons(False)
        self.log("[SKIP] 收到指令：准备在当前页面强制点击 Checkpoint 并跳转下一关...")
        threading.Thread(target=self.run_skip_and_checkpoint_pipeline, daemon=True).start()

    def run_skip_and_checkpoint_pipeline(self):
        """强行打勾跳过后台线程"""
        try:
            driver = BrowserManager.get_driver()
            checker = BaseChecker(driver, self.log)
            self.log("[SKIP] 正在强行执行当前页面的 Checkpoint 动作...")
            checker.click_checkpoint()
            self.log("[SKIP SUCCESS] 当前页面 Checkpoint 打勾完成！即刻进入下一关...")

            next_index = self.last_failed_index + 1
            if self.last_failed_type == "Copier":
                if next_index < 9:
                    self.run_copier_pipeline(start_index=next_index)
                else:
                    self.log("[COMPLETE] Copier & Server 已巡检完毕所有关卡！")
            else:
                if next_index < 15:
                    self.run_niw_pipeline(start_index=next_index)
                else:
                    self.log("[COMPLETE] NIW 已巡检完毕所有关卡！")
        except Exception as e:
            self.log(f"[ERROR] 强制跳过与 Checkpoint 过程异常: {e}\n{traceback.format_exc()}")
        finally:
            self.after(0, self.reset_buttons)

    def toggle_buttons(self, state_bool: bool):
        """巡检过程中禁用/恢复控制按钮状态"""
        st = "normal" if state_bool else "disabled"
        self.btn_run_niw.configure(state=st)
        self.btn_run_copier.configure(state=st)
        self.btn_resume.configure(state=st)
        self.btn_skip.configure(state=st)

    def reset_buttons(self):
        """重置按钮状态"""
        self.is_running = False
        self.toggle_buttons(True)

    def run_niw_pipeline(self, start_index=0):
        """
        [NIW 15 大关卡巡检主流水线]
        依次实例化 15 个 Checker 校验对象并执行 check()。
        若发现未勾选则 skip；若 check() 返回 False 则自动记录断点并暂停，等待用户人工介入。
        """
        try:
            user, pwd = self.app.get_credentials()
            url = self.app.get_login_url()
            self.log(f"[CONFIG] 登录账号: {user} | 目标域名: {url}")
            self.log("--------------------------------------------------")
            self.log(f"[PIPELINE START] 执行 NIW 巡检流程 [起始: 第 {start_index + 1} 关]")
            self.log("--------------------------------------------------")

            self.log("[BROWSER] 正在秒级探针/连接 Chrome 浏览器...")
            driver = BrowserManager.get_driver(url=url, user=user, pwd=pwd)
            self.log("[BROWSER] 浏览器驱动准备就绪！")

            all_checkers = [
                ("第1站 Pending Wager", PendingWagerChecker(driver, self.log)),
                ("第2站 CCL Recover", CCLRecoverChecker(driver, self.log)),
                ("第3站 Matches Wagers", MatchesWagersChecker(driver, self.log)),
                ("第4站 Result Process", ResultProcessChecker(driver, self.log)),
                ("第5站 Calculate Betslips", CalculateBetslipsChecker(driver, self.log)),
                ("第6站 RPT PolyMarket", RPTPolyMarketChecker(driver, self.log)),
                ("第7站 RPT Compare", RPTCompareChecker(driver, self.log)),
                ("第8站 RPT AI", RPTAIChecker(driver, self.log)),
                ("第9站 RPT Compare UTC", RPTCompareUTCChecker(driver, self.log)),
                ("第10站 Forecast", ForecastChecker(driver, self.log)),
                ("第11站 Check CCL", CheckCCLChecker(driver, self.log)),
                ("第12站 Wsum Sport", WsumSportChecker(driver, self.log)),
                ("第13站 HG Percentages", HGPercentagesChecker(driver, self.log)),
                ("第14站 RPT CRS", RPTCRSChecker(driver, self.log)),
                ("第15站 1 Wallet Pending", OneWalletPendingChecker(driver, self.log))
            ]

            active_checkers = all_checkers[start_index:]

            for i, (name, checker) in enumerate(active_checkers):
                current_idx = start_index + i

                # 检查用户是否取消勾选了该关卡
                if not self.niw_vars[current_idx].get():
                    self.log(f"[SKIP] 依据勾选设置，跳过 {name}...")
                    continue

                res = checker.check()
                if not res:
                    self.last_failed_type = "NIW"
                    self.last_failed_index = current_idx
                    self.log(f"\n[INTERRUPT] {name} 检测到异常，已自动记录断点。")
                    self.log("  选项 1. 点击 [RESUME] 从中断关卡续传 重新检测当前页；")
                    self.log("  选项 2. 点击 [SKIP] 跳过当前页打勾去下一页 强行完成当前页 Checkpoint 并跳去下一关。")
                    break
            else:
                self.last_failed_type = None
                self.last_failed_index = 0
                self.log("\n[COMPLETE] 恭喜！NIW 巡检全部关卡顺畅通关！")

        except Exception as e:
            self.log(f"\n[ERROR] 巡检过程出现异常: {e}\n{traceback.format_exc()}")
        finally:
            self.after(0, self.reset_buttons)

    def run_copier_pipeline(self, start_index=0):
        """
        [Copier & Server 9 大关卡巡检流水线]
        """
        try:
            user, pwd = self.app.get_credentials()
            url = self.app.get_login_url()
            self.log(f"[CONFIG] 登录账号: {user} | 目标域名: {url}")
            self.log("--------------------------------------------------")
            self.log(f"[PIPELINE START] 执行 Copier & Server 巡检流程 [起始: 第 {start_index + 1} 关]")
            self.log("--------------------------------------------------")

            self.log("[BROWSER] 正在秒级探针/连接 Chrome 浏览器...")
            driver = BrowserManager.get_driver(url=url, user=user, pwd=pwd)
            self.log("[BROWSER] 浏览器驱动准备就绪！")

            all_checkers = [
                ("Copier 第1站 Copier", CopierChecker(driver, self.log)),
                ("Copier 第2站 DB Server Status", DBServerStatusChecker(driver, self.log)),
                ("Copier 第3站 AP Server Status", APServerStatusChecker(driver, self.log)),
                ("Copier 第4站 Check AP Space", CheckAPSpaceChecker(driver, self.log)),
                ("Copier 第5站 Error Log", ErrorLogChecker(driver, self.log)),
                ("Copier 第6站 Redis Server", RedisServerChecker(driver, self.log)),
                ("Copier 第7站 Robot Monitor", RobotMonitorChecker(driver, self.log)),
                ("Copier 第8站 NIW Robot Monitor", NIWRobotMonitorChecker(driver, self.log)),
                ("Copier 第9站 Info Robot Monitor", InfoRobotMonitorChecker(driver, self.log))
            ]

            active_checkers = all_checkers[start_index:]

            for i, (name, checker) in enumerate(active_checkers):
                current_idx = start_index + i

                # 检查用户是否取消勾选了该关卡
                if not self.copier_vars[current_idx].get():
                    self.log(f"[SKIP] 依据勾选设置，跳过 {name}...")
                    continue

                res = checker.check()
                if not res:
                    self.last_failed_type = "Copier"
                    self.last_failed_index = current_idx
                    self.log(f"\n[INTERRUPT] {name} 检测到异常，已自动记录断点。")
                    self.log("  选项 1. 点击 [RESUME] 从中断关卡续传 重新检测当前页；")
                    self.log("  选项 2. 点击 [SKIP] 跳过当前页打勾去下一页 强行完成当前页 Checkpoint 并跳去下一关。")
                    break
            else:
                self.last_failed_type = None
                self.last_failed_index = 0
                self.log("\n[COMPLETE] 恭喜！Copier & Server 巡检全部关卡顺畅通关！")

        except Exception as e:
            self.log(f"\n[ERROR] 巡检过程出现异常: {e}\n{traceback.format_exc()}")
        finally:
            self.after(0, self.reset_buttons)
