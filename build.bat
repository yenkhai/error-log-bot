@echo off
title Error Log Bot - 自动打包工具
color 0A

echo ==================================================
echo          开始打包 Error Log Bot...
echo ==================================================
echo.

:: 1. 清理旧的编译文件 (可选，保持环境干净)
if exist build (
    echo [1/3] 正在清理旧的 build 文件夹...
    rmdir /s /q build
)
if exist "Error Log Bot.spec" (
    echo [1/3] 正在清理旧的 .spec 配置文件...
    del "Error Log Bot.spec"
)

:: 2. 执行打包命令
echo.
echo [2/3] 正在调用 PyInstaller 进行打包...
echo       (这可能需要几分钟，请耐心等待)
echo.

py -m PyInstaller --onefile --noconsole --collect-all customtkinter --collect-all selenium --icon="logo.ico" --name="Error Log Bot" bot.py

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
    echo     你的 .exe 文件已经在 dist 文件夹里了。
    echo ==================================================
    
    :: 自动打开文件夹 (方便你直接拿文件)
    start explorer dist
)

pause