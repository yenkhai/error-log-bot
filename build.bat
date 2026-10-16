@echo off
title Work App - 一键自动打包工具
color 0A

echo ==================================================
echo          开始打包 Work App (work.exe)...
echo ==================================================
echo.

:: Always build relative to this script, so resource paths do not depend on the current working directory.
cd /d "%~dp0"
echo [1/2] Building work.exe...
py -m PyInstaller --noconfirm --onefile --noconsole --collect-all customtkinter --collect-all selenium --icon="logo.ico" --name="work" main.py

:: 3. 检查结果
echo.
if %errorlevel% neq 0 (
    color 0C
    echo ==================================================
    echo [X] 打包失败！请检查上面的错误信息。
    echo ==================================================
) else (
    color 0A
    echo ==================================================
    echo [V] 打包成功！
    echo     你的独立桌面程序 work.exe 已经生成在 dist 文件夹里了！
    echo ==================================================
    
    :: 自动弹出 dist 文件夹
    start explorer dist
)

pause