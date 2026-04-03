#!/bin/bash
# 打包脚本 - macOS/Linux
# 打包成可执行文件

cd "$(dirname "$0")"

echo "========================================"
echo "  打包豆瓣专辑上传工具"
echo "========================================"
echo ""

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "安装 PyInstaller..."
    pip install pyinstaller
fi

echo "开始打包..."
echo ""

pyinstaller douban_fucker_gui.spec --clean

echo ""
echo "========================================"
echo "  打包完成！"
echo "========================================"
echo ""
echo "可执行文件位于: dist/"
echo ""
ls -la dist/
