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
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

from config import load_config
from core.browser import BrowserManager

class ErrorLogScraperService:
    """Error Log 自动化抓取与导出引擎"""

    def __init__(self, ui_logger=None, ui_skipper=None):
        self.driver = None
        self.logger = ui_logger  # 左侧 Terminal 日志回调
        self.skipper = ui_skipper # 右侧 >10k 跳过记录回调
        self.stop_flag = False
        self.processed_ips = set() # 已处理完毕的 IP 集合 (用于断点续传)
        self.success = False

        # 从全局 config 加载 URL 与鉴权配置
        config = load_config()
        self.login_url = config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")
        self.auth_user = config.get("AUTH_USER", "bersih")
        self.auth_pass = config.get("AUTH_PASS", "bersih428")
        self.max_record_limit = config.get("MAX_RECORD_LIMIT", 10000) # >10k 安全阈值

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
        """执行后台登录并自动跳转至 Error Log 页面"""
        self.log(f"[START] 获取浏览器实例... 账号: {username}")
        try:
            # 统一使用 BrowserManager 获取浏览器，共享免登录状态！
            self.driver = BrowserManager.get_driver(user=username, pwd=password)
            
            self.log("正在寻找菜单...")
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "frameset")))
            self.driver.switch_to.default_content()
            
            try:
                self.driver.switch_to.frame(0)
                menu = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Copier & Server')]"))
                )
                self.driver.execute_script("arguments[0].click();", menu)
            except Exception:
                self.log(f"⚠️ 菜单点击遇到小问题 (尝试继续)")

            self.log("正在寻找 Error Log 链接...")
            log_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Error Log')]"))
            )
            self.driver.execute_script("arguments[0].click();", log_link)
            self.log("🖱️ 已点击 Error Log")
            
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
        direct_url = f"http://{self.auth_user}:{self.auth_pass}@10.16.250.9/ubah/check_ap/system_tool/check_error_log_popup.php?serverap={url_param}"
        
        self.driver.get(direct_url)
        
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr")) >= min(3, count + 1)
            )
        except TimeoutException:
            pass
            
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr")

        server_logs = {}
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 4:
                no_txt = cells[0].text.strip()
                date_txt = cells[1].text.strip()
                comp_txt = cells[2].text.strip()
                error_msg = cells[3].text.strip()
                
                if error_msg and "Error Message" not in error_msg:
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
        if self.driver:
            try: self.driver.quit()
            except: pass
        self.success = True
        return True
