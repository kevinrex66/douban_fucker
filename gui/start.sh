#!/bin/bash
# 豆瓣专辑上传工具 - 启动脚本
# 自动安装依赖、启动服务并打开浏览器

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}🎵 豆瓣专辑上传工具${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 需要安装 Python 3${NC}"
    echo "请访问 https://www.python.org/downloads/"
    exit 1
fi

# 确定 Python 命令
PYTHON_CMD="python3"
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

echo -e "${YELLOW}检查依赖...${NC}"

# 安装依赖
$PYTHON_CMD -m pip install -q fastapi uvicorn python-multipart 2>/dev/null

echo ""
echo -e "${GREEN}启动服务...${NC}"
echo -e "浏览器将自动打开 http://127.0.0.1:18901"
echo -e "按 Ctrl+C 停止服务"
echo ""

# 启动
$PYTHON_CMD main.py
