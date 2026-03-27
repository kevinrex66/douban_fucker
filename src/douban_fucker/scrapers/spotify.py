"""Spotify 爬虫 - 使用 Spotify Web API"""
import re
import time
from typing import List, Optional

import httpx

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class SpotifyScraper(BaseScraper):
    """Spotify 爬虫 - 使用 Spotify Web API"""

    name = "spotify"
    base_url = "https://api.spotify.com/v1"

    def __init__(self):
        super().__init__()
        config = get_config()
        self.client_id = config.scrapers.spotify.client_id
        self.client_secret = config.scrapers.spotify.client_secret
        self.access_token = None
        self.token_expires_at = 0

    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {
            "Accept": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _ensure_token(self) -> bool:
        """确保有有效的 access token"""
        # 检查 token 是否过期
        if self.access_token and time.time() < self.token_expires_at:
            return True

        # 需要获取新 token
        if not self.client_id or not self.client_secret:
            print("Spotify API 需要 client_id 和 client_secret")
            print("请在 https://developer.spotify.com/dashboard 创建应用")
            return False

        try:
            # 使用 Client Credentials Flow 获取 token
            response = httpx.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            self.access_token = data["access_token"]
            # token 通常 1 小时有效
            self.token_expires_at = time.time() + data.get("expires_in", 3600) - 60

            return True

        except Exception as e:
            print(f"Spotify token 获取失败: {e}")
            return False

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        results = []

        if not self._ensure_token():
            return results

        try:
            params = {
                "q": query,
                "type": "album",
                "limit": min(limit, 50),
            }

            with self._get_client() as client:
                self._rate_limit()
                response = client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("albums", {}).get("items", []):
                    album = self._parse_search_result(item)
                    if album:
                        results.append(SearchResult(
                            source=self.name,
                            album=album,
                            relevance=1.0
                        ))

        except Exception as e:
            print(f"Spotify search failed: {e}")

        return results

    def get_album(self, album_id: str) -> Optional[Album]:
        """通过 ID 获取专辑详情"""
        if not self._ensure_token():
            return None

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(
                    f"{self.base_url}/albums/{album_id}",
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()

                return self._parse_album_data(data)

        except Exception as e:
            print(f"Spotify album fetch failed: {e}")

        return None

    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过 URL 获取专辑"""
        # Spotify URL 格式: https://open.spotify.com/album/xxxxx
        match = re.search(r"/album/([a-zA-Z0-9]+)", url)
        if match:
            return self.get_album(match.group(1))
        return None

    def _parse_search_result(self, data: dict) -> Optional[Album]:
        """解析搜索结果"""
        try:
            artists = [a["name"] for a in data.get("artists", [])]
            artist_str = ", ".join(artists) if artists else "Unknown"

            album = Album(
                title=data.get("name", ""),
                artist=artist_str,
                year=int(data.get("release_date", "0000")[:4]) if data.get("release_date") else None,
                cover_url=data.get("images", [{}])[0].get("url", "") if data.get("images") else "",
                source=self.name,
                source_id=data.get("id", ""),
                source_url=f"https://open.spotify.com/album/{data.get('id', '')}",
                api_source="spotify_api",
            )

            # 格式
            album.format = data.get("album_type", "")

            return album

        except Exception:
            return None

    def _parse_album_data(self, data: dict) -> Optional[Album]:
        """解析专辑详情数据"""
        try:
            artists = [a["name"] for a in data.get("artists", [])]
            artist_str = ", ".join(artists) if artists else "Unknown"

            # 解析曲目列表
            tracklist = []
            for idx, item in enumerate(data.get("tracks", {}).get("items", []), 1):
                duration_ms = item.get("duration_ms", 0)
                duration = self._ms_to_duration(duration_ms) if duration_ms else ""

                tracklist.append(Track(
                    position=str(idx),
                    title=item.get("name", ""),
                    duration=duration,
                ))

            # 流派 - Spotify 没有直接的流派，但有 genres
            genres = data.get("genres", [])

            album = Album(
                title=data.get("name", ""),
                artist=artist_str,
                year=int(data.get("release_date", "0000")[:4]) if data.get("release_date") else None,
                genre=genres,
                label="",  # Spotify 没有厂牌信息
                format=data.get("album_type", ""),
                country=data.get("country", ""),
                tracklist=tracklist,
                cover_url=data.get("images", [{}])[0].get("url", "") if data.get("images") else "",
                source=self.name,
                source_id=data.get("id", ""),
                source_url=f"https://open.spotify.com/album/{data.get('id', '')}",
                api_source="spotify_api",
            )

            return album

        except Exception as e:
            print(f"Failed to parse album data: {e}")
            return None

    def _ms_to_duration(self, ms: int) -> str:
        """毫秒转换为时长字符串"""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
