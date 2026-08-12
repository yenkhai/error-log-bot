"""
================================================================================
巡检报告与 HTML 仪表盘管理器 (core/report_manager.py)
--------------------------------------------------------------------------------
功能:
1. 保留原本控制台与 Bot 日志的文本输出不受任何影响。
2. 每一个 Checkpoint 关卡将数据存入 `logs/checkpoint_history/` 中。
3. 【自动清理】：超过 24 小时 (1 天) 的关卡历史数据自动物理删除。
4. 【HTML 仪表盘生成】：读取 24 小时内的所有关卡数据，生成高保真 CSS 样式的
   `reports/dashboard.html` 网页。
   - 绿底 (#00CC00 / #28a745) 表示 OK/正常；
   - 红底 (#FF0000 / #dc3545) 表示 Tier 1 报错阻断；
   - 黄底 (#FFCC00 / #ffc107) 表示 Tier 3 提醒；
   - 尽量 100% 还原后台原始表格视觉感观。
================================================================================
"""

import os
import json
import time
import glob
import webbrowser

class ReportManager:
    HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "checkpoint_history")
    REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
    DASHBOARD_FILE = os.path.join(REPORT_DIR, "dashboard.html")

    @classmethod
    def ensure_dirs(cls):
        """确保日志与报告目录存在"""
        os.makedirs(cls.HISTORY_DIR, exist_ok=True)
        os.makedirs(cls.REPORT_DIR, exist_ok=True)

    @classmethod
    def cleanup_old_data(cls, max_hours: float = 24.0):
        """超过一天 (24 小时) 的 Checkpoint 历史文件自动物理删除"""
        cls.ensure_dirs()
        now = time.time()
        cutoff = now - (max_hours * 3600)

        for filepath in glob.glob(os.path.join(cls.HISTORY_DIR, "*.json")):
            try:
                file_mtime = os.path.getmtime(filepath)
                if file_mtime < cutoff:
                    os.remove(filepath)
            except Exception:
                pass

    @classmethod
    def save_checkpoint(cls, station_id: str, station_name: str, status: str, summary_list: list, table_data: dict = None):
        """
        保存单个 Checkpoint 关卡的数据
        station_id: 如 "page_07"
        station_name: 如 "第7站 RPT Compare"
        status: "SUCCESS" | "FAILED" | "WARNING"
        summary_list: 日志摘要文本列表
        table_data: 结构化表格字典对象 (包含单元格与颜色高亮)
        """
        cls.ensure_dirs()
        cls.cleanup_old_data(max_hours=24.0)

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{station_id}.json"
        filepath = os.path.join(cls.HISTORY_DIR, filename)

        data_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp_raw": time.time(),
            "station_id": station_id,
            "station_name": station_name,
            "status": status,
            "summary_list": summary_list,
            "table_data": table_data or {}
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 每次保存后增量重新构建 HTML 仪表盘
        cls.generate_html_dashboard()

    @classmethod
    def generate_html_dashboard(cls):
        """读取 24 小时内的全量 Checkpoint 历史，重新渲染 dashboard.html"""
        cls.ensure_dirs()
        cls.cleanup_old_data(max_hours=24.0)

        files = glob.glob(os.path.join(cls.HISTORY_DIR, "*.json"))
        records = []

        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                    records.append(rec)
            except Exception:
                pass

        # 按时间倒序或正序排列
        records.sort(key=lambda x: x.get("timestamp_raw", 0))

        html_content = cls._build_html_str(records)

        try:
            with open(cls.DASHBOARD_FILE, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            pass

    @classmethod
    def open_dashboard(cls):
        """在默认浏览器中打开 HTML 仪表盘"""
        cls.generate_html_dashboard()
        if os.path.exists(cls.DASHBOARD_FILE):
            webbrowser.open(f"file:///{os.path.abspath(cls.DASHBOARD_FILE)}")

    @classmethod
    def _build_html_str(cls, records: list) -> str:
        """构建高保真真实后台 UI 风格的 HTML 报告"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        stations_html = ""
        for rec in records:
            st_name = rec.get("station_name", "未知关卡")
            st_time = rec.get("timestamp", "")
            st_status = rec.get("status", "SUCCESS")
            summaries = rec.get("summary_list", [])

            status_badge = '<span class="badge bg-success">PASS / 合格</span>'
            if st_status == "FAILED":
                status_badge = '<span class="badge bg-danger">Tier 1 报错阻断</span>'
            elif st_status == "WARNING":
                status_badge = '<span class="badge bg-warning text-dark">Tier 3 通报提醒</span>'

            summary_rows = ""
            for s in summaries:
                row_style = ""
                if "Tier 1" in s or "ERROR" in s:
                    row_style = 'style="background-color: #ffe6e6; color: #cc0000; font-weight: bold;"'
                elif "Tier 3" in s or "Pending" in s:
                    row_style = 'style="background-color: #fff9e6; color: #b38f00; font-weight: bold;"'
                elif "OK" in s or "正常" in s or "ok" in s:
                    row_style = 'style="background-color: #e6ffe6; color: #008000;"'

                summary_rows += f'<tr {row_style}><td style="padding: 6px 12px;">{s}</td></tr>\n'

            stations_html += f"""
            <div class="card mb-4 shadow-sm border-0">
                <div class="card-header d-flex justify-content-between align-items-center" style="background-color: #0C63AF; color: white; font-weight: bold;">
                    <span><i class="bi bi-shield-check me-2"></i>{st_name}</span>
                    <div>
                        <span class="me-3" style="font-size: 0.85rem; opacity: 0.9;">{st_time}</span>
                        {status_badge}
                    </div>
                </div>
                <div class="card-body p-0">
                    <table class="table table-bordered table-sm mb-0">
                        <tbody>
                            {summary_rows if summary_rows else '<tr><td class="text-muted p-3">无详细明细记录</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIW 关卡巡检实时仪表盘 (Google Sheet 视觉对齐版)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{
            background-color: #f4f6f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: #333;
        }}
        .table-bg-ok {{ background-color: #00CC00 !important; color: #ffffff; font-weight: bold; text-align: center; }}
        .table-bg-err {{ background-color: #FF0000 !important; color: #ffffff; font-weight: bold; text-align: center; }}
        .table-bg-warn {{ background-color: #FFCC00 !important; color: #000000; font-weight: bold; text-align: center; }}
        .header-box {{
            background: linear-gradient(135deg, #0C63AF 0%, #1e88e5 100%);
            color: white;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(12, 99, 175, 0.2);
        }}
    </style>
</head>
<body>
    <div class="container my-4">
        <div class="header-box d-flex justify-content-between align-items-center">
            <div>
                <h3 class="mb-1 fw-bold">📊 NIW 关卡巡检实时 HTML 仪表盘</h3>
                <p class="mb-0 text-white-50" style="font-size: 0.9rem;">最近 24 小时历史 Checkpoint 自动数据汇总 (超时 24h 自动物理清理)</p>
            </div>
            <div class="text-end">
                <div class="badge bg-light text-dark mb-1 p-2">最后更新: {now_str}</div>
                <div><button onclick="location.reload();" class="btn btn-sm btn-outline-light">🔄 刷新数据</button></div>
            </div>
        </div>

        <div class="row mb-4">
            <div class="col-md-4">
                <div class="p-3 bg-white rounded shadow-sm border-start border-4 border-primary">
                    <small class="text-muted d-block">活跃 Checkpoint 关卡数</small>
                    <span class="fs-3 fw-bold text-primary">{len(records)}</span>
                </div>
            </div>
            <div class="col-md-4">
                <div class="p-3 bg-white rounded shadow-sm border-start border-4 border-success">
                    <small class="text-muted d-block">数据保存期</small>
                    <span class="fs-3 fw-bold text-success">24 小时自动循环</span>
                </div>
            </div>
            <div class="col-md-4">
                <div class="p-3 bg-white rounded shadow-sm border-start border-4 border-info">
                    <small class="text-muted d-block">视觉还原引擎</small>
                    <span class="fs-3 fw-bold text-info">OK 绿底 / 报错红底 / 提醒黄底</span>
                </div>
            </div>
        </div>

        {stations_html if stations_html else '<div class="alert alert-info text-center p-4">暂无 24 小时内的 Checkpoint 巡检记录。启动关卡巡检后将自动呈现在此！</div>'}

        <footer class="text-center text-muted my-5" style="font-size: 0.85rem;">
            Error Log Bot 巡检系统 &copy; {time.strftime('%Y')} | 自动清理解析引擎
        </footer>
    </div>
</body>
</html>
"""
        return full_html
