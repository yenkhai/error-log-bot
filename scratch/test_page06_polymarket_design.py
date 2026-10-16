"""
验证 RPT PolyMarket 报表新设计测试脚本
"""
import sys
import unittest
from pathlib import Path
import tkinter as tk
import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.checkpoint_store import CheckpointStore
from gui.tab_log_viewer import LogViewerTab, LogDetailWindow

class TestRPTPolyMarketDesign(unittest.TestCase):
    def setUp(self):
        CheckpointStore.clear()

    def test_polymarket_table_structure_and_colors(self):
        """测试根据用户截图设计的 1:1 表格结构与色彩：
        - 移除 NIW 与 Type 列
        - 保留 Reset Log (0 绿底)、Satellite (超链接) 以及 7 个独立日期列 (ok 绿底)
        """
        dates = ["22/09/2026", "23/09/2026", "24/09/2026", "25/09/2026", "26/09/2026", "27/09/2026", "28/09/2026"]
        table_headers = ["Reset Log", "Satellite"] + dates
        self.assertEqual(len(table_headers), 9)
        self.assertNotIn("NIW", table_headers, "表头不能包含 NIW 列")
        self.assertNotIn("Type", table_headers, "表头不能包含 Type 列")
        self.assertNotIn("7-Day Dates Status", table_headers, "不能使用合并后的 7-Day Dates Status")

        # 模拟数据行 (与用户截图 8 个卫星公司 1:1 对齐)
        satellites = ["f0001", "e1002", "e2002", "j0002", "e2003", "p0008", "tq001", "eq001"]
        table_rows = []
        for sat in satellites:
            row = [
                CheckpointStore.make_cell("0", bg="green"),
                CheckpointStore.make_cell(sat, is_link=True),
            ]
            for d in dates:
                row.append(CheckpointStore.make_cell("ok", bg="green"))
            table_rows.append(row)

        self.assertEqual(len(table_rows), 8)
        self.assertEqual(len(table_rows[0]), 9)

        # 验证 Reset Log 为 0 时为绿底
        self.assertEqual(table_rows[0][0]["bg"], "green")
        self.assertEqual(table_rows[0][0]["text"], "0")

        # 验证 Satellite 单元格属性
        self.assertTrue(table_rows[0][1]["is_link"])
        self.assertEqual(table_rows[0][1]["text"], "f0001")

        # 验证每个日期列单元格属性
        for i in range(2, 9):
            self.assertEqual(table_rows[0][i]["text"], "ok")
            self.assertEqual(table_rows[0][i]["bg"], "green")

        # 存入 CheckpointStore
        subtables = [{
            "title": "RPT PolyMarket (RCM)",
            "headers": table_headers,
            "rows": table_rows
        }]
        CheckpointStore.save(
            page_key="niw_06",
            title="RPT PolyMarket",
            status=True,
            headers=table_headers,
            rows=table_rows,
            tables=subtables,
            summary="全部 8 个 Satellite 节点 7 天全部正常"
        )

        data = CheckpointStore.get("niw_06")
        self.assertIsNotNone(data)
        self.assertEqual(data["headers"], table_headers)
        self.assertEqual(len(data["rows"]), 8)
        self.assertEqual(len(data["rows"][0]), 9)

    def test_log_detail_window_rendering(self):
        """测试 LogDetailWindow 能否正确加载并渲染 9 列的 RPT PolyMarket 表格"""
        dates = ["22/09/2026", "23/09/2026", "24/09/2026", "25/09/2026", "26/09/2026", "27/09/2026", "28/09/2026"]
        table_headers = ["Reset Log", "Satellite"] + dates
        satellites = ["f0001", "e1002", "e2002", "j0002", "e2003", "p0008", "tq001", "eq001"]
        table_rows = []
        for sat in satellites:
            row = [
                CheckpointStore.make_cell("0", bg="green"),
                CheckpointStore.make_cell(sat, is_link=True),
            ]
            for d in dates:
                row.append(CheckpointStore.make_cell("ok", bg="green"))
            table_rows.append(row)

        subtables = [{
            "title": "RPT PolyMarket (RCM)",
            "headers": table_headers,
            "rows": table_rows
        }]
        CheckpointStore.save(
            page_key="niw_06",
            title="RPT PolyMarket",
            status=True,
            headers=table_headers,
            rows=table_rows,
            tables=subtables,
            summary="全部 8 个 Satellite 节点 7 天全部正常"
        )

        root = tk.Tk()
        root.withdraw()
        try:
            frame = ctk.CTkFrame(root)
            tab = LogViewerTab(frame, None)
            tab.refresh_list()

            # 打开第 6 站 (niw_06, 索引 5)
            detail_win = LogDetailWindow(tab, station_index=5)
            self.assertEqual(detail_win.station_index, 5)

            # 验证 table_frame 中生成的 Label 控件
            tables = detail_win.table_frame.winfo_children()
            self.assertEqual(len(tables), 1)
            children = tables[0].winfo_children()
            self.assertGreater(len(children), 0, "必须生成表格控件")

            # 1 个子标题 Label + 9 个表头 Label + 8 * 9 = 72 个数据单元格 Label = 82 个
            expected_labels = 1 + 9 + (8 * 9)
            self.assertEqual(len(children), expected_labels)

            # 验证第一个表头是 Reset Log，第二个是 Satellite
            # children[0] 是标题 "▶ RPT PolyMarket (RCM)"
            # children[1] 是 "Reset Log"
            # children[2] 是 "Satellite"
            self.assertIn("Reset Log", children[1].cget("text"))
            self.assertIn("Satellite", children[2].cget("text"))
            self.assertIn("22/09/2026", children[3].cget("text"))

            detail_win.destroy()
        finally:
            root.destroy()

if __name__ == "__main__":
    unittest.main()
