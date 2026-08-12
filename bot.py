# ==============================================================================
# 📌 第一部分：导入工具箱 (Import Modules)
# ==============================================================================
import json                 # 用于读取和保存 JSON 格式的配置文件 (config.json)
import os                   # 用于处理操作系统的文件和目录（虽然后面主要用了 pathlib，但保留以防万一）
import time                 # 用于控制程序的休眠/等待时间 (例如 time.sleep)
import re                   # 正则表达式模块，用于从复杂的字符串中精准提取 IP 地址和记录条数
import threading            # 多线程模块，用于把爬虫逻辑放在后台运行，防止前台 UI 界面卡死
from pathlib import Path    # 现代化的路径处理库，用来替代老旧的 os.path 拼接，更加安全优雅
from datetime import datetime, timedelta # 日期和时间处理模块，用于计算“昨天”的日期
import tkinter.messagebox as messagebox # 引入 tkinter 的弹窗模块（因为 CustomTkinter 没有自带的系统弹窗）

# --- Modern UI (CustomTkinter) ---
import customtkinter as ctk # 引入现代化 UI 库，用于绘制高级感、带圆角和深色主题的图形界面

# --- Selenium 相关库 (浏览器的自动化遥控器) ---
from selenium import webdriver  
from selenium.webdriver.common.by import By # 用于通过 ID、XPath、CSS 选择器等方式定位网页元素
from selenium.webdriver.chrome.service import Service # 用于配置和启动 ChromeDriver 服务
from selenium.webdriver.support.ui import WebDriverWait # 用于实现智能等待 (直到页面某个元素加载出来为止)
from selenium.webdriver.support import expected_conditions as EC # 配合 WebDriverWait 使用，定义各种等待条件
from selenium.common.exceptions import WebDriverException, TimeoutException # 捕获浏览器崩溃、网络断开或超时等异常

# ==============================================================================
# 📌 全局 UI 主题设置
# ==============================================================================
ctk.set_appearance_mode("Dark")      # 强制设置界面为暗黑模式 (支持 "System", "Dark", "Light")
ctk.set_default_color_theme("blue")  # 设置按钮和高亮的主题颜色为蓝色 (支持 "blue", "green", "dark-blue")

# ==============================================================================
# 📌 第二部分：全局配置 (Global Configuration)
# ==============================================================================
CONFIG_FILE = Path("config.json") # 定义配置文件的存放路径

# 如果配置文件不存在，这就是默认会写入的参数
DEFAULT_CONFIG = {
    "LOGIN_URL": "http://10.16.250.9/ubah/index.php?", # 登录网站的地址
    "AUTH_USER": "bersih",                             # 用于绕过 Basic Auth (弹窗验证) 的默认账号
    "AUTH_PASS": "bersih428",                          # 用于绕过 Basic Auth (弹窗验证) 的默认密码
    "MAX_RECORD_LIMIT": 10000                          # 最大记录数限制，超过这个数值的 IP 会被直接跳过
}

def load_config() -> dict:
    """读取 config.json 配置文件，如果没有则自动创建一个默认的。"""
    if not CONFIG_FILE.exists(): # 检查文件是否存在
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4) # 写入默认配置，并格式化缩进
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f) # 如果存在，则尝试读取其中的 JSON 数据
    except Exception:
        # 如果文件损坏或读取失败，退回到使用默认配置
        return DEFAULT_CONFIG

# 将读取到的配置保存到变量中供后续使用
config = load_config()
LOGIN_URL = config.get("LOGIN_URL", DEFAULT_CONFIG["LOGIN_URL"])
AUTH_USER = config.get("AUTH_USER", DEFAULT_CONFIG["AUTH_USER"])
AUTH_PASS = config.get("AUTH_PASS", DEFAULT_CONFIG["AUTH_PASS"])
MAX_RECORD_LIMIT = config.get("MAX_RECORD_LIMIT", DEFAULT_CONFIG["MAX_RECORD_LIMIT"])

# ==============================================================================
# 📌 第三部分：自动计算文件名与路径
# ==============================================================================
# 1. 获取当前时间，减去 1 天，得到“昨天”的时间
yesterday = datetime.now() - timedelta(days=1)
# 2. 将昨天的日期格式化为 "日月" 的格式，例如 11 月 5 日 -> "0511"
date_str = yesterday.strftime("%d%m")
# 3. 拼接出最终保存的文件名
filename = f"error log {date_str}.txt"

# 4. 获取当前用户的桌面路径，并与文件名组合成完整的绝对路径
OUTPUT_FILE = Path.home() / "Desktop" / filename

# ==============================================================================
# 📌 第四部分：核心爬虫逻辑类 (The Brain)
# ==============================================================================
class ErrorLogScraper:
    def __init__(self, ui_logger, ui_skipper):
        """
        初始化爬虫对象。
        :param ui_logger: 传入的函数，用于将文字打印到 UI 的日志框中
        :param ui_skipper: 传入的函数，用于将跳过的 IP 显示到 UI 的警告框中
        """
        self.driver = None         # 存放浏览器实例的变量
        self.logger = ui_logger    # 绑定日志输出函数
        self.skipper = ui_skipper  # 绑定跳过输出函数
        self.stop_flag = False     # 控制是否中断爬虫的标志位 (点击停止按钮时会变成 True)
        self.processed_ips = set() # 存放已经处理过的 IP 地址，用于断点续传去重
        self.success = False       # 标记本次任务是否彻头彻尾地成功完成
    
    def load_progress(self):
        """断点续传功能：读取已存在的桌面日志文件，恢复之前已经做过的进度。"""
        if not OUTPUT_FILE.exists(): # 如果文件压根不存在，说明是全新运行，直接跳过
            return
        
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                content = f.read() # 读取文件所有内容
                
                # 使用正则表达式从文件内容中找回成功处理过的 IP 
                found_ips = re.findall(r'Error Message \( ([\d\.]+) \)', content)
                for ip in found_ips:
                    self.processed_ips.add(ip)
                
                # 同样把那些因为数量太多被跳过的 IP 也找回来
                skipped_ips = re.findall(r'SKIPPED Server ([\d\.]+):', content)
                for ip in skipped_ips:
                    self.processed_ips.add(ip)

            # 在日志中提醒用户已恢复的进度
            self.log(f"🔄 检测到旧文件，已恢复 {len(self.processed_ips)} 个任务进度")
        except Exception as e:
            self.log(f"⚠️ 读取进度失败: {e}")

    def log(self, msg: str):
        """统一日志函数：不仅在黑色控制台打印，还会实时推送到 UI 界面的文本框里。"""
        print(msg)
        if self.logger:
            self.logger(msg)

    def setup_driver(self):
        """初始化配置 Google Chrome 浏览器"""
        options = webdriver.ChromeOptions()
        # 设置浏览器偏好：关闭烦人的“保存密码”提示和浏览器通知
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--disable-popup-blocking") # 禁止浏览器拦截弹窗
        
        # 📌 离线包与自动下载双重保障机制
        # 尝试寻找与本程序放在同一个文件夹下的 chromedriver.exe 文件
        local_driver = Path.cwd() / "chromedriver.exe"
        
        try:
            if local_driver.exists():
                # 如果用户在同目录放了驱动，优先使用本地驱动 (适合没网的电脑)
                self.log("✅ 发现本地 chromedriver.exe，直接使用本地驱动...")
                service = Service(executable_path=str(local_driver))
                driver = webdriver.Chrome(service=service, options=options)
            else:
                # 如果没找到，则使用 Selenium 4 的原生能力自动联网下载并启动浏览器
                self.log("🌐 未发现本地驱动，尝试通过网络自动匹配您的 Chrome 版本...")
                driver = webdriver.Chrome(options=options)
                
            driver.maximize_window() # 将浏览器窗口最大化
            return driver
        except Exception as e:
            # 启动浏览器失败时的友好的错误排查提示
            self.log(f"❌ 浏览器驱动启动失败！原因: {e}")
            self.log("💡 解决办法 1：确保这台电脑上安装了正常的 Google Chrome 浏览器。")
            self.log("💡 解决办法 2：如果这台电脑没联网，请下载与该电脑 Chrome 版本一致的 chromedriver.exe，并把它和 bot.exe 放在同一个文件夹里！")
            raise e

    def login_and_navigate(self, username, password):
        """
        核心步骤 1：启动浏览器 -> 处理防呆系统 -> 登录系统 -> 点击进入 Error Log 列表页
        """
        self.log(f"🚀 启动浏览器... 登录账号: {username}")
        
        # 为了防止残留，如果旧的浏览器还在，先强制关掉它
        if self.driver:
            try: self.driver.quit()
            except: pass
            
        self.driver = self.setup_driver() # 召唤新的浏览器
        
        try:
            self.driver.set_page_load_timeout(15) # 设置网页最长容忍加载时间为 15 秒
            
            # 【凭证注入】将 http:// 替换为携带账号密码的格式，直接绕过烦人的弹窗
            if LOGIN_URL.startswith("http://"):
                auth_login_url = LOGIN_URL.replace("http://", f"http://{AUTH_USER}:{AUTH_PASS}@")
            elif LOGIN_URL.startswith("https://"):
                auth_login_url = LOGIN_URL.replace("https://", f"https://{AUTH_USER}:{AUTH_PASS}@")
            else:
                auth_login_url = LOGIN_URL
                
            # 访问附带凭证的链接
            self.driver.get(auth_login_url)
        except WebDriverException:
            # 打不开网页通常意味着没有连公司 VPN
            self.log("❌ 严重错误: 无法连接到公司网站！请检查 VPN。")
            messagebox.showerror("连接失败", "无法打开公司网站！\n请检查 VPN。")
            self.driver.quit()
            raise Exception("VPN Error") # 直接中断程序运行

        try:
            # --- 填写账号密码登录 ---
            # 智能等待：直到页面上出现 ID 为 "id_username" 的输入框
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "id_username"))).clear()
            self.driver.find_element(By.ID, "id_username").send_keys(username) # 输入账号
            
            self.driver.find_element(By.NAME, "fr_password").clear()
            self.driver.find_element(By.NAME, "fr_password").send_keys(password) # 输入密码
            
            self.log("点击登录...")
            self.driver.find_element(By.ID, "id_save_button").click() # 点击登录按钮
            
            # --- 跳转主界面并寻找菜单 ---
            self.log("正在寻找菜单...")
            # 智能等待：直到页面的主要框架架构 (frameset) 渲染出来
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "frameset")))
            self.driver.switch_to.default_content() # 切回最顶层网页结构

            try:
                # 网页套娃严重，需要先切入第 0 个 iframe (左侧菜单栏)
                self.driver.switch_to.frame(0)
                # 使用 XPath 模糊匹配找到名叫 'Copier & Server' 的菜单夹
                menu = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Copier & Server')]"))
                )
                # 利用 JavaScript 强制点击它（防止它被其他元素遮挡导致无法点击）
                self.driver.execute_script("arguments[0].click();", menu)
            except Exception:
                self.log(f"⚠️ 菜单点击遇到小问题 (尝试继续)")

            # --- 点击进入 Error Log ---
            self.log("正在寻找 Error Log 链接...")
            # 寻找包含 'Error Log' 文字的链接 a 标签
            log_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Error Log')]"))
            )
            self.driver.execute_script("arguments[0].click();", log_link) # 强制点击进去
            self.log("🖱️ 已点击 Error Log")
            
            # 智能等待列表页完全加载完毕 (等待 mainFrame 这个重要区块出现)
            self.log("等待列表页加载...")
            self.driver.switch_to.default_content()
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            
        except Exception as e:
            self.log(f"❌ 登录或导航过程出错: {e}")
            raise e # 如果出错，把锅甩出去让外面的总控管捕捉

    def scan_tasks(self):
        """
        核心步骤 2：充当侦察兵，全局扫视列表页，找出所有有记录的 IP 并存入计划表。
        """
        self.log("\n📥 [阶段一] 全量扫描任务...")
        self.driver.switch_to.default_content() 
        try:
            # 确保 mainFrame 加载完成，然后把视角切进去
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            self.driver.switch_to.frame("mainFrame")
        except:
            self.log("⚠️ 警告：找不到 mainFrame")

        # 智能等待：最起码表格的行 (tr) 要加载出来
        try:
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        except TimeoutException:
            pass # 如果超时还没刷出来，可能今天真的没数据，无视继续
            
        all_rows = self.driver.find_elements(By.TAG_NAME, "tr") # 把所有的表格行全部抓下来
        self.log(f"🔎 正在分析 {len(all_rows)} 行数据...")
        
        unique_tasks = {} # 使用字典来存放任务，自带去重效果
        for row in all_rows:
            try:
                row_text = row.text
                # 如果这一行的文字里面有 "records" 关键字，才说明它是我们要找的猎物 (加上 .lower() 防止网站改大小写)
                if "records" in row_text.lower():
                    # 用正则提取 IP (比如 10.x.x.x)
                    ip_match = re.search(r'(10\.\d{1,3}\.\d{1,3}\.\d{1,3})', row_text)
                    # 用正则提取记录的数量 (比如 125 records -> 提取出 125)
                    count_match = re.search(r'(\d+)\s*records', row_text, re.IGNORECASE)
                    
                    if ip_match and count_match:
                        found_ip = ip_match.group(1)
                        count = int(count_match.group(1))
                        # 记录到任务字典里
                        unique_tasks[found_ip] = {'ip': found_ip, 'count': count}
            except: continue # 如果某一行提取失败，不影响其他行，继续下一行
            
        return list(unique_tasks.values()) # 返回整理好的任务清单列表

    def run(self, username, password):
        """
        🏁 任务总指挥官：协调登录、扫描、执行等所有步骤。
        """
        self.success = False # 每次运行前，先把成功标志重置为 False
        final_tasks = []
        try:
            # 1. 尝试登录和跳转
            self.login_and_navigate(username, password)

            # 2. 如果这是第一次进来（processed_ips为空），先读取以前的文件看看有什么是做过的
            if not self.processed_ips:
                self.load_progress()
            
            # 3. 如果桌面上还不存在今天（昨天数据）的文件，就创建一个空的 txt 备用
            if not OUTPUT_FILE.exists():
                 with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    pass 

            # 4. 去列表页把今天要做的所有任务列一张表
            final_tasks = self.scan_tasks()
            self.log(f"共发现 {len(final_tasks)} 个任务")
        except Exception as e:
            # 如果前面这四步任何一步抛出异常（比如 VPN 断了），就中止整个计划
            self.log(f"程序停止 (原因: {e})")
            return False

        self.log(f"\n[阶段二] 开始抓取...")
        
        i = 0
        # 开始逐一处理任务清单里的内容
        while i < len(final_tasks):
            if self.stop_flag: break # 用户如果点击了停止，循环立即中断
            
            task = final_tasks[i]
            ip = task['ip']
            count = task['count']

            # 如果这个 IP 之前已经做过了，就直接跳过它
            if ip in self.processed_ips:
                i += 1 
                continue

            self.log(f"[{i+1}/{len(final_tasks)}] 处理: {ip} ({count} 条)")
            
            # ⚠️ 数量拦截保护机制
            if count > MAX_RECORD_LIMIT:
                self.log(f"⚠️ 跳过 {ip}: >10k")
                if self.skipper: self.skipper(ip, count) # 在 UI 右侧的警告框里加上记录
                # 写入文本文件作为备份提示
                with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                    f.write(f"!!! SKIPPED Server {ip}: Too many records ({count}) !!!\n\n")
                self.processed_ips.add(ip) # 标记为已处理，防止重做
                i += 1
                continue 

            try:
                # 把具体的 IP 交给单兵干员 (process_single_ip) 去抓取
                self.process_single_ip(ip, count)
                self.processed_ips.add(ip) # 抓取成功，加入已完成名单
                self.log(f"⏳ (冷却) 休息 1 秒...")
                time.sleep(1) # 略微休息，防止把服务器打死
                i += 1 # 只有成功做完，才进入下一个

            except (WebDriverException, ConnectionError) as e:
                # 如果在抓取中途浏览器崩了或者掉线了，尝试满血复活 (重启浏览器)
                self.log(f"🔥 浏览器连接断开! 正在尝试重启恢复...")
                try:
                    self.login_and_navigate(username, password)
                    self.log("✅ 恢复成功，继续处理当前 IP...")
                    # 这里不需要 i+=1，因为它会在下一轮循环再次挑战这个还没做完的 IP
                except Exception as restart_err:
                    self.log(f"❌ 重启失败: {restart_err}。终止程序。")
                    break # 连复活都失败了，只能彻底投降
            except Exception as e:
                # 遇到非网络类的未知错误，为了防止无限死循环，跳过该 IP
                self.log(f"❌ 未知错误: {e}")
                self.processed_ips.add(ip)
                i += 1

        # 全部循环结束，宣告胜利，关闭浏览器并标记为彻底成功
        self.log(f"\n🎉 全部完成！文件: {OUTPUT_FILE}")
        if self.driver:
            self.driver.quit()
        self.success = True
        return True

    def process_single_ip(self, ip, count):
        """
        核心步骤 3：特种兵单刀直入。
        根据 IP 组合出一个直达目标数据的隐藏 URL 并把它们抓取下来。
        """
        # 有些 IP 记录是以 10. 开头的冗余格式，需要清理一下提取出真实的尾号
        url_param = ip[3:] if ip.startswith("10.") and len(ip) > 7 else ip
        
        # 组装直达车 URL，不仅绕过繁琐的点击，还自带账号密码绕过验证弹窗
        direct_url = f"http://{AUTH_USER}:{AUTH_PASS}@10.16.250.9/ubah/check_ap/system_tool/check_error_log_popup.php?serverap={url_param}"
        
        self.driver.get(direct_url) # 访问组装好的 URL
        
        # 智能等待：记录条数越多，页面渲染越慢，所以最长给它 15 秒的时间
        # 只要表格出现的行数 >= 我们预期的 count（或者最少3行），就说明数据出来了
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr")) >= min(3, count + 1)
            )
        except TimeoutException:
            pass # 如果15秒还没出来完，也不报错，能抓多少抓多少
            
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr") # 获取所有渲染出的表格行

        server_logs = {} # 用字典暂存日志，顺便利用字典键值唯一的特性对重复数据进行去重
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td") # 找到一行中的所有单元格
            if len(cells) >= 4:
                # 获取前四列的文本内容，并剥离掉两端的空格
                no_txt = cells[0].text.strip()
                date_txt = cells[1].text.strip()
                comp_txt = cells[2].text.strip()
                error_msg = cells[3].text.strip()
                
                # 数据清洗：排除空数据或表格头部文字
                if error_msg and "Error Message" not in error_msg:
                    # 去重：如果同样的报错还没记录过，就存起来
                    if error_msg not in server_logs:
                        # 拼接成最终要写入 txt 的格式：各列之间用 \t (制表符) 隔开
                        formatted_line = f"{no_txt}\t{date_txt}\t{comp_txt}\t{error_msg}\n"
                        server_logs[error_msg] = formatted_line
        
        # 把收集到的干货全部一口气写入本地的 txt 文件中
        if server_logs:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                header = f"No\tDate\tCompany\tError Message ( {ip} )\n" # 写入标题行
                f.write(header)
                for line in server_logs.values():
                    f.write(line) # 写入具体数据
                f.write("\n") # 每个 IP 之间空一行，方便阅读
            self.log(f"   -> ✅ 已保存 {len(server_logs)} 条")
        else:
            self.log("   -> (无内容)")

# ==============================================================================
# 📌 第五部分：UI 界面类 (The Face)
# ==============================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Error Log Bot (v19.0 Modern UI)") # 设定窗口标题
        self.geometry("750x600") # 设定初始窗口的长宽
        
        # 配置网格布局权重，使得中间的日志区域可以随着窗口拉大而自动放大
        self.grid_rowconfigure(1, weight=1)  
        self.grid_columnconfigure(0, weight=1)
        
        self.scraper = None # 预留存放爬虫实例的变量

        # --- 1. 顶部区块：账号选择与输入 ---
        self.frame_top = ctk.CTkFrame(self) # 创建一个带底色的容器框
        self.frame_top.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        
        # 区块标题
        label_login = ctk.CTkLabel(self.frame_top, text="1. 账户登录", font=ctk.CTkFont(size=16, weight="bold"))
        label_login.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        self.account_var = ctk.StringVar(value="op35") # 用于记录当前选中的单选按钮
        
        # 单选按钮容器
        radio_frame = ctk.CTkFrame(self.frame_top, fg_color="transparent")
        radio_frame.grid(row=0, column=1, padx=15, pady=10, sticky="w")
        
        # 生成三个选项，一点就触发 self.update_inputs 自动填写密码
        ctk.CTkRadioButton(radio_frame, text="Default (op35)", variable=self.account_var, value="op35", command=self.update_inputs).pack(side="left", padx=5)
        ctk.CTkRadioButton(radio_frame, text="Default (op38)", variable=self.account_var, value="op38", command=self.update_inputs).pack(side="left", padx=5)
        ctk.CTkRadioButton(radio_frame, text="Custom Login", variable=self.account_var, value="custom", command=self.update_inputs).pack(side="left", padx=5)
        
        # 账号和密码输入框的容器
        input_frame = ctk.CTkFrame(self.frame_top, fg_color="transparent")
        input_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w")
        
        ctk.CTkLabel(input_frame, text="User:").pack(side="left", padx=(0, 5))
        self.entry_user = ctk.CTkEntry(input_frame, width=150)
        self.entry_user.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(input_frame, text="Pass:").pack(side="left", padx=(0, 5))
        self.entry_pass = ctk.CTkEntry(input_frame, width=150, show="*") # 密码框内容隐藏为*号
        self.entry_pass.pack(side="left")
        
        self.update_inputs() # 运行一次以填入默认的 op35 数据
        
        # --- 2. 中部区块：代码运行日志输出区 ---
        self.frame_mid = ctk.CTkFrame(self)
        self.frame_mid.grid(row=1, column=0, padx=15, pady=5, sticky="nsew")
        
        # 左侧比右侧宽一点，所以左边(0)给3倍权重，右边(1)给1倍权重
        self.frame_mid.grid_columnconfigure(0, weight=3) 
        self.frame_mid.grid_columnconfigure(1, weight=1)
        self.frame_mid.grid_rowconfigure(1, weight=1)
        
        # 正常运行时的日志黑框 (黑客绿字体)
        ctk.CTkLabel(self.frame_mid, text="运行日志 (Terminal)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        self.txt_log = ctk.CTkTextbox(self.frame_mid, fg_color="#1E1E1E", text_color="#00FF00", font=ctk.CTkFont(family="Consolas", size=13))
        self.txt_log.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # 数量超标被跳过 IP 的警告框 (警报红字体)
        ctk.CTkLabel(self.frame_mid, text="⚠️ 已跳过 (>10k)", font=ctk.CTkFont(weight="bold"), text_color="#FF4C4C").grid(row=0, column=1, padx=10, pady=(10, 0), sticky="w")
        self.txt_skip = ctk.CTkTextbox(self.frame_mid, fg_color="#1E1E1E", text_color="#FF4C4C", font=ctk.CTkFont(family="Consolas", size=13))
        self.txt_skip.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        self.txt_skip.configure(state="disabled") # 默认设为只读，不允许用户在框里乱敲
        
        # --- 3. 底部区块：按钮控制区 ---
        self.frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_btn.grid(row=2, column=0, padx=15, pady=(10, 15), sticky="ew")
        self.frame_btn.grid_columnconfigure(0, weight=1)
        self.frame_btn.grid_columnconfigure(1, weight=1)

        # 巨大的绿色开始按钮
        self.btn_start = ctk.CTkButton(self.frame_btn, text="▶ 开始执行 (断点续传 + VPN检测)", fg_color="#28A745", hover_color="#218838", font=ctk.CTkFont(size=15, weight="bold"), height=40, command=self.start_thread)
        self.btn_start.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # 巨大的红色停止按钮 (默认不可点)
        self.btn_stop = ctk.CTkButton(self.frame_btn, text="⏹ 停止", fg_color="#DC3545", hover_color="#C82333", font=ctk.CTkFont(size=15, weight="bold"), height=40, state="disabled", command=self.stop_thread)
        self.btn_stop.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    def update_inputs(self):
        """交互逻辑：点击不同单选按钮时，自动锁定或解锁账号密码输入框"""
        choice = self.account_var.get()
        if choice in ["op35", "op38"]:
            self.entry_user.configure(state="normal")
            self.entry_user.delete(0, "end")
            self.entry_user.insert(0, choice)
            self.entry_user.configure(state="disabled") # 填完就锁起来不让改
            
            self.entry_pass.configure(state="normal")
            self.entry_pass.delete(0, "end")
            self.entry_pass.insert(0, "123qwe")
            self.entry_pass.configure(state="disabled")
        else:
            # 如果是自定义选项，就打开输入框的限制，让用户自己敲
            self.entry_user.configure(state="normal")
            self.entry_pass.configure(state="normal")

    def log_to_ui(self, msg: str):
        """UI的后门：允许爬虫把信息插入到左边的绿色文本框里"""
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end") # 每次写新信息时，自动把滚动条拉到最底下

    def add_skipped_to_ui(self, ip: str, count: int):
        """UI的后门：允许爬虫把跳过的 IP 插入到右边的红色文本框里"""
        self.txt_skip.configure(state="normal") # 先解锁
        self.txt_skip.insert("end", f"{ip} ({count} Rec)\n")
        self.txt_skip.see("end")
        self.txt_skip.configure(state="disabled") # 重新锁上

    def start_thread(self):
        """当用户点击“开始”按钮时触发。为了防止抓取卡死主界面，我们开启多线程任务"""
        choice = self.account_var.get()
        # 获取最终用于登录的账号密码
        if choice == "op35":
            user = "op35"; pwd = "123qwe"
        elif choice == "op38":
            user = "op38"; pwd = "123qwe"
        else:
            user = self.entry_user.get(); pwd = self.entry_pass.get()
        
        if not user or not pwd:
            messagebox.showwarning("错误", "请输入账号和密码") # 防呆机制：没账号不准跑
            return

        # 按钮状态切换：开始变灰，停止变红可用
        self.btn_start.configure(state="disabled", text="⏳ 正在运行...")
        self.btn_stop.configure(state="normal")
        
        self.txt_log.delete("1.0", "end") # 每次点击开始都清空一下旧日志
        
        # 创建并启动后台干活的子线程 (daemon=True 意味着窗口关了它也会被强杀)
        t = threading.Thread(target=self.run_scraper, args=(user, pwd), daemon=True)
        t.start()
    
    def stop_thread(self):
        """当用户点击“停止”按钮时触发，将标志位变为 True，告诉后台线程下班"""
        if self.scraper:
            self.scraper.stop_flag = True
            self.log_to_ui("🛑 正在停止，请稍候...")
            self.btn_stop.configure(state="disabled") # 停止按过一次就灰掉，防连点

    def run_scraper(self, user, pwd):
        """这个函数是真正在后台子线程里跑的代码"""
        # 实例化爬虫大脑，并把 UI 上的文本插入功能授权给它
        self.scraper = ErrorLogScraper(self.log_to_ui, self.add_skipped_to_ui)
        # 让大脑开始干活，并且接受一个返回值代表是否彻头彻尾地成功了
        success = self.scraper.run(user, pwd)
        
        # 活干完了(不管成功失败)，把按钮的状态重置回默认
        self.btn_start.configure(state="normal", text="▶ 开始执行 (断点续传 + VPN检测)")
        self.btn_stop.configure(state="disabled")
        
        if self.scraper.stop_flag:
            self.log_to_ui("🚫 任务已手动停止。")
        elif success: 
            # 只有当 success 是 True 时（意味着没有半路被 VPN Error 掐断），才开心底宣告文件已保存
            messagebox.showinfo("完成", f"任务已结束！\n文件已保存为: {OUTPUT_FILE}")

# ==============================================================================
# 📌 程序总入口 (Main Entry)
# ==============================================================================
if __name__ == "__main__":
    app = App()      # 召唤主界面
    app.mainloop()   # 让主界面一直循环刷新保持显示，直到用户点击右上角的红叉叉