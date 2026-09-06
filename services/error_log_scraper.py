"""
================================================================================
Error Log 日志抓取与导出引擎服务类 (services/error_log_scraper.py)
--------------------------------------------------------------------------------
作用:
1. 从底层自动导航至 Error Log 页面，自动选择【Yesterday 昨天】并计算输出文件名 (如 error log 3107.txt)。
2. 支持【断点续传】: 自动扫描桌面已生成的 txt 文本，提取已抓取的 IP 列表，避免重复抓取。
3. 智能阀门控制 (>10,000 条安全拦截): 如果某台服务器日志记录数超过 10,000 条，自动跳过并记录在右侧警报栏，防止内存溢出与死机。
================================================================================
"""

import re
from urllib.parse import urlparse
import time
from pathlib import Path
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

from config import load_config
from core.browser import BrowserManager

class ErrorLogScraperService:
    """Error Log 自动化抓取与导出引擎"""

    def __init__(self, ui_logger=None, ui_skipper=None, login_url=None):
        self.driver = None
        self.logger = ui_logger  # 左侧 Terminal 日志回调
        self.skipper = ui_skipper # 右侧 >10k 跳过记录回调
        self.stop_flag = False
        self.processed_ips = set() # 已处理完毕的 IP 集合 (用于断点续传)
        self.success = False

        # 从全局 config 加载 URL 与鉴权配置 (支持外部传入 UI 当前配置)
        config = load_config()
        self.login_url = login_url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")
        self.auth_user = config.get("AUTH_USER", "bersih")
        self.auth_pass = config.get("AUTH_PASS", "bersih428")
        self.max_record_limit = config.get("MAX_RECORD_LIMIT", 10000) # >10k 安全阈值

        # 从 login_url 动态提取基础主机地址 (避免硬编码 IP)
        parsed = urlparse(self.login_url)
        self.base_url = f"{parsed.scheme}://{parsed.hostname}"  # e.g. "http://10.16.250.9"

        # 计算昨天的日期，并生成桌面目标文件名 (例如: "error log 3107.txt")
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%d%m")
        filename = f"error log {date_str}.txt"
        self.output_file = Path.home() / "Desktop" / filename

    def log(self, msg: str):
        """日志输出器"""
        print(msg)
        if self.logger:
            self.logger(msg)

    def load_progress(self):
        """
        [断点续传恢复]
        读取桌面已存在的 txt 导出文本，使用正则表达式提取所有已完成的 IP 地址存入 processed_ips。
        这样即使中途关掉软件重开，也能秒级接着上一次的进度继续抓取！
        """
        if not self.output_file.exists():
            return
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                content = f.read()
                found_ips = re.findall(r'Error Message \( ([\d\.]+) \)', content)
                for ip in found_ips:
                    self.processed_ips.add(ip)
                skipped_ips = re.findall(r'SKIPPED Server ([\d\.]+):', content)
                for ip in skipped_ips:
                    self.processed_ips.add(ip)
            self.log(f"[RESUME] 检测到旧导出文件，已恢复 {len(self.processed_ips)} 个 IP 任务进度")
        except Exception as e:
            self.log(f"[WARN] 读取断点进度失败: {e}")

    def login_and_navigate(self, username, password):
        """执行后台登录并自动跳转至 Error Log 页面（兼容复用 Checkpoint 已开启的浏览器）"""
        self.log(f"[START] 获取浏览器实例... 账号: {username}")
        try:
            # 统一使用 BrowserManager 获取浏览器，共享免登录状态！
            self.driver = BrowserManager.get_driver(user=username, pwd=password)
            
            # 先无条件切回顶层，确保不会卡在某个 iframe 里
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

            # 检查当前页面是否已经在系统内（frameset 存在说明已登录）
            has_frameset = len(self.driver.find_elements(By.TAG_NAME, "frameset")) > 0
            has_frames = len(self.driver.find_elements(By.TAG_NAME, "frame")) > 0 or \
                         len(self.driver.find_elements(By.TAG_NAME, "iframe")) > 0

            if not has_frameset and not has_frames:
                # 浏览器可能不在系统页面内，尝试导航到登录页
                self.log("[NAVIGATE] 浏览器未在系统页面，正在导航...")
                auth_url = self.login_url.replace("http://", f"http://{self.auth_user}:{self.auth_pass}@")
                self.driver.get(auth_url)
                BrowserManager.auto_fill_login(self.driver, username, password)
                time.sleep(2)
                self.driver.switch_to.default_content()

            # 切入菜单 Frame 并点击 Copier & Server -> Error Log
            self.log("正在寻找菜单...")
            try:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(0)
                
                # 先点击 Copier & Server 分区选项卡
                menu = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Copier & Server')]"))
                )
                self.driver.execute_script("arguments[0].click();", menu)
                time.sleep(0.5)
            except Exception:
                self.log(f"⚠️ 菜单点击遇到小问题 (尝试继续)")

            # 点击 Error Log 链接
            self.log("正在寻找 Error Log 链接...")
            log_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Error Log')]"))
            )
            self.driver.execute_script("arguments[0].click();", log_link)
            self.log("🖱️ 已点击 Error Log")
            
            # 切入 mainFrame 等待列表页加载
            self.log("等待列表页加载...")
            self.driver.switch_to.default_content()
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            
        except Exception as e:
            self.log(f"❌ 登录或导航过程出错: {e}")
            raise e

    def scan_tasks(self):
        """
        全量扫描任务...
        """
        self.log("\n📥 [阶段一] 全量扫描任务...")
        self.driver.switch_to.default_content() 
        try:
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            self.driver.switch_to.frame("mainFrame")
        except:
            self.log("⚠️ 警告：找不到 mainFrame")

        try:
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        except TimeoutException:
            pass
            
        all_rows = self.driver.find_elements(By.TAG_NAME, "tr")
        self.log(f"🔎 正在分析 {len(all_rows)} 行数据...")
        
        unique_tasks = {}
        for row in all_rows:
            try:
                row_text = row.text
                if "records" in row_text.lower():
                    ip_match = re.search(r'(10\.\d{1,3}\.\d{1,3}\.\d{1,3})', row_text)
                    count_match = re.search(r'(\d+)\s*records', row_text, re.IGNORECASE)
                    
                    if ip_match and count_match:
                        found_ip = ip_match.group(1)
                        count = int(count_match.group(1))
                        unique_tasks[found_ip] = {'ip': found_ip, 'count': count}
            except: continue
            
        return list(unique_tasks.values())

    def process_single_ip(self, ip, count):
        """
        单兵干员：直接访问数据弹出窗口 URL 并抓取表格写入 txt
        """
        url_param = ip[3:] if ip.startswith("10.") and len(ip) > 7 else ip
        direct_url = f"http://{self.auth_user}:{self.auth_pass}@{urlparse(self.base_url).hostname}/ubah/check_ap/system_tool/check_error_log_popup.php?serverap={url_param}"
        
        self.driver.get(direct_url)
        
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr")) >= min(3, count + 1)
            )
        except TimeoutException:
            pass
            
        # 使用 execute_script 单次瞬时提取表格全部文本，彻底消除几百次 WebDriver HTTP 网络往返通信延迟 (提速 500x)
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
                    if (errorMsg && errorMsg.indexOf("Error Message") === -1) {
                        res.push([noTxt, dateTxt, compTxt, errorMsg]);
                    }
                }
            }
            return res;
        """)

        server_logs = {}
        for item in (table_data or []):
            no_txt, date_txt, comp_txt, error_msg = item
            if error_msg not in server_logs:
                formatted_line = f"{no_txt}\t{date_txt}\t{comp_txt}\t{error_msg}\n"
                server_logs[error_msg] = formatted_line
        
        if server_logs:
            with open(self.output_file, "a", encoding="utf-8") as f:
                header = f"No\tDate\tCompany\tError Message ( {ip} )\n"
                f.write(header)
                for line in server_logs.values():
                    f.write(line)
                f.write("\n")
            self.log(f"   -> ✅ 已保存 {len(server_logs)} 条")
        else:
            self.log("   -> (无内容)")

    def run(self, username, password):
        """
        ================================================================================
        [核心抓取导出循环 - 完全复刻经典 bot.py 稳定版]
        ================================================================================
        """
        self.success = False
        final_tasks = []
        try:
            self.login_and_navigate(username, password)
            if not self.processed_ips:
                self.load_progress()
            
            if not self.output_file.exists():
                 with open(self.output_file, "w", encoding="utf-8") as f:
                    pass 

            final_tasks = self.scan_tasks()
            self.log(f"共发现 {len(final_tasks)} 个任务")
        except Exception as e:
            self.log(f"程序停止 (原因: {e})")
            return False

        self.log(f"\n[阶段二] 开始抓取...")
        
        i = 0
        while i < len(final_tasks):
            if self.stop_flag: break
            
            task = final_tasks[i]
            ip = task['ip']
            count = task['count']

            if ip in self.processed_ips:
                i += 1 
                continue

            self.log(f"[{i+1}/{len(final_tasks)}] 处理: {ip} ({count} 条)")
            
            if count > self.max_record_limit:
                self.log(f"⚠️ 跳过 {ip}: >10k")
                if self.skipper: self.skipper(ip, count)
                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(f"!!! SKIPPED Server {ip}: Too many records ({count}) !!!\n\n")
                self.processed_ips.add(ip)
                i += 1
                continue 

            try:
                self.process_single_ip(ip, count)
                self.processed_ips.add(ip)
                self.log(f"⏳ (冷却) 休息 1 秒...")
                time.sleep(1)
                i += 1

            except (WebDriverException, ConnectionError) as e:
                self.log(f"🔥 浏览器连接断开! 正在尝试重启恢复...")
                try:
                    self.login_and_navigate(username, password)
                    self.log("✅ 恢复成功，继续处理当前 IP...")
                except Exception as restart_err:
                    self.log(f"❌ 重启失败: {restart_err}。终止程序。")
                    break
            except Exception as e:
                self.log(f"❌ 未知错误: {e}")
                self.processed_ips.add(ip)
                i += 1

        self.log(f"\n🎉 全部完成！文件: {self.output_file}")
        # 不执行 driver.quit()！浏览器是与 Checkpoint 共享的，
        # 只需切回系统主页，方便下一个功能模块无缝继续使用。
        if self.driver:
            try:
                self.driver.switch_to.default_content()
                self.driver.get(f"http://{self.auth_user}:{self.auth_pass}@{urlparse(self.base_url).hostname}/ubah/index.php?p=main_system")
            except Exception:
                pass
        self.success = True
        return True
