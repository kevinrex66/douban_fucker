"""会话管理模块 - 管理豆瓣登录 cookies"""
import json
from pathlib import Path
from typing import Optional

from ..utils import get_config


class SessionManager:
    """管理豆瓣登录会话"""

    def __init__(self):
        config = get_config()
        self.cookies_file = Path(config.douban.cookies_file)
        self.cookies_file.parent.mkdir(parents=True, exist_ok=True)

    def save_cookies(self, cookies: list) -> None:
        """保存 cookies 到文件"""
        with open(self.cookies_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    def load_cookies(self) -> Optional[list]:
        """从文件加载 cookies"""
        if not self.cookies_file.exists():
            return None

        try:
            with open(self.cookies_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def delete_cookies(self) -> None:
        """删除 cookies 文件"""
        if self.cookies_file.exists():
            self.cookies_file.unlink()

    def has_cookies(self) -> bool:
        """检查是否有保存的 cookies"""
        return self.cookies_file.exists()

    def is_valid(self, cookies: list) -> bool:
        """检查 cookies 是否有效（简单检查）"""
        if not cookies:
            return False
        # 检查是否包含必要的 cookies
        names = {c.get("name", "") for c in cookies}
        # 豆瓣登录后会话的 cookie 名称可能包括 dbcl2, bid 等
        return len(names) > 0
