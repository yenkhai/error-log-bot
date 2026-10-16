import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from gui.tab_checkpoint import CheckpointTab


class TestCheckpointPause(unittest.TestCase):
    def make_tab(self, mode='FULL'):
        tab = SimpleNamespace(
            stop_requested=False, paused_station=None,
            last_failed_type=None, last_failed_index=0,
            current_pipeline_mode=mode, app=SimpleNamespace(),
            log=Mock(), play_error_sound=Mock(),
            is_noon_fast_mode_active=lambda: False,
            is_running=False, _check_cross_tab_busy=lambda: False,
            _start_pipeline_thread=Mock(),
        )
        return tab

    def run_section(self, tab, section, checkers, selected=None):
        return CheckpointTab._execute_station_loop(
            tab, section, [(str(i), c) for i, c in enumerate(checkers)],
            ['test'] * len(checkers),
            [SimpleNamespace(get=lambda v=v: v) for v in (selected or [True] * len(checkers))], 0,
        )

    def test_stop_finishes_current_then_records_next_selected(self):
        tab = self.make_tab()
        def stop():
            tab.stop_requested = True
            return True
        first = SimpleNamespace(check=Mock(side_effect=stop))
        skipped = SimpleNamespace(check=Mock())
        next_page = SimpleNamespace(check=Mock())
        self.assertTrue(self.run_section(tab, 'NIW', [first, skipped, next_page], [True, False, True]))
        self.assertEqual(tab.paused_station, ('NIW', 2))
        skipped.check.assert_not_called()
        next_page.check.assert_not_called()

    def test_stop_at_section_boundary_pauses_copier(self):
        tab = self.make_tab()
        tab.stop_requested = True
        self.assertFalse(self.run_section(tab, 'NIW', []))
        checker = SimpleNamespace(check=Mock())
        self.assertTrue(self.run_section(tab, 'Copier', [checker]))
        self.assertEqual(tab.paused_station, ('Copier', 0))
        checker.check.assert_not_called()

    def test_failure_remains_retryable_when_stop_requested(self):
        tab = self.make_tab()
        def fail():
            tab.stop_requested = True
            return False
        self.assertTrue(self.run_section(tab, 'NIW', [SimpleNamespace(check=fail)]))
        self.assertEqual(tab.last_failed_type, 'NIW')
        self.assertIsNone(tab.paused_station)

    def test_last_station_finishes_without_extra_resume(self):
        tab = self.make_tab()
        def stop():
            tab.stop_requested = True
            return True
        self.assertFalse(self.run_section(tab, 'Copier', [SimpleNamespace(check=stop)]))
        self.assertIsNone(tab.paused_station)

    def test_resume_preserves_mode_and_position(self):
        for mode, section, index in [('FULL', 'Copier', 0), ('NIW', 'NIW', 4), ('COPIER', 'Copier', 3)]:
            with self.subTest(mode=mode):
                tab = self.make_tab(mode)
                tab.paused_station = (section, index)
                CheckpointTab.start_resume_thread(tab)
                tab._start_pipeline_thread.assert_called_once_with(
                    mode=mode, niw_start=index if section == 'NIW' else 15,
                    copier_start=index if section == 'Copier' else 0,
                    full=mode == 'FULL', banner_text='Checkpoint Resumed',
                )


if __name__ == '__main__':
    unittest.main()
