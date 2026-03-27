"""爬虫基类"""
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

from ..models import Album, SearchResult
from ..utils import get_config


class BaseScraper(ABC):
    """爬虫基类"""

    name: str = "base"
    base_url: str = ""

    def __init__(self):
        config = get_config()
        self.timeout = config.request.timeout
        self.delay = config.request.delay
        self.max_retries = config.request.max_retries

    def _get_client(self) -> httpx.Client:
        """获取HTTP客户端"""
        return httpx.Client(
            timeout=self.timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            follow_redirects=True,
        )

    def _rate_limit(self) -> None:
        """请求限速"""
        time.sleep(self.delay)

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        pass

    @abstractmethod
    def get_album(self, album_id: str) -> Optional[Album]:
        """通过ID获取专辑详情"""
        pass

    @abstractmethod
    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过URL获取专辑详情"""
        pass

    def parse_duration(self, duration: str) -> str:
        """解析时长字符串"""
        if not duration:
            return ""

        # 移除可能的空白字符
        duration = duration.strip()

        # 如果是纯数字（秒），转换为 mm:ss
        try:
            seconds = int(duration)
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}:{secs:02d}"
        except ValueError:
            pass

        # 如果是 mm:ss 或 hh:mm:ss 格式，确保格式正确
        parts = duration.replace(",", ".").split(":")
        if len(parts) == 2:
            try:
                m, s = parts
                return f"{int(m)}:{int(s):02d}"
            except ValueError:
                return duration
        elif len(parts) == 3:
            try:
                h, m, s = parts
                return f"{int(h)}:{int(m):02d}:{int(s):02d}"
            except ValueError:
                return duration

        return duration
