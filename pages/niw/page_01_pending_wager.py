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

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore

class PendingWagerChecker(BaseChecker):
    def check(self) -> bool:
        # 1. 打印当前关卡页头日志信息
        self.log_station_header("第1站 Pending Wager", menu_id="apy_b0i2text")
        try:
            # 2. 导航切入 Pending Wager 专属菜单 (Menu ID: apy_b0i2text)
            self.navigate_to_menu("Pending Wager", menu_id="apy_b0i2text", section="NIW")

            # 3. 执行核心前端 JavaScript 脚本：遍历 HTML 提取所有卫星公司的 Pending 积压数据明细
            wager_info = self.driver.execute_script("""
                // 查找页面所有 onclick 包含 'drawTbl' 的 <a> 超链接节点（每个超链接代表一家卫星公司/平台）
                var links = document.querySelectorAll("a[onclick*='drawTbl']");
                var allCompanyDetails = [];   // 存放所有公司的日志文本明细 (OK/ERROR)
                var errorCompanyDetails = []; // 仅存放存在积压异常的公司明细
                var rawRows = [];             // 存放结构化数据，供前端/报告生成表格

                // 循环遍历每一家公司对应的超链接
                for (var i = 0; i < links.length; i++) {
                    var name = links[i].innerText.trim(); // 获取公司名称 (ex. nv01 - p0001)
                    console.log("公司名称: " + (i+1).toString() + ": " + name);

                    var parentTr = links[i].closest("tr"); // 向上查找超链接所在的表格行 <tr>
                    if (parentTr) {
                        var tds = parentTr.querySelectorAll("td"); // 获取该行所有的单元格 <td>
                        if (tds.length >= 2) {
                            // 倒数第 2 个单元格: Wager 积压单数 (>200s)
                            var WagerCountText = tds[tds.length - 2].innerText.trim();
                            // 倒数第 1 个单元格: Mulp (串关/多元) 积压单数
                            var mulpCountText = tds[tds.length - 1].innerText.trim();

                            // 转为整型数字，转换失败则默认为 0
                            var WagerCnt = parseInt(WagerCountText) || 0; // Wager 积压整型数量
                            var mulpCnt = parseInt(mulpCountText) || 0;   // Mulp 积压整型数量
                            
                            // Boolean 判定是否有异常：任一单数 > 0 即为异常(true)
                            var isErr = (WagerCnt > 0 || mulpCnt > 0);

                            // 组装格式化日志明细行
                            var detailStr = name + ": total wager pending: " + WagerCnt + ", Total Mulp pending: " + mulpCnt;
                            allCompanyDetails.push(detailStr + (isErr ? "status: [ERROR]" : "status: [OK]"));
                            
                            // 保存到 rawRows 结构化数组
                            rawRows.push({
                                company: name,
                                wager: WagerCnt,
                                mulp: mulpCnt,
                                status: isErr ? "ERROR" : "OK"
                            });

                            // 如果存在异常，进行总数累加并加入错误列表
                            if (isErr) {
                                errorCompanyDetails.push(detailStr);
                            }
                        }
                    }
                }

                // 将抓取到的全量数据打包返回给 Python 侧
                return { 
                    allCompanyDetails: allCompanyDetails, 
                    errorCompanyDetails: errorCompanyDetails, 
                    rawRows: rawRows,
                    linkCount: links.length 
                };
            """)

            # 4. 在 Python 侧解构 JS 返回的字段变量
            all_company_details = wager_info.get("allCompanyDetails", [])
            error_company_details = wager_info.get("errorCompanyDetails", [])
            raw_rows = wager_info.get("rawRows", [])
            link_count = wager_info.get("linkCount", 0)

            # 输出数据提取的汇总提示日志
            self.log_data_extracted(f"成功抓取到 RCM and LRCM {link_count} 家公司完整数据")

            # 5. 无论是否有 error，一律将全量抓取到的公司及单数明细完整打印在 log 中！
            self.log_data_summary([f"【Pending Wager 全量数据明细 (共 {link_count} 家公司)】:"] + [f"   * {item}" for item in all_company_details])

            # 构筑写回 CheckpointStore 存储库的表头和数据行
            table_headers = ["Company", "Wager Pending (>200s)", "Mulp Pending", "Status"]
            table_rows = [
                [
                    CheckpointStore.make_cell(r["company"]),
                    CheckpointStore.make_cell(str(r["wager"])),
                    CheckpointStore.make_cell(str(r["mulp"])),
                    CheckpointStore.make_cell(r["status"])
                ]
                for r in raw_rows
            ]

            # 6. 判断是否存在积压单（如果有错误公司明细）
            if len(error_company_details) > 0:
                # 记录报错日志
                self.log(f"[Error] Got pending wager or mulp record!")
                for item in error_company_details:
                    self.log(f"  - {item}")
                self.log_check_result(False, "Pending Wager [Error]")
                
                # 保存 Checkpoint 状态为失败 (False)
                CheckpointStore.save(
                    page_key="niw_01",
                    title="Pending Wager",
                    status=False,
                    headers=table_headers,
                    rows=table_rows,
                    summary=f"[Error] Got pending wager or mulp record!"
                )
                return False
            else:
                self.log_check_result(True, f"Pending Wager 巡检通过，全表 {link_count} 家公司")

            # 7. 无异常时，精准点击页面上的 Checkpoint 按钮提交保存 (<input id="checkpoint" onclick="setCP();">)
            self.click_checkpoint()
            
            # 保存 Checkpoint 状态为成功 (True)
            CheckpointStore.save(
                page_key="niw_01",
                title="Pending Wager",
                status=True,
                headers=table_headers,
                rows=table_rows,
                summary=f"全表 {link_count} 家公司全部 0 积压正常"
            )
            return True

        except Exception as e:
            # 捕获运行中的未知异常并自动记录 CheckpointStore
            return self.handle_exception("niw_01", "Pending Wager", e)

