#!/usr/bin/env python3
"""RYM Cookies 导入工具"""
import sys
import json
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.douban_fucker.scrapers.rym import RYMScraper

def main():
    print("=" * 50)
    print("RYM Cookies 导入工具")
    print("=" * 50)
    print()
    print("使用方法:")
    print("1. 在 EditThisCookie 中点击 Export")
    print("2. 保存为文件 (如 rym_cookies.json)")
    print("3. 运行: python main.py rym-import rym_cookies.json")
    print()

    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if file_path.exists():
            print(f"从文件读取: {file_path}")
            with open(file_path, 'r') as f:
                json_str = f.read()
        else:
            print(f"文件不存在: {file_path}")
            return
    else:
        print("请粘贴 JSON (Ctrl+D 结束输入):")
        json_str = sys.stdin.read()

    if not json_str.strip():
        print("未输入内容")
        return

    scraper = RYMScraper()
    success = scraper.import_cookies(json_str)
    scraper.close()

    if success:
        print()
        print("=" * 50)
        print("✓ Cookies 导入成功！")
        print("=" * 50)
    else:
        print("✗ Cookies 导入失败")

if __name__ == "__main__":
    main()
