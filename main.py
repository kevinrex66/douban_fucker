#!/usr/bin/env python3
"""豆瓣多功能爬虫 - 主入口"""
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.douban_fucker.cli import main

if __name__ == "__main__":
    main()
