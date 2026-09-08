"""
================================================================================
巡检日志浏览器选项卡 (gui/tab_log_viewer.py)
--------------------------------------------------------------------------------
作用与设计解析:
1. 第 3 个 Tab【📋 巡检日志浏览器】— 全局列表化汇总展示全部 24 个关卡的最新巡检状态。
2. 架构特点: 数据完全源自内存单例 `CheckpointStore`，不再依赖读取本地磁盘 txt 文件，巡检进行时实时同步。
3. 双击任一关卡，自动弹出独立窗口 (`LogDetailWindow`)，以 1:1 仿公司内部工控网页系统的彩色表格风格渲染全量数据:
   - 绿底 (#00D000) = ok / success / Running / 正常通过 (加粗黑字)
   - 红底 (#FF0000) = error / Die / 异常时间戳 / 严重积压 (加粗黑字)
   - 黄底 (#FFFF00) = Wager Cal / 报警提醒 (加粗黑字)
   - 表头底 (#C8D7A6 橄榄浅绿 或 #5B9BD5 工控蓝) = 原生表格标题栏
   - 白底 (#FFFFFF) + 黑色数据文字 = 普通数据行
   - 蓝色下划线 (#0000EE) = 仿网页超链接文字 (如 s0001, d0005, 10.x.x.x IP)
4. 独立详情弹窗支持键盘快捷键:
   - ◀ / ▶ 左右箭头: 上一站 / 下一站快速翻页
   - Esc: 快速关闭弹窗
   - 鼠标滚轮: 仅在光标置于弹窗内部时支持平滑滚动，不干扰主窗口
================================================================================
"""

# 导入正则表达式模块，用于快速匹配企业网页链接特征 (如卫星代号 s0001、IP 地址、Generate 日期等)
import re

# 导入 Tkinter 原生 GUI 模块与 ttk 高级主题组件库
import tkinter as tk
import tkinter.ttk as ttk

# 导入 CustomTkinter 现代 GUI 库
import customtkinter as ctk

# 导入内存巡检结果存储中心，用于读取 24 关的最新表格数据与摘要
from core.checkpoint_store import CheckpointStore


# ─────────────────────────────────────────────────────────────────────────────
#  24 个关卡的系统标准代号与用户友好显示名称映射表
# ─────────────────────────────────────────────────────────────────────────────
STATION_LIST = [
    # ── NIW 核心业务区 15 关 ──
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
    # ── Copier & 服务器基础设施区 9 关 ──
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

# ─────────────────────────────────────────────────────────────────────────────
#  企业系统网页真实色彩常量定义 (1:1 还原内部页面像素级视觉风格)
# ─────────────────────────────────────────────────────────────────────────────
COLOR_GREEN_BG       = "#00D000"   # 纯鲜艳绿底 (ok / success / Running / 正常状态)
COLOR_RED_BG         = "#FF0000"   # 纯鲜艳红底 (error / Die / 异常时间戳 / 致命故障)
COLOR_YELLOW_BG      = "#FFFF00"   # 纯鲜艳黄底 (Wager Cal / 警告提醒)
COLOR_HEADER_OLIVE   = "#C8D7A6"   # 原生工控浅橄榄/卡其色表头底色 (RPT Compare, RPT AI 等通用报表)
COLOR_HEADER_BLUE    = "#5B9BD5"   # 原生工控科技蓝表头底色 (Robot Monitor 机器人监控等页面)
COLOR_HEADER_FG      = "#000000"   # 原生深黑表头文字 (加粗显示)
COLOR_WHITE_BG       = "#FFFFFF"   # 纯白底色 (普通普通数据单元格)
COLOR_BLACK_FG       = "#000000"   # 原生深黑色数据文字
COLOR_LINK_FG        = "#0000EE"   # 原生蓝色超链接文字 (如 s0001, d0005, IP 地址等)
COLOR_BORDER         = "#000000"   # 原生极细纯黑边框线条


class LogViewerTab(ctk.CTkFrame):
    """
    巡检日志浏览器 Tab 容器类
    从内存 CheckpointStore 中动态读取 24 个关卡的最新结构化结果，
    以现代深色 Treeview 表格展示概要，并响应用户双击弹出全量仿真数据。
    """

    def __init__(self, parent, app):
        # 1. 初始化父类 CTkFrame
        super().__init__(parent)

        # 2. 保存对主窗口应用的引用
        self.app = app

        # 3. 记录当前已打开的详情弹窗指针 (防止用户反复连击生成大量重复的弹窗)
        self._detail_window = None

        # 4. 执行界面渲染构造
        self.build_ui()

    def build_ui(self):
        """
        组装日志浏览器 Tab 界面:
        - 顶部标题提示与手动刷新按钮
        - 中部现代化深色 Treeview 列表
        """
        # ── 1. 顶部控制栏 (Top Header Bar) ──
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 提示标签：提示运维双击即可打开企业仿真实体表格
        ctk.CTkLabel(
            top_frame,
            text="📋 Checkpoint Log Viewer — Double-click any station to view full data table",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side="left", padx=10, pady=6)

        # 手动刷新按钮：当后台巡检正在推进时，可手动强制拉取内存最新数据
        btn_refresh = ctk.CTkButton(
            top_frame,
            text="🔄 Refresh",
            command=self.refresh_list,
            fg_color="#17a2b8",
            hover_color="#138496",
            width=85
        )
        btn_refresh.pack(side="right", padx=10, pady=6)

        # ── 2. 中部关卡汇总列表 (Treeview List) ──
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 在 CTkFrame 内部嵌入一个原生 tk.Frame，作为 ttk 样式的容器
        inner = tk.Frame(tree_frame, bg="#1a1a2e")
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        # 配置现代深蓝灰风格的 ttk Treeview 样式
        style = ttk.Style()
        style.theme_use("clam")
        self.tree_style = style
        style.configure(
            "LogViewer.Treeview",
            background="#16213e",         # 表体深蓝背景
            foreground="#e0e0e0",         # 白灰文字
            fieldbackground="#16213e",
            rowheight=28,                 # 适宜的行高，防止文字拥挤
            font=("Consolas", 11)
        )
        style.configure(
            "LogViewer.Treeview.Heading",
            background="#1a1a2e",         # 表头更深的蓝黑底色
            foreground="#8be9fd",         # 亮青蓝表头文字
            font=("Segoe UI", 11, "bold")
        )
        # 默认选中样式设为中性深蓝底色与淡灰文字，具体选中色会随选中行的状态动态调整（杜绝异常行显示为绿色）
        style.map(
            "LogViewer.Treeview",
            background=[("selected", "#203247")],
            foreground=[("selected", "#c5cdd9")]
        )

        # 定义 3 列: station (关卡名), status (巡检状态), time (最后巡检时间)
        columns = ("station", "status", "time")
        self.tree = ttk.Treeview(
            inner,
            columns=columns,
            show="headings",
            height=22,
            style="LogViewer.Treeview"
        )

        # 设置表头文字与对齐方式
        self.tree.heading("station", text="Checkpoint Station", anchor="w")
        self.tree.heading("status",  text="Status", anchor="center")
        self.tree.heading("time",    text="Last Inspected", anchor="center")

        # 设定各列初始宽度与最小自适应宽度
        self.tree.column("station", width=340, minwidth=220, anchor="w")
        self.tree.column("status",  width=100, minwidth=70,  anchor="center")
        self.tree.column("time",    width=200, minwidth=140, anchor="center")

        # 绑定原生垂直滚动条
        scrollbar = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # 绑定鼠标左键双击事件与键盘回车事件，触发弹出详情弹窗
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._on_double_click)
        # 绑定行选中切换事件，动态依据行状态调整选中高亮配色（Error 保持醒目红，Passed 保持绿）
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 启动时执行第一次列表加载刷新
        self.refresh_list()

    # 行选中时的动态配色映射表 (tag -> (选中背景色, 选中文字色))
    _SELECT_COLORS = {
        "status_error":   ("#4a151b", "#ff6b6b"),   # 酒红底 + 亮红字
        "status_pass":    ("#133926", "#50fa7b"),   # 墨绿底 + 翠绿字
        "status_not_run": ("#203247", "#c5cdd9"),   # 蓝灰底 + 浅银灰字
    }

    def _on_tree_select(self, event=None):
        """
        [行选中事件响应]
        依据当前被选中的行状态（Passed、Error、Not Run），
        动态更新 Treeview 的选中高亮配色，彻底杜绝选中有异常 (Error) 的行时显示为绿色。
        - 异常关卡选中: 酒红底色 (#4a151b) + 亮红文字 (#ff6b6b)，极其醒目清晰
        - 通过关卡选中: 墨绿底色 (#133926) + 亮绿文字 (#50fa7b)
        - 未跑关卡选中: 蓝灰底色 (#203247) + 浅灰文字 (#c5cdd9)
        """
        selection = self.tree.selection()
        if not selection:
            return
        tags = self.tree.item(selection[0], "tags")
        # 按 tag 查表获取对应配色，默认为未跑状态的中性色
        bg, fg = next(
            (self._SELECT_COLORS[t] for t in tags if t in self._SELECT_COLORS),
            ("#203247", "#c5cdd9")
        )
        self.tree_style.map(
            "LogViewer.Treeview",
            background=[("selected", bg)],
            foreground=[("selected", fg)]
        )

    def refresh_list(self):
        """
        [刷新关卡状态列表]
        从内存单例 CheckpointStore.get_all_summary() 读取所有关卡的执行结果快照，
        清空现有 Treeview 并按 24 关顺序逐一插入，赋予通过 (绿)、异常 (红)、未跑 (灰) 标签色彩。
        """
        # 0. 记录当前选中的行索引，以便刷新后无缝恢复高亮
        selected_idx = None
        cur_selection = self.tree.selection()
        if cur_selection:
            children = self.tree.get_children()
            if cur_selection[0] in children:
                selected_idx = children.index(cur_selection[0])

        # 1. 清空 Treeview 当前所有展示项
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 2. 从内存获取全局摘要字典 {page_key: {"status": bool, "timestamp": str, "summary": str}}
        all_summary = CheckpointStore.get_all_summary()

        # 3. 按 STATION_LIST 预设次序遍历渲染 24 个关卡
        for page_key, display_name in STATION_LIST:
            info = all_summary.get(page_key)
            tag = f"tag_{page_key}"
            if info:
                # 关卡已执行过巡检
                status_text = "✅ Passed" if info["status"] else "❌ Error"
                time_text = info["timestamp"]
                status_tag = "status_pass" if info["status"] else "status_error"
                self.tree.insert(
                    "",
                    "end",
                    values=(display_name, status_text, time_text),
                    tags=(tag, status_tag)
                )
                # 依据通过与否，配置行文字高亮色 (通过为亮绿，异常为亮红)
                if info["status"]:
                    self.tree.tag_configure(tag, foreground="#50fa7b")
                else:
                    self.tree.tag_configure(tag, foreground="#ff6b6b")
            else:
                # 关卡尚未开始巡检 (初始状态)
                self.tree.insert(
                    "",
                    "end",
                    values=(display_name, "📭 Not Run", "—"),
                    tags=(tag, "status_not_run")
                )
                self.tree.tag_configure(tag, foreground="#555e70") # 灰色显示

        # 4. 恢复先前选中的行选中状态并同步高亮色彩
        if selected_idx is not None:
            new_children = self.tree.get_children()
            if 0 <= selected_idx < len(new_children):
                self.tree.selection_set(new_children[selected_idx])
                self._on_tree_select()

    def _on_double_click(self, event=None):
        """
        [双击行响应事件]
        获取用户双击选中的行在列表中的绝对序号 (0~23)，调用弹窗展示函数。
        """
        selection = self.tree.selection()
        if not selection:
            return
        all_items = self.tree.get_children()
        selected_idx = list(all_items).index(selection[0])
        self._open_detail_window(selected_idx)

    def _open_detail_window(self, station_index: int):
        """
        [打开/切换详情弹窗]
        若之前已存在开启的弹窗实例，则先将其安全销毁，确保桌面上永远只有一个活动的详情观察器。
        """
        if self._detail_window is not None:
            try:
                if self._detail_window.winfo_exists():
                    self._detail_window.destroy()
            except Exception:
                pass
        # 实例化新的 LogDetailWindow 弹窗对象
        self._detail_window = LogDetailWindow(self, station_index)


class LogDetailWindow(ctk.CTkToplevel):
    """
    独立日志详情弹窗类 — 仿企业内部网页系统的彩色像素级表格渲染器
    核心特性:
    - 1:1 还原企业真实工控表格: 绿底通过、红底异常、黄底警告、橄榄浅绿/工控蓝表头。
    - 纯内存双向加载，不读本地磁盘，响应极快。
    - 支持左右箭头按键及顶部 Prev/Next 按钮平滑翻页。
    """

    def __init__(self, parent_tab: LogViewerTab, station_index: int):
        # 1. 显式初始化父类 CTkToplevel 顶层独立窗口
        super().__init__()

        # 2. 保存所属 Tab 引用及当前关卡序号 (0-based)
        self.parent_tab = parent_tab
        self.station_index = station_index

        # 3. 设置窗口基础标题与启动几何尺寸 (宽 920，高 660)
        self.title("Log Details")
        self.geometry("920x660")
        self.configure(fg_color="#f0f0f0") # 浅灰外框底色

        # 4. 弹窗出现瞬间短暂置顶 (300ms 后解除)，确保其不会被主窗口掩盖，同时不剥夺用户切到其他软件的自由
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

        # 5. 构建弹窗 UI 容器结构
        self.build_ui()

        # 6. 从内存读取并渲染当前关卡数据
        self.load_data()

        # 7. 绑定键盘快捷键: 左箭头上一站、右箭头下一站、Esc 退出
        self.bind("<Left>",   lambda e: self.prev_station())
        self.bind("<Right>",  lambda e: self.next_station())
        self.bind("<Escape>", lambda e: self.destroy())

    def build_ui(self):
        """
        构造弹窗的视觉骨架:
        - 顶部深色导航工具栏 (Prev, Title, Next)
        - 次顶部巡检时间与状态信息条
        - 中部带双向滚动条的可平滑滚动 Canvas 画布及内嵌网格 Frame
        - 底部快捷键提示状态栏
        """
        # ── 1. 顶部导航栏 (Top Navigation Bar) ──
        nav_frame = tk.Frame(self, bg="#2c3e50", height=45)
        nav_frame.pack(fill="x")
        nav_frame.pack_propagate(False)

        # ◀ Prev 上一站按钮
        self.btn_prev = tk.Button(
            nav_frame,
            text="◀ Prev",
            command=self.prev_station,
            bg="#34495e",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padx=12,
            pady=4,
            activebackground="#4a6785"
        )
        self.btn_prev.pack(side="left", padx=10, pady=8)

        # 关卡名称居中展示标签
        self.lbl_title = tk.Label(
            nav_frame,
            text="",
            bg="#2c3e50",
            fg="#58a6ff",
            font=("Segoe UI", 13, "bold")
        )
        self.lbl_title.pack(side="left", expand=True, pady=8)

        # Next ▶ 下一站按钮
        self.btn_next = tk.Button(
            nav_frame,
            text="Next ▶",
            command=self.next_station,
            bg="#34495e",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padx=12,
            pady=4,
            activebackground="#4a6785"
        )
        self.btn_next.pack(side="right", padx=10, pady=8)

        # ── 2. 状态信息栏 (Status Info Bar) ──
        self.info_frame = tk.Frame(self, bg="#ecf0f1", height=35)
        self.info_frame.pack(fill="x")
        self.info_frame.pack_propagate(False)

        # 显示巡检通过与否、巡检时间戳及单据概要
        self.lbl_info = tk.Label(
            self.info_frame,
            text="",
            bg="#ecf0f1",
            fg="#2c3e50",
            font=("Consolas", 11)
        )
        self.lbl_info.pack(side="left", padx=15, pady=6)

        # ── 3. 表格渲染区域 (Canvas + Scrollbar 实现可滚动表格) ──
        table_container = tk.Frame(self, bg="#d0d0d0")
        table_container.pack(fill="both", expand=True, padx=5, pady=5)

        # 画布与滚动条
        self.canvas = tk.Canvas(table_container, bg="white", highlightthickness=0)
        self.v_scroll = tk.Scrollbar(table_container, orient="vertical", command=self.canvas.yview)
        self.h_scroll = tk.Scrollbar(table_container, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        # 内嵌 Frame: 所有表格单元格 Label 将作为子控件网格排列在此容器中
        self.table_frame = tk.Frame(self.canvas, bg="white")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.table_frame, anchor="nw")

        # 监听容器尺寸调整事件，动态更新滚动区域
        self.table_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 鼠标滚轮动态绑定机制:
        # 仅当光标进入弹窗 (<Enter>) 时才响应滚轮，光标离开 (<Leave>) 立即注销，防止抢占主界面的滚动操作
        self.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # ── 4. 底部快捷键提示 (Bottom Shortcut Hints) ──
        bottom = tk.Frame(self, bg="#2c3e50", height=28)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        tk.Label(
            bottom,
            text="Shortcuts: ← → Switch Station  |  Esc Close  |  Scroll Wheel to Navigate Table",
            bg="#2c3e50",
            fg="#7f8c8d",
            font=("Consolas", 9)
        ).pack(side="right", padx=10, pady=4)

    def _on_frame_configure(self, event=None):
        """当表格内部控件变动导致尺寸变化时，重新计算 Canvas 的全量滚动范围"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        """确保内嵌表格宽度至少等于画布当前可视宽度，对于宽表格则允许横向滚动自适应"""
        canvas_width = event.width if event else self.canvas.winfo_width()
        frame_width = self.table_frame.winfo_reqwidth()
        self.canvas.itemconfig(self.canvas_window, width=max(frame_width, canvas_width))

    def _on_mousewheel(self, event):
        """鼠标滚轮事件响应，按 120 像素步长平滑垂直滚动 Canvas"""
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def load_data(self):
        """
        [核心渲染引擎]
        从 CheckpointStore 读取当前关卡数据，解析原生表头、数据行及色彩配置，
        在 table_frame 中以 1:1 工控网页像素风格动态生成所有表格单元格。
        """
        # 1. 获取当前关卡 page_key 与全称
        page_key, display_name = STATION_LIST[self.station_index]

        # 2. 从内存单例获取该关卡的结构化数据
        data = CheckpointStore.get(page_key)

        # 3. 更新顶部标题栏与窗口外框标题
        self.lbl_title.configure(text=f"{display_name}  ({self.station_index + 1}/{len(STATION_LIST)})")
        self.title(f"Log Details — {display_name}")

        # 4. 更新上一站/下一站按钮的可用状态 (边界保护)
        self.btn_prev.configure(state="normal" if self.station_index > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.station_index < len(STATION_LIST) - 1 else "disabled")

        # 5. 销毁 table_frame 中原有的旧表格所有子 Label 控件
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        # 6. 分支 A: 若此关卡尚未执行过巡检
        if data is None:
            self.lbl_info.configure(text="Status: 📭 Not Run", fg="#7f8c8d")
            lbl = tk.Label(
                self.table_frame,
                text=f"\n\n    📭 {display_name} has not been inspected yet.\n\n    Please run a checkpoint inspection first to generate data.\n",
                bg="white",
                fg="#7f8c8d",
                font=("Segoe UI", 14),
                justify="left",
                anchor="nw"
            )
            lbl.grid(row=0, column=0, padx=30, pady=30, sticky="nw")
            return

        # 7. 更新状态信息栏显示
        status_icon = "✅ Passed" if data["status"] else "❌ Error"
        self.lbl_info.configure(
            text=f"Inspection Time: {data['timestamp']}  |  Status: {status_icon}"
                 + (f"  |  {data['summary']}" if data.get("summary") else ""),
            fg="#27ae60" if data["status"] else "#e74c3c"
        )

        # 8. 统一标准化表格数据格式 (兼容多子表格式与旧版单表格式)
        tables = data.get("tables", [])
        if not tables and (data.get("headers") or data.get("rows")):
            tables = [{"title": "", "headers": data.get("headers", []), "rows": data.get("rows", [])}]

        # 9. 分支 B: 若没有表格明细 (如只有文字摘要)
        if not tables:
            lbl = tk.Label(
                self.table_frame,
                text=f"\n  {status_icon}  {data.get('summary', 'No detailed table data available')}\n",
                bg="white",
                fg="#2c3e50",
                font=("Segoe UI", 13),
                justify="left",
                anchor="nw"
            )
            lbl.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
            return

        # 10. 判断该关卡是否适合工控蓝表头 (如 Robot Monitor 机器人监控或 AP 服务器监控类)
        is_robot_page = "robot" in display_name.lower() or "copier" in display_name.lower() or "ap" in display_name.lower()
        default_header_bg = COLOR_HEADER_BLUE if is_robot_page else COLOR_HEADER_OLIVE

        current_grid_row = 0

        # ── 11. 循环渲染各个独立子表格 (支持原生单表或多个子表) ──
        for t_idx, tbl in enumerate(tables):
            sub_title = tbl.get("title", "").strip()
            tbl_headers = tbl.get("headers", [])
            tbl_rows = tbl.get("rows", [])
            tbl_header_bg = tbl.get("header_bg", default_header_bg)

            # (1) 若定义了子表名称，先渲染子表条目标题栏
            if sub_title:
                title_lbl = tk.Label(
                    self.table_frame,
                    text=f"  ▶ {sub_title}  ",
                    bg="#2c3e50",
                    fg="#58a6ff",
                    font=("Segoe UI", 11, "bold"),
                    relief="flat",
                    anchor="w"
                )
                title_lbl.grid(
                    row=current_grid_row,
                    column=0,
                    columnspan=max(len(tbl_headers), 1),
                    sticky="ew",
                    padx=2,
                    pady=(12 if t_idx > 0 else 4, 4)
                )
                current_grid_row += 1

            # (2) 渲染表头单元格行 (加粗文字，工控底色，实线细边框)
            if tbl_headers:
                for col_idx, header_text in enumerate(tbl_headers):
                    cell = tk.Label(
                        self.table_frame,
                        text=f" {header_text} ",
                        bg=tbl_header_bg,
                        fg=COLOR_HEADER_FG,
                        font=("Segoe UI", 10, "bold"),
                        relief="solid",
                        borderwidth=1,
                        padx=6,
                        pady=3,
                        anchor="center"
                    )
                    cell.grid(row=current_grid_row, column=col_idx, sticky="nsew")
                current_grid_row += 1

            # (3) 渲染具体数据行
            for row_data in tbl_rows:
                for col_idx, cell_data in enumerate(row_data):
                    # 兼容单元格数据类型: 支持原始字典 dict {"text", "bg", "is_link", "fg"} 或简单字符串/数字
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

                    # 若未显式指定颜色 (bg_key == "auto")，调用静态规则引擎自动推导颜色
                    if bg_key == "auto":
                        bg_key = self._auto_color(text)

                    # 映射实际的十六进制背景色
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

                    # 超链接样式判断 (如 s0001, d0005, 10.x.x.x, Generate 日期等)
                    if fg_custom:
                        fg_color = fg_custom
                    elif is_link or self._is_link_text(text, col_idx):
                        if bg_color == COLOR_WHITE_BG:
                            fg_color = COLOR_LINK_FG # 赋予网页超链接纯蓝色

                    # 若为链接则附加下划线效果
                    font_spec = ("Consolas", 10, "underline") if (fg_color == COLOR_LINK_FG) else ("Consolas", 10)

                    # 创建单元格 Label
                    cell = tk.Label(
                        self.table_frame,
                        text=f" {text} ",
                        bg=bg_color,
                        fg=fg_color,
                        font=font_spec,
                        relief="solid",
                        borderwidth=1,
                        padx=5,
                        pady=2,
                        anchor="w"
                    )
                    cell.grid(row=current_grid_row, column=col_idx, sticky="nsew")
                current_grid_row += 1

            # 表格之间留出适当空白行
            current_grid_row += 1

        # 12. 均衡网格列宽，使其在窗口中均匀分布
        all_col_counts = [len(t.get("headers", [])) for t in tables] + [
            len(r) for t in tables for r in t.get("rows", [])
        ]
        max_cols = max(all_col_counts, default=1)
        for col_idx in range(max_cols):
            self.table_frame.columnconfigure(col_idx, weight=1)

    @staticmethod
    def _is_link_text(text: str, col_idx: int) -> bool:
        """
        [超链接特征识别规则]
        静态工具方法：判断某文本是否属于公司系统的可点击链接 (如节点代码、操作按钮、服务器 IP 等)。
        """
        s = text.strip()
        if not s:
            return False

        # 规则 1: 卫星节点代码 (5 位，以特定字母开头 + 4位数字，如 s0001, d0005, p0001, e1001, j0001)
        if len(s) == 5 and s[0] in "sdtpekj" and s[1:].isdigit():
            return True

        # 规则 2: 操作指令特征文字 (如 "Generate 2026-08-12", "Show Process", "Resume", "Release Report")
        if re.match(r"^Generate \d{4}-", s) or s in ("Show Process", "Resume", "Release Report"):
            return True

        # 规则 3: 内部私有 IP 地址 (10.x.x.x 格式)
        if s.startswith("10.") and (len(s.split(".")) == 4):
            return True

        return False

    @staticmethod
    def _auto_color(text: str) -> str:
        """
        [单元格背景色自动推导引擎]
        静态工具方法：根据内容语义自动推导出对应的警示背景色，1:1 对齐企业系统规范。
        """
        lower = text.strip().lower()

        # 绿色: 明确的成功/正常标识
        if lower in ("ok", "success", "0", "-", "no error", "normal", "idle", "running"):
            return "green"

        # 黄色: 正在计算注单状态
        if "wager cal" in lower:
            return "yellow"

        # 红色: 明确的致命错误/停止运行标识
        if any(k in lower for k in ("error", "fail", "die", "fatal", "block", "red")):
            return "red"

        # 数字推导: 若解析为纯数字且等于 0，视作正常清空状态 (如积压为 0)
        try:
            val = int(lower.replace(",", "").replace(" ", ""))
            if val == 0:
                return "green"
        except (ValueError, TypeError):
            pass

        # 默认底色为普通白色
        return "white"

    def prev_station(self):
        """[快捷切换上一站] 序号递减并重新渲染数据"""
        if self.station_index > 0:
            self.station_index -= 1
            self.load_data()

    def next_station(self):
        """[快捷切换下一站] 序号递增并重新渲染数据"""
        if self.station_index < len(STATION_LIST) - 1:
            self.station_index += 1
            self.load_data()

    def destroy(self):
        """
        [弹窗销毁生命周期重写]
        关闭弹窗前，必须显式解绑全局绑定在 Canvas 上的 MouseWheel 滚轮事件，
        防止在弹窗注销后主界面滚动时抛出已销毁控件引用的异常。
        """
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if hasattr(self, 'parent_tab') and self.parent_tab:
            self.parent_tab._detail_window = None
        super().destroy()

