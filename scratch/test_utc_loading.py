import unittest
from unittest.mock import Mock, patch
from selenium.common.exceptions import TimeoutException
from pages.niw.page_09_rpt_compare_utc import RPTCompareUTCChecker


class UTCLoadingTests(unittest.TestCase):
    def test_wait_rejects_blank_loading_and_incomplete_hours(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        complete={'uniqueHours':list(range(24)),'hoursCount':24,'pendingCells':0,'errList':[]}
        c._extract_data=Mock(side_effect=[dict(complete,pendingCells=40),dict(complete,uniqueHours=list(range(23))),complete,complete])
        c.driver.execute_script.return_value=True
        def until(predicate):
            self.assertFalse(predicate(c.driver))
            self.assertFalse(predicate(c.driver))
            self.assertFalse(predicate(c.driver))
            self.assertEqual(predicate(c.driver),complete)
            return complete
        with patch('selenium.webdriver.support.ui.WebDriverWait') as wait, patch('time.monotonic',side_effect=[0,1,2,3,4.1]):
            wait.return_value.until.side_effect=until
            self.assertEqual(c._wait_for_matrix_loaded(),complete)

    def test_timeout_has_specific_loading_message(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        with patch('selenium.webdriver.support.ui.WebDriverWait') as wait:
            wait.return_value.until.side_effect=TimeoutException('loading')
            with self.assertRaisesRegex(RuntimeError,'数据加载超时'):
                c._wait_for_matrix_loaded()

    def test_loading_timeout_never_clicks_checkpoint(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        c.navigate_to_menu=Mock()
        c.click_search_button=Mock(return_value=True)
        c._wait_for_matrix_loaded=Mock(side_effect=RuntimeError('UTC 数据加载超时'))
        c.click_checkpoint=Mock()
        self.assertFalse(c.check())
        c.click_checkpoint.assert_not_called()

    def test_complete_matrix_with_error_blocks_checkpoint(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        c.navigate_to_menu=Mock()
        c.click_search_button=Mock(return_value=True)
        c._wait_for_matrix_loaded=Mock(return_value={'hoursCount':24,'errList':['Hour 12: error'],'rawRows':[]})
        c.click_checkpoint=Mock()
        self.assertFalse(c.check())
        c.click_checkpoint.assert_not_called()

    def test_one_search_retry_after_first_timeout(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        c.navigate_to_menu=Mock()
        c.click_search_button=Mock(return_value=True)
        c._wait_for_matrix_loaded=Mock(side_effect=[RuntimeError('UTC 数据加载超时'),{'hoursCount':24,'errList':[],'rawRows':[]}])
        c.click_checkpoint=Mock(return_value=True)
        self.assertTrue(c.check())
        self.assertEqual(c.click_search_button.call_count,2)
        self.assertEqual(c._wait_for_matrix_loaded.call_count,2)
        for call in c._wait_for_matrix_loaded.call_args_list:
            self.assertEqual(call.kwargs,{'timeout':120})
        c.click_checkpoint.assert_called_once()

    def test_second_timeout_stops_after_exactly_one_search_retry(self):
        c=RPTCompareUTCChecker(Mock(),Mock())
        c.navigate_to_menu=Mock()
        c.click_search_button=Mock(return_value=True)
        c._wait_for_matrix_loaded=Mock(side_effect=RuntimeError('UTC 数据加载超时'))
        c.click_checkpoint=Mock()
        self.assertFalse(c.check())
        self.assertEqual(c.click_search_button.call_count,2)
        self.assertEqual(c._wait_for_matrix_loaded.call_count,2)
        c.click_checkpoint.assert_not_called()


if __name__=='__main__':
    unittest.main()
