import sys
import time
import traceback
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BaseChecker:
    """
    ================================================================================
    所有关卡检查器的核心基类 (BaseChecker)
    --------------------------------------------------------------------------------
    作用:
    1. 统一管理与 Chrome 浏览器的底层交互（如框架 Frame 切换、菜单点击、Search 搜索）。
    2. 提供【全页 RGB 真实计算颜色扫描器】(scan_red_cells)，精准捕获所有红字/红背景。
    3. 提供透明化的【日志打印助手】(log_station_header, log_data_extracted 等)，向界面输出清晰解说。
    ================================================================================
    """

    def __init__(self, driver, logger_func=None):
        # driver: Selenium WebDriver 实例对象，用于控制浏览器
        self.driver = driver
        # logger_func: 回调函数，用于将日志实时推送给 CustomTkinter GUI 界面显示
        self.logger_func = logger_func

    def log(self, message: str):
        """
        [日志输出函数] 统一处理日志输出，防止 Windows 控制台出现 UTF-8 Emoji 编码崩溃问题
        """
        if self.logger_func:
            try:
                self.logger_func(message)
            except Exception:
                pass
        else:
            try:
                print(message)
            except Exception:
                try:
                    print(message.encode('utf-8', 'ignore').decode('utf-8'))
                except Exception:
                    pass

    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------
    # 结构化解说日志组件 (方便用户在控制台直观理解当前步骤)
    # --------------------------------------------------------------------------------
    def log_station_header(self, station_name: str, menu_id: str = None, page_key: str = None):
        """打印关卡标题分隔线，并复位日志缓冲与表格数据"""
        self._current_station_name = station_name
        self._current_station_id = menu_id if menu_id else station_name.replace(" ", "_")
        self._current_page_key = page_key
        self._current_log_buffer = []
        self._current_table_headers = None
        self._current_table_rows = None

        self.log("\n================================================================================")
        self.log(f"[STATION] 开始巡检: {station_name} (Target Menu ID: {menu_id if menu_id else 'Direct Nav'})")
        self.log("================================================================================")

    def log_data_extracted(self, description: str):
        """打印抓取到的数据解说"""
        self.log(f"[DATA EXTRACTED] 页面数据抓取: {description}")

    def log_check_method(self, method_description: str):
        """打印本关卡采取的判定计算规则"""
        self.log(f"[CHECK METHOD] 校验计算规则: {method_description}")

    def log_table_data(self, headers: list, rows: list):
        """保存并格式化打印结构化表格数据（供桌面 .txt 和 HTML 仪表盘渲染）"""
        self._current_table_headers = headers
        self._current_table_rows = rows
        
        try:
            from core.page_logger import PageLogger
            ascii_table = PageLogger.format_ascii_table(headers, rows)
            self.log("[TABLE DATA] 提取表格数据明细:")
            for line in ascii_table.splitlines():
                self.log(f"   {line}")
        except Exception:
            pass

    def log_data_summary(self, details: list):
        """打印结构化明细列表"""
        self._current_summary_details = details
        self.log("[DATA SUMMARY] 抓取到具体数据明细如下:")
        for line in details:
            self.log(f"   -> {line}")

    def log_check_result(self, is_success: bool, summary_msg: str):
        """
        打印最终判定结论，并自动：
        1. 写入桌面 .txt 日志文件 (PageLogger)
        2. 重新渲染 HTML 仪表盘 (ReportManager)
        """
        if is_success:
            self.log(f"[CHECK RESULT] SUCCESS: {summary_msg}")
        else:
            self.log(f"[CHECK RESULT] FAILED: {summary_msg}")

        # 1. 自动写入桌面 .txt 分页日志
        try:
            from core.page_logger import PageLogger
            page_key = getattr(self, "_current_page_key", None)
            if not page_key:
                # 尝试根据 station_id 推导 page_key
                sid = getattr(self, "_current_station_id", "")
                station_name = getattr(self, "_current_station_name", "")
                page_key = self._infer_page_key(sid, station_name)

            if page_key:
                PageLogger.write_page_log(
                    page_key=page_key,
                    station_name=getattr(self, "_current_station_name", "巡检关卡"),
                    is_success=is_success,
                    raw_lines=getattr(self, "_current_log_buffer", [summary_msg]),
                    table_headers=getattr(self, "_current_table_headers", None),
                    table_rows=getattr(self, "_current_table_rows", None)
                )
        except Exception:
            pass

        # 2. 自动更新 HTML 仪表盘
        try:
            from core.report_manager import ReportManager
            ReportManager.generate_html_dashboard()
        except Exception:
            pass

    def _infer_page_key(self, menu_id: str, station_name: str) -> str | None:
        """内部工具: 根据 menu_id 或站名自动匹配 page_key"""
        menu_map = {
            "apy_b0i2text": "niw_01", "apy_b0i3text": "niw_02", "apy_b0i4text": "niw_03",
            "apy_b0i5text": "niw_04", "apy_b0i6text": "niw_05", "apy_b0i7text": "niw_06",
            "apy_b0i8text": "niw_07", "apy_b0i9text": "niw_08", "apy_b0i10text": "niw_09",
            "apy_b0i11text": "niw_10", "apy_b0i13text": "niw_11", "apy_b0i14text": "niw_12",
            "apy_b0i15text": "niw_13", "apy_b0i16text": "niw_14", "apy_b0i17text": "niw_15",
            "apy_b0i19text": "copier_01", "apy_b0i20text": "copier_02", "apy_b0i21text": "copier_03",
            "apy_b0i22text": "copier_04", "apy_b0i23text": "copier_05", "apy_b0i24text": "copier_06",
            "apy_b0i25text": "copier_07", "apy_b0i26text": "copier_08", "apy_b0i27text": "copier_09",
        }
        if menu_id in menu_map:
            return menu_map[menu_id]
        return None

    # --------------------------------------------------------------------------------
    # 浏览器 Frame 框架切换组件
    # --------------------------------------------------------------------------------
    def switch_to_menu_frame(self, frame_index=0):
        """
        切换到顶部导航菜单框架 (通常为 Frame 0)
        系统采用 iframe 嵌套结构: 菜单在 Top Frame，主内容在 mainFrame
        """
        self.driver.switch_to.default_content() # 先切回最顶层
        self.driver.switch_to.frame(frame_index) # 再切入菜单 Frame

    def switch_to_main_frame(self, frame_name="mainFrame", timeout=10):
        """
        切换到中间主内容显示框架 (mainFrame)
        网页上的表格、数据、Search 按钮和 Checkpoint 按钮全在这个 Frame 里面
        """
        self.driver.switch_to.default_content() # 先切回最顶层
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.NAME, frame_name))
        )
        self.driver.switch_to.frame(frame_name) # 切入主页面 Frame

    def wait_for_page_loaded(self, seconds=3, max_wait=30, check_spinner=True):
        """
        [全局智能动态页面就绪检测机制 (Universal Smart Polling Engine)]
        核心原理:
        1. 动画与遮罩检测: 实时监测页面上是否存在可见的 Loading 动画 / Spinner / Mask / Loading 提示文本。
        2. AJAX 异步完成检测: 监测 document.readyState === 'complete' 以及 jQuery.active === 0。
        3. 动态智能轮询: 
           - 如果数据 1-2 秒内加载完且动画消失，立刻继续，不浪费一秒钟；
           - 如果数据仍在加载 (Loading 动画还亮着)，系统自动等待，直到动画彻底消失；
           - 最多智能轮询 max_wait 秒 (默认 30s)，防止因网络死锁卡死。
        """
        start_time = time.time()
        poll_interval = 0.5
        min_seconds = max(1.0, float(seconds) if seconds else 2.0)
        
        # 初始微缓冲，让浏览器有时间发起请求并挂起加载动画
        time.sleep(0.6)

        while (time.time() - start_time) < max_wait:
            try:
                status = self.driver.execute_script("""
                    var res = {
                        isDomReady: (document.readyState === "complete"),
                        isAjaxDone: (typeof jQuery === "undefined" || jQuery.active === 0),
                        hasSpinner: false,
                        loadingDetails: ""
                    };

                    // 1. 检查所有可能的 Loading 动画 / 遮罩元素
                    var loaderSelectors = [
                        "#loading", ".loading", "[id*='loading']", "[class*='loading']",
                        "[id*='load']", "[class*='load']", "[id*='wait']", "[class*='spinner']",
                        "img[src*='load']", "img[src*='wait']", "div.ui-dialog", "div.blockUI",
                        "div.loading-mask", "div.modal-backdrop", "#progress", ".progress"
                    ];

                    for (var i = 0; i < loaderSelectors.length; i++) {
                        var els = document.querySelectorAll(loaderSelectors[i]);
                        for (var j = 0; j < els.length; j++) {
                            var el = els[j];
                            if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                                var style = window.getComputedStyle(el);
                                if (style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0") {
                                    // 确认为屏幕上可见的加载动画
                                    res.hasSpinner = true;
                                    res.loadingDetails = loaderSelectors[i] + " 正在显示";
                                    return res;
                                }
                            }
                        }
                    }

                    // 2. 检查页面文本中是否包含全屏可见的 "Loading..." 提示
                    var bodyText = document.body ? document.body.innerText : "";
                    if (bodyText.indexOf("Loading...") !== -1 || bodyText.indexOf("Please wait...") !== -1 || bodyText.indexOf("正在加载") !== -1) {
                        var visibleLoading = false;
                        var allDivs = document.querySelectorAll("div, span, td, p");
                        for (var k = 0; k < allDivs.length; k++) {
                            var t = allDivs[k].innerText ? allDivs[k].innerText.trim().toLowerCase() : "";
                            if (t === "loading..." || t === "please wait..." || t === "正在加载...") {
                                if (allDivs[k].offsetWidth > 0 && allDivs[k].offsetHeight > 0) {
                                    var st = window.getComputedStyle(allDivs[k]);
                                    if (st.display !== "none" && st.visibility !== "hidden") {
                                        visibleLoading = true;
                                        break;
                                    }
                                }
                            }
                        }
                        if (visibleLoading) {
                            res.hasSpinner = true;
                            res.loadingDetails = "文本 Loading... 正在显示";
                            return res;
                        }
                    }

                    return res;
                """)

                is_ready = status.get("isDomReady", True) and status.get("isAjaxDone", True) and not status.get("hasSpinner", False)
                elapsed = time.time() - start_time

                if is_ready and elapsed >= min_seconds:
                    # 数据与动画均已就绪，立即返回继续！
                    break

            except Exception:
                pass

            time.sleep(poll_interval)

    def navigate_to_menu(self, menu_title: str, menu_id: str = None, section: str = "NIW", wait_seconds: int = 4):
        """
        [通用关卡导航函数]
        1. 自动在顶部 Frame 中切换 NIW / Copier & Server 分组选项卡。
        2. 根据 Menu ID 或 菜单文本名称 定位具体的关卡按钮并点击。
        3. 自动切入 mainFrame 框架，并调用 wait_for_page_loaded() 等待页面载入完。
        """
        self.switch_to_menu_frame()
        
        # 激活顶层 Tab 选项卡 (NIW 或 Copier & Server)
        try:
            if section == "NIW":
                niw_tab = self.driver.find_elements(By.XPATH, "//td[@id='apy_b0i1text']//a | //font[text()='NIW']")
                if niw_tab:
                    self.driver.execute_script("arguments[0].click();", niw_tab[0])
                    time.sleep(0.5)
            elif section == "Copier":
                copier_tab = self.driver.find_elements(By.XPATH, "//td[@id='apy_b0i18text']//a | //font[contains(text(), 'Copier')]")
                if copier_tab:
                    self.driver.execute_script("arguments[0].click();", copier_tab[0])
                    time.sleep(0.5)
        except Exception:
            pass

        # 查找具体关卡的点击链接 (优先通过 ID 查找，找不到则通过文本查找)
        menu_link = None
        if menu_id:
            try:
                elems = self.driver.find_elements(By.XPATH, f"//td[@id='{menu_id}']//a")
                if elems:
                    menu_link = elems[0]
            except Exception:
                pass
        
        if not menu_link:
            try:
                elems = self.driver.find_elements(By.XPATH, f"//a[contains(text(), '{menu_title}')]")
                if elems:
                    menu_link = elems[0]
            except Exception:
                pass

        if not menu_link:
            menu_link = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, f"//a[contains(text(), '{menu_title}')] | //td[contains(@id, 'text')]//a[contains(text(), '{menu_title}')]"))
            )
        
        # 通过 JavaScript 触发点击，避免被页面遮挡拦截
        self.driver.execute_script("arguments[0].click();", menu_link)
        self.log(f"[NAVIGATE] 已成功进入 {menu_title} 页面 (Menu ID: {menu_id if menu_id else 'Text Match'})")
        
        # 自动切换到主页面框架并缓冲等待
        self.switch_to_main_frame()
        self.wait_for_page_loaded(seconds=wait_seconds)

    def select_rcm_company(self) -> bool:
        """
        [下拉框选择函数] 自动在页面下拉框 com_select 中选中 RCM 公司，并触发 change 事件通知网页更新数据
        """
        try:
            select_elems = self.driver.find_elements(By.ID, "com_select") or self.driver.find_elements(By.NAME, "com_select")
            if select_elems:
                self.driver.execute_script("""
                    var sel = arguments[0];
                    for (var i = 0; i < sel.options.length; i++) {
                        if (sel.options[i].text.indexOf('RCM') !== -1 || sel.options[i].value.indexOf('RCM') !== -1) {
                            sel.selectedIndex = i;
                            sel.dispatchEvent(new Event('change')); // 触发网页的原生 change 事件
                            break;
                        }
                    }
                """, select_elems[0])
                self.log("[SELECT] 已在下拉框中定位并选择公司: RCM")
                time.sleep(1)
                return True
        except Exception as e:
            self.log(f"[WARN] 选择 RCM 下拉框提示: {e}")
        return False

    def click_search_button(self, wait_seconds: int = 4) -> bool:
        """
        [Search 按钮点击函数]
        原理: 自动查找网页上的 Search 提交按钮（支持 <input>、<a>、<button> 等形式），点击后强制缓冲 wait_seconds 秒。
        """
        try:
            search_btn = self.driver.execute_script("""
                var btn = document.querySelector("input[value*='Search'], input[value*='search'], input[name*='search'], input[id*='search']") ||
                          document.querySelector("a[href*='search'], button[type='submit'], input[type='submit']");
                if (btn) return btn;
                var links = document.getElementsByTagName('a');
                for (var i = 0; i < links.length; i++) {
                    if (links[i].innerText.toLowerCase().includes('search')) return links[i];
                }
                return null;
            """)
            if search_btn:
                self.log("[SEARCH] 找到 Search 按钮，点击触发查询...")
                self.driver.execute_script("arguments[0].click();", search_btn)
                self.wait_for_page_loaded(seconds=wait_seconds)
                return True
            else:
                elems = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(translate(text(), 'SEARCH', 'search'), 'search')] | //input[contains(translate(@value, 'SEARCH', 'search'), 'search')]"
                )
                if elems:
                    self.log("[SEARCH] 找到 Search 按钮 (XPath)，点击触发查询...")
                    self.driver.execute_script("arguments[0].click();", elems[0])
                    self.wait_for_page_loaded(seconds=wait_seconds)
                    return True
        except Exception as e:
            self.log(f"[WARN] 点击 Search 按钮提示: {e}")
        return False

    def click_checkpoint(self) -> bool:
        """
        [Check Point 点击函数]
        在页面无任何红字报错时调用。显示隐藏的 div_checkpoint 并点击 id 为 checkpoint 的打勾按钮。
        """
        try:
            # 确保 checkpoint 区域在页面上显示出来
            self.driver.execute_script("if(typeof jQuery !== 'undefined') { $('#div_checkpoint').show(); }")
            checkpoint_btn = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "checkpoint"))
            )
            self.log("[CHECKPOINT] 找到 Check Point 按钮 (ID: checkpoint)，准备点击...")
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", checkpoint_btn)
            self.log("[CHECKPOINT] SUCCESS: 已成功点击 Check Point 按钮！")
            time.sleep(3)
            return True
        except Exception as e:
            self.log(f"[WARN] 没有找到 id 为 checkpoint 的按钮，或不可点击: {e}")
            return False

    def scan_red_cells(self) -> list:
        """
        ================================================================================
        [核心算法] DOM window.getComputedStyle 真实 RGB 颜色深度扫描引擎
        --------------------------------------------------------------------------------
        原理:
        1. 直接在浏览器 JavaScript 内存中遍历页面所有单元格 (td, span, div, font 等)。
        2. 调用浏览器原生 `window.getComputedStyle(el)` 读取元素渲染在屏幕上的最终 RGB 颜色。
        3. 提取 R, G, B 三原色分量：只要满足 (R >= 170 且 G <= 110 且 B <= 110)，不论网页是用 CSS Class, 
           bgcolor="red", style="color:red", 还是第三方框架渲染的，都能 100% 判为红字/红背景！
        4. 自动智能过滤 <th> 表头和 Remarks 使用指南框中的提示段落。
        ================================================================================
        """
        self.log("[SCAN] 正在通过 DOM RGB 计算样式深度扫描全页红字、红背景及异常节点...")
        
        red_items = self.driver.execute_script("""
            var elements = document.querySelectorAll("td, div, span, font, a, td font, td div, td span");
            var results = [];
            for (var i = 0; i < elements.length; i++) {
                var el = elements[i];
                if (el.offsetWidth === 0 && el.offsetHeight === 0) continue; // 忽略不可见的节点
                var tag = el.tagName.toLowerCase();
                if (tag === 'th') continue; // 过滤表头

                // 获取浏览器计算出来的最终渲染样式
                var style = window.getComputedStyle(el);
                var bg = style.backgroundColor; // 背景颜色 RGB
                var fg = style.color;           // 字体颜色 RGB
                var txt = el.innerText ? el.innerText.trim() : "";
                if (!txt) continue;

                var lowerTxt = txt.toLowerCase();

                // 过滤 Remarks 静态使用指南与说明短语
                if (lowerTxt.includes("remarks") || lowerTxt.includes("if show error") || 
                    lowerTxt.includes("this tool") || lowerTxt.includes("click patch") ||
                    lowerTxt.includes("robot recalculate") || lowerTxt.includes("click complete")) {
                    continue;
                }

                // 提取背景色 RGB 并判定是否为红色系 (Red >= 170, Green <= 110, Blue <= 110)
                var isRedBg = false;
                var bgMatch = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                if (bgMatch) {
                    var r = parseInt(bgMatch[1]), g = parseInt(bgMatch[2]), b = parseInt(bgMatch[3]);
                    if (r >= 170 && g <= 110 && b <= 110) isRedBg = true;
                }

                // 提取前景色 RGB 并判定是否为红色字体
                var isRedFg = false;
                var fgMatch = fg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                if (fgMatch) {
                    var r = parseInt(fgMatch[1]), g = parseInt(fgMatch[2]), b = parseInt(fgMatch[3]);
                    if (r >= 170 && g <= 110 && b <= 110) isRedFg = true;
                }

                // 如果命中红背景、红字体或者文本明确为 "error" / "missing"
                if (isRedBg || isRedFg || lowerTxt === "error" || lowerTxt === "missing") {
                    if (txt.length <= 60 && !results.includes(txt)) {
                        results.push(txt);
                    }
                }
            }
            return results;
        """)

        errors = red_items if isinstance(red_items, list) else []
        self.log(f"[SCAN DETAIL] 全局 RGB 深度扫描完毕，捕捉到 {len(errors)} 个红色/异常节点。")
        return errors
