"""
测试关卡警告 (has_warn) 黄色状态逻辑测试脚本
"""
import sys
import unittest
from pathlib import Path

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.checkpoint_store import CheckpointStore
import tkinter as tk
import customtkinter as ctk
from gui.tab_log_viewer import LogViewerTab, STATION_LIST

class TestWarningDisplay(unittest.TestCase):
    def setUp(self):
        CheckpointStore.clear()

    def test_detect_has_warn_errors_precedence(self):
        """当 status 为 False 时，即使有警告词或黄色，也必须判定为 Error (has_warn=False)"""
        has_warn = CheckpointStore._detect_has_warn(
            status=False,
            summary="存在 Tier 3 提示与 Tier 1 异常",
            rows=[[{"text": "err", "bg": "yellow"}]]
        )
        self.assertFalse(has_warn, "status=False 时 has_warn 应为 False")

    def test_detect_has_warn_clean_pass(self):
        """纯净通过，无警告"""
        has_warn = CheckpointStore._detect_has_warn(
            status=True,
            summary="全部 0 积压，正常通关",
            rows=[[{"text": "0", "bg": "green"}]]
        )
        self.assertFalse(has_warn, "纯净通过时不应有 has_warn")

    def test_detect_has_warn_zero_tier3(self):
        """带有 0 项 Tier 3 提示字样不应误判为警告"""
        has_warn = CheckpointStore._detect_has_warn(
            status=True,
            summary="全部正常 (0 项 Tier 3 提示)",
            rows=[[{"text": "0", "bg": "green"}]]
        )
        self.assertFalse(has_warn, "0 项 Tier 3 提示不应判定为警告")

    def test_detect_has_warn_positive_tier3_summary(self):
        """Station 03 典型场景：有 1 项 Tier 3 提示，status=True"""
        has_warn = CheckpointStore._detect_has_warn(
            status=True,
            summary="全部 Tier 1 阻断项 0 积压正常 (含 1 项 Tier 3 提示)"
        )
        self.assertTrue(has_warn, "含 1 项 Tier 3 提示应判定为 has_warn=True")

    def test_detect_has_warn_yellow_cell_in_rows(self):
        """单表模式下存在 yellow 背景单元格"""
        has_warn = CheckpointStore._detect_has_warn(
            status=True,
            summary="磁盘空间正常",
            rows=[[{"text": "10.0.0.1", "bg": "white"}, {"text": "85%", "bg": "yellow"}]]
        )
        self.assertTrue(has_warn, "rows 中有 yellow 单元格应判定为 has_warn=True")

    def test_detect_has_warn_yellow_cell_in_tables(self):
        """多表模式下子表格存在 yellow 单元格 (如 Station 03 Poly Table 或 NoMap)"""
        tables = [
            {
                "title": "Uncomplete Poly Market",
                "headers": ["Company", "Wager", "Event", "Status"],
                "rows": [
                    [{"text": "s0001", "bg": "white"}, {"text": "1", "bg": "yellow"}, {"text": "0", "bg": "yellow"}, {"text": "Warning", "bg": "yellow"}]
                ]
            }
        ]
        has_warn = CheckpointStore._detect_has_warn(
            status=True,
            summary="全部正常",
            tables=tables
        )
        self.assertTrue(has_warn, "tables 中有 yellow 单元格应判定为 has_warn=True")

    def test_save_and_get_all_summary(self):
        """验证 CheckpointStore.save() 与 get_all_summary() 返回 has_warn"""
        # 1. 纯净通过
        CheckpointStore.save(
            page_key="niw_01",
            title="Pending Wager",
            status=True,
            summary="全部 0 积压正常"
        )
        # 2. 警告通过 (Station 03 模拟)
        CheckpointStore.save(
            page_key="niw_03",
            title="Matches & Wagers",
            status=True,
            summary="全部 Tier 1 阻断项 0 积压正常 (含 2 项 Tier 3 提示)"
        )
        # 3. 错误
        CheckpointStore.save(
            page_key="niw_02",
            title="CCL Recover",
            status=False,
            summary="发现 1 项红色异常"
        )

        all_summary = CheckpointStore.get_all_summary()

        self.assertIn("niw_01", all_summary)
        self.assertTrue(all_summary["niw_01"]["status"])
        self.assertFalse(all_summary["niw_01"]["has_warn"])

        self.assertIn("niw_03", all_summary)
        self.assertTrue(all_summary["niw_03"]["status"])
        self.assertTrue(all_summary["niw_03"]["has_warn"])

        self.assertIn("niw_02", all_summary)
        self.assertFalse(all_summary["niw_02"]["status"])
        self.assertFalse(all_summary["niw_02"]["has_warn"])

    def test_explicit_has_warn_override(self):
        """显式传入 has_warn 参数时的行为验证"""
        CheckpointStore.save(
            page_key="custom_01",
            title="Custom Page",
            status=True,
            summary="Normal",
            has_warn=True
        )
        data = CheckpointStore.get("custom_01")
        self.assertTrue(data["has_warn"])

        CheckpointStore.save(
            page_key="custom_02",
            title="Custom Page 2",
            status=True,
            summary="Normal",
            has_warn=False
        )
        data2 = CheckpointStore.get("custom_02")
        self.assertFalse(data2["has_warn"])

    def test_tab_log_viewer_rendering(self):
        """验证 LogViewerTab 的 Treeview 列表渲染：
        1. 警告关卡 (has_warn=True, status=True) 呈现 ⚠️ Warning 与明黄文字 (#f1fa8c)
        2. 正常关卡 (has_warn=False, status=True) 呈现 ✅ Passed 与翠绿文字 (#50fa7b)
        3. 错误关卡 (status=False) 呈现 ❌ Error 与亮红文字 (#ff6b6b)
        4. 未跑关卡 呈现 📭 Not Run 与暗灰文字 (#555e70)
        """
        root = tk.Tk()
        root.withdraw()
        try:
            # 准备数据
            CheckpointStore.save("niw_01", "Pending Wager", True, summary="All OK") # Passed
            CheckpointStore.save("niw_02", "CCL Recover", False, summary="Fail")    # Error
            CheckpointStore.save("niw_03", "Matches Wagers", True, summary="全部 Tier 1 阻断项 0 积压正常 (含 1 项 Tier 3 提示)") # Warning

            frame = ctk.CTkFrame(root)
            tab = LogViewerTab(frame, None)
            tab.refresh_list()

            items = tab.tree.get_children()
            self.assertEqual(len(items), 24, "必须展示全部 24 个关卡")

            # 检查 niw_01 (Passed)
            item_niw01 = items[0]
            val_01 = tab.tree.item(item_niw01, "values")
            tags_01 = tab.tree.item(item_niw01, "tags")
            self.assertEqual(val_01[1], "✅ Passed")
            self.assertIn("status_pass", tags_01)
            cfg_01 = tab.tree.tag_configure("tag_niw_01")
            self.assertEqual(cfg_01.get("foreground"), "#50fa7b")

            # 检查 niw_02 (Error)
            item_niw02 = items[1]
            val_02 = tab.tree.item(item_niw02, "values")
            tags_02 = tab.tree.item(item_niw02, "tags")
            self.assertEqual(val_02[1], "❌ Error")
            self.assertIn("status_error", tags_02)
            cfg_02 = tab.tree.tag_configure("tag_niw_02")
            self.assertEqual(cfg_02.get("foreground"), "#ff6b6b")

            # 检查 niw_03 (Warning - 黄色)
            item_niw03 = items[2]
            val_03 = tab.tree.item(item_niw03, "values")
            tags_03 = tab.tree.item(item_niw03, "tags")
            self.assertEqual(val_03[1], "⚠️ Warning", "有warn但无error必须显示 ⚠️ Warning")
            self.assertIn("status_warn", tags_03)
            cfg_03 = tab.tree.tag_configure("tag_niw_03")
            self.assertEqual(cfg_03.get("foreground"), "#f1fa8c", "有warn但无error必须配置明黄色前景色 #f1fa8c")

            # 检查 niw_04 (Not Run)
            item_niw04 = items[3]
            val_04 = tab.tree.item(item_niw04, "values")
            tags_04 = tab.tree.item(item_niw04, "tags")
            self.assertEqual(val_04[1], "📭 Not Run")
            self.assertIn("status_not_run", tags_04)
            cfg_04 = tab.tree.tag_configure("tag_niw_04")
            self.assertEqual(cfg_04.get("foreground"), "#555e70")

            # 验证行选中配色映射
            self.assertIn("status_warn", tab._SELECT_COLORS)
            self.assertEqual(tab._SELECT_COLORS["status_warn"], ("#4d3d14", "#f1fa8c"))

        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
