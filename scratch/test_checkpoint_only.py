import unittest
from unittest.mock import Mock, patch
from services.checkpoint_engine import CheckpointEngine
from core.checkpoint_store import CheckpointStore


class CheckpointOnlyTests(unittest.TestCase):
    def test_selected_station_does_not_check(self):
        e = CheckpointEngine()
        e.log = Mock()
        c = Mock()
        c.click_checkpoint.return_value = True
        with patch.object(CheckpointStore, "save") as save:
            self.assertTrue(e._checkpoint_only_station(c, "niw_15", "Wallet", "NIW"))
            self.assertTrue(save.call_args.kwargs["has_warn"])
        c.check.assert_not_called()
        c.navigate_to_menu.assert_called_once_with("1 Wallet Pending", menu_id="apy_b0i17text", section="NIW")
        c.click_checkpoint.assert_called_once()

    def test_failed_submission_does_not_pass(self):
        e = CheckpointEngine()
        e.log = Mock()
        c = Mock()
        c.click_checkpoint.return_value = False
        c.handle_exception.return_value = False
        with patch.object(CheckpointStore, "save") as save:
            self.assertFalse(e._checkpoint_only_station(c, "niw_01", "Pending", "NIW"))
            save.assert_not_called()

    def test_robot_monitor_has_no_checkpoint(self):
        e = CheckpointEngine()
        e.log = Mock()
        c = Mock()
        with patch.object(CheckpointStore, "save"):
            self.assertTrue(e._checkpoint_only_station(c, "copier_07", "Robot", "Copier"))
        c.check.assert_not_called()
        c.click_checkpoint.assert_not_called()


class AdditionalReviewTests(unittest.TestCase):
    def test_bypass_messages_are_visible(self):
        from core.compact_log import compact_message
        for message in ("[BYPASS] 未检查", "[SETTINGS] 已保存"):
            self.assertEqual(compact_message(message), message)

    def test_readonly_robot_skip_advances_without_checkpoint(self):
        e = CheckpointEngine()
        e.log = Mock()
        e.app = Mock()
        e.reset_buttons = Mock()
        e.last_failed_type, e.last_failed_index = "Copier", 6
        e.current_pipeline_mode = "FULL"
        e.run_full_pipeline = Mock()
        with patch("services.checkpoint_engine.BrowserManager.get_driver"), patch("services.checkpoint_engine.BaseChecker") as checker, patch.object(CheckpointStore, "get", return_value=None), patch.object(CheckpointStore, "save"):
            e.run_skip_and_checkpoint_pipeline()
            checker.return_value.click_checkpoint.assert_not_called()
            e.run_full_pipeline.assert_called_once_with(niw_start=15, copier_start=7, full=False)
