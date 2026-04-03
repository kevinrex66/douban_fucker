#!/bin/bash
# ============================================
#   豆瓣专辑上传工具 - macOS 打包脚本
# ============================================

set -e

echo "============================================"
echo "  豆瓣专辑上传工具 - macOS 打包"
echo "============================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 检查依赖
echo "[1/5] 检查依赖..."

if ! command -v pyinstaller &> /dev/null; then
    echo "安装 PyInstaller..."
    pip install pyinstaller
fi

# 2. 确保 Playwright 浏览器已安装
echo "[2/5] 确保 Playwright 浏览器已安装..."
python -m playwright install chromium 2>/dev/null || true

# 3. 清理旧构建
echo "[3/5] 清理旧构建..."
rm -rf dist build *.spec

# 4. 打包
echo "[4/5] 开始打包..."
pyinstaller app.spec --clean --noconfirm

# 5. 完成
echo "[5/5] 打包完成！"
echo ""
echo "============================================"
echo "  打包完成！"
echo "============================================"
echo ""
echo "可执行文件位于: dist/"
echo ""
ls -la "dist/豆瓣专辑上传工具.app/Contents/MacOS/" 2>/dev/null || ls -la dist/
echo ""
echo "使用方法:"
echo "  双击 dist/豆瓣专辑上传工具.app 即可运行"
