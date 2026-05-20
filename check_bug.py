import time
import re
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 🟢 配置区域 ---
LOGIN_URL = "http://10.16.250.9/ubah/index.php?"
USERNAME = "op35"
PASSWORD = "123qwe"
# ------------------

def setup_driver():
    options = webdriver.ChromeOptions()
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-popup-blocking")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.maximize_window()
    return driver

def login_and_navigate(driver):
    print("🚀 正在打开登录页面...")
    driver.get(LOGIN_URL)
    
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "id_username")))
    driver.find_element(By.ID, "id_username").clear()
    driver.find_element(By.ID, "id_username").send_keys(USERNAME)
    driver.find_element(By.NAME, "fr_password").clear()
    driver.find_element(By.NAME, "fr_password").send_keys(PASSWORD)
    
    print("点击登录...")
    driver.find_element(By.ID, "id_save_button").click()
    time.sleep(3) # 等待页面加载

    print("正在寻找菜单 'Copier & Server'...")
    driver.switch_to.default_content()
    try:
        driver.switch_to.frame(0)
        menu = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Copier & Server')]"))
        )
        driver.execute_script("arguments[0].click();", menu)
        print("✅ 菜单点击成功")
    except Exception as e:
        print(f"⚠️ 菜单点击遇到问题: {e}")

    print("正在寻找 Error Log 链接...")
    time.sleep(2)
    try:
        log_link = driver.find_element(By.XPATH, "//a[contains(text(), 'Error Log')]")
        driver.execute_script("arguments[0].click();", log_link)
        print("🖱️ 已点击 Error Log")
        
        # 处理 Bersih 验证
        print("🤖 (键盘模拟) 输入 Bersih 验证信息...")
        time.sleep(2)
        pyautogui.write("bersih")
        time.sleep(0.5)
        pyautogui.press('tab')
        time.sleep(0.5)
        pyautogui.write("bersih428")
        time.sleep(0.5)
        pyautogui.press('enter')
        
        print("等待列表页加载...")
        time.sleep(5)
    except Exception as e:
        print(f"❌ 导航失败: {e}")

def check_list_only():
    driver = setup_driver()
    try:
        login_and_navigate(driver)
        
        print("\n🔎 [侦察模式] 开始扫描页面上的服务器...")
        driver.switch_to.default_content() 
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
            driver.switch_to.frame("mainFrame")
            print("✅ 进入 mainFrame")
        except:
            print("⚠️ 警告：找不到 mainFrame")

        # --- 核心逻辑：扫描所有表格行 ---
        all_rows = driver.find_elements(By.TAG_NAME, "tr")
        print(f"📄 页面上总共有 {len(all_rows)} 行表格数据，正在逐行分析...\n")
        
        valid_servers = []
        
        print(f"{'No.':<5} {'Server IP':<20} {'Records':<10}")
        print("-" * 40)

        for i, row in enumerate(all_rows):
            try:
                row_text = row.text
                
                # 1. 检查有没有 "Records" 关键字
                if "Records" in row_text:
                    # 2. 提取 IP (例如 10.101.10.15)
                    ip_match = re.search(r'(10\.\d{1,3}\.\d{1,3}\.\d{1,3})', row_text)
                    # 3. 提取 数量
                    count_match = re.search(r'(\d+)\s*Records', row_text, re.IGNORECASE)
                    
                    if ip_match and count_match:
                        ip = ip_match.group(1)
                        count = int(count_match.group(1))
                        
                        # 保存结果
                        valid_servers.append({'ip': ip, 'count': count})
                        print(f"{len(valid_servers):<5} {ip:<20} {count:<10}")
            except:
                continue
        
        print("-" * 40)
        print(f"\n📊 扫描报告:")
        print(f"   共发现: {len(valid_servers)} 个有效服务器")
        
        # 验证一下数量
        if len(valid_servers) < 10:
             print("⚠️ 警告：数量看起来有点少，可能还有遗漏？")
        else:
             print("✅ 数量看起来很正常！可以准备抓取了。")

    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        input("\n按 Enter 键关闭浏览器...")
        driver.quit()

if __name__ == "__main__":
    check_list_only()