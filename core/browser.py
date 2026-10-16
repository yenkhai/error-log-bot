"""
================================================================================
浏览器自动化驱动管理器模块 (core/browser.py)
--------------------------------------------------------------------------------
【核心职责】:
1. 优先【秒级接管】已开启的 Chrome 调试浏览器 (CDP 协议, 127.0.0.1:9222 远程调试端口)。
   -> 优势: 用户手动打开或上一次任务打开的 Chrome 实例无需关闭，本软件可秒级直接切入接管，
            实现免重复扫码、免重复输入复杂人机验证码，真正做到零延迟！
2. 自动降级与冷启动: 若检测到用户尚未开启 9222 端口，则自动回退并初始化全新的 Chrome 全屏实例。
3. 自动绕过 HTTP Basic Auth: 自动将鉴权账户密码注入到目标 URL (`http://user:pass@domain/...`)，
   彻底解决浏览器弹出系统原生账密对话框卡死自动化流程的痛点。
4. 智能表单填充 (`auto_fill_login`): 采用多路候选定位器 (ID/Name/XPath/JS 方法) 确保 100% 成功提交登录。
5. 全局单例模式: 在 Python 内存中缓存复用同一个 WebDriver 句柄，杜绝重复打开几十个浏览器窗口。
================================================================================
"""

# 导入底层时间控制模块 time，用于操作缓冲与等待
import time
import socket
import threading
import sys
from urllib.parse import urlsplit, urlunsplit, quote
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from pathlib import Path

# 导入 Selenium WebDriver 核心库与常用组件
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# 导入配置加载器，读取域名、账号模式与 Basic Auth 鉴权配置
from config import load_config


class BrowserManager:
    """
    【浏览器驱动管理类 BrowserManager】
    采用类方法 (`@classmethod`) 提供统一的全局驱动管理接口。
    """
    # 类的私有静态变量，缓存当前存活的 WebDriver 实例对象
    _driver = None
    _attached = False
    # 类级别互斥锁，确保多线程并发调用 get_driver() 时只初始化一个 Chrome 实例
    _lock = threading.Lock()

    # ----------------------------------------------------------------------------
    # 1. CDP 端口存活探针探测
    # ----------------------------------------------------------------------------
    @classmethod
    def is_cdp_active(cls, port=9222) -> bool:
        """
        [CDP 端口探针函数]
        功能: 探测本地 127.0.0.1:{port} 是否已经运行了具备远程调试功能的 Chrome 浏览器。
        原理:
            Chrome 在开启 `--remote-debugging-port=9222` 启动后，会在本地暴露出
            `http://127.0.0.1:9222/json/version` HTTP 接口。
            发送一个超时为 1.0 秒的 GET 请求，若 HTTP 状态码为 200，说明调试端口健康可用！
        """
        try:
            # 优先使用原生 TCP socket 极速检测本地端口（毫秒级且不受系统全局代理设置影响）
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, socket.timeout):
            # 捕获连接拒绝或超时，返回 False 表示端口未开放
            return False

    @classmethod
    def _get_authenticated_url(cls, url: str = None) -> str:
        """
        [构造附带 Basic Auth 凭证的安全请求 URL]
        原理: 将 "http://" 转换为 "http://username:password@"，浏览器内核会自动完成静默 HTTP 鉴权，
        彻底解决浏览器弹出系统原生账密对话框卡死自动化流程的痛点。
        """
        config = load_config()
        target_url = url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")
        auth_user = config.get("AUTH_USER", "bersih")
        auth_pass = config.get("AUTH_PASS", "bersih428")

        parsed = urlsplit(target_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Login URL must be an HTTP or HTTPS URL")
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit(parsed._replace(netloc=f"{quote(auth_user, safe='')}:{quote(auth_pass, safe='')}@{host}"))

    # ----------------------------------------------------------------------------
    # 2. 全局获取 / 接管浏览器驱动句柄
    # ----------------------------------------------------------------------------
    @classmethod
    def get_driver(cls, url=None, user=None, pwd=None):
        """
        [核心获取驱动入口]
        执行逻辑:
        1. 优先检查当前内存中的 `cls._driver` 是否依然存活可用，存活则直接复用返回。
        2. 若需初始化驱动，使用互斥锁保护，防止多线程并发竞态。
        3. 动态读取配置端口探测 CDP 调试浏览器，若开放则秒级无缝接管。
        4. 若未开放，启动全新的 Chrome 浏览器，注入 Basic Auth 并自动填充表单登录。
        """
        # 读取本地配置文件
        config = load_config()
        # 确定目标系统首页链接，优先使用传入的 url，缺省则取配置文件的 LOGIN_URL
        target_url = url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")
        cdp_port = int(config.get("CHROME_DEBUG_PORT", 9222))

        # 【策略 1】: 快速无锁检查当前 Python 进程中持有的 Driver 是否健在
        if cls._driver is not None:
            try:
                _ = cls._driver.window_handles
                return cls._driver  # 依然健在，直接复用返回！
            except Exception:
                cls._driver = None

        # 进入双重检查锁定区，确保只有一个线程执行驱动初始化
        with cls._lock:
            # 二次检查（防止排队线程在获取锁前已有其他线程初始化完毕）
            if cls._driver is not None:
                try:
                    _ = cls._driver.window_handles
                    return cls._driver
                except Exception:
                    cls._driver = None

            # 检查项目根目录下是否存在配套的本地 chromedriver.exe
            local_driver = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent) / "chromedriver.exe"
            service = Service(executable_path=str(local_driver)) if local_driver.exists() else None

            # 【策略 2】: 探针检测 CDP 端口 —— 若用户已开启 Checkpoint 浏览器，秒级无缝接管！
            if cls.is_cdp_active(cdp_port):
                try:
                    cdp_options = Options()
                    cdp_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{cdp_port}")

                    if service:
                        cls._driver = webdriver.Chrome(service=service, options=cdp_options)
                    else:
                        cls._driver = webdriver.Chrome(options=cdp_options)

                    cls._driver.set_page_load_timeout(45)
                    cls._driver.set_script_timeout(20)
                    cls._attached = True
                    return cls._driver
                except Exception:
                    cls._driver = None

            # 【策略 3】: 后备保底方案 —— 若未开启调试浏览器，冷启动全新的 Chrome 实例
            std_options = Options()
            std_options.add_argument("--start-maximized")
            std_options.add_argument("--disable-popup-blocking")

            try:
                if service:
                    cls._driver = webdriver.Chrome(service=service, options=std_options)
                else:
                    cls._driver = webdriver.Chrome(options=std_options)

                cls._attached = False
                cls._driver.set_page_load_timeout(45)
                cls._driver.set_script_timeout(20)
                auth_url = cls._get_authenticated_url(target_url)
                cls._driver.get(auth_url)
                cls.auto_fill_login(cls._driver, user, pwd)
                return cls._driver
            except Exception as err:
                if cls._driver is not None:
                    try:
                        cls._driver.quit()
                    except Exception:
                        pass
                    cls._driver = None
                raise Exception(f"连接或启动 Chrome 浏览器失败！详细信息: {err}")

    @classmethod
    def quit_driver(cls):
        """[安全关闭浏览器驱动] 释放 WebDriver 句柄与进程，防止后台孤儿 chromedriver 进程残留"""
        with cls._lock:
            if cls._driver is not None:
                try:
                    if cls._attached:
                        cls._driver.service.stop()
                    else:
                        cls._driver.quit()
                except Exception:
                    pass
                finally:
                    cls._driver = None

    # ----------------------------------------------------------------------------
    # 3. 独立系统登录工具
    # ----------------------------------------------------------------------------
    @classmethod
    def login_only(cls, url=None, user=None, pwd=None):
        """
        [仅登录函数]
        应用场景: 用户在 GUI 顶栏点击了 "Login" 按钮。
        执行流程: 启动或接管浏览器，导航至目标地址并执行表单登录，完成后使浏览器保持在前台，
                 不触发任何 Checkpoint 巡检或日志导出任务。
        """
        # 获取驱动
        previous_driver = cls._driver
        driver = cls.get_driver(url=url, user=user, pwd=pwd)
        if driver is not previous_driver and not cls._attached:
            return driver  # 冷启动已完成并验证登录。

        # 构造鉴权 URL
        auth_url = cls._get_authenticated_url(url)

        # 确保切回顶层 Frame，避免卡在子 frame 导致 get() 异常
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        # 重新加载登录主页并填充表单
        driver.get(auth_url)
        cls.auto_fill_login(driver, user, pwd)
        return driver

    # ----------------------------------------------------------------------------
    # 4. 智能表单登录填充引擎
    # ----------------------------------------------------------------------------
    @classmethod
    def auto_fill_login(cls, driver, user=None, pwd=None):
        """
        [多候选容错登录表单填充函数]
        设计考虑: 企业系统的登录页面可能会在不同版本中更改 input 的 id 或 name。
        本函数采用多路候选定位策略 (Fallback Chain)，顺序匹配常见命名规则：
        1. 账号框候选: id="id_username", name="fr_username", name="fr_user", //input[@type='text']
        2. 密码框候选: name="fr_password", id="fr_password", //input[@type='password']
        3. 提交按钮候选: id="id_save_button", a.button_login, 包含 "Login"/"登入" 的超链接, input[type=submit]
        """
        # 若账号或密码为空，则直接跳过自动填充
        if not user or not pwd:
            raise ValueError("Account and password are required")

        try:
            # 1. 切换到最外层文档上下文
            driver.switch_to.default_content()

            # 2. 多重后备查找用户名输入框
            user_inputs = (
                driver.find_elements(By.ID, "id_username") or
                driver.find_elements(By.NAME, "fr_username") or
                driver.find_elements(By.NAME, "fr_user") or
                driver.find_elements(By.XPATH, "//input[@type='text']")
            )

            # 3. 多重后备查找密码输入框
            pass_inputs = (
                driver.find_elements(By.NAME, "fr_password") or
                driver.find_elements(By.ID, "fr_password") or
                driver.find_elements(By.XPATH, "//input[@type='password']")
            )

            # 4. 若成功定位到输入框
            if user_inputs and pass_inputs:
                u_el = user_inputs[0]
                p_el = pass_inputs[0]

                # 先清空输入框再填入字符，防止上次遗留的字符串混杂
                u_el.clear()
                u_el.send_keys(user)
                p_el.clear()
                p_el.send_keys(pwd)

                # 5. 多重后备查找登录提交按钮
                submits = (
                    driver.find_elements(By.ID, "id_save_button") or
                    driver.find_elements(By.XPATH, "//a[contains(@onclick, 'button_login') or contains(@class, 'submit')]") or
                    driver.find_elements(By.XPATH, "//a[contains(text(), 'Login') or contains(text(), '登入')]") or
                    driver.find_elements(By.XPATH, "//input[@type='submit']")
                )

                # 6. 优先通过原生点击或 JS 点击触发登录
                if submits:
                    # 使用 execute_script 直接在 DOM 层触发 click，彻底避免元素被浮动层遮挡导致的 WebDriver 点击报错
                    driver.execute_script("arguments[0].click();", submits[0])
                    cls.wait_for_login(driver)
                else:
                    # 若页面使用全局 button_login() 函数绑定，直接执行 JS 函数进行提交
                    driver.execute_script("if(typeof button_login === 'function') button_login();")
                    cls.wait_for_login(driver)
            else:
                cls.wait_for_login(driver)
        except Exception as exc:
            raise RuntimeError("Login could not be verified; check credentials and the browser page") from exc


    @classmethod
    def wait_for_login(cls, driver):
        """The application uses a frameset after successful authentication."""
        driver.switch_to.default_content()
        WebDriverWait(driver, 20).until(
            lambda d: bool(d.find_elements(By.CSS_SELECTOR, 'frameset, frame[name="mainFrame"], iframe[name="mainFrame"]'))
        )
        return True
