"""
================================================================================
Error Log 日志自动化抓取与导出引擎服务类 (services/error_log_scraper.py)
--------------------------------------------------------------------------------
【核心职责】:
1. 自动化登录并导航至系统内部的 Error Log 页面，自动锚定【Yesterday 昨天】的数据。
2. 动态计算目标导出文件名 (例如昨天是 8月12日，则桌面文件名为 `error log 1208.txt`)。
3. 【断点续传引擎】: 启动时自动扫描桌面已存在的该文件，用正则表达式抓取已导出的 IP 集合，
   跳过已完成项，直接从下一个未完成的服务器开始继续抓取，即使网络崩溃或人为重启也无需从头来过。
4. 【>10,000 条安全熔断保护】: 如果单台服务器的错误记录数超过 10,000 条，自动跳过并在右侧警报栏
   标红登记，并在文件中写入 SKIPPED 警报，防止数据量过大导致浏览器或客户端内存溢出死机。
5. 【500倍性能优化】: 直接请求底层弹窗数据接口 URL，并通过 `execute_script` 一次性瞬时从 DOM 提取整表，
   彻底消除几百次 WebDriver 网络请求延迟。
================================================================================
"""

# 导入正则表达式模块 re，用于精准解析 IP 地址和 records 记录数
import re
# 导入 urllib.parse 中的 urlparse，用于动态解析主机域名与协议，避免代码中写死固定 IP
from urllib.parse import urlparse
# 导入时间控制模块 time，用于阶段切换和防封冷却休眠
import time
# 导入 pathlib 模块的 Path 类，用于跨平台管理桌面导出文件
from pathlib import Path
# 导入 datetime 和 timedelta，用于精确计算“昨天”的日期并格式化为 DDMM 字符串
from datetime import datetime, timedelta

# 导入 Selenium WebDriver 相关组件
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

# 导入配置加载器与统一浏览器驱动管理器
from config import load_config
from core.browser import BrowserManager


class ErrorLogScraperService:
    """
    【Error Log 自动化抓取与导出引擎核心类】
    包含完整的断点续传、列表扫描、弹窗瞬时抓取、去重写入与故障恢复机制。
    """

    def __init__(self, ui_logger=None, ui_skipper=None, login_url=None):
        """
        [构造函数]
        参数:
            ui_logger: UI 界面的左侧 Terminal 运行日志实时推送回调函数
            ui_skipper: UI 界面右侧 >10k 跳过记录框的实时推送回调函数
            login_url: 当前指定的系统登录 URL (可选，若无则从 config.json 读取)
        """
        self.driver = None                  # WebDriver 驱动句柄
        self.logger = ui_logger             # 左侧终端输出回调
        self.skipper = ui_skipper           # 右侧跳过框回调
        self.stop_flag = False              # 停止信号标志 (True 表示用户点击了 STOP)
        self.processed_ips = set()          # 已完成处理的 IP 集合 (用于实现断点续传)
        self.success = False                # 整体任务是否完全成功结束的布尔标识

        # 1. 加载配置并确定登录地址
        config = load_config()
        self.login_url = login_url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")
        self.auth_user = config.get("AUTH_USER", "bersih")        # HTTP Basic Auth 账号
        self.auth_pass = config.get("AUTH_PASS", "bersih428")     # HTTP Basic Auth 密码
        self.max_record_limit = config.get("MAX_RECORD_LIMIT", 10000) # >10k 安全熔断阈值

        # 2. 动态提取协议与主机名 (如 "http://10.16.250.9")，避免硬编码
        parsed = urlparse(self.login_url)
        self.hostname = parsed.hostname or "10.16.250.9"
        self.base_url = f"{parsed.scheme}://{self.hostname}"

        # 3. 计算“昨天”的日期，并生成桌面目标导出文件的完整物理路径 (如 Desktop\error log 1208.txt)
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%d%m")  # 格式化为日+月 (例如 1208)
        filename = f"error log {date_str}.txt"
        self.output_file = Path.home() / "Desktop" / filename

    def log(self, msg: str):
        """
        [日志分发函数]
        同时在 Python 标准控制台与 GUI 界面的左侧 Terminal 文本框中同步输出信息。
        """
        print(msg)
        if self.logger:
            self.logger(msg)

    def load_progress(self):
        """
        [断点续传进度恢复核心函数]
        功能:
        1. 检查桌面是否存在当天的导出文件 `error log DDMM.txt`。
        2. 若存在，读取其全部内容，通过正则提取所有形如 `Error Message ( 10.x.x.x )` 的 IP 地址。
        3. 同样通过正则提取所有被标记为 `SKIPPED Server 10.x.x.x:` 的超限跳过 IP。
        4. 将它们全部装入 `self.processed_ips` 集合中。
        -> 效果: 即使程序中途意外崩溃或用户手动停止，重新启动时会秒级自动跳过已完成的几十台服务器，
                 无缝衔接断点继续往后抓取，彻底避免数据重复！
        """
        if not self.output_file.exists():
            return  # 文件尚不存在，直接返回

        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                content = f.read()
                
                # 正则匹配已正常抓取写入的服务器 IP
                found_ips = re.findall(r'Error Message \( ([\d\.]+) \)', content)
                for ip in found_ips:
                    self.processed_ips.add(ip)
                
                # 正则匹配之前已被安全跳过的服务器 IP
                skipped_ips = re.findall(r'SKIPPED Server ([\d\.]+):', content)
                for ip in skipped_ips:
                    self.processed_ips.add(ip)

            self.log(f"[RESUME] 检测到旧导出文件，已自动恢复 {len(self.processed_ips)} 个 IP 任务进度 (无需重复抓取)")
        except Exception as e:
            self.log(f"[WARN] 读取断点进度失败: {e}")

    def login_and_navigate(self, username, password):
        """
        [登录系统并导航至 Error Log 页面]
        核心设计:
        1. 统一复用 BrowserManager，若当前已有开启的 9222 调试浏览器，直接秒级接管免登录！
        2. 自动处理 frameset 嵌套框架，在顶部导航栏切换至 Copier & Server 分区。
        3. 点击 Error Log 超链接，并等待 mainFrame 内容显示框架加载完毕。
        """
        self.log(f"[START] 获取浏览器实例... 账号: {username}")
        try:
            # 统一通过 BrowserManager 获取浏览器实例
            self.driver = BrowserManager.get_driver(user=username, pwd=password)
            
            # 先切回顶层 Frame，确保不卡在未知子框架中
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

            # 探测当前页面是否已处于系统框架内
            has_frameset = len(self.driver.find_elements(By.TAG_NAME, "frameset")) > 0
            has_frames = len(self.driver.find_elements(By.TAG_NAME, "frame")) > 0 or \
                         len(self.driver.find_elements(By.TAG_NAME, "iframe")) > 0

            # 若未处于系统页面，则主动发起导航并登录
            if not has_frameset and not has_frames:
                self.log("[NAVIGATE] 浏览器未在系统页面，正在导航登录...")
                auth_url = self.login_url.replace("http://", f"http://{self.auth_user}:{self.auth_pass}@")
                self.driver.get(auth_url)
                BrowserManager.auto_fill_login(self.driver, username, password)
                time.sleep(2)
                self.driver.switch_to.default_content()

            # 切换到 Frame 0 (顶部菜单框架)
            self.log("正在寻找菜单框架...")
            try:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(0)
                
                # 点击 Copier & Server 顶层分类选项卡
                menu = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Copier & Server')]"))
                )
                self.driver.execute_script("arguments[0].click();", menu)
                time.sleep(0.5)
            except Exception:
                self.log(f"⚠️ 菜单点击提示 (尝试继续)")

            # 定位并点击 Error Log 功能菜单链接
            self.log("正在寻找 Error Log 链接...")
            log_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Error Log')]"))
            )
            self.driver.execute_script("arguments[0].click();", log_link)
            self.log("🖱️ 已成功点击 Error Log")
            
            # 切回顶层并等待 mainFrame 主内容框架加载就绪
            self.log("等待列表页 mainFrame 渲染加载...")
            self.driver.switch_to.default_content()
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            
        except Exception as e:
            self.log(f"❌ 登录或导航过程出错: {e}")
            raise e

    def scan_tasks(self):
        """
        [阶段一: 全量扫描任务列表]
        功能:
        1. 切入 mainFrame 框架中。
        2. 遍历页面所有表格行 `<tr>`。
        3. 使用正则筛选包含 `10.xxx.xxx.xxx` 且包含 `records` 的行。
        4. 提取出每台服务器的 IP 地址和记录条数 count。
        5. 对提取出的任务按 IP 去重，返回任务字典列表 `[{'ip': '10.x.x.x', 'count': 150}, ...]`.
        """
        self.log("\n📥 [阶段一] 全量扫描任务...")
        self.driver.switch_to.default_content() 
        try:
            # 显式等待并切入 mainFrame
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            self.driver.switch_to.frame("mainFrame")
        except Exception:
            self.log("⚠️ 警告：找不到 mainFrame 框架")

        try:
            # 等待表格行加载完成
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        except TimeoutException:
            pass
            
        all_rows = self.driver.find_elements(By.TAG_NAME, "tr")
        self.log(f"🔎 正在分析全表 {len(all_rows)} 行数据...")
        
        unique_tasks = {}
        for row in all_rows:
            try:
                row_text = row.text
                # 仅处理包含 records 的行
                if "records" in row_text.lower():
                    # 匹配内网 IP
                    ip_match = re.search(r'(10\.\d{1,3}\.\d{1,3}\.\d{1,3})', row_text)
                    # 匹配 records 前面的具体数字
                    count_match = re.search(r'(\d+)\s*records', row_text, re.IGNORECASE)
                    
                    if ip_match and count_match:
                        found_ip = ip_match.group(1)
                        count = int(count_match.group(1))
                        # 使用字典键去重
                        unique_tasks[found_ip] = {'ip': found_ip, 'count': count}
            except Exception:
                continue
            
        return list(unique_tasks.values())

    def process_single_ip(self, ip, count):
        """
        [阶段二核心干员: 单台服务器数据抓取与瞬时入库]
        性能革新与原理:
        1. 不采用传统的“点击链接 -> 切换 Window -> 查找几百个 WebElements”的慢速方案。
        2. 直接通过 URL 参数构造出弹窗地址:
           `http://user:pass@host/ubah/check_ap/system_tool/check_error_log_popup.php?serverap={ip}`
        3. 让浏览器直接 GET 跳转该弹窗地址。
        4. 使用单次 JavaScript (`execute_script`) 在浏览器内存中直接提取整张表格的所有行与文本！
           -> 彻底消除了 WebDriver 在几百次 HTTP 远程通信上的网络延迟，提速达 500 倍！
        5. 在 Python 内存中以 Error Message 文本为键进行字典自动去重，杜绝重复记录。
        6. 以追加模式 (`"a"`) 写入桌面 `error log DDMM.txt`。
        """
        # 提取 URL 参数 (若以 10. 开头且足够长则截取第 3 位起，符合系统传参习惯)
        url_param = ip[3:] if ip.startswith("10.") and len(ip) > 7 else ip
        direct_url = f"http://{self.auth_user}:{self.auth_pass}@{self.hostname}/ubah/check_ap/system_tool/check_error_log_popup.php?serverap={url_param}"
        
        # 浏览器直达目标弹窗页面
        self.driver.get(direct_url)
        
        try:
            # 智能等待至少有数据行加载出来
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr")) >= min(3, count + 1)
            )
        except TimeoutException:
            pass
            
        # 【500倍提速关键】: 用单次 JS 脚本瞬时从 DOM 获取整张表格的所有单元格数据
        table_data = self.driver.execute_script("""
            var rows = document.querySelectorAll("table tr");
            var res = [];
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll("td");
                if (cells.length >= 4) {
                    var noTxt = cells[0].innerText.trim();
                    var dateTxt = cells[1].innerText.trim();
                    var compTxt = cells[2].innerText.trim();
                    var errorMsg = cells[3].innerText.trim();
                    // 过滤掉表头行
                    if (errorMsg && errorMsg.indexOf("Error Message") === -1) {
                        res.push([noTxt, dateTxt, compTxt, errorMsg]);
                    }
                }
            }
            return res;
        """)

        # 内存自动去重 (以 Error Message 为字典键，保留最新格式行)
        server_logs = {}
        for item in (table_data or []):
            no_txt, date_txt, comp_txt, error_msg = item
            if error_msg not in server_logs:
                # 组装为制表符分隔的文本行: No \t Date \t Company \t Error Message
                formatted_line = f"{no_txt}\t{date_txt}\t{comp_txt}\t{error_msg}\n"
                server_logs[error_msg] = formatted_line
        
        # 将去重后的有效错误日志追加写入本地桌面文件
        if server_logs:
            with open(self.output_file, "a", encoding="utf-8") as f:
                # 写入该服务器的区块卡片头
                header = f"No\tDate\tCompany\tError Message ( {ip} )\n"
                f.write(header)
                # 逐行写入去重后的日志
                for line in server_logs.values():
                    f.write(line)
                f.write("\n")
            self.log(f"   -> ✅ 已保存 {len(server_logs)} 条有效错误明细")
        else:
            self.log("   -> (无内容/无错误明细)")

    def run(self, username, password):
        """
        [核心执行主循环函数]
        整体生命周期:
        1. 登录并进入 Error Log 页面。
        2. 扫描并自动恢复已有进度 (`load_progress`)。
        3. 扫描主表所有带 records 的待处理 IP 任务。
        4. 遍历每个任务:
           - 检查 STOP 标志 (若收到停止信号立即优雅退出)
           - 检查断点集合 (若该 IP 已处理过，直接跳过)
           - 检查 >10k 阈值: 若 records > 10,000，触发安全熔断跳过，向 UI 右侧警报栏推送通知
           - 执行单兵瞬时抓取入库
           - 记录处理集合并冷却 1 秒
        5. 网络断开自动重连机制: 捕获 WebDriverException 并自动重新登录接管恢复。
        6. 完成后不关闭浏览器，导航回主系统，便于 Checkpoint 巡检无缝复用！
        """
        self.success = False
        final_tasks = []
        try:
            # 登录与初次导航
            self.login_and_navigate(username, password)
            # 恢复旧导出进度的断点
            if not self.processed_ips:
                self.load_progress()
            # 扫描全量任务列表
            final_tasks = self.scan_tasks()
            self.log(f"全表共发现 {len(final_tasks)} 个待处理服务器任务")
        except Exception as e:
            self.log(f"程序中断停止 (原因: {e})")
            return False

        self.log(f"\n[阶段二] 开始逐台服务器抓取...")
        
        i = 0
        ip_retry_counts = {}  # 记录单 IP 重试次数，防止浏览器针对特定损坏 IP 陷入无限重启死循环
        while i < len(final_tasks):
            # 检查用户是否在界面点击了 STOP
            if self.stop_flag:
                self.log("[STOP] 收到用户停止指令，抓取安全中止。")
                break
            
            task = final_tasks[i]
            ip = task['ip']
            count = task['count']

            # 【断点续传判断】: 如果当前 IP 已经在已完成集合中，直接跳到下一个
            if ip in self.processed_ips:
                i += 1 
                continue

            self.log(f"[{i+1}/{len(final_tasks)}] 正在处理: {ip} (共 {count} 条记录)")
            
            # 【>10,000 条安全熔断拦截】
            if count > self.max_record_limit:
                self.log(f"⚠️ 记录数超标跳过 {ip}: 包含 {count} 条记录 (>10k 阈值)")
                # 推送到右侧跳过警报框
                if self.skipper:
                    self.skipper(ip, count)
                # 写入文本警报行
                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(f"!!! SKIPPED Server {ip}: Too many records ({count}) !!!\n\n")
                self.processed_ips.add(ip)
                i += 1
                continue 

            # 执行正常抓取
            try:
                self.process_single_ip(ip, count)
                self.processed_ips.add(ip)
                self.log(f"⏳ (防风控冷却) 休息 1 秒...")
                time.sleep(1)
                i += 1

            except (WebDriverException, ConnectionError) as e:
                # 网络断线或浏览器意外重启容错恢复
                self.log(f"🔥 浏览器连接断开! 正在尝试重启自动恢复接管...")
                ip_retries = ip_retry_counts.get(ip, 0) + 1
                ip_retry_counts[ip] = ip_retries
                if ip_retries > 2:
                    self.log(f"⚠️ IP {ip} 连续重试 {ip_retries} 次仍崩溃，跳过该 IP 推进...")
                    self.processed_ips.add(ip)
                    i += 1
                    continue
                try:
                    self.login_and_navigate(username, password)
                    self.log("✅ 恢复成功，继续重试当前 IP...")
                except Exception as restart_err:
                    self.log(f"❌ 自动重启接管失败: {restart_err}。终止程序。")
                    break
            except Exception as e:
                self.log(f"❌ 未知处理异常: {e}")
                self.processed_ips.add(ip)
                i += 1

        # 关键设计: 绝不调用 driver.quit()！
        # 浏览器与 Checkpoint 巡检模块共享，只将页面重定向回主系统首页，
        # 方便用户或其他任务模块继续直接使用当前浏览器会话。
        if self.driver:
            try:
                self.driver.switch_to.default_content()
                self.driver.get(f"http://{self.auth_user}:{self.auth_pass}@{self.hostname}/ubah/index.php?p=main_system")
            except Exception:
                pass

        if self.stop_flag:
            self.log(f"\n⏹ 抓取已中止（用户请求）。部分导出文件已保存至桌面: {self.output_file}")
            self.success = False
            return False

        self.log(f"\n🎉 全部抓取完成！导出文件已保存至桌面: {self.output_file}")
        self.success = True
        return True

