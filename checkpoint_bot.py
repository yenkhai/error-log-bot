import sys
import os

# 强制 UTF-8 编码，防止 Windows 控制台 Encoding 崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

from gui.app import UnifiedBotApp
from core.browser import BrowserManager
from pages.niw.page_01_pending_wager import PendingWagerChecker
from pages.niw.page_02_ccl_recover import CCLRecoverChecker
from pages.niw.page_03_matches_wagers import MatchesWagersChecker
from pages.niw.page_04_result_process import ResultProcessChecker
from pages.niw.page_05_calculate_betslips import CalculateBetslipsChecker
from pages.niw.page_06_rpt_polymarket import RPTPolyMarketChecker
from pages.niw.page_07_rpt_compare import RPTCompareChecker
from pages.niw.page_08_rpt_ai import RPTAIChecker
from pages.niw.page_09_rpt_compare_utc import RPTCompareUTCChecker
from pages.niw.page_10_forecast import ForecastChecker
from pages.niw.page_11_check_ccl import CheckCCLChecker
from pages.niw.page_12_wsum_sport import WsumSportChecker
from pages.niw.page_13_hg_percentages import HGPercentagesChecker
from pages.niw.page_14_rpt_crs import RPTCRSChecker
from pages.niw.page_15_one_wallet_pending import OneWalletPendingChecker

class CheckPointRunner:
    """模块化引擎桥接兼容类"""
    def __init__(self, port=9222):
        self.driver = BrowserManager.get_driver(port)

    def log(self, msg):
        try:
            print(msg)
        except Exception:
            print(msg.encode('utf-8', 'ignore').decode('utf-8'))

    def run_once(self):
        self.log("\n==========================================")
        self.log("🚀 [模块化引擎] 开始执行 NIW 15 大关卡巡检...")
        self.log("==========================================")

        checkers = [
            PendingWagerChecker(self.driver, self.log),
            CCLRecoverChecker(self.driver, self.log),
            MatchesWagersChecker(self.driver, self.log),
            ResultProcessChecker(self.driver, self.log),
            CalculateBetslipsChecker(self.driver, self.log),
            RPTPolyMarketChecker(self.driver, self.log),
            RPTCompareChecker(self.driver, self.log),
            RPTAIChecker(self.driver, self.log),
            RPTCompareUTCChecker(self.driver, self.log),
            ForecastChecker(self.driver, self.log),
            CheckCCLChecker(self.driver, self.log),
            WsumSportChecker(self.driver, self.log),
            HGPercentagesChecker(self.driver, self.log),
            RPTCRSChecker(self.driver, self.log),
            OneWalletPendingChecker(self.driver, self.log)
        ]

        for idx, checker in enumerate(checkers, 1):
            if not checker.check():
                self.log(f"\n❌ [巡检中断] 第 {idx} 关检测到致命错误，已停止后续 Checkpoint，保留页面停留。")
                break
        else:
            self.log("\n🎉🎉 恭喜！NIW 15 大关卡全部顺畅通关！")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        runner = CheckPointRunner()
        runner.run_once()
    else:
        app = UnifiedBotApp()
        app.mainloop()
