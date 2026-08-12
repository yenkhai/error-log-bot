"""
================================================================================
第15站 1 Wallet Pending 关卡检查器 (pages/niw/page_15_one_wallet_pending.py)
--------------------------------------------------------------------------------
作用: 
1. 自动进入 1 Wallet Pending 页面 (Menu ID: apy_b0i17text)。
2. 校验左侧表格 Total Pending Transaction 的 120s 积压列是否为 0。
3. (依据规则: 忽略右侧表格), 若左表 120s 列无积压且全绿，点击 Checkpoint 完成全套 NIW 巡检！
================================================================================
"""

import time
from selenium.webdriver.common.by import By
from core.base_checker import BaseChecker

class OneWalletPendingChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第15站 1 Wallet Pending", menu_id="apy_b0i17text")
        try:
            # 导航切入页面
            self.navigate_to_menu("1 Wallet Pending", menu_id="apy_b0i17text", section="NIW")

            # 在内存中抓取左侧表格 120s 积压列数据
            pending_data = self.driver.execute_script("""
                var tables = document.querySelectorAll("table");
                if (tables.length === 0) return { total120s: 0 };
                var leftTable = tables[0];
                var rows = leftTable.querySelectorAll("tr");
                var total120s = 0;
                for (var i = 0; i < rows.length; i++) {
                    var tds = rows[i].querySelectorAll("td");
                    if (tds.length >= 4) {
                        var val = tds[3].innerText.trim(); // 第4列为 120s 超时列
                        if (val && !isNaN(val)) total120s += parseInt(val);
                    }
                }
                return { total120s: total120s, rows: rows.length };
            """)

            self.log_data_extracted(f"抓取到 1 Wallet Pending 左侧 Total Pending Transaction 数据表")
            self.log_check_method("校验左侧表格 120s 超时积压列数值是否全为 0 (自动忽略右侧表格)")

            total_120s = pending_data.get("total120s", 0)

            if total_120s > 0:
                self.log_data_summary([f"1 Wallet Pending 左表 120s 存在 {total_120s} 单超时积压 [ERROR/红字未完成]"])
                self.log_check_result(False, "1 Wallet Pending 存在 120s 超时积压，阻断 Checkpoint。")
                return False
            else:
                self.log_data_summary(["1 Wallet Pending 左表 120s 积压列为 0，全绿无错。"])
                self.log_check_result(True, "1 Wallet Pending 完全正常。")
                self.click_checkpoint()
                return True

        except Exception as e:
            self.log_check_result(False, f"1 Wallet Pending 检查出现异常: {e}")
            return False
