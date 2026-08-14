"""
================================================================================
桌面日志管理器 (core/page_logger.py)
--------------------------------------------------------------------------------
【存储结构】每次 Checkpoint 独立一个文件，文件名含时间戳：

  Desktop\\CheckpointLogs\\
  ├── INDEX.txt
  ├── niw\\
  │   ├── 01_pending_wager_20260813_1500.txt   ← 3点那次
  │   ├── 01_pending_wager_20260813_1600.txt   ← 4点那次
  │   ├── 02_ccl_recover_20260813_1501.txt
  │   └── ...
  └── copier\\
      ├── 01_copier_20260813_1502.txt
      └── ...

【清理规则】超过 12 小时的旧文件自动删除（按文件名时间戳判断）。
================================================================================
"""

import os
import glob
from datetime import datetime, timedelta

# ── 常量 ────────────────────────────────────────────────────────────────────
DESKTOP_PATH     = os.path.join(os.path.expanduser("~"), "Desktop")
LOG_ROOT         = os.path.join(DESKTOP_PATH, "CheckpointLogs")
LOG_RETAIN_HOURS = 12   # 保留最近 12 小时

# 每个 page_key → (子目录, 文件名前缀)
PAGE_LOG_META = {
    "niw_01":    ("niw",    "01_pending_wager"),
    "niw_02":    ("niw",    "02_ccl_recover"),
    "niw_03":    ("niw",    "03_matches_wagers"),
    "niw_04":    ("niw",    "04_result_process"),
    "niw_05":    ("niw",    "05_calculate_betslips"),
    "niw_06":    ("niw",    "06_rpt_polymarket"),
    "niw_07":    ("niw",    "07_rpt_compare"),
    "niw_08":    ("niw",    "08_rpt_ai"),
    "niw_09":    ("niw",    "09_rpt_compare_utc"),
    "niw_10":    ("niw",    "10_forecast"),
    "niw_11":    ("niw",    "11_check_ccl"),
    "niw_12":    ("niw",    "12_wsum_sport"),
    "niw_13":    ("niw",    "13_hg_percentages"),
    "niw_14":    ("niw",    "14_rpt_crs"),
    "niw_15":    ("niw",    "15_one_wallet_pending"),
    "copier_01": ("copier", "01_copier"),
    "copier_02": ("copier", "02_db_server_status"),
    "copier_03": ("copier", "03_ap_server_status"),
    "copier_04": ("copier", "04_check_ap_space"),
    "copier_05": ("copier", "05_error_log"),
    "copier_06": ("copier", "06_redis_server"),
    "copier_07": ("copier", "07_robot_monitor"),
    "copier_08": ("copier", "08_niw_robot_monitor"),
    "copier_09": ("copier", "09_info_robot_monitor"),
}

# 兼容旧代码引用 PAGE_LOG_FILES（指向 get_page_log_files）
# report_manager 直接调用 PageLogger.get_page_log_files()，不再用此 dict
PAGE_LOG_FILES = {}   # 保留空 dict，防止 import 报错

# RECORD_SEPARATOR 已废弃（每文件一条记录不再需要分隔符），保留仅供兼容
RECORD_SEPARATOR = ">>>RECORD_START<<<"


class PageLogger:
    """
    桌面分页日志管理器
    - 每次 write_page_log() 新建一个独立 .txt 文件（文件名含时间戳）
    - 超过 12 小时的旧文件自动删除
    """

    # ── 目录初始化 ────────────────────────────────────────────────────────
    @staticmethod
    def ensure_dirs():
        """确保桌面日志文件夹结构完整"""
        for subdir in ("niw", "copier"):
            os.makedirs(os.path.join(LOG_ROOT, subdir), exist_ok=True)

    # ── 获取某 page_key 的所有历史文件（按时间降序） ─────────────────────
    @staticmethod
    def get_page_log_files(page_key: str) -> list[str]:
        """
        返回该 page_key 下所有 .txt 文件路径，按文件名时间戳降序排列
        （最新在最前）。
        """
        meta = PAGE_LOG_META.get(page_key)
        if not meta:
            return []
        subdir, prefix = meta
        dir_path = os.path.join(LOG_ROOT, subdir)
        pattern  = os.path.join(dir_path, f"{prefix}_*.txt")
        files    = glob.glob(pattern)

        def ts_key(f):
            """从文件名 prefix_YYYYMMDD_HHMMSS.txt 提取时间戳用于排序"""
            try:
                name = os.path.basename(f).replace(f"{prefix}_", "").replace(".txt", "")
                # 支持 YYYYMMDD_HHMMSS (新格式) 和 YYYYMMDD_HHMM (旧格式)
                try:
                    return datetime.strptime(name, "%Y%m%d_%H%M%S")
                except ValueError:
                    return datetime.strptime(name, "%Y%m%d_%H%M")
            except ValueError:
                return datetime.min

        files.sort(key=ts_key, reverse=True)   # 最新在前
        return files

    # ── ASCII 表格格式化 ──────────────────────────────────────────────────
    @staticmethod
    def format_ascii_table(headers: list, rows: list) -> str:
        """生成 ASCII 边框表格"""
        if not headers:
            return ""

        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        def make_row(cells, widths, sep="│"):
            parts = [f" {str(c).ljust(w)} " for c, w in zip(cells, widths)]
            return sep + sep.join(parts) + sep

        def make_line(widths, left="├", mid="┼", right="┤", fill="─"):
            parts = [fill * (w + 2) for w in widths]
            return left + mid.join(parts) + right

        lines = [
            make_line(col_widths, "┌", "┬", "┐"),
            make_row(headers, col_widths),
            make_line(col_widths),
        ]
        for row in rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            lines.append(make_row(padded, col_widths))
        lines.append(make_line(col_widths, "└", "┴", "┘"))
        return "\n".join(lines)

    # ── 写入单次 Checkpoint 日志（每次新文件） ────────────────────────────
    @staticmethod
    def write_page_log(page_key: str, station_name: str, is_success: bool,
                       raw_lines: list,
                       table_headers: list = None, table_rows: list = None):
        """
        写入一次 Checkpoint 记录到独立文件。
        文件名格式: {prefix}_{YYYYMMDD_HHMM}.txt
        同时触发旧文件清理（超过 12 小时）。
        """
        PageLogger.ensure_dirs()
        meta = PAGE_LOG_META.get(page_key)
        if not meta:
            return

        subdir, prefix = meta
        dir_path = os.path.join(LOG_ROOT, subdir)

        now      = datetime.now()
        ts_str   = now.strftime("%Y%m%d_%H%M%S")   # 精确到秒，避免同分钟撞名
        filename = f"{prefix}_{ts_str}.txt"
        filepath = os.path.join(dir_path, filename)

        result_icon = "SUCCESS" if is_success else "FAILED"

        lines = []
        lines.append("=" * 80)
        lines.append(f"  巡检时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  页面站点: {station_name}")
        lines.append(f"  结果    : {'✅ SUCCESS' if is_success else '❌ FAILED'}")
        lines.append("=" * 80)
        lines.append("")

        # ASCII 表格（若提供结构化数据）
        if table_headers and table_rows is not None:
            lines.append(PageLogger.format_ascii_table(table_headers, table_rows))
            lines.append("")

        # 原始日志行
        if raw_lines:
            lines.append("--- 原始日志 ---")
            for line in raw_lines:
                if any(k in line for k in ["chromedriver!", "KERNEL32!", "ntdll!"]):
                    continue
                lines.append(line)
            lines.append("")

        lines.append("─" * 80)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # 触发旧文件清理
        PageLogger._cleanup_old_files(dir_path, prefix)

    # ── 旧文件自动清理 ────────────────────────────────────────────────────
    @staticmethod
    def _cleanup_old_files(dir_path: str, prefix: str):
        """删除超过 LOG_RETAIN_HOURS 的旧 .txt 文件（按文件名时间戳判断）"""
        cutoff = datetime.now() - timedelta(hours=LOG_RETAIN_HOURS)
        pattern = os.path.join(dir_path, f"{prefix}_*.txt")
        for filepath in glob.glob(pattern):
            try:
                name = os.path.basename(filepath).replace(f"{prefix}_", "").replace(".txt", "")
                try:
                    file_ts = datetime.strptime(name, "%Y%m%d_%H%M%S")
                except ValueError:
                    file_ts = datetime.strptime(name, "%Y%m%d_%H%M")
                if file_ts < cutoff:
                    os.remove(filepath)
            except (ValueError, OSError):
                pass

    # ── 更新 INDEX.txt ─────────────────────────────────────────────────
    @staticmethod
    def update_index(results: list):
        """
        更新 CheckpointLogs\\INDEX.txt 汇总最近一次巡检的所有页面状态
        results: [(page_key, station_name, is_success, timestamp_str), ...]
        """
        PageLogger.ensure_dirs()
        index_path = os.path.join(LOG_ROOT, "INDEX.txt")
        now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = []
        lines.append("=" * 80)
        lines.append("  CheckpointLogs 巡检目录索引")
        lines.append(f"  最近更新时间: {now_str}")
        lines.append("=" * 80)
        lines.append("")

        lines.append("  NIW 区域 (15 站):")
        lines.append("  " + "─" * 60)
        for page_key, name, ok, ts in results:
            if page_key.startswith("niw_"):
                icon = "✅" if ok else "❌"
                lines.append(f"  {icon}  {name:<35} {ts}")

        lines.append("")
        lines.append("  Copier & Server 区域 (9 站):")
        lines.append("  " + "─" * 60)
        for page_key, name, ok, ts in results:
            if page_key.startswith("copier_"):
                icon = "✅" if ok else "❌"
                lines.append(f"  {icon}  {name:<35} {ts}")

        lines.append("")
        total  = len(results)
        passed = sum(1 for _, _, ok, _ in results if ok)
        lines.append(f"  总计: {passed}/{total} 站通过  "
                     f"{'全部通关！' if passed == total else '有关卡需要检查'}")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"  日志文件夹: {LOG_ROOT}")
        lines.append("  ├── niw\\    (NIW 15 站独立日志)")
        lines.append("  └── copier\\ (Copier 9 站独立日志)")
        lines.append("")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
