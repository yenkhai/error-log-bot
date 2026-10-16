import unittest
from unittest.mock import Mock
from pages.niw.page_02_ccl_recover import CCLRecoverChecker
from pages.niw.page_11_check_ccl import CheckCCLChecker
from pages.niw.page_12_wsum_sport import WsumSportChecker
from pages.niw.page_14_hg_percentages import HGPercentagesChecker

class EmptyDataTests(unittest.TestCase):
    def test_empty_pages_never_submit_checkpoint(self):
        for cls in (CCLRecoverChecker, CheckCCLChecker, WsumSportChecker, HGPercentagesChecker):
            with self.subTest(checker=cls.__name__):
                c=cls.__new__(cls)
                c.driver=Mock()
                c.driver.execute_script.return_value={}
                for name in ('log_station_header','navigate_to_menu','wait_for_page_loaded','click_search_button','log','log_search_action'):
                    setattr(c,name,Mock())
                c.click_checkpoint=Mock(return_value=True)
                c.handle_exception=Mock(return_value=False)
                self.assertFalse(c.check())
                c.click_checkpoint.assert_not_called()
