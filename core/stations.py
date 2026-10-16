"""Single source for station order, titles and checker classes."""
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
from pages.niw.page_13_rpt_crs import RPTCRSChecker
from pages.niw.page_14_hg_percentages import HGPercentagesChecker
from pages.niw.page_15_one_wallet_pending import OneWalletPendingChecker

# ── 导入所有 9 个 Copier & Server 基础设施关卡检查器 ──
from pages.copier_server.page_01_copier import CopierChecker
from pages.copier_server.page_02_db_server_status import DBServerStatusChecker
from pages.copier_server.page_03_ap_server_status import APServerStatusChecker
from pages.copier_server.page_04_check_ap_space import CheckAPSpaceChecker
from pages.copier_server.page_05_error_log import ErrorLogChecker
from pages.copier_server.page_06_redis_server import RedisServerChecker
from pages.copier_server.page_07_robot_monitor import RobotMonitorChecker
from pages.copier_server.page_08_niw_robot_monitor import NIWRobotMonitorChecker
from pages.copier_server.page_09_info_robot_monitor import InfoRobotMonitorChecker



STATIONS = [
    ("niw_01", 'NIW Station 01 - Pending Wager', PendingWagerChecker),
    ("niw_02", 'NIW Station 02 - CCL Recover', CCLRecoverChecker),
    ("niw_03", 'NIW Station 03 - Matches Wagers', MatchesWagersChecker),
    ("niw_04", 'NIW Station 04 - Result Process', ResultProcessChecker),
    ("niw_05", 'NIW Station 05 - Calculate Betslips', CalculateBetslipsChecker),
    ("niw_06", 'NIW Station 06 - RPT PolyMarket', RPTPolyMarketChecker),
    ("niw_07", 'NIW Station 07 - RPT Compare', RPTCompareChecker),
    ("niw_08", 'NIW Station 08 - RPT AI', RPTAIChecker),
    ("niw_09", 'NIW Station 09 - RPT Compare UTC', RPTCompareUTCChecker),
    ("niw_10", 'NIW Station 10 - Forecast', ForecastChecker),
    ("niw_11", 'NIW Station 11 - Check CCL', CheckCCLChecker),
    ("niw_12", 'NIW Station 12 - Wsum Sport', WsumSportChecker),
    ("niw_13", 'NIW Station 13 - RPT CRS', RPTCRSChecker),
    ("niw_14", 'NIW Station 14 - HG Percentages', HGPercentagesChecker),
    ("niw_15", 'NIW Station 15 - 1 Wallet Pending', OneWalletPendingChecker),
    ("copier_01", 'Copier Station 01 - Copier', CopierChecker),
    ("copier_02", 'Copier Station 02 - DB Server Status', DBServerStatusChecker),
    ("copier_03", 'Copier Station 03 - AP Server Status', APServerStatusChecker),
    ("copier_04", 'Copier Station 04 - Check AP Space', CheckAPSpaceChecker),
    ("copier_05", 'Copier Station 05 - Error Log', ErrorLogChecker),
    ("copier_06", 'Copier Station 06 - Redis Server', RedisServerChecker),
    ("copier_07", 'Copier Station 07 - Robot Monitor', RobotMonitorChecker),
    ("copier_08", 'Copier Station 08 - NIW Robot Monitor', NIWRobotMonitorChecker),
    ("copier_09", 'Copier Station 09 - Info Robot Monitor', InfoRobotMonitorChecker),
]
STATION_LIST = [(key, title) for key, title, _ in STATIONS]

def build_checkers(section, driver, logger):
    return [(title, checker(driver, logger)) for key, title, checker in STATIONS if key.startswith(section + "_")]
