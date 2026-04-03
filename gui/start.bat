@echo off
:: 豆瓣专辑上传工具 - Windows 启动脚本
:: 双击此文件即可运行

cd /d "%~dp0"

echo ========================================
echo    豆瓣专辑上传工具
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 需要安装 Python
    echo 请访问 https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 安装依赖
echo 安装依赖...
pip install -q fastapi uvicorn python-multipart

echo.
echo 启动服务...
echo 浏览器将自动打开 http://127.0.0.1:18901
echo 按 Ctrl+C 停止服务
echo.

:: 启动
python main.py

pause
