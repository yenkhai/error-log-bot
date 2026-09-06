"""
================================================================================
巡检日志浏览器选项卡 (gui/tab_log_viewer.py)
--------------------------------------------------------------------------------
作用:
1. 第 3 个 Tab【📋 巡检日志浏览器】— 列表展示 24 个关卡最新巡检状态
2. 数据源: 纯内存 CheckpointStore (不再读取桌面 txt 文件)
3. 双击弹出独立窗口，以仿公司内部系统的彩色表格风格渲染数据:
   - 绿底 (#90EE90) = ok / success / 正常
   - 红底 (#FF6B6B) = error / 异常
   - 蓝底 (#4A90D9) = 表头行
   - 白底           = 普通数据
4. 独立窗口支持 ◀ 上一站 / ▶ 下一站 快速翻页
================================================================================
"""

import re
import tkinter as tk
import tkinter.ttk as ttk
import customtkinter as ctk
from core.checkpoint_store import CheckpointStore


# ── 24 个关卡的显示名称 ──────────────────────────────────────────────────────
STATION_LIST = [
    ("niw_01",    "NIW Station 01 - Pending Wager"),
    ("niw_02",    "NIW Station 02 - CCL Recover"),
    ("niw_03",    "NIW Station 03 - Matches Wagers"),
    ("niw_04",    "NIW Station 04 - Result Process"),
    ("niw_05",    "NIW Station 05 - Calculate Betslips"),
    ("niw_06",    "NIW Station 06 - RPT PolyMarket"),
    ("niw_07",    "NIW Station 07 - RPT Compare"),
    ("niw_08",    "NIW Station 08 - RPT AI"),
    ("niw_09",    "NIW Station 09 - RPT Compare UTC"),
    ("niw_10",    "NIW Station 10 - Forecast"),
    ("niw_11",    "NIW Station 11 - Check CCL"),
    ("niw_12",    "NIW Station 12 - Wsum Sport"),
    ("niw_13",    "NIW Station 13 - HG Percentages"),
    ("niw_14",    "NIW Station 14 - RPT CRS"),
    ("niw_15",    "NIW Station 15 - 1 Wallet Pending"),
    ("copier_01", "Copier Station 01 - Copier"),
    ("copier_02", "Copier Station 02 - DB Server Status"),
    ("copier_03", "Copier Station 03 - AP Server Status"),
    ("copier_04", "Copier Station 04 - Check AP Space"),
    ("copier_05", "Copier Station 05 - Error Log"),
    ("copier_06", "Copier Station 06 - Redis Server"),
    ("copier_07", "Copier Station 07 - Robot Monitor"),
    ("copier_08", "Copier Station 08 - NIW Robot Monitor"),
    ("copier_09", "Copier Station 09 - Info Robot Monitor"),
]

# ── 颜色常量 (1:1 还原企业系统网页真实配色) ──────────────────────────────────
COLOR_GREEN_BG       = "#00D000"   # 纯鲜艳绿底 (ok / success / Running)
COLOR_RED_BG         = "#FF0000"   # 纯鲜艳红底 (error / Die / 异常时间戳)
COLOR_YELLOW_BG      = "#FFFF00"   # 纯鲜艳黄底 (Wager Cal / 警告提醒)
COLOR_HEADER_OLIVE   = "#C8D7A6"   # 原生工控浅橄榄/卡其表头底 (RPT Compare, RPT AI 等)
COLOR_HEADER_BLUE    = "#5B9BD5"   # 原生工控蓝表头底 (Robot Monitor 等)
COLOR_HEADER_BG      = "#C8D7A6"   # 默认表头底
COLOR_HEADER_FG      = "#000000"   # 原生深黑表头文字 (加粗)
COLOR_WHITE_BG       = "#FFFFFF"   # 白底 (普通数据)
COLOR_BLACK_FG       = "#000000"   # 原生黑色数据文字
COLOR_LINK_FG        = "#0000EE"   # 原生蓝色超链接文字 (如 s0001, d0005, IP)
COLOR_BORDER         = "#000000"   # 细黑边框


class LogViewerTab(ctk.CTkFrame):
    """巡检日志浏览器 Tab — 从内存读取每个关卡最新的结构化表格数据"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._detail_window = None
        self.build_ui()

    def build_ui(self):
        # ── 顶部控制栏 ──────────────────────────────────────────────────
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            top_frame, text="📋 Checkpoint Log Viewer — Double-click any station to view full data table",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side="left", padx=10, pady=6)

        btn_refresh = ctk.CTkButton(
            top_frame, text="🔄 Refresh", command=self.refresh_list,
            fg_color="#17a2b8", hover_color="#138496", width=85
        )
        btn_refresh.pack(side="right", padx=10, pady=6)

        # ── 列表 Treeview ──────────────────────────────────────────────
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inner = tk.Frame(tree_frame, bg="#1a1a2e")
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("LogViewer.Treeview",
                         background="#16213e", foreground="#e0e0e0",
                         fieldbackground="#16213e", rowheight=28,
                         font=("Consolas", 11))
        style.configure("LogViewer.Treeview.Heading",
                         background="#1a1a2e", foreground="#8be9fd",
                         font=("Segoe UI", 11, "bold"))
        style.map("LogViewer.Treeview",
                   background=[("selected", "#2c3e50")],
                   foreground=[("selected", "#50fa7b")])

        columns = ("station", "status", "time")
        self.tree = ttk.Treeview(inner, columns=columns, show="headings",
                                  height=22, style="LogViewer.Treeview")

        self.tree.heading("station", text="Checkpoint Station", anchor="w")
        self.tree.heading("status",  text="Status", anchor="center")
        self.tree.heading("time",    text="Last Inspected", anchor="center")

        self.tree.column("station", width=340, minwidth=220, anchor="w")
        self.tree.column("status",  width=100, minwidth=70,  anchor="center")
        self.tree.column("time",    width=200, minwidth=140, anchor="center")

        scrollbar = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._on_double_click)

        self.refresh_list()

    def refresh_list(self):
        """从内存 CheckpointStore 刷新 24 个关卡的最新状态"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        all_summary = CheckpointStore.get_all_summary()

        for page_key, display_name in STATION_LIST:
            info = all_summary.get(page_key)
            tag = f"tag_{page_key}"
            if info:
                status_text = "✅ Passed" if info["status"] else "❌ Error"
                time_text = info["timestamp"]
                self.tree.insert("", "end",
                                 values=(display_name, status_text, time_text),
                                 tags=(tag,))
                if info["status"]:
                    self.tree.tag_configure(tag, foreground="#50fa7b")
                else:
                    self.tree.tag_configure(tag, foreground="#ff6b6b")
            else:
                self.tree.insert("", "end",
                                 values=(display_name, "📭 Not Run", "—"),
                                 tags=(tag,))
                self.tree.tag_configure(tag, foreground="#555e70")

    def _on_double_click(self, event=None):
        """双击 → 弹出仿公司风格的彩色表格详情窗口"""
        selection = self.tree.selection()
        if not selection:
            return
        all_items = self.tree.get_children()
        selected_idx = list(all_items).index(selection[0])
        self._open_detail_window(selected_idx)

    def _open_detail_window(self, station_index: int):
        if self._detail_window is not None:
            try:
                if self._detail_window.winfo_exists():
                    self._detail_window.destroy()
            except Exception:
                pass
        self._detail_window = LogDetailWindow(self, station_index)


class LogDetailWindow(ctk.CTkToplevel):
    """
    独立日志详情弹窗 — 仿公司内部系统风格的彩色表格渲染器
    绿底 = ok / success / 正常
    红底 = error / 异常
    蓝底 = 表头
    支持 ◀ ▶ 快速切换关卡
    """

    def __init__(self, parent_tab: LogViewerTab, station_index: int):
        super().__init__()
        self.parent_tab = parent_tab
        self.station_index = station_index

        self.title("Log Details")
        self.geometry("920x660")
        self.configure(fg_color="#f0f0f0")
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

        self.build_ui()
        self.load_data()

        self.bind("<Left>",   lambda e: self.prev_station())
        self.bind("<Right>",  lambda e: self.next_station())
        self.bind("<Escape>", lambda e: self.destroy())

    def build_ui(self):
        # ── 顶部导航栏 ──────────────────────────────────────────────────
        nav_frame = tk.Frame(self, bg="#2c3e50", height=45)
        nav_frame.pack(fill="x")
        nav_frame.pack_propagate(False)

        self.btn_prev = tk.Button(
            nav_frame, text="◀ Prev", command=self.prev_station,
            bg="#34495e", fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=12, pady=4, activebackground="#4a6785"
        )
        self.btn_prev.pack(side="left", padx=10, pady=8)

        self.lbl_title = tk.Label(
            nav_frame, text="", bg="#2c3e50", fg="#58a6ff",
            font=("Segoe UI", 13, "bold")
        )
        self.lbl_title.pack(side="left", expand=True, pady=8)

        self.btn_next = tk.Button(
            nav_frame, text="Next ▶", command=self.next_station,
            bg="#34495e", fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=12, pady=4, activebackground="#4a6785"
        )
        self.btn_next.pack(side="right", padx=10, pady=8)

        # ── 状态信息栏 ──────────────────────────────────────────────────
        self.info_frame = tk.Frame(self, bg="#ecf0f1", height=35)
        self.info_frame.pack(fill="x")
        self.info_frame.pack_propagate(False)

        self.lbl_info = tk.Label(
            self.info_frame, text="", bg="#ecf0f1", fg="#2c3e50",
            font=("Consolas", 11)
        )
        self.lbl_info.pack(side="left", padx=15, pady=6)

        # ── 表格渲染区域（使用 Canvas + Scrollbar 实现可滚动彩色表格）────
        table_container = tk.Frame(self, bg="#d0d0d0")
        table_container.pack(fill="both", expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(table_container, bg="white", highlightthickness=0)
        self.v_scroll = tk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        self.h_scroll = tk.Scrollbar(table_container, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        # 内嵌 Frame 用于放置表格 Label 网格
        self.table_frame = tk.Frame(self.canvas, bg="white")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")

        self.table_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 鼠标滚轮动态绑定 (仅光标进入弹窗时才响应滚轮，防止抢占主窗口滚动)
        self.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # ── 底部快捷键提示 ──────────────────────────────────────────────
        bottom = tk.Frame(self, bg="#2c3e50", height=28)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        tk.Label(
            bottom, text="Shortcuts: ← → Switch Station  |  Esc Close  |  Scroll Wheel to Navigate Table",
            bg="#2c3e50", fg="#7f8c8d", font=("Consolas", 9)
        ).pack(side="right", padx=10, pady=4)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        # 确保内嵌表格宽度至少等于画布宽度，宽表格则允许水平自适应并滚动
        canvas_width = event.width if event else self.canvas.winfo_width()
        frame_width = self.table_frame.winfo_reqwidth()
        self.canvas.itemconfig(self.canvas_window, width=max(frame_width, canvas_width))

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def load_data(self):
        """加载当前关卡的结构化数据并渲染为仿公司风格的彩色表格"""
        page_key, display_name = STATION_LIST[self.station_index]
        data = CheckpointStore.get(page_key)

        # 更新标题
        self.lbl_title.configure(text=f"{display_name}  ({self.station_index + 1}/{len(STATION_LIST)})")
        self.title(f"Log Details — {display_name}")

        # 更新按钮状态
        self.btn_prev.configure(state="normal" if self.station_index > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.station_index < len(STATION_LIST) - 1 else "disabled")

        # 清空旧表格
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        if data is None:
            # 未巡检过
            self.lbl_info.configure(text="Status: 📭 Not Run", fg="#7f8c8d")
            lbl = tk.Label(
                self.table_frame, text=f"\n\n    📭 {display_name} has not been inspected yet.\n\n    Please run a checkpoint inspection first to generate data.\n",
                bg="white", fg="#7f8c8d", font=("Segoe UI", 14),
                justify="left", anchor="nw"
            )
            lbl.grid(row=0, column=0, padx=30, pady=30, sticky="nw")
            return

        # 更新状态信息栏
        status_icon = "✅ Passed" if data["status"] else "❌ Error"
        self.lbl_info.configure(
            text=f"Inspection Time: {data['timestamp']}  |  Status: {status_icon}"
                 + (f"  |  {data['summary']}" if data.get("summary") else ""),
            fg="#27ae60" if data["status"] else "#e74c3c"
        )

        tables = data.get("tables", [])
        if not tables and (data.get("headers") or data.get("rows")):
            tables = [{"title": "", "headers": data.get("headers", []), "rows": data.get("rows", [])}]

        if not tables:
            lbl = tk.Label(
                self.table_frame, text=f"\n  {status_icon}  {data.get('summary', 'No detailed table data available')}\n",
                bg="white", fg="#2c3e50", font=("Segoe UI", 13),
                justify="left", anchor="nw"
            )
            lbl.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
            return

        # 判断关卡是否适合工控蓝表头 (如 Robot Monitor 类页面)
        is_robot_page = "robot" in display_name.lower() or "copier" in display_name.lower() or "ap" in display_name.lower()
        default_header_bg = COLOR_HEADER_BLUE if is_robot_page else COLOR_HEADER_OLIVE

        current_grid_row = 0

        # ── 循环渲染各个独立表格 (支持单表或多个原生子表) ─────────────────
        for t_idx, tbl in enumerate(tables):
            sub_title = tbl.get("title", "").strip()
            tbl_headers = tbl.get("headers", [])
            tbl_rows = tbl.get("rows", [])
            tbl_header_bg = tbl.get("header_bg", default_header_bg)

            # 1. 若有子表标题，渲染子表名栏
            if sub_title:
                title_lbl = tk.Label(
                    self.table_frame,
                    text=f"  ▶ {sub_title}  ",
                    bg="#2c3e50", fg="#58a6ff",
                    font=("Segoe UI", 11, "bold"),
                    relief="flat", anchor="w"
                )
                title_lbl.grid(row=current_grid_row, column=0, columnspan=max(len(tbl_headers), 1),
                               sticky="ew", padx=2, pady=(12 if t_idx > 0 else 4, 4))
                current_grid_row += 1

            # 2. 渲染表头
            if tbl_headers:
                for col_idx, header_text in enumerate(tbl_headers):
                    cell = tk.Label(
                        self.table_frame,
                        text=f" {header_text} ",
                        bg=tbl_header_bg, fg=COLOR_HEADER_FG,
                        font=("Segoe UI", 10, "bold"),
                        relief="solid", borderwidth=1,
                        padx=6, pady=3, anchor="center"
                    )
                    cell.grid(row=current_grid_row, column=col_idx, sticky="nsew")
                current_grid_row += 1

            # 3. 渲染数据行
            for row_data in tbl_rows:
                for col_idx, cell_data in enumerate(row_data):
                    # 解析 cell: str 或 dict
                    is_link = False
                    fg_custom = None
                    if isinstance(cell_data, dict):
                        text = str(cell_data.get("text", "")) if cell_data.get("text") is not None else ""
                        bg_key = cell_data.get("bg", "auto")
                        is_link = cell_data.get("is_link", False)
                        fg_custom = cell_data.get("fg")
                    else:
                        text = "" if cell_data is None else str(cell_data)
                        bg_key = "auto"

                    # 自动色彩推导
                    if bg_key == "auto":
                        bg_key = self._auto_color(text)

                    # 映射背景色
                    if bg_key == "green":
                        bg_color = COLOR_GREEN_BG
                        fg_color = COLOR_BLACK_FG
                    elif bg_key == "red":
                        bg_color = COLOR_RED_BG
                        fg_color = COLOR_BLACK_FG
                    elif bg_key == "yellow":
                        bg_color = COLOR_YELLOW_BG
                        fg_color = COLOR_BLACK_FG
                    elif bg_key == "header":
                        bg_color = tbl_header_bg
                        fg_color = COLOR_HEADER_FG
                    else:
                        bg_color = COLOR_WHITE_BG
                        fg_color = COLOR_BLACK_FG

                    # 超链接样式判断 (如 s0001, d0005, 10.x.x.x, Generate ...)
                    if fg_custom:
                        fg_color = fg_custom
                    elif is_link or self._is_link_text(text, col_idx):
                        if bg_color == COLOR_WHITE_BG:
                            fg_color = COLOR_LINK_FG

                    font_spec = ("Consolas", 10, "underline") if (fg_color == COLOR_LINK_FG) else ("Consolas", 10)

                    cell = tk.Label(
                        self.table_frame,
                        text=f" {text} ",
                        bg=bg_color, fg=fg_color,
                        font=font_spec,
                        relief="solid", borderwidth=1,
                        padx=5, pady=2, anchor="w"
                    )
                    cell.grid(row=current_grid_row, column=col_idx, sticky="nsew")
                current_grid_row += 1

            # 留出子表间距
            current_grid_row += 1

        # 列宽均匀配置
        all_col_counts = [len(t.get("headers", [])) for t in tables] + [
            len(r) for t in tables for r in t.get("rows", [])
        ]
        max_cols = max(all_col_counts, default=1)
        for col_idx in range(max_cols):
            self.table_frame.columnconfigure(col_idx, weight=1)

    @staticmethod
    def _is_link_text(text: str, col_idx: int) -> bool:
        """判断是否为企业网页中的链接文本 (如节点名 s0001, 详情链接等)"""
        s = text.strip()
        if not s:
            return False
        # 卫星节点代号 (如 s0001, d0005, p0001, e1001, j0001, f0001)
        if len(s) == 5 and s[0] in "sdtpekj" and s[1:].isdigit():
            return True
        # 操作指令链接 (如 Generate 2026-08-12, Show Process, Resume)
        if re.match(r"^Generate \d{4}-", s) or s in ("Show Process", "Resume", "Release Report"):
            return True
        # IP 地址
        if s.startswith("10.") and (len(s.split(".")) == 4):
            return True
        return False

    @staticmethod
    def _auto_color(text: str) -> str:
        """根据文本内容自动判断单元格背景色 (1:1 对齐企业系统判定)"""
        lower = text.strip().lower()
        if lower in ("ok", "success", "0", "-", "no error", "normal", "idle", "running"):
            return "green"
        if "wager cal" in lower:
            return "yellow"
        if any(k in lower for k in ("error", "fail", "die", "fatal", "block", "red")):
            return "red"
        # 数字判断: 非零整数可能代表积压或异常
        try:
            val = int(lower.replace(",", "").replace(" ", ""))
            if val == 0:
                return "green"
        except (ValueError, TypeError):
            pass
        return "white"

    def prev_station(self):
        if self.station_index > 0:
            self.station_index -= 1
            self.load_data()

    def next_station(self):
        if self.station_index < len(STATION_LIST) - 1:
            self.station_index += 1
            self.load_data()

    def destroy(self):
        """重写 destroy 以解绑全局滚轮事件"""
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()
