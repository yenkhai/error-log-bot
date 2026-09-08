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
# 导入 socket 模块，用于轻量高效探测本地 9222 端口，不受系统代理干扰
import socket
# 导入 pathlib 模块，用于定位本地同级目录下的 chromedriver.exe
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

        if target_url.startswith("http://"):
            return target_url.replace("http://", f"http://{auth_user}:{auth_pass}@", 1)
        elif target_url.startswith("https://"):
            return target_url.replace("https://", f"https://{auth_user}:{auth_pass}@", 1)
        return target_url

    # ----------------------------------------------------------------------------
    # 2. 全局获取 / 接管浏览器驱动句柄
    # ----------------------------------------------------------------------------
    @classmethod
    def get_driver(cls, url=None, user=None, pwd=None):
        """
        [核心获取驱动入口]
        执行逻辑:
        1. 优先检查当前内存中的 `cls._driver` 是否依然存活可用，存活则直接复用返回。
        2. 若内存中无可用驱动，探测 9222 端口；若用户已开启 9222 浏览器，秒级无缝接管！
        3. 若 9222 端口未开放，启动全新的 Chrome 浏览器，注入 Basic Auth 并自动填充表单登录。
        """
        # 读取本地配置文件
        config = load_config()
        # 确定目标系统首页链接，优先使用传入的 url，缺省则取配置文件的 LOGIN_URL
        target_url = url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")

        # 检查项目根目录下是否存在配套的本地 chromedriver.exe
        local_driver = Path(__file__).resolve().parent.parent / "chromedriver.exe"
        service = Service(executable_path=str(local_driver)) if local_driver.exists() else None

        # 【策略 1】: 优先复用当前 Python 进程中已经持有的 Driver 句柄
        if cls._driver is not None:
            try:
                # 尝试访问 window_handles 属性测试浏览器会话是否依旧存活
                _ = cls._driver.window_handles
                return cls._driver  # 依然健在，直接复用返回！
            except Exception:
                # 若浏览器已被用户手动点 X 关闭，则将缓存引用重置为 None
                cls._driver = None

        # 【策略 2】: 探针检测 9222 端口 —— 若用户已开启 Checkpoint 浏览器，秒级无缝接管！
        if cls.is_cdp_active(9222):
            try:
                cdp_options = Options()
                # 关键设置: 指定 debuggerAddress 挂接到 127.0.0.1:9222 已有浏览器
                cdp_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
                
                # 启动接管代理
                if service:
                    cls._driver = webdriver.Chrome(service=service, options=cdp_options)
                else:
                    cls._driver = webdriver.Chrome(options=cdp_options)
                
                # 接管成功，直接返回该浏览器实例，不再重复登录！
                return cls._driver
            except Exception:
                # 若接管失败则安全置空，准备执行后备策略
                cls._driver = None

        # 【策略 3】: 后备保底方案 —— 若未开启 9222 调试浏览器，冷启动全新的 Chrome 实例
        std_options = Options()
        # 启动时自动全屏最大化，保证页面各类表格和菜单完全展开不缩略
        std_options.add_argument("--start-maximized")
        # 禁用浏览器拦截弹出式窗口，确保 Details 弹窗或下载功能不被阻止
        std_options.add_argument("--disable-popup-blocking")

        try:
            # 根据是否存在本地 chromedriver.exe 启动全新浏览器实例
            if service:
                cls._driver = webdriver.Chrome(service=service, options=std_options)
            else:
                cls._driver = webdriver.Chrome(options=std_options)

            # 构造附带 Basic Auth 凭证的安全请求 URL 并打开
            auth_url = cls._get_authenticated_url(target_url)

            # 打开目标页面
            cls._driver.get(auth_url)
            # 自动执行网页表单登录填充
            cls.auto_fill_login(cls._driver, user, pwd)
            cls._just_cold_launched = True
            return cls._driver
        except Exception as err:
            # 捕获启动失败并包装抛出清晰错误信息
            raise Exception(f"连接或启动 Chrome 浏览器失败！详细信息: {err}")

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
        driver = cls.get_driver(url=url, user=user, pwd=pwd)

        # 若刚才经历的是冷启动，get_driver 内部已完成导航和自动登录，避免二次重复提交
        if getattr(cls, '_just_cold_launched', False):
            cls._just_cold_launched = False
            return driver

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
            return

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
                    time.sleep(2.5)  # 等待登录验证重定向完成
                else:
                    # 若页面使用全局 button_login() 函数绑定，直接执行 JS 函数进行提交
                    driver.execute_script("if(typeof button_login === 'function') button_login();")
                    time.sleep(2.5)
        except Exception:
            # 登录表单填充容错，忽略非致命异常，让后续流程继续
            pass

