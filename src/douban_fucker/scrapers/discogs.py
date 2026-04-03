"""Discogs 爬虫"""
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class DiscogsScraper(BaseScraper):
    """Discogs 爬虫"""

    name = "discogs"
    base_url = "https://api.discogs.com"
    site_url = "https://www.discogs.com"

    def __init__(self):
        super().__init__()
        config = get_config()
        self.api_key = config.scrapers.discogs.api_key
        self.preferred_size = config.images.preferred_size

    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {
            "User-Agent": config.scrapers.discogs.user_agent,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Discogs token={self.api_key}"
        return headers

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        results = []

        # 优先使用 API
        if self.api_key:
            results = self._search_api(query, limit)
        else:
            # 使用页面爬取
            results = self._search_page(query, limit)

        return results

    def _search_api(self, query: str, limit: int) -> List[SearchResult]:
        """通过 API 搜索"""
        results = []
        config = get_config()

        headers = self._get_headers()
        url = f"{self.base_url}/database/search"
        params = {
            "q": query,
            "type": "release",
            "per_page": limit,
        }

        try:
            with self._get_client() as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    album = self._parse_search_result(item)
                    if album:
                        results.append(SearchResult(
                            source=self.name,
                            album=album,
                            relevance=1.0
                        ))

        except Exception as e:
            print(f"Discogs API search failed: {e}")

        return results

    def _search_page(self, query: str, limit: int) -> List[SearchResult]:
        """通过页面爬取搜索"""
        results = []

        url = f"{self.site_url}/search"
        params = {"q": query, "type": "release"}

        try:
            with self._get_client() as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")

                cards = soup.select("li.shortcut_navigate")
                for card in cards[:limit]:
                    link = card.select_one("a")
                    title_elem = card.select_one(".search_result_title")
                    artist_elem = card.select_one(".search_result_title a")

                    if link and title_elem:
                        title = title_elem.get_text(strip=True)
                        artist = artist_elem.get_text(strip=True) if artist_elem else "Unknown"

                        album = Album(
                            title=title,
                            artist=artist,
                            source=self.name,
                            source_url=self.site_url + link.get("href", ""),
                        )

                        results.append(SearchResult(
                            source=self.name,
                            album=album,
                            relevance=1.0
                        ))

        except Exception as e:
            print(f"Discogs page search failed: {e}")

        return results

    def get_album(self, album_id: str) -> Optional[Album]:
        """通过 ID 获取专辑详情"""
        # 尝试 API
        if self.api_key:
            return self._get_album_api(album_id)
        else:
            return self._get_album_page(album_id)

    def _get_album_api(self, album_id: str) -> Optional[Album]:
        """通过 API 获取专辑"""
        headers = self._get_headers()
        url = f"{self.base_url}/releases/{album_id}"

        try:
            with self._get_client() as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                return self._parse_album_data(data)

        except Exception as e:
            print(f"Discogs API album fetch failed: {e}")

        return None

    def _get_album_page(self, album_id: str) -> Optional[Album]:
        """通过页面获取专辑"""
        url = f"{self.site_url}/release/{album_id}"

        try:
            with self._get_client() as client:
                response = client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")

                return self._parse_album_page(soup, url, album_id)

        except Exception as e:
            print(f"Discogs page album fetch failed: {e}")

        return None

    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过 URL 获取专辑"""
        # 从 URL 提取 release ID
        match = re.search(r"/release/(\d+)", url)
        if match:
            return self.get_album(match.group(1))
        return None

    def _parse_search_result(self, data: dict) -> Optional[Album]:
        """解析搜索结果"""
        try:
            album = Album(
                title=data.get("title", ""),
                artist=data.get("title", ""),  # Discogs search result has combined title
                year=int(data.get("year", 0)) if data.get("year") else None,
                source=self.name,
                source_id=str(data.get("id", "")),
                source_url=data.get("uri", ""),
                api_source="discogs_api",
            )

            # 从 title 中分离 artist 和 album
            title = data.get("title", "")
            if " - " in title:
                parts = title.split(" - ", 1)
                album.artist = parts[0]
                album.title = parts[1]

            # 获取封面
            if data.get("cover_image"):
                album.cover_url = data.get("cover_image")
            elif data.get("thumb"):
                album.cover_url = data.get("thumb")

            # 获取格式
            if data.get("format"):
                album.format = ", ".join(data.get("format", []))

            # 获取国家
            album.country = data.get("country", "")

            return album

        except Exception:
            return None

    def _parse_album_data(self, data: dict) -> Optional[Album]:
        """解析完整专辑数据 (API)"""
        try:
            # 获取艺术家
            artists = []
            for artist in data.get("artists", []):
                artists.append(artist.get("name", ""))
            artist_str = ", ".join(artists) if artists else data.get("artists_sort", "Unknown")

            # 获取曲目列表
            tracklist = []
            for track in data.get("tracklist", []):
                position = track.get("position", "")
                title = track.get("title", "")
                duration = self.parse_duration(track.get("duration", ""))
                tracklist.append(Track(
                    position=position,
                    title=title,
                    duration=duration
                ))

            # 获取风格/类型
            genres = data.get("genres", [])
            styles = data.get("styles", [])

            # 获取发行信息
            labels = data.get("labels", [])
            label_str = ", ".join([l.get("name", "") for l in labels])
            catalog_nums = [l.get("catno", "") for l in labels]
            catalog_str = ", ".join([c for c in catalog_nums if c])

            # 获取封面图片
            cover_url = ""
            images = data.get("images", [])
            for img in images:
                if img.get("type") == "primary":
                    cover_url = img.get("uri", "")
                    break
            if not cover_url and images:
                cover_url = images[0].get("uri", "")

            # 从 formats 中提取介质和专辑类型
            format_str = ""
            album_type = ""
            formats = data.get("formats", [])
            if formats:
                # format name 是介质类型 (如 "Vinyl", "CD")
                format_str = formats[0].get("name", "")
                # descriptions 包含专辑类型 (如 "Album", "EP", "Compilation")
                descriptions = formats[0].get("descriptions", [])
                type_keywords = {"Album", "EP", "Single", "Compilation", "Soundtrack",
                                 "Live", "Remix", "Mixtape", "Mini-Album"}
                for desc in descriptions:
                    if desc in type_keywords:
                        album_type = desc
                        break

            album = Album(
                title=data.get("title", ""),
                artist=artist_str,
                year=int(data.get("year", 0)) if data.get("year") else None,
                genre=genres,
                style=styles,
                label=label_str,
                catalog_number=catalog_str,
                format=format_str,
                album_type=album_type,
                country=data.get("country", ""),
                tracklist=tracklist,
                cover_url=cover_url,
                source=self.name,
                source_url=data.get("uri", ""),
                source_id=str(data.get("id", "")),
                description=data.get("notes", ""),
                api_source="discogs_api",
            )

            return album

        except Exception as e:
            print(f"Failed to parse album data: {e}")
            return None

    def _parse_album_page(self, soup: BeautifulSoup, url: str, album_id: str) -> Optional[Album]:
        """解析专辑页面"""
        try:
            # 获取标题
            title_elem = soup.select_one("h1#title")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"

            # 获取艺术家
            artist_elem = soup.select_one("h1 a span")
            artist = artist_elem.get_text(strip=True) if artist_elem else "Unknown"

            # 获取年份
            year_elem = soup.select_one(".profile__release-date")
            year_text = year_elem.get_text(strip=True) if year_elem else ""
            year = None
            year_match = re.search(r"\d{4}", year_text)
            if year_match:
                year = int(year_match.group())

            # 获取封面
            cover_elem = soup.select_one("img#release-image")
            cover_url = cover_elem.get("src", "") if cover_elem else ""

            # 获取风格/类型
            genres = []
            styles = []
            genre_elems = soup.select(".profile__genres a")
            style_elems = soup.select(".profile__styles a")
            genres = [e.get_text(strip=True) for e in genre_elems]
            styles = [e.get_text(strip=True) for e in style_elems]

            # 获取发行信息
            label_elem = soup.select_one(".profile__label")
            label = label_elem.get_text(strip=True).split("\n")[0] if label_elem else ""

            # 获取曲目
            tracklist = []
            track_elems = soup.select(".tracklist__track")
            for track in track_elems:
                position = track.select_one(".track__pos")
                track_title = track.select_one(".track__title")
                duration = track.select_one(".track__length")

                tracklist.append(Track(
                    position=position.get_text(strip=True) if position else "",
                    title=track_title.get_text(strip=True) if track_title else "",
                    duration=duration.get_text(strip=True) if duration else ""
                ))

            album = Album(
                title=title,
                artist=artist,
                year=year,
                genre=genres,
                style=styles,
                label=label,
                tracklist=tracklist,
                cover_url=cover_url,
                source=self.name,
                source_url=url,
                source_id=album_id,
                api_source="discogs_page",
            )

            return album

        except Exception as e:
            print(f"Failed to parse album page: {e}")
            return None


# 导入配置
from ..utils.config import get_config as _get_config
config = _get_config()
