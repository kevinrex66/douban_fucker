@echo off
:: ============================================
::   豆瓣专辑上传工具 - Windows 打包脚本
:: ============================================

cd /d "%~dp0"

echo ============================================
echo    豆瓣专辑上传工具 - Windows 打包
echo ============================================
echo.

:: 1. 检查依赖
echo [1/5] 检查依赖...
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller
)

:: 2. 确保 Playwright 浏览器已安装
echo [2/5] 确保 Playwright 浏览器已安装...
python -m playwright install chromium

:: 3. 清理旧构建
echo [3/5] 清理旧构建...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
if exist "*.spec" del /q *.spec

:: 4. 打包
echo [4/5] 开始打包...
pyinstaller app.spec --clean --noconfirm

:: 5. 完成
echo [5/5] 打包完成！
echo.
echo ============================================
echo    打包完成！
echo ============================================
echo.
echo 可执行文件位于: dist\ 目录
echo.
dir /b dist\

pause
