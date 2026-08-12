"""
================================================================================
第1站 Pending Wager 关卡检查器 (pages/niw/page_01_pending_wager.py)
--------------------------------------------------------------------------------
作用: 
1. 导航至 Pending Wager 页面 (Menu ID: apy_b0i2text)。
2. 自动载入数据缓冲（无需重复点击 Search 按钮）。
3. 提取全表所有 Satellite 卫星公司（RCM & LRCM）的:
   - Total Wager Pending (>200s) 积压单数
   - Total Mulp Pending 积压单数
4. 无论是否有 error，一律将所有抓取到的公司及单数明细完整打印在 log 中！
================================================================================
"""

import time
from selenium.webdriver.common.by import By
from core.base_checker import BaseChecker

class PendingWagerChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第1站 Pending Wager", menu_id="apy_b0i2text")
        try:
            # 1. 导航切入 Pending Wager 专属菜单
            self.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW")

            # 进入 pending wager page 会自动刷新，无需再次点击 search 按钮
            #self.log("[INFO] auto refresh, wait for 2 seconds...")
            #self.wait_for_page_loaded(seconds=2)

            time.sleep(2)
            # 2. 提取全表所有卫星公司 Pending 积压数据明细 (包含 Wager Pending 与 Mulp Pending)
            wager_info = self.driver.execute_script("""
                var links = document.querySelectorAll("a[onclick*='drawTbl']");
                var allCompanyDetails = [];
                var errorCompanyDetails = [];
                var totalWagerPending = 0;
                var totalPendingMulp = 0;

                for (var i = 0; i < links.length; i++) {
                    var name = links[i].innerText.trim();      // company name
                    var parentTr = links[i].closest("tr");     // tr element
                    if (parentTr) {
                        var tds = parentTr.querySelectorAll("td"); // td element
                        if (tds.length >= 2) {
                            var WagerCountText = tds[tds.length - 2].innerText.trim();  // wager (>200s)
                            var mulpCountText = tds[tds.length - 1].innerText.trim();   // mulp 

                            var WagerCnt = parseInt(WagerCountText) || 0;  // pending wager count integer
                            var mulpCnt = parseInt(mulpCountText) || 0;    // pending mulp count integer

                            var detailStr = name + ": total wager pending: " + WagerCnt + ", Total Mulp pending: " + mulpCnt;

                            // 修正 JS 逻辑或运算符: 将 Python 的 or 修正为 JavaScript 的 || 运算符
                            allCompanyDetails.push(detailStr + (WagerCnt > 0 || mulpCnt > 0 ? " [ERROR]" : " [OK]"));
                            if (WagerCnt > 0 || mulpCnt > 0) {
                                totalWagerPending += WagerCnt;
                                totalPendingMulp += mulpCnt;
                                errorCompanyDetails.push(detailStr);
                            }
                        }
                    }
                }
                return { 
                    allCompanyDetails: allCompanyDetails, 
                    errorCompanyDetails: errorCompanyDetails, 
                    totalWagerPending: totalWagerPending, 
                    totalPendingMulp: totalPendingMulp, 
                    linkCount: links.length 
                };
            """)

            all_company_details = wager_info.get("allCompanyDetails", [])
            error_company_details = wager_info.get("errorCompanyDetails", [])
            total_wager_pending = wager_info.get("totalWagerPending", 0)
            total_pending_mulp = wager_info.get("totalPendingMulp", 0)
            link_count = wager_info.get("linkCount", 0)

            self.log_data_extracted(f"成功抓取到 RCM and LRCM {link_count} 家公司完整数据 (Total pending wager (>200s): {total_wager_pending} 单 wager, Total Mulp pending: {total_pending_mulp} 单 mulp)")

            # 3. 无论是否有 error，一律打印完整数据明细！
            self.log_data_summary([f"【Pending Wager 全量数据明细 (共 {link_count} 家公司)】:"] + [f"   * {item}" for item in all_company_details])

            # 4. 判断是否存在未处理积压单
            if len(error_company_details) > 0:
                self.log(f"[Error] total wager pending >200s: {total_wager_pending} and total mulp pending: {total_pending_mulp}")
                for item in error_company_details:
                    self.log(f"  - {item}")
                self.log_check_result(False, "Pending Wager [Error]")
                return False
            else:
                self.log_check_result(True, f"Pending Wager 巡检通过，全表 {link_count} 家公司")

            # 5. 精准点击 Pending Wager 专属 Checkpoint 按钮 (<input id="checkpoint" onclick="setCP();">)
            self.click_checkpoint()
            return True

        except Exception as e:
            self.log_check_result(False, f"Pending Wager 检查出现异常: {e}")
            return False
