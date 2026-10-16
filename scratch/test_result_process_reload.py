import unittest
from unittest.mock import Mock, patch
from selenium.common.exceptions import TimeoutException
from pages.niw.page_04_result_process import ResultProcessChecker
from core.checkpoint_store import CheckpointStore
from core.compact_log import compact_message


def snapshot(error=False):
    row={'section':'Syn Event','satellite':'d0008','d1':'error' if error else 'success','d2':'success','d1_error':error,'d2_error':False,'status':'ERROR' if error else 'OK','is_error':error}
    return {'dates':['14/10/2026','15/10/2026'],'rawRows':[row],'synEventRows':[row], 'errorCount':int(error)}


class ResultProcessReloadTests(unittest.TestCase):
    def checker(self, states):
        c=ResultProcessChecker(Mock(),Mock())
        c.navigate_to_menu=Mock()
        c._wait_for_all_data=Mock(side_effect=states)
        c._click_company=Mock(return_value=True)
        c.click_checkpoint=Mock(return_value=True)
        return c

    def test_first_complete_pass_has_no_reload(self):
        c=self.checker([snapshot()])
        self.assertTrue(c.check())
        c._click_company.assert_not_called()

    def test_error_reloads_company_and_waits_before_final_result(self):
        c=self.checker([snapshot(True),snapshot()])
        self.assertTrue(c.check())
        c._click_company.assert_called_once_with('Syn Event','d0008')
        self.assertEqual(c._wait_for_all_data.call_count,2)
        c.driver.execute_script.assert_not_called() # no Search fallback

    def test_still_error_after_two_clicks_blocks(self):
        c=self.checker([snapshot(True)]*3)
        self.assertFalse(c.check())
        self.assertEqual(c._click_company.call_count,2)
        c.click_checkpoint.assert_not_called()
        row=CheckpointStore.get('niw_04')['tables'][0]['rows'][0]
        self.assertEqual(row[1]['bg'],'red')
        self.assertEqual(row[2]['bg'],'green')

    def test_loading_timeout_never_passes_or_reloads(self):
        c=self.checker([])
        c._wait_for_all_data.side_effect=TimeoutException('still loading')
        self.assertFalse(c.check())
        c._click_company.assert_not_called()
        c.click_checkpoint.assert_not_called()

    def test_missing_company_link_keeps_error(self):
        c=self.checker([snapshot(True)])
        c._click_company.return_value=False
        self.assertFalse(c.check())
        c._click_company.assert_called_once()
        c.click_checkpoint.assert_not_called()

    def test_summary_hidden_but_reload_visible(self):
        self.assertIsNone(compact_message('[SUMMARY] totals'))
        self.assertIsNotNone(compact_message('[RELOAD] Syn Event / d0008 重载 (1/2)'))

    def test_wait_does_not_accept_partial_sections(self):
        c=ResultProcessChecker(Mock())
        c.driver.execute_script.return_value=True
        complete=snapshot()
        for key in ('eventScoreRows','resultActionRows','promotionActionRows','missingRows'):
            complete[key]=[dict(complete['rawRows'][0])]
        c._extract_data=Mock(side_effect=[snapshot(True),complete,complete])
        def until(predicate, **kwargs):
            self.assertFalse(predicate(c.driver))
            self.assertFalse(predicate(c.driver))
            self.assertIs(predicate(c.driver),complete)
        with patch('selenium.webdriver.support.ui.WebDriverWait') as wait, patch('time.monotonic',side_effect=[1,2.1]):
            wait.return_value.until.side_effect=until
            c._wait_for_all_data()


if __name__=='__main__':
    unittest.main()
