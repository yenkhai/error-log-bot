"""
================================================================================
主程序入口文件 (main.py)
--------------------------------------------------------------------------------
作用: 
1. 重定向 sys.stdout 和 sys.stderr 标准输出流为 UTF-8 编码，防止 Windows cp1252 编码崩溃。
2. 初始化 CustomTkinter UI 应用程序窗口实例 UnifiedBotApp 并启动主事件循环 (mainloop)。
================================================================================
"""

import sys
import io

# 强制将标准输出与错误流重定向为 UTF-8 编码，解决 Windows cp1252 环境打印 Unicode Emoji 报错的隐患
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from gui.app import UnifiedBotApp

def main():
    """主函数：创建全局 CustomTkinter 窗口对象并启动应用运行"""
    app = UnifiedBotApp()
    app.mainloop()

if __name__ == "__main__":
    main()
