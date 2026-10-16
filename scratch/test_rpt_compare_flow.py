import unittest
from unittest.mock import Mock, patch
from selenium.common.exceptions import TimeoutException
from pages.niw.page_07_rpt_compare import RPTCompareChecker
from core.checkpoint_store import CheckpointStore


def data(*companies):
    return {'matrixWagerCalList':[{'sat':c} for c in companies], 'matrixSatellitesCount':3,
            'rptCompleteInfo':'Complete','mainTableRows':[]}


class RPTCompareFlowTests(unittest.TestCase):
    def checker(self, snapshots):
        c=RPTCompareChecker(Mock(), Mock())
        c.navigate_to_menu=Mock()
        c._wait_for_matrix_loaded=Mock()
        c._extract_page7_data=Mock(side_effect=snapshots)
        c._click_satellite_company=Mock(return_value=True)
        c.click_checkpoint=Mock(return_value=True)
        return c

    def test_one_search_then_company_reload_serially(self):
        c=self.checker([data('f0001','e1002'),data('e1002'),data()])
        events=[]
        c._wait_for_matrix_loaded.side_effect=lambda: events.append('wait')
        c._extract_page7_data.side_effect=lambda: (events.append('read') or [data('f0001','e1002'),data('e1002'),data()][events.count('read')-1])
        c._click_satellite_company.side_effect=lambda sat: (events.append(sat) or True)
        self.assertTrue(c.check())
        # f0001 was cleared by the first refresh, so it must not be clicked.
        self.assertEqual(events,['wait','read','e1002','wait','read','e1002','wait','read'])
        self.assertEqual(c.driver.execute_script.call_count,1)
        self.assertIn('search_data()',c.driver.execute_script.call_args.args[0])

    def test_two_companies_each_wait_before_next(self):
        c=self.checker([data('e1002','f0001'),data('f0001'),data()])
        self.assertTrue(c.check())
        self.assertEqual([call.args[0] for call in c._click_satellite_company.call_args_list],['e1002','f0001'])
        self.assertEqual(c._wait_for_matrix_loaded.call_count,3)
        self.assertEqual(c.driver.execute_script.call_count,1)

    def test_persistent_wager_cal_only_two_clicks_and_warning(self):
        c=self.checker([data('f0001')]*3)
        self.assertTrue(c.check())
        self.assertEqual(c._click_satellite_company.call_count,2)
        self.assertTrue(CheckpointStore.get('niw_07')['has_warn'])
        self.assertEqual(c.driver.execute_script.call_count,1)

    def test_missing_company_link_blocks_without_search_fallback(self):
        c=self.checker([data('f0001')])
        c._click_satellite_company.return_value=False
        self.assertFalse(c.check())
        c.click_checkpoint.assert_not_called()
        self.assertEqual(c.driver.execute_script.call_count,1)

    def test_incomplete_initial_load_does_not_click_company_or_checkpoint(self):
        c=self.checker([])
        c._wait_for_matrix_loaded.side_effect=TimeoutException('white empty cells remain')
        self.assertFalse(c.check())
        c._extract_page7_data.assert_not_called()
        c._click_satellite_company.assert_not_called()
        c.click_checkpoint.assert_not_called()

    def test_wait_requires_filled_stable_rows(self):
        c=RPTCompareChecker(Mock())
        c._matrix_load_state=Mock(side_effect=[
            {'rows':3,'pending':8,'idle':True,'signature':'partial'},
            {'rows':3,'pending':0,'idle':False,'signature':'loaded'},
            {'rows':3,'pending':0,'idle':True,'signature':'loaded'},
            {'rows':3,'pending':0,'idle':True,'signature':'loaded'},
        ])
        def until(predicate, **kwargs):
            results=[predicate(None) for _ in range(4)]
            self.assertEqual(results,[False,False,False,True])
        with patch('selenium.webdriver.support.ui.WebDriverWait') as wait, patch('pages.niw.page_07_rpt_compare.time.monotonic',side_effect=[1,2.1]):
            wait.return_value.until.side_effect=until
            c._wait_for_matrix_loaded()

    def test_noon_mode_allows_red_rpt_without_score_only_probe(self):
        state=data()
        state['rptCompleteHasErr']=True
        c=self.checker([state])
        self.assertTrue(c.check(is_noon_fast=True))
        c.click_checkpoint.assert_called_once()
        c.navigate_to_menu.assert_called_once_with('RPT Compare',menu_id='apy_b0i8text',section='NIW')
        self.assertTrue(CheckpointStore.get('niw_07')['has_warn'])

    def test_ended_noon_mode_blocks_red_rpt(self):
        state=data()
        state['rptCompleteHasErr']=True
        c=self.checker([state])
        self.assertFalse(c.check(is_noon_fast=False))
        c.click_checkpoint.assert_not_called()

    def test_matrix_error_still_blocks_in_noon_mode(self):
        state=data()
        state['matrixErrList']=['f0001 RED ERROR']
        c=self.checker([state])
        self.assertFalse(c.check(is_noon_fast=True))
        c.click_checkpoint.assert_not_called()


if __name__=='__main__':
    unittest.main()
