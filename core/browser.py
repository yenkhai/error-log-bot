"""
================================================================================
[浏览器驱动管理器] (core/browser.py)
--------------------------------------------------------------------------------
作用:
1. 优先秒级自动接管/连接已打开的 Checkpoint 浏览器 (CDP 端口 127.0.0.1:9222)。
2. 若未启动 9222 浏览器，则自动退回到启动全新的 Chrome 全屏实例。
3. 自动完成 Basic Auth 与静默登录表单提交。
4. 全局复用 Driver 句柄，避免重复打开窗口。
================================================================================
"""

import time
import urllib.request
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config import load_config


class BrowserManager:
    _driver = None

    @classmethod
    def is_cdp_active(cls, port=9222) -> bool:
        """测试本地 127.0.0.1:{port} 调试接口是否开放且存活"""
        try:
            url = f"http://127.0.0.1:{port}/json/version"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.0) as res:
                return res.status == 200
        except Exception:
            return False

    @classmethod
    def get_driver(cls, url=None, user=None, pwd=None):
        config = load_config()
        target_url = url or config.get("LOGIN_URL", "http://10.16.250.9/ubah/index.php?")

        local_driver = Path(__file__).resolve().parent.parent / "chromedriver.exe"
        service = Service(executable_path=str(local_driver)) if local_driver.exists() else None

        # 1. 优先复用当前 Python 进程已有的 Driver 句柄
        if cls._driver is not None:
            try:
                _ = cls._driver.window_handles
                return cls._driver
            except Exception:
                cls._driver = None

        # 2. 探针检测：若用户已开启 9222 Checkpoint 浏览器，秒级无缝接管！
        if cls.is_cdp_active(9222):
            try:
                cdp_options = Options()
                cdp_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
                if service:
                    cls._driver = webdriver.Chrome(service=service, options=cdp_options)
                else:
                    cls._driver = webdriver.Chrome(options=cdp_options)
                
                # 接管成功，直接返回已有浏览器实例
                return cls._driver
            except Exception:
                cls._driver = None

        # 3. 后备方案：若未开启 9222 浏览器，启动全新的 Chrome 实例
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
                auth_url = target_url.replace("https://", f"https://{auth_user}:{auth_pass}@")
            else:
                auth_url = target_url

            cls._driver.get(auth_url)
            cls.auto_fill_login(cls._driver, user, pwd)
            return cls._driver
        except Exception as err:
            raise Exception(f"连接或启动 Chrome 浏览器失败！详细信息: {err}")

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
