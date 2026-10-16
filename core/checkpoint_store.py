"""
================================================================================
巡检数据内存仓库模块 (core/checkpoint_store.py)
--------------------------------------------------------------------------------
【核心职责】:
1. 作为全局单例纯内存仓库，安全存储 24 个关卡最新一次巡检的结构化表格与状态数据。
2. 线程安全保护: 使用 Python threading.Lock 互斥锁，确保多线程下读写数据不冲突。
3. 提供统一的单元格构建器 `make_cell`: 根据指标文本自动智能推导背景颜色 (绿/红/黄/白)。
4. 纯内存生命周期: 进程关闭后数据自动释放，不产生垃圾文件，由日志查看器实时拉取渲染。
================================================================================
"""

# 导入 Python 多线程支持模块 threading，主要使用其 Lock 互斥锁实现线程安全
import threading
from datetime import datetime
import copy
import re


class CheckpointStore:
    """
    【全局内存仓库类 CheckpointStore】
    - 所有数据保存在类级别的私有变量 `_data` 字典中。
    - 所有方法均使用 `@classmethod` 类方法修饰，全局无需重复实例化，直接通过类名调用。

    【内部存储结构示例】:
        _data[page_key] = {
            "title":     "Pending Wager",               # 关卡显示名称
            "status":    True,                           # True 代表合格/通过, False 代表报错/阻断
            "timestamp": "2026-08-20 17:55:06",         # 巡检记录生成的时间戳
            "headers":   ["Company", "Pending", "Status"], # 兼容单表的表头列表
            "rows":      [                              # 兼容单表的数据行列表
                [{"text": "d0001", "bg": "green"}, {"text": "0", "bg": "green"}, ...],
                [{"text": "d0013", "bg": "red"},   {"text": "5", "bg": "red"},   ...],
            ],
            "tables":    [                              # 1:1 还原企业网页的多张独立子表格
                {"title": "SubTable 1", "headers": [...], "rows": [...]},
                ...
            ],
            "summary":   "全部 0 积压，正常通关"          # 一句话简述或异常原因
        }
    """

    # 1. 类级别私有字典，存储所有关卡的巡检数据，键为 page_key (如 "niw_01", "copier_05")
    _data = {}
    
    # 2. 类级别互斥锁，防止 GUI 主线程与后台巡检线程同时读写 _data 造成字典竞争异常
    _lock = threading.Lock()

    # 3. make_cell 自动色彩推导的关键字常量 (单词边界正则匹配，防止 credit, ordered 等被误伤)
    _OK_KEYWORDS = frozenset({"ok", "success", "0", "-", "no error", "normal", "idle", "running"})
    _RED_PATTERN = re.compile(r'\b(error|fail|failed|red|block|blocked|fatal|die)\b', re.IGNORECASE)

    @classmethod
    def _detect_has_warn(cls, status: bool, summary: str = "", tables: list = None, rows: list = None) -> bool:
        """
        [自动推导警告状态]
        当 status 为 True (无 Tier 1 阻断错误) 时，检测是否存在 Tier 3 提示、警告关键词或黄色单元格。
        若 status 为 False，则优先呈现为 Error，返回 False。
        """
        if not status:
            return False

        # 1. 检查摘要文本中的警告关键字
        if summary:
            s_lower = summary.lower()
            warn_keywords = [
                "tier 3", "tier3", "warning", "提醒", "提示",
                "wager cal", "挂起", "未完成正常"
            ]
            has_kw = any(kw in s_lower for kw in warn_keywords) or bool(re.search(r'\bwarn\b', s_lower))
            if has_kw:
                # 排除纯 0 项的假阳性情况 (例如 "0 项 Tier 3 提示", "Tier 3: 0")
                zero_patterns = [
                    r'0\s*项\s*(?:tier\s*3|提示|提醒)',
                    r'tier\s*3[^\d]*[:=]\s*0\b',
                    r'0\s*台[^\n,]*(?:use%|>80%|tier|warn)',
                    r'tier\s*3\s*提醒:\s*0'
                ]
                is_pure_zero = any(re.search(pat, s_lower) for pat in zero_patterns)
                if not is_pure_zero:
                    return True

        # 2. 检查单表 rows 中是否存在黄底或警告标记单元格
        for r in (rows or []):
            if isinstance(r, list):
                for cell in r:
                    if isinstance(cell, dict):
                        bg = (cell.get("bg") or "").lower()
                        if bg == "yellow":
                            return True
                        txt = str(cell.get("text") or "").strip().lower()
                        if txt in ("warning", "warn") or "warn/" in txt:
                            return True

        # 3. 检查多表 tables 中是否存在黄底或警告标记单元格
        for tbl in (tables or []):
            if isinstance(tbl, dict):
                for r in tbl.get("rows", []):
                    if isinstance(r, list):
                        for cell in r:
                            if isinstance(cell, dict):
                                bg = (cell.get("bg") or "").lower()
                                if bg == "yellow":
                                    return True
                                txt = str(cell.get("text") or "").strip().lower()
                                if txt in ("warning", "warn") or "warn/" in txt:
                                    return True

        return False

    @classmethod
    def save(cls, page_key: str, title: str, status: bool,
             headers: list = None, rows: list = None, summary: str = "",
             tables: list = None, has_warn: bool = None, derived_status_columns: tuple = ()):
        """
        [保存关卡巡检结果数据]
        参数:
            page_key: 关卡的唯一英文标识 (例如 "niw_01", "copier_02")
            title:    关卡人类可读的标题 (例如 "Pending Wager", "DB Server Status")
            status:   关卡巡检结论布尔值 (True=通过/合格, False=异常/阻断)
            headers:  单表模式下的表头列名列表 (可选)
            rows:     单表模式下的数据行二维列表 (可选)
            summary:  可选的单行文本摘要 (例如 "发现 2 项红色异常" 或 "全部绿底正常")
            tables:   多表结构列表，格式为: [{"title": "表名", "headers": [...], "rows": [...]}]
            has_warn: 是否包含非阻断警告 (可选，默认 None 自动根据摘要和单元格颜色智能推导)
        """
        # 步骤 A: 兼容性处理 —— 若提供了多表 tables 但未传单表 headers/rows，取首张子表以保证旧组件向下兼容
        if tables and not headers:
            headers = tables[0].get("headers", [])
            rows = tables[0].get("rows", [])
        # 步骤 B: 反向兼容 —— 若只传了单表 headers/rows，自动包裹为单一子表的 tables 结构
        elif not tables and headers is not None:
            tables = [{"title": "", "headers": headers or [], "rows": rows or [],
                       "derived_status_columns": list(derived_status_columns)}]

        # 步骤 C: 自动推导或校验 has_warn
        if has_warn is None:
            actual_has_warn = cls._detect_has_warn(status, summary, tables, rows)
        else:
            actual_has_warn = bool(has_warn) and bool(status)

        # 步骤 D: 构造本次保存的完整字典对象
        item = {
            "title":     title,                                              # 关卡名称
            "status":    status,                                             # 通关状态
            "has_warn":  actual_has_warn,                                    # 是否含警告 (Tier 3)
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),      # 当前时间字符串
            "headers":   headers or [],                                      # 表头列表 (防 None)
            "rows":      rows or [],                                         # 行数据 (防 None)
            "tables":    tables or [],                                       # 原生多表结构
            "summary":   summary,                                            # 摘要信息
        }
        
        # 步骤 E: 加锁写入全局字典，保证线程安全
        with cls._lock:
            cls._data[page_key] = item

    @classmethod
    def get(cls, page_key: str) -> dict:
        """
        [获取单个关卡最新数据]
        参数:
            page_key: 关卡标识 (如 "niw_01")
        返回:
            该关卡的数据字典拷贝，若尚未运行过则返回 None。
        """
        # 加锁保护读取
        with cls._lock:
            # 从字典中取值
            val = cls._data.get(page_key, None)
            # 返回字典深拷贝，防止调用方在外层意外修改内部数据
            return copy.deepcopy(val) if val else None

    @classmethod
    def get_all_summary(cls) -> dict:
        """
        [获取所有关卡概要列表]
        供 GUI 界面列表 (Treeview) 快速刷新状态使用，仅返回关卡名称、状态、警告标记和时间戳，避免传输大量表格数据。
        返回:
            {page_key: {"title": ..., "status": ..., "has_warn": ..., "summary": ..., "timestamp": ...}}
        """
        # 加锁遍历字典，使用字典推导式一次构建（更简洁且 CPython 中更高效）
        with cls._lock:
            return {
                pk: {
                    "title": d["title"],
                    "status": d["status"],
                    "has_warn": d.get("has_warn", False),
                    "summary": d.get("summary", ""),
                    "timestamp": d["timestamp"]
                }
                for pk, d in cls._data.items()
            }

    @classmethod
    def clear(cls):
        """
        [清空所有数据]
        当用户开启全新一轮巡检或手动重置时调用，清空内存中所有关卡的数据。
        """
        with cls._lock:
            cls._data.clear()

    @classmethod
    def make_cell(cls, text: str, bg: str = "auto", fg: str = None, is_link: bool = False) -> dict:
        """
        [便捷方法: 构建标准单元格对象]
        参数:
            text:    单元格内显示的文本内容。
            bg:      单元格背景色 (默认 "auto" 自动识别，也可强制指定 "green", "red", "yellow", "white")。
            fg:      单元格字体颜色 (默认 None，使用默认色或蓝色超链接色)。
            is_link: 是否渲染为类似超链接的下划线样式。
        
        自动色彩推导规则 (bg="auto"):
            - "ok", "success", "0", "-", "no error", "normal", "idle", "running" -> "green" (高亮鲜艳绿)
            - 包含 "wager cal" -> "yellow" (黄色警示)
            - 包含 "error", "fail", "red", "block", "fatal", "die" -> "red" (高亮鲜艳红)
            - 其余所有普通文本 -> "white" (默认纯白)
        """
        # 安全处理 None 值为纯空字符串
        raw_text = "" if text is None else str(text)
        
        # 若开启了自动颜色推导
        if bg == "auto":
            # 转换为小写并去除首尾空格进行匹配
            lower = raw_text.strip().lower()
            
            # 1. 匹配正常合格关键字 -> 标记绿底 (frozenset O(1) 查找)
            if lower in cls._OK_KEYWORDS:
                bg = "green"
            # 2. 匹配黄色刷新提醒关键字 -> 标记黄底
            elif "wager cal" in lower:
                bg = "yellow"
            # 3. 匹配致命错误与异常关键字 -> 标记红底 (单词边界匹配)
            elif cls._RED_PATTERN.search(lower):
                bg = "red"
            # 4. 其他常规数据 -> 保持白底
            else:
                bg = "white"
        
        # 返回包装好的标准单元格字典
        return {
            "text": raw_text,
            "bg": bg,
            "fg": fg,
            "is_link": is_link
        }

