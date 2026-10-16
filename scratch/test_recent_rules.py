"""Regression coverage for incomplete Copier reads and recent color rules."""
import unittest
from unittest.mock import Mock, patch
from core.checkpoint_store import CheckpointStore
from pages.copier_server.page_01_copier import CopierChecker
from pages.copier_server.page_04_check_ap_space import space_rows
from pages.copier_server.page_05_error_log import record_tier
from pages.copier_server.page_06_redis_server import redis_display_tables
from pages.copier_server.page_08_niw_robot_monitor import NIWRobotMonitorChecker


class RecentRulesTests(unittest.TestCase):
    def checker(self, cls):
        c = cls.__new__(cls)
        c.driver = Mock()
        for name in ("log_station_header", "navigate_to_menu", "wait_for_page_loaded", "log_data_extracted",
                     "log_check_method", "log_data_summary", "log_check_result", "log", "switch_to_main_frame"):
            setattr(c, name, Mock())
        c.click_checkpoint = Mock(return_value=True)
        c.handle_exception = Mock(return_value=False)
        return c

    def test_copier_no_company_frames_does_not_submit(self):
        c = self.checker(CopierChecker)
        c.driver.find_elements.return_value = []
        self.assertFalse(c.check())
        c.click_checkpoint.assert_not_called()

    def test_copier_failed_company_read_blocks(self):
        c = self.checker(CopierChecker)
        frame = Mock()
        frame.get_attribute.return_value = "f_D0005"
        frame.rect = {"x": 0, "y": 0}
        c.driver.find_elements.return_value = [frame]
        c.driver.switch_to.frame.side_effect = RuntimeError("unavailable")
        with patch("pages.copier_server.page_01_copier.time.sleep"), patch.object(CheckpointStore, "save") as save:
            self.assertFalse(c.check())
            self.assertFalse(save.call_args.kwargs["status"])
        c.click_checkpoint.assert_not_called()

    def test_niw_robot_checks_after_first_200_rows(self):
        c = self.checker(NIWRobotMonitorChecker)
        c.driver.execute_script.return_value = [
            {"values": [str(i), "robot", "30", "timestamp"], "green": i != 265, "group": "RCM"}
            for i in range(266)]
        with patch.object(CheckpointStore, "save") as save:
            self.assertFalse(c.check())
            self.assertEqual(len(save.call_args.kwargs["tables"][0]["rows"]), 266)
            self.assertEqual(save.call_args.kwargs["tables"][0]["rows"][-1][-1]["bg"], "red")
        c.click_checkpoint.assert_not_called()

    def test_disk_missing_and_connection_die(self):
        for extra in ({"connectionDie": True}, {"size": ""}):
            server = {"ip": "10.0.0.1", "size": "30G", "used": "1G", "avail": "29G",
                      "use": {"text": "5%"}, **extra}
            rows, errors = space_rows([server])
            self.assertTrue(errors)
            self.assertEqual(rows[0][-1]["bg"], "red")

    def test_error_log_thresholds(self):
        self.assertEqual([record_tier(n) for n in (5000, 5001, 8000, 8001)],
                         ["OK", "TIER3", "TIER3", "TIER1"])

    def test_redis_only_total_color_matters(self):
        tables, errors = redis_display_tables([{"headers": ["Server", "Remark", "Total"],
            "rows": [[{"text": "host", "bg": "red"}, "remark", {"text": "3 Records", "bg": "white"}]]}])
        self.assertFalse(errors)
        self.assertEqual(tables[0]["rows"][0][2]["bg"], "green")


if __name__ == "__main__":
    unittest.main()
