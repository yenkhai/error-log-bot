@echo off
title Work App - 一键自动打包工具
color 0A

echo ==================================================
echo          开始打包 Work App (work.exe)...
echo ==================================================
echo.

:: 1. 清理旧的编译缓存
if exist build (
    echo [1/3] 正在清理旧的 build 缓存文件夹...
    rmdir /s /q build
)
if exist "work.spec" (
    echo [1/3] 正在清理旧的 work.spec 配置文件...
    del "work.spec"
)

:: 2. 执行打包命令 (打包统一入口 main.py -> work.exe)
echo.
echo [2/3] 正在调用 PyInstaller 进行打包 (main.py -> work.exe)...
echo       (正在封装 CustomTkinter、Selenium、模块化巡检与导出工具，请稍候...)
echo.

py -m PyInstaller --onefile --noconsole --collect-all customtkinter --collect-all selenium --icon="logo.ico" --name="work" main.py

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