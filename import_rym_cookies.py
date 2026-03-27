#!/usr/bin/env python3
"""RYM Cookies 导入工具"""
import sys
import json
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.douban_fucker.scrapers.rym import RYMScraper

def main():
    print("=" * 50)
    print("RYM Cookies 导入工具")
    print("=" * 50)
    print()

    # 读取 cookies 文件
    cookies_path = Path("data/cookies/rym.json")

    if not cookies_path.exists():
        print(f"文件不存在: {cookies_path}")
        print("请先将 EditThisCookie 导出的 JSON 保存到该路径")
        return

    print(f"从 {cookies_path} 读取...")

    with open(cookies_path, 'r') as f:
        data = json.load(f)

    print(f"读取了 {len(data)} 个 cookies")

    # 转换 sameSite
    for cookie in data:
        same_site = cookie.get("sameSite", "Lax")
        if same_site == "no_restriction":
            cookie["sameSite"] = None
        elif same_site == "unspecified":
            cookie["sameSite"] = "Lax"

    # 保存转换后的 cookies
    with open(cookies_path, 'w') as f:
        json.dump(data, f, indent=2)

    print("✓ Cookies 已转换")

    # 验证
    scraper = RYMScraper()
    success = scraper.import_cookies(json.dumps(data))
    scraper.close()

    if success:
        print()
        print("=" * 50)
        print("✓ Cookies 导入成功！")
        print("=" * 50)
    else:
        print("✗ Cookies 可能无效（可能需要登录 session cookie）")

if __name__ == "__main__":
    main()
