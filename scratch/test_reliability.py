import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import datetime

import config
from core.base_checker import BaseChecker
from core.browser import BrowserManager
from core.checkpoint_store import CheckpointStore
from core.stations import STATIONS
from gui.app import UnifiedBotApp
from gui.tab_checkpoint import CheckpointTab
from gui.tab_error_log import ErrorLogTab
from services.error_log_scraper import ErrorLogScraperService
from services.checkpoint_engine import CheckpointEngine


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = ErrorLogScraperService(login_url='https://example.test:8443/ubah/index.php')
        self.service.output_file = Path(self.tmp.name) / 'export.txt'
        self.service.logger = None

    def test_year_and_port_preserved(self):
        with patch('services.error_log_scraper.datetime') as clock:
            clock.now.return_value = datetime(2026, 1, 1)
            service = ErrorLogScraperService(login_url='https://example.test:8443/index')
        self.assertEqual(service.output_file.name, 'error log 2025-12-31.txt')
        url = service._url('/popup', serverap='1.2.3')
        self.assertTrue(url.startswith('https://'))
        self.assertIn('example.test:8443/popup?serverap=1.2.3', url)

    def test_progress_requires_complete_valid_block(self):
        s = self.service
        s.output_file.write_text('No\tError Message ( 10.1.1.1 )\npartial\n', encoding='utf-8')
        s._append_completed_block('10.2.2.2', 'complete\n')
        with s.output_file.open('a', encoding='utf-8') as f:
            f.write('BEGIN Server 10.3.3.3 EXPORTED\npartial\n')
        s.load_progress()
        self.assertEqual(s.processed_ips, {'10.2.2.2'})
        s._append_completed_block('10.3.3.3', 'retry complete\n')
        s.load_progress()
        self.assertIn('10.3.3.3', s.processed_ips)

    def test_corruption_does_not_restore_progress(self):
        s=self.service
        s._append_completed_block('10.1.1.1', 'complete\n')
        s.output_file.write_text(s.output_file.read_text().replace('complete','corrupt'), encoding='utf-8')
        s.load_progress()
        self.assertFalse(s.processed_ips)

    def prepare_run(self):
        s = self.service
        s.login_and_navigate = Mock()
        s.scan_tasks = Mock(return_value=[{'ip':'10.1.1.1', 'count':2}])
        s.log = Mock()
        return s

    def test_export_failure_is_retryable(self):
        s=self.prepare_run()
        s.process_single_ip=Mock(side_effect=OSError('disk full'))
        self.assertFalse(s.run('user','pass'))
        self.assertNotIn('10.1.1.1', s.processed_ips)
        s.process_single_ip=Mock()
        self.assertTrue(s.run('user','pass'))
        self.assertFalse(s.failed_ips)

    def test_reconnect_failure_not_success(self):
        from selenium.common.exceptions import WebDriverException
        s=self.prepare_run()
        s.login_and_navigate.side_effect=[None,RuntimeError('offline')]
        s.process_single_ip=Mock(side_effect=WebDriverException('offline'))
        self.assertFalse(s.run('user','pass'))
        self.assertFalse(s.processed_ips)

    def test_skips_are_reported_as_partial(self):
        s=self.prepare_run()
        s.max_record_limit=1
        self.assertFalse(s.run('user','pass'))
        self.assertIn('10.1.1.1', s.skipped_ips)
        s.processed_ips.clear()
        s.skipped_ips.clear()
        s.load_progress()
        self.assertIn('10.1.1.1', s.skipped_ips)

    def test_save_failure_does_not_show_saved(self):
        tab=SimpleNamespace(entry_url=SimpleNamespace(get=lambda:'https://example.test'), config_data={'LOGIN_URL':'old'},lbl_login_status=Mock())
        with patch('gui.app.save_config', return_value=False):
            UnifiedBotApp.save_domain_url(tab)
        self.assertEqual(tab.config_data['LOGIN_URL'],'old')
        tab.lbl_login_status.configure.assert_called_once()

    def test_atomic_save_failure_preserves_existing(self):
        path=Path(self.tmp.name)/'config.json'
        path.write_text('{"old":true}')
        with patch.object(config,'CONFIG_FILE',path), patch('config.os.replace',side_effect=OSError('denied')):
            self.assertFalse(config.save_config({'new':True}))
        self.assertEqual(path.read_text(),'{"old":true}')

    def test_frozen_data_path_is_persistent(self):
        from core.paths import data_dir
        with patch('sys.frozen',True,create=True), patch.dict('os.environ',{'LOCALAPPDATA':self.tmp.name}):
            self.assertEqual(data_dir(),Path(self.tmp.name)/'ErrorLogBot')

    def test_login_blocks_both_task_launchers(self):
        tab=SimpleNamespace(app=SimpleNamespace(is_logging_in=True),log=Mock())
        self.assertTrue(CheckpointTab._check_cross_tab_busy(tab))
        self.assertTrue(ErrorLogTab._check_cross_tab_busy(tab))

    def test_failed_checkpoint_does_not_report_success(self):
        checker=BaseChecker(Mock())
        checker.click_checkpoint=Mock(return_value=False)
        self.assertFalse(checker.finish_success('test','Test','normal'))
        self.assertFalse(CheckpointStore.get('test')['status'])

    def test_fast_mode_does_not_hide_checkpoint_failure(self):
        tab=SimpleNamespace(log=Mock())
        checker=Mock()
        checker.click_checkpoint.return_value=False
        checker.handle_exception.return_value=False
        self.assertFalse(CheckpointEngine._fast_checkpoint_station(tab,checker,'niw_05','Test'))

    def test_login_form_failure_propagates(self):
        driver=Mock()
        driver.find_elements.return_value=[]
        with patch.object(BrowserManager,'wait_for_login',side_effect=RuntimeError('login rejected')):
            with self.assertRaises(RuntimeError):
                BrowserManager.auto_fill_login(driver,'user','pass')

    def test_station_registry_unique_and_complete(self):
        self.assertEqual(len(STATIONS),24)
        self.assertEqual(len({key for key,_,_ in STATIONS}),24)
        self.assertEqual([k for k,_,_ in STATIONS if k.startswith('niw_')],[f'niw_{i:02}' for i in range(1,16)])

    def test_missing_checkpoint_button_returns_false(self):
        from selenium.common.exceptions import TimeoutException
        checker=BaseChecker(Mock())
        with patch('core.base_checker.WebDriverWait') as wait:
            wait.return_value.until.side_effect=TimeoutException('missing')
            self.assertFalse(checker.click_checkpoint())

    def test_shutdown_waits_for_active_tasks(self):
        app=SimpleNamespace(is_any_task_running=True,after=Mock(),_wait_for_shutdown=Mock(),destroy=Mock())
        UnifiedBotApp._wait_for_shutdown(app)
        app.after.assert_called_once_with(100,app._wait_for_shutdown)
        app.destroy.assert_not_called()

    def test_browser_start_failure_preserves_resume_position(self):
        tab=SimpleNamespace(run_settings={'credentials':('user','pass'),'url':'https://example.test'},
            last_failed_type=None,paused_station=None,log=Mock(),play_error_sound=Mock(),
            app=SimpleNamespace(post_ui=Mock()),reset_buttons=Mock())
        with patch('services.checkpoint_engine.BrowserManager.get_driver',side_effect=RuntimeError('offline')):
            CheckpointEngine.run_full_pipeline(tab,niw_start=4)
        self.assertEqual(tab.paused_station,('NIW',4))
        tab.app.post_ui.assert_called_once_with(tab.reset_buttons)

    def test_done_panel_allows_progress_without_clicking_again(self):
        checker=BaseChecker(Mock(),Mock())
        checker._checkpoint_done=Mock(return_value=True)
        with patch('core.base_checker.WebDriverWait') as wait:
            wait.return_value.until.side_effect=lambda predicate: predicate(checker.driver)
            self.assertTrue(checker.click_checkpoint())
        checker.driver.find_elements.assert_not_called()
        self.assertEqual(checker.driver.execute_script.call_count,1) # reveal only, no second submission

    def test_done_after_submission_is_accepted(self):
        checker=BaseChecker(Mock(),Mock())
        button=Mock()
        button.get_attribute.return_value='button'
        checker.driver.find_elements.return_value=[button]
        checker._checkpoint_done=Mock(side_effect=[False,True])
        with patch('core.base_checker.WebDriverWait') as wait:
            wait.return_value.until.side_effect=lambda predicate: predicate(checker.driver)
            self.assertTrue(checker.click_checkpoint())
        self.assertEqual(checker._checkpoint_done.call_count,2)

    def test_done_arriving_at_timeout_is_accepted(self):
        from selenium.common.exceptions import TimeoutException
        checker=BaseChecker(Mock(),Mock())
        checker._checkpoint_done=Mock(return_value=True)
        with patch('core.base_checker.WebDriverWait') as wait:
            wait.return_value.until.side_effect=TimeoutException('late acknowledgement')
            self.assertTrue(checker.click_checkpoint())


if __name__ == '__main__':
    unittest.main()
