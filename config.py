"""
================================================================================
全局配置文件管理模块 (config.py)
--------------------------------------------------------------------------------
作用: 
1. 负责从本地 `config.json` JSON 文件中读取和保存系统配置。
2. 管理默认账号模式 (op35 / op38 / custom) 以及默认的目标登录 Domain/URL 链接。
================================================================================
"""

import json
from pathlib import Path

# 配置文件路径: 存储在当前项目根目录下的 config.json
CONFIG_FILE = Path.cwd() / "config.json"

# 默认配置字典
DEFAULT_CONFIG = {
    "LOGIN_URL": "http://10.16.250.9/ubah/index.php?",  # 默认运营系统登录主页 URI
    "ACCOUNT_MODE": "op35",                              # 默认登录账号模式 (op35/op38/custom)
    "AUTH_USER": "bersih",                               # HTTP Basic Auth 鉴权账号
    "AUTH_PASS": "bersih428",                            # HTTP Basic Auth 鉴权密码
    "CHROME_DEBUG_PORT": 9222,                           # Chrome 远程调试端口号
    "NIW_STATIONS": 15,                                  # NIW 巡检关卡数量
    "COPIER_STATIONS": 9                                 # Copier & Server 巡检关卡数量
}

def load_config() -> dict:
    """
    [读取配置] 从本地 config.json 加载配置，如果文件不存在则自动创建并写入默认配置
    """
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 补全可能缺失的配置键
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg: dict):
    """
    [保存配置] 将最新的配置字典持久化写入 config.json
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存配置文件出错: {e}")
