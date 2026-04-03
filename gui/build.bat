@echo off
:: 打包脚本 - Windows
:: 打包成可执行文件

cd /d "%~dp0"

echo ========================================
echo    打包豆瓣专辑上传工具
echo ========================================
echo.

:: 检查 PyInstaller
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller
)

echo 开始打包...
echo.

pyinstaller douban_fucker_gui.spec --clean

echo.
echo ========================================
echo    打包完成！
echo ========================================
echo.
echo 可执行文件位于: dist\
echo.
dir /b dist\

pause
