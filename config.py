"""
================================================================================
全局配置文件管理模块 (config.py)
--------------------------------------------------------------------------------
【核心作用】:
1. 负责从本地磁盘 `config.json` 文件中读取和保存系统的核心配置参数。
2. 管理默认账号模式 (op35 / op38 / custom) 以及默认的目标登录 Domain/URL 链接。
3. 提供自动创建配置文件的能力：当初次运行找不到 config.json 时，自动生成默认配置文件。
================================================================================
"""

# 导入 Python 内置的 json 模块，用于处理 JSON 数据的编码与解码
import json
import os
import sys
import warnings
from pathlib import Path

# --------------------------------------------------------------------------------
# 1. 配置文件路径定义
# --------------------------------------------------------------------------------
# __file__ 代表当前文件 (config.py) 的绝对路径
# resolve() 解析所有符号链接以获取标准绝对路径
# parent 获取当前文件所在的父目录（即项目根目录）
# / "config.json" 使用 Path 操作符拼接出配置文件的完整物理路径
# 这样无论在哪个目录下运行 Python，都能准确定位到项目根目录下的 config.json，避免路径漂移
from core.paths import data_dir
CONFIG_FILE = data_dir() / "config.json"

# --------------------------------------------------------------------------------
# 2. 默认配置字典 (当本地文件丢失或缺少键值时使用此保底配置)
# --------------------------------------------------------------------------------
DEFAULT_CONFIG = {
    # 默认运营系统登录主页 URI 地址 (支持内网 IP 或域名)
    "LOGIN_URL": "http://10.16.250.9/ubah/index.php?",

    # 默认登录账号模式:
    # "op35": 预设操作员 35 号
    # "op38": 预设操作员 38 号
    # "custom": 用户自定义手动输入账号密码

    # HTTP Basic Authentication (浏览器弹出式基本身份验证) 的账号
    "AUTH_USER": "bersih",

    # HTTP Basic Authentication 的密码
    "AUTH_PASS": "bersih428",

    # Chrome 远程调试端口号 (用于无缝接管用户已打开的调试浏览器，默认 9222)
    "CHROME_DEBUG_PORT": 9222,

    # NIW 巡检关卡总数量 (15 站)

    # Copier & Server 巡检关卡总数量 (9 站)

    "MAX_RECORD_LIMIT": 10000
}

# --------------------------------------------------------------------------------
# 3. 读取配置函数
# --------------------------------------------------------------------------------
def load_config() -> dict:
    """
    [读取配置函数]
    功能: 从本地 config.json 读取配置并返回字典。
    特性:
    1. 若 config.json 文件不存在，则调用 save_config 写入默认配置，返回默认配置副本。
    2. 若 config.json 中缺少部分键（如软件升级新增了参数），会自动从 DEFAULT_CONFIG 中补齐。
    3. 若读取过程中出现 JSON 语法损坏等异常，自动安全降级返回默认配置副本，防止软件崩溃。
    """
    # 检查本地磁盘是否存在 config.json 文件
    if not CONFIG_FILE.exists() and getattr(sys, 'frozen', False):
        legacy = Path(sys.executable).parent / 'config.json'
        if legacy.exists():
            try:
                migrated = {**DEFAULT_CONFIG, **json.loads(legacy.read_text(encoding='utf-8'))}
                save_config(migrated)
                return migrated
            except (OSError, ValueError, TypeError) as exc:
                warnings.warn(f"无法读取旧配置: {exc}", RuntimeWarning)
    if not CONFIG_FILE.exists():
        # 如果不存在，先将默认配置写入磁盘生成文件
        save_config(DEFAULT_CONFIG)
        # 返回默认配置的浅拷贝，避免外部修改影响 DEFAULT_CONFIG 原型
        return DEFAULT_CONFIG.copy()

    try:
        # 使用 utf-8 编码只读打开配置文件
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            # 解析 JSON 文本为 Python 字典
            cfg = json.load(f)

            # 使用字典解包合并: DEFAULT_CONFIG 为底，cfg 中的值覆盖默认值，未填项自动保底
            return {**DEFAULT_CONFIG, **cfg}
    except Exception as exc:
        warnings.warn(f"配置读取失败，使用默认配置: {exc}", RuntimeWarning)
        # 发生任何读取异常（如 json 格式写错、编码错误等），安全返回默认配置
        return DEFAULT_CONFIG.copy()

# --------------------------------------------------------------------------------
# 4. 保存配置函数
# --------------------------------------------------------------------------------
def save_config(cfg: dict):
    """
    [保存配置函数 - 原子安全写入]
    功能: 将最新的配置字典持久化写入本地 config.json 文件。
    原理: 先写入 .tmp 临时文件并 flush/fsync 到磁盘，再通过 os.replace 原语原子重命名替换原文件。
    即便在写入瞬间遇到断电、进程强杀或异常崩溃，也不会导致配置文件被截断为空文件。
    """
    tmp_file = CONFIG_FILE.with_suffix(".tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, CONFIG_FILE)
        return True
    except Exception as e:
        print(f"保存配置文件出错: {e}")
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        return False
