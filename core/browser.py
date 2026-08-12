import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config import load_config

class BrowserManager:
    """
    ================================================================================
    [浏览器驱动管理器] (BrowserManager - 标准自动巡检版)
    --------------------------------------------------------------------------------
    作用:
    1. 负责自动启动全屏 Chrome 巡检实例，并导航至目标系统登录页。
    2. 自动进行账号密码静默填充与提交，保证巡检全自动化高效运行。
    3. 支持单例模式，同一巡检生命周期内复用 Driver 实例。
    ================================================================================
    """
    _driver = None

    @classmethod
    def get_driver(cls, url=None, user=None, pwd=None):
        config = load_config()
        target_url = url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")

        local_driver = Path.cwd() / "chromedriver.exe"
        service = Service(executable_path=str(local_driver)) if local_driver.exists() else None

        # 1. 优先复用当前 Python 进程已有的 Driver 句柄
        if cls._driver is not None:
            try:
                _ = cls._driver.window_handles
                return cls._driver
            except Exception:
                cls._driver = None

        # 2. 启动标准的 Chrome 巡检实例
        std_options = Options()
        std_options.add_argument("--start-maximized")
        std_options.add_argument("--disable-popup-blocking")
        
        try:
            if service:
                cls._driver = webdriver.Chrome(service=service, options=std_options)
            else:
                cls._driver = webdriver.Chrome(options=std_options)

            auth_user = config.get("AUTH_USER", "bersih")
            auth_pass = config.get("AUTH_PASS", "bersih428")

            if target_url.startswith("http://"):
                auth_url = target_url.replace("http://", f"http://{auth_user}:{auth_pass}@")
            elif target_url.startswith("https://"):
                auth_url = target_url.replace("https://", f"https://{auth_pass}@")
            else:
                auth_url = target_url

            cls._driver.get(auth_url)
            cls.auto_fill_login(cls._driver, user, pwd)
            return cls._driver
        except Exception as err:
            raise Exception(f"启动 Chrome 浏览器失败！详细信息: {err}")

    @classmethod
    def auto_fill_login(cls, driver, user=None, pwd=None):
        """精准登录表单填充函数"""
        if not user or not pwd:
            return

        try:
            driver.switch_to.default_content()
            
            user_inputs = (
                driver.find_elements(By.ID, "id_username") or 
                driver.find_elements(By.NAME, "fr_username") or 
                driver.find_elements(By.NAME, "fr_user") or 
                driver.find_elements(By.XPATH, "//input[@type='text']")
            )

            pass_inputs = (
                driver.find_elements(By.NAME, "fr_password") or 
                driver.find_elements(By.ID, "fr_password") or 
                driver.find_elements(By.XPATH, "//input[@type='password']")
            )

            if user_inputs and pass_inputs:
                u_el = user_inputs[0]
                p_el = pass_inputs[0]

                u_el.clear()
                u_el.send_keys(user)
                p_el.clear()
                p_el.send_keys(pwd)

                submits = (
                    driver.find_elements(By.ID, "id_save_button") or 
                    driver.find_elements(By.XPATH, "//a[contains(@onclick, 'button_login') or contains(@class, 'submit')]") or 
                    driver.find_elements(By.XPATH, "//a[contains(text(), 'Login') or contains(text(), '登入')]") or 
                    driver.find_elements(By.XPATH, "//input[@type='submit']")
                )

                if submits:
                    driver.execute_script("arguments[0].click();", submits[0])
                    time.sleep(2.5)
                else:
                    driver.execute_script("if(typeof button_login === 'function') button_login();")
                    time.sleep(2.5)
        except Exception:
            pass
