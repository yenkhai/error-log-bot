"""
================================================================================
巡检数据内存仓库 (core/checkpoint_store.py)
--------------------------------------------------------------------------------
作用:
1. 全局单例内存仓库，存储每个关卡最新一次巡检的结构化表格数据。
2. 每个关卡调用 CheckpointStore.save() 存入 headers + rows + status。
3. 日志浏览器 Tab 从此处读取数据并渲染仿公司风格的彩色表格。
4. 程序关闭后数据自动清空（纯内存，不持久化）。
================================================================================
"""

import threading
from datetime import datetime


class CheckpointStore:
    """
    全局内存仓库 — 存储每个关卡最新一次巡检的结构化表格数据。

    数据结构:
        _data[page_key] = {
            "title":     "Pending Wager",
            "status":    True/False,
            "timestamp": "2026-08-20 17:55:06",
            "headers":   ["Company", "Pending", "Status"],
            "rows":      [
                [{"text": "d0001", "bg": "green"}, {"text": "0", "bg": "green"}, ...],
                [{"text": "d0013", "bg": "red"},   {"text": "5", "bg": "red"},   ...],
            ],
            "summary":   "全部 0 积压，正常通关"  (可选的一行摘要文本)
        }

    每个 cell 可以是:
        - str:  纯文本，自动判断颜色 (ok/success/0 → 绿底, error/red → 红底)
        - dict: {"text": "xxx", "bg": "green"/"red"/"white"/"header"}
    """

    _data = {}
    _lock = threading.Lock()

    @classmethod
    def save(cls, page_key: str, title: str, status: bool,
             headers: list = None, rows: list = None, summary: str = "",
             tables: list = None):
        """
        保存一个关卡的最新巡检结构化数据。

        参数:
            page_key:  关卡唯一标识 (如 "niw_01", "copier_05")
            title:     关卡显示名 (如 "Pending Wager")
            status:    True=通过, False=异常
            headers:   单表表头列表 (如 ["Company", "Pending Count", "Status"])
            rows:      单表二维数据列表，每行是 [cell, cell, ...]
            summary:   可选的一行文字摘要
            tables:    多表结构列表，格式为:
                       [{"title": "子表名", "headers": [...], "rows": [...]}, ...]
                       用于一个页面包含多张独立原生表格时 1:1 还原展示
        """
        # 若提供了 tables，确保 headers/rows 也具备首表数据以保证 100% 向下兼容
        if tables and not headers and len(tables) > 0:
            headers = tables[0].get("headers", [])
            rows = tables[0].get("rows", [])
        elif not tables and headers is not None:
            tables = [{"title": "", "headers": headers or [], "rows": rows or []}]

        item = {
            "title":     title,
            "status":    status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "headers":   headers or [],
            "rows":      rows or [],
            "tables":    tables or [],
            "summary":   summary,
        }
        with cls._lock:
            cls._data[page_key] = item

    @classmethod
    def get(cls, page_key: str) -> dict:
        """获取某关卡的最新数据，未跑过则返回 None"""
        with cls._lock:
            val = cls._data.get(page_key, None)
            return dict(val) if val else None

    @classmethod
    def get_all_summary(cls) -> dict:
        """返回全部已存储的关卡概要 {page_key: {title, status, timestamp}}"""
        result = {}
        with cls._lock:
            for pk, d in cls._data.items():
                result[pk] = {
                    "title":     d["title"],
                    "status":    d["status"],
                    "timestamp": d["timestamp"],
                }
        return result

    @classmethod
    def clear(cls):
        """清空所有数据"""
        with cls._lock:
            cls._data.clear()

    @classmethod
    def make_cell(cls, text: str, bg: str = "auto", fg: str = None, is_link: bool = False) -> dict:
        """
        便捷方法：创建一个带颜色与属性的单元格。
        bg="auto" 时根据文本内容自动判断颜色:
            ok/success/0/-/normal/running → green (高亮鲜艳绿)
            error/fail/red/block/die/fatal → red (高亮鲜艳红)
            其余                           → white (纯白底)
        """
        raw_text = "" if text is None else str(text)
        if bg == "auto":
            lower = raw_text.strip().lower()
            if lower in ("ok", "success", "0", "-", "no error", "normal", "idle", "running"):
                bg = "green"
            elif "wager cal" in lower:
                bg = "yellow"
            elif any(k in lower for k in ("error", "fail", "red", "block", "fatal", "die")):
                bg = "red"
            else:
                bg = "white"
        return {"text": raw_text, "bg": bg, "fg": fg, "is_link": is_link}
