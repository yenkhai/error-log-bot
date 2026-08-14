"""
================================================================================
HTML 仪表盘管理器 (core/report_manager.py)
--------------------------------------------------------------------------------
数据来源: Desktop\\CheckpointLogs\\{niw,copier}\\*.txt  (page_logger.py 写入)

功能:
1. 读取所有页面的 .txt 日志文件中每一条历史记录 (全量，非仅最新)
2. 每个关卡显示完整的历史 Timeline — 按时间倒序排列，每次 Checkpoint 一条
3. ASCII 表格数据直接转换成 HTML 彩色表格 (OK=绿/FAILED=红/WARN=黄)
4. 生成 reports/dashboard.html 并在浏览器中打开
================================================================================
"""

import os
import time
import webbrowser
from datetime import datetime
from core.page_logger import LOG_ROOT, PAGE_LOG_META, PageLogger, RECORD_SEPARATOR

_PROJ_ROOT = os.path.dirname(os.path.dirname(__file__))
DASHBOARD_FILE = os.path.join(_PROJ_ROOT, "reports", "dashboard.html")


# ─────────────────────────────────────────────────────────────────────────────
# 解析单个 .txt 文件（每文件一条记录）
# ─────────────────────────────────────────────────────────────────────────────

def _parse_single_file(txt_path: str) -> dict | None:
    """
    解析单个 checkpoint .txt 文件（每文件刚好一条记录）。
    返回 dict: timestamp, timestamp_str, station_name, is_success, ascii_lines, raw_lines
    """
    if not os.path.exists(txt_path):
        return None

    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return None

    # 常加内容可能包含旧式 RECORD_SEPARATOR，简单去除即可
    content = content.replace(RECORD_SEPARATOR, "")
    lines = content.splitlines()

    # 提取关键字段
    timestamp_str = ""
    is_success = True
    station_name = ""
    for line in lines:
        if "巡检时间:" in line:
            timestamp_str = line.replace("巡检时间:", "").strip()
        if "结果" in line and ("SUCCESS" in line or "FAILED" in line):
            is_success = "SUCCESS" in line
        if "页面站点:" in line:
            station_name = line.replace("页面站点:", "").strip()

    # 如果内容里没有时间，从文件名提取
    if not timestamp_str:
        try:
            basename = os.path.basename(txt_path).replace(".txt", "")
            # 格式: prefix_YYYYMMDD_HHMMSS 或 prefix_YYYYMMDD_HHMM
            parts = basename.rsplit("_", 2)
            ts_raw = parts[-2] + "_" + parts[-1]
            try:
                dt = datetime.strptime(ts_raw, "%Y%m%d_%H%M%S")
            except ValueError:
                dt = datetime.strptime(ts_raw, "%Y%m%d_%H%M")
            timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            timestamp_str = ""

    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
        except ValueError:
            timestamp = datetime.min

    # ASCII 表格行
    ascii_chars = set("┌┐└┘├┼┤─│┬┴")
    ascii_lines = [ln for ln in lines if any(c in ln for c in ascii_chars)]

    # 原始日志行
    raw_lines = []
    in_raw = False
    for line in lines:
        if "--- 原始日志 ---" in line:
            in_raw = True
            continue
        if in_raw:
            stripped = line.strip()
            if stripped and all(c == "─" for c in stripped) and len(stripped) > 5:
                break
            raw_lines.append(line)

    return {
        "timestamp":     timestamp,
        "timestamp_str": timestamp_str,
        "station_name":  station_name,
        "is_success":    is_success,
        "ascii_lines":   ascii_lines,
        "raw_lines":     raw_lines,
        "filename":      os.path.basename(txt_path),
    }


def _parse_all_records(page_key: str) -> list:
    """
    读取某个 page_key 下所有独立 .txt 文件，返回全量历史记录列表。
    已按时间降序排列（最新在最前）。
    """
    files = PageLogger.get_page_log_files(page_key)   # 已降序排列
    records = []
    for fp in files:
        rec = _parse_single_file(fp)
        if rec:
            records.append(rec)
    return records


# ─────────────────────────────────────────────────────────────────────────────
# ASCII 表格 → HTML <table> (完整显示，不截断)
# ─────────────────────────────────────────────────────────────────────────────

def _ascii_table_to_html(ascii_lines: list) -> str:
    """把 ASCII 边框表格行转成完整的 HTML <table>（含行颜色语义）"""
    if not ascii_lines:
        return ""

    data_lines = [ln for ln in ascii_lines if "│" in ln]
    if not data_lines:
        return ""

    def parse_row(line: str) -> list:
        parts = line.split("│")
        return [p.strip() for p in parts if p != ""]

    def row_class(row: list) -> str:
        text = " ".join(row).upper()
        if any(k in text for k in ["ERROR", "TIER 1", "TIER1", "FAILED", "❌", "[ERROR"]):
            return "row-err"
        if any(k in text for k in ["WARN", "TIER 3", "TIER3", "提醒", "[WARN"]):
            return "row-warn"
        if any(k in text for k in ["OK/", "SUCCESS", "正常", "NO ERROR", "✅", "[OK"]):
            return "row-ok"
        return ""

    rows = [parse_row(ln) for ln in data_lines]
    if not rows:
        return ""

    # 过滤掉空行 (有时 ASCII 分隔线混入)
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        return ""

    header_row = rows[0]
    body_rows  = rows[1:]

    thead = "<thead><tr>" + "".join(
        f"<th>{h}</th>" for h in header_row
    ) + "</tr></thead>"

    tbody_html = ""
    for row in body_rows:
        cls = row_class(row)
        tds = "".join(f"<td>{cell}</td>" for cell in row)
        tbody_html += f'<tr class="{cls}">{tds}</tr>\n'

    return f'<div class="table-scroll"><table class="data-table"><colgroup>' + \
           "".join("<col>" for _ in header_row) + \
           f"</colgroup>{thead}<tbody>{tbody_html}</tbody></table></div>"


# ─────────────────────────────────────────────────────────────────────────────
# 原始日志行 → HTML
# ─────────────────────────────────────────────────────────────────────────────

def _raw_lines_to_html(raw_lines: list) -> str:
    """把原始日志行转成带颜色的 <pre> 块，内容完整不截断"""
    if not raw_lines:
        return ""

    items = []
    for line in raw_lines:
        if not line.strip():
            items.append("<br>")
            continue
        u = line.upper()
        if any(k in u for k in ["[ERROR]", "FAILED", "TIER 1", "TIER1", "致命", "阻断", "❌"]):
            cls = "log-err"
        elif any(k in u for k in ["SUCCESS", "通关", "✅", "巡检通过", "CHECK RESULT] SUCCESS"]):
            cls = "log-ok"
        elif any(k in u for k in ["[WARN]", "TIER 3", "TIER3", "提醒", "WARNING", "[NOTICE]"]):
            cls = "log-warn"
        elif any(k in u for k in ["CHECKPOINT", "打勾"]):
            cls = "log-ckpt"
        elif any(k in u for k in ["[STATION]", "[PIPELINE", "════"]):
            cls = "log-station"
        else:
            cls = "log-info"

        escaped = (line
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        items.append(f'<div class="log-line {cls}">{escaped}</div>')

    return "\n".join(items)


# ─────────────────────────────────────────────────────────────────────────────
# 构建单次 Checkpoint 记录块 HTML
# ─────────────────────────────────────────────────────────────────────────────

def _build_record_block(rec: dict, idx: int, is_latest: bool) -> str:
    """
    生成单次巡检记录的可折叠块 HTML。
    idx=0 (最新的) 默认展开；其余默认折叠。
    """
    ts      = rec["timestamp_str"]
    ok      = rec["is_success"]
    badge   = "✅ PASS" if ok else "❌ FAILED"
    badge_c = "badge-ok" if ok else "badge-err"
    bg_c    = "rec-ok" if ok else "rec-err"
    uid     = f"rec_{id(rec)}_{idx}"  # 唯一 ID 给 details/summary 用

    table_html = _ascii_table_to_html(rec["ascii_lines"])
    log_html   = _raw_lines_to_html(rec["raw_lines"])

    body_parts = []
    if table_html:
        body_parts.append(f'<div class="section-label">📋 数据明细表</div>{table_html}')
    if log_html:
        body_parts.append(
            f'<div class="section-label">📝 原始日志</div>'
            f'<div class="log-wrap">{log_html}</div>'
        )
    if not body_parts:
        body_parts.append('<div class="log-info-dim">此次记录无详细数据</div>')

    body_html = "\n".join(body_parts)
    open_attr = " open" if is_latest else ""

    return f"""
    <details class="record-block {bg_c}"{open_attr}>
      <summary class="rec-summary">
        <span class="rec-ts">🕐 {ts}</span>
        <span class="badge {badge_c}">{badge}</span>
        {"<span class='latest-tag'>最新</span>" if is_latest else ""}
      </summary>
      <div class="rec-body">
        {body_html}
      </div>
    </details>"""


# ─────────────────────────────────────────────────────────────────────────────
# 构建单个关卡 card HTML (含所有历史记录)
# ─────────────────────────────────────────────────────────────────────────────

def _build_station_card(key: str, records: list) -> str:
    """生成单个关卡的 HTML card，含全量历史 Timeline"""
    if not records:
        label = key.replace("niw_", "NIW #").replace("copier_", "Copier #")
        return f"""
    <div class="station-card no-data">
      <div class="card-header dim">
        <span class="station-name">{label}</span>
        <span class="badge badge-none">暂无记录</span>
      </div>
      <div class="card-body"><p class="no-data-msg">尚未执行过巡检</p></div>
    </div>"""

    latest  = records[0]
    name    = latest["station_name"] or key
    ok      = latest["is_success"]
    count   = len(records)
    hdr_c   = "header-ok" if ok else "header-err"
    badge_c = "badge-ok"  if ok else "badge-err"
    badge_t = "✅ PASS"    if ok else "❌ FAILED"

    records_html = "\n".join(
        _build_record_block(rec, i, i == 0)
        for i, rec in enumerate(records)
    )

    return f"""
    <div class="station-card">
      <div class="card-header {hdr_c}">
        <span class="station-name">{name}</span>
        <div class="card-meta">
          <span class="rec-count">共 {count} 次记录</span>
          <span class="badge {badge_c}">{badge_t} (最新)</span>
        </div>
      </div>
      <div class="card-body">
        {records_html}
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# ReportManager 公开接口
# ─────────────────────────────────────────────────────────────────────────────

class ReportManager:
    DASHBOARD_FILE = DASHBOARD_FILE

    @classmethod
    def generate_html_dashboard(cls):
        """Scan all per-checkpoint .txt files via PageLogger, build dashboard.html"""
        os.makedirs(os.path.dirname(cls.DASHBOARD_FILE), exist_ok=True)

        NIW_KEYS    = [f"niw_{str(i+1).zfill(2)}"    for i in range(15)]
        COPIER_KEYS = [f"copier_{str(i+1).zfill(2)}" for i in range(9)]

        niw_data    = [(k, _parse_all_records(k)) for k in NIW_KEYS]
        copier_data = [(k, _parse_all_records(k)) for k in COPIER_KEYS]

        html = cls._build_html(niw_data, copier_data)
        with open(cls.DASHBOARD_FILE, "w", encoding="utf-8") as f:
            f.write(html)

    @classmethod
    def open_dashboard(cls):
        cls.generate_html_dashboard()
        if os.path.exists(cls.DASHBOARD_FILE):
            webbrowser.open(f"file:///{os.path.abspath(cls.DASHBOARD_FILE)}")

    @classmethod
    def _build_html(cls, niw_data: list, copier_data: list) -> str:
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        all_data  = niw_data + copier_data
        total     = len(all_data)
        passed    = sum(1 for _, recs in all_data if recs and recs[0]["is_success"])
        failed    = sum(1 for _, recs in all_data if recs and not recs[0]["is_success"])
        no_data   = sum(1 for _, recs in all_data if not recs)
        total_runs = sum(len(recs) for _, recs in all_data)

        niw_html    = "\n".join(_build_station_card(k, r) for k, r in niw_data)
        copier_html = "\n".join(_build_station_card(k, r) for k, r in copier_data)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIW 巡检仪表盘</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  font-family:"Segoe UI","Microsoft YaHei",sans-serif;
  background:#0D1117;color:#C9D1D9;font-size:13px;line-height:1.5;
}}
/* ── TopBar ── */
.top-bar{{
  background:linear-gradient(135deg,#0C63AF,#1565C0);
  padding:18px 30px;display:flex;justify-content:space-between;align-items:center;
  box-shadow:0 2px 12px rgba(0,0,0,.5);
}}
.top-bar h1{{font-size:20px;font-weight:700;color:#fff;}}
.top-bar .meta{{font-size:11px;color:rgba(255,255,255,.65);margin-top:3px;}}
.btn-refresh{{
  background:rgba(255,255,255,.12);color:#fff;
  border:1px solid rgba(255,255,255,.3);padding:6px 18px;
  border-radius:6px;cursor:pointer;font-size:13px;
}}
.btn-refresh:hover{{background:rgba(255,255,255,.22);}}
/* ── Stats ── */
.stats-bar{{
  display:flex;gap:12px;padding:14px 30px;
  background:#161B22;border-bottom:1px solid #30363D;flex-wrap:wrap;
}}
.stat-box{{
  background:#21262D;border:1px solid #30363D;border-radius:8px;
  padding:10px 18px;min-width:120px;text-align:center;
}}
.stat-box .num{{font-size:24px;font-weight:700;}}
.stat-box .label{{font-size:11px;color:#8B949E;margin-top:2px;}}
.num-pass{{color:#3FB950;}} .num-fail{{color:#F85149;}}
.num-none{{color:#8B949E;}} .num-total{{color:#58A6FF;}}
/* ── Section Title ── */
.section-title{{
  padding:13px 30px 8px;font-size:13px;font-weight:700;
  color:#8BE9FD;letter-spacing:.8px;
  background:#161B22;border-bottom:1px solid #30363D;
}}
/* ── Cards Grid ── */
.cards-grid{{
  padding:14px 30px;display:grid;gap:14px;background:#0D1117;
}}
/* ── Station Card ── */
.station-card{{border:1px solid #30363D;border-radius:8px;overflow:hidden;background:#161B22;}}
.station-card.no-data{{opacity:.5;}}
.card-header{{
  display:flex;justify-content:space-between;align-items:center;
  padding:10px 16px;font-weight:700;font-size:13px;
}}
.header-ok{{background:#0D4429;border-bottom:2px solid #3FB950;}}
.header-err{{background:#490202;border-bottom:2px solid #F85149;}}
.dim{{background:#21262D;border-bottom:1px solid #30363D;}}
.card-meta{{display:flex;align-items:center;gap:10px;}}
.station-name{{color:#E6EDF3;}}
.rec-count{{font-size:11px;color:#8B949E;font-weight:400;}}
.card-body{{padding:10px 14px;}}
.no-data-msg{{color:#8B949E;font-style:italic;padding:8px 0;}}
/* ── Badge ── */
.badge{{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;}}
.badge-ok{{background:#238636;color:#fff;}}
.badge-err{{background:#B91C1C;color:#fff;}}
.badge-none{{background:#30363D;color:#8B949E;}}
.latest-tag{{
  background:#1f538d;color:#79c0ff;
  font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:6px;
}}
/* ── Record Block (details/summary) ── */
.record-block{{
  border:1px solid #30363D;border-radius:6px;margin-bottom:8px;overflow:hidden;
}}
.record-block.rec-ok{{border-left:3px solid #3FB950;}}
.record-block.rec-err{{border-left:3px solid #F85149;}}
.rec-summary{{
  display:flex;align-items:center;gap:10px;
  padding:8px 12px;cursor:pointer;user-select:none;
  background:#21262D;list-style:none;
}}
.rec-summary:hover{{background:#2D333B;}}
.rec-summary::-webkit-details-marker{{display:none;}}
.record-block[open] .rec-summary{{background:#2D333B;}}
.rec-ts{{font-family:"Consolas",monospace;font-size:12px;color:#8B949E;}}
.rec-body{{padding:12px 14px;background:#0D1117;}}
/* ── Section labels ── */
.section-label{{
  font-size:11px;font-weight:700;color:#8B949E;
  letter-spacing:.5px;margin:10px 0 6px;text-transform:uppercase;
}}
/* ── Data Table ── */
.table-scroll{{overflow-x:auto;margin-bottom:10px;}}
.data-table{{
  border-collapse:collapse;width:100%;font-size:12px;
  font-family:"Consolas","Courier New",monospace;white-space:nowrap;
}}
.data-table th{{
  background:#0C63AF;color:#fff;padding:6px 12px;
  text-align:left;border:1px solid #1565C0;
}}
.data-table td{{
  padding:5px 12px;border:1px solid #30363D;color:#C9D1D9;
}}
.data-table tr.row-ok td{{background:#0D4429;color:#3FB950;}}
.data-table tr.row-err td{{background:#490202;color:#F85149;}}
.data-table tr.row-warn td{{background:#3D2B00;color:#F0A500;}}
.data-table tr:not(.row-ok):not(.row-err):not(.row-warn):hover td{{background:#1C2128;}}
/* ── Log Lines ── */
.log-wrap{{
  background:#010409;border:1px solid #21262D;border-radius:6px;
  padding:8px 10px;max-height:300px;overflow-y:auto;
  font-family:"Consolas","Courier New",monospace;font-size:12px;
}}
.log-line{{padding:1px 6px;border-radius:3px;margin:1px 0;white-space:pre-wrap;word-break:break-all;}}
.log-ok{{background:#0D4429;color:#3FB950;}}
.log-err{{background:#490202;color:#F85149;}}
.log-warn{{background:#3D2B00;color:#F0A500;}}
.log-ckpt{{background:#082032;color:#58A6FF;}}
.log-station{{color:#8BE9FD;font-weight:bold;}}
.log-info{{color:#8B949E;}}
.log-info-dim{{color:#484F58;font-style:italic;padding:8px 0;}}
/* ── Footer ── */
footer{{
  text-align:center;padding:18px;color:#484F58;
  font-size:11px;background:#0D1117;border-top:1px solid #21262D;
}}
</style>
</head>
<body>
<div class="top-bar">
  <div>
    <h1>📊 NIW 关卡巡检仪表盘</h1>
    <div class="meta">
      数据源: {LOG_ROOT} &nbsp;|&nbsp;
      保留最近 12 小时记录 &nbsp;|&nbsp;
      最后生成: {now_str}
    </div>
  </div>
  <button class="btn-refresh" onclick="location.reload()">🔄 刷新</button>
</div>

<div class="stats-bar">
  <div class="stat-box"><div class="num num-total">{total}</div><div class="label">总关卡数</div></div>
  <div class="stat-box"><div class="num num-pass">{passed}</div><div class="label">✅ 最新通过</div></div>
  <div class="stat-box"><div class="num num-fail">{failed}</div><div class="label">❌ 最新异常</div></div>
  <div class="stat-box"><div class="num num-none">{no_data}</div><div class="label">⬜ 暂无数据</div></div>
  <div class="stat-box"><div class="num num-total">{total_runs}</div><div class="label">📋 历史记录总数</div></div>
</div>

<div class="section-title">🔷 NIW 区域 (15 站)</div>
<div class="cards-grid">{niw_html}</div>

<div class="section-title">🔶 Copier & Server 区域 (9 站)</div>
<div class="cards-grid">{copier_html}</div>

<footer>
  Error Log Bot 巡检系统 &copy; {time.strftime('%Y')} &nbsp;|&nbsp;
  数据目录: {LOG_ROOT}
</footer>
</body>
</html>"""
