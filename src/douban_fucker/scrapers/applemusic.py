"""Apple Music 爬虫 - 页面爬取"""
import json
import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class AppleMusicScraper(BaseScraper):
    """Apple Music 爬虫 - 使用页面爬取"""

    name = "applemusic"
    base_url = "https://music.apple.com"
    search_url = "https://music.apple.com/cn/search"

    def __init__(self):
        super().__init__()
        config = get_config()
        self.user_agent = config.scrapers.applemusic.user_agent
        self.delay = max(self.delay, 1.0)

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        results = []

        # Generate query variations - try shorter variations first for better results
        # Apple Music search works better with shorter queries
        query_variations = [
            # Remove common filler words first (shortest)
            query.replace(" at ", " ").replace(" the ", " "),
            query.replace(" the ", " "),
            query.replace(" at ", " "),
            # Then try with minimal removal
            re.sub(r"\s+", " ", query).strip(),
            query,  # Original query last
        ]

        # Deduplicate variations
        query_variations = list(dict.fromkeys(query_variations))

        seen_urls = set()
        seen_titles = set()

        for q in query_variations:
            if len(results) >= limit:
                break

            # URL encode the query - replace spaces with +
            encoded_query = q.replace(" ", "+")
            url = f"{self.search_url}?term={encoded_query}&entity=album"

            try:
                with self._get_client() as client:
                    self._rate_limit()
                    response = client.get(url, headers=self._get_headers())
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find product-lockup elements (album results)
                    lockups = soup.select(".product-lockup, .top-search-lockup")

                    for lockup in lockups:
                        if len(results) >= limit:
                            break

                        # Find album link
                        album_link = lockup.select_one('a[href*="/album/"]')
                        if not album_link:
                            continue

                        href = album_link.get("href", "")
                        # Skip if no valid href
                        if not href:
                            continue

                        # Get aria-label for filtering and title extraction
                        aria_label = album_link.get("aria-label", "")

                        # Only include albums (专辑/Album), skip individual tracks (歌曲/Song)
                        # The aria-label format is "Title · Type · Artist"
                        if "歌曲" in aria_label or "Song" in aria_label:
                            # This is a track, skip unless it's also the album page
                            if "?" in href:
                                continue

                        # Extract album URL - remove track query params
                        if "?" in href and "/album/" in href:
                            album_url_match = re.match(r"(https?://music\.apple\.com/[^/]+/album/[^?]+)", href)
                            if album_url_match:
                                href = album_url_match.group(1)
                            elif href.startswith("/"):
                                href = f"{self.base_url}{href.split('?')[0]}"
                            else:
                                href = href.split('?')[0]

                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        # Extract title from aria-label
                        title = aria_label
                        if not title:
                            # Find title in lockup
                            for sel in [".product-lockup__title", ".lockup__title",
                                       "[class*='title']", ".top-search-lockup__title"]:
                                t = lockup.select_one(sel)
                                if t and t.text.strip():
                                    title = t.text.strip()
                                    break

                        if not title:
                            continue

                        # Normalize title for deduplication
                        title_normalized = title.lower().strip()
                        if title_normalized in seen_titles:
                            continue
                        seen_titles.add(title_normalized)

                        # Clean up title - remove " · Type · Artist" suffix
                        title = re.sub(r"\s*[·•  ]\s*(专辑|Album|单|歌曲|Song).*$", "", title)
                        title = title.strip()

                        if not title:
                            continue

                        album = self._parse_search_result(title, href)
                        if album:
                            results.append(SearchResult(
                                source=self.name,
                                album=album,
                                relevance=1.0
                            ))

            except Exception as e:
                print(f"Apple Music search failed for '{q}': {e}")
                continue

        return results

    def get_album(self, album_id: str) -> Optional[Album]:
        """通过 ID 获取专辑详情"""
        # Apple Music URL 格式: https://music.apple.com/cn/album/xxx/id123
        url = f"{self.base_url}/cn/album/{album_id}"
        return self.get_album_by_url(url)

    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过 URL 获取专辑"""
        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(url, headers=self._get_headers())
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")

                return self._parse_album_page(soup, url)

        except Exception as e:
            print(f"Apple Music album fetch failed: {e}")

        return None

    def _parse_search_result(self, title: str, href: str) -> Optional[Album]:
        """解析搜索结果"""
        try:
            if not title:
                return None

            # Clean up title
            title = title.strip()

            # Extract album_id from URL
            match = re.search(r"/album/[^/]+/(\d+)", href)
            album_id = match.group(1) if match else href

            album = Album(
                title=title,
                artist="",  # 搜索结果可能没有艺术家
                source=self.name,
                source_id=album_id,
                source_url=href,
                api_source="applemusic_page",
            )

            return album

        except Exception:
            return None

    def _parse_iso_duration(self, duration: str) -> str:
        """解析 ISO 8601 时长格式为 mm:ss 或 hh:mm:ss"""
        if not duration:
            return ""
        # PT14M14S -> 14:14
        match = re.match(r"PT(?:(\d+)H)?(\d+)M(\d+)S", duration)
        if match:
            hours = match.group(1)
            minutes = match.group(2)
            seconds = match.group(3)
            if hours:
                return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
            return f"{int(minutes)}:{int(seconds):02d}"
        return ""

    def _parse_album_page(self, soup: BeautifulSoup, url: str) -> Optional[Album]:
        """解析专辑详情页面"""
        try:
            # Parse JSON-LD for structured data
            json_ld = None
            for script in soup.select('script[type="application/ld+json"]'):
                content = script.string
                if content and 'MusicAlbum' in content:
                    json_ld = json.loads(content)
                    break

            # 获取标题 - prefer JSON-LD
            title = ""
            if json_ld:
                title = json_ld.get("name", "")

            # Fallback to DOM selectors
            if not title:
                title_elem = (
                    soup.select_one(".headings__title span") or
                    soup.select_one(".headings__title") or
                    soup.select_one("h1") or
                    soup.select_one("[data-testid='product-title']")
                )
                if title_elem:
                    title = title_elem.text.strip()

            # Clean title - remove Apple Music prefix if present
            title = re.sub(r"^Apple\s+Music\s+上.*?的专辑《", "", title)
            title = re.sub(r"》.*$", "", title)
            title = title.strip()

            # 获取艺术家 - prefer JSON-LD for name, fallback to DOM
            artist = ""
            if json_ld:
                by_artist = json_ld.get("byArtist", [])
                if isinstance(by_artist, list) and len(by_artist) > 0:
                    by_artist = by_artist[0]
                if isinstance(by_artist, dict):
                    artist = by_artist.get("name", "")

            if not artist:
                # Try DOM selectors
                artist_elem = soup.select_one(".headings__subtitle a")
                if artist_elem:
                    artist = artist_elem.text.strip()

            # 获取发行信息
            year = None
            release_date = ""  # 完整发行日期
            label = ""
            genre_list = []
            style_list = []
            track_count = 0

            # Parse JSON-LD meta
            if json_ld:
                # Release date
                release_date_raw = json_ld.get("datePublished", "") or json_ld.get("music:release_date", "")
                if release_date_raw:
                    release_date = str(release_date_raw)[:10]  # 取前10个字符 YYYY-MM-DD
                    year_match = re.match(r"(\d{4})", release_date_raw)
                    if year_match:
                        year = int(year_match.group(1))

                # Genre - Apple Music 的 JSON-LD 中有 genre 字段
                json_genre = json_ld.get("genre", [])
                if isinstance(json_genre, list):
                    genre_list = [g for g in json_genre if g]
                elif json_genre:
                    genre_list = [json_genre]

                # Track count from description (e.g., "4 首歌曲")
                desc = json_ld.get("description", "")
                track_match = re.search(r"(\d+)\s*首歌曲", desc)
                if track_match:
                    track_count = int(track_match.group(1))

            # Try meta tags for year and release date
            meta_tags = {meta.get("property", ""): meta.get("content", "")
                        for meta in soup.select("meta[property]")}

            if not year:
                release_date_raw = meta_tags.get("music:release_date", "")
                if release_date_raw:
                    release_date = str(release_date_raw)[:10]
                    year_match = re.match(r"(\d{4})", release_date_raw)
                    if year_match:
                        year = int(year_match.group(1))

            # Try product meta section - 从 script 标签中提取完整日期
            for script in soup.select('script'):
                script_text = script.string or ''
                if 'Apple Music' in script_text or 'immanuel' in script_text.lower():
                    # 提取完整日期: "2026年3月20日"
                    if not release_date:
                        date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', script_text)
                        if date_match:
                            year_g = date_match.group(1)
                            month_g = date_match.group(2)
                            day_g = date_match.group(3)
                            release_date = f"{year_g}-{int(month_g):02d}-{int(day_g):02d}"
                            if not year:
                                year = int(year_g)

                    # 提取风格信息 - 从 script 中查找
                    # Apple Music 有时会包含 genre/style 信息
                    if not genre_list:
                        # 尝试从页面文本中提取
                        genre_pattern = re.findall(r'"genre"\s*:\s*\[([^\]]+)\]', script_text)
                        for gp in genre_pattern:
                            genres = re.findall(r'"([^"]+)"', gp)
                            for g in genres:
                                if len(g) > 2 and g not in ['Jazz', 'Pop', 'Music', '音乐']:
                                    genre_list.append(g)
                    break

            # Try product meta section
            for elem in soup.select(".product-meta__value, .product-creator, .release-date"):
                text = elem.text.strip()
                if re.match(r"\d{4}", text):
                    year = int(text[:4])
                elif "Label" in text or "厂牌" in text:
                    label = text.split(":")[-1].strip()

            # 从所有 script 标签中提取厂牌信息
            # Apple Music 在页面的 JSON 数据中包含厂牌，格式如:
            # "2026年3月20日\n4 首歌曲、1 小时 2 分钟\nBlue Note Records; ℗ 2026 UMG Recordings, Inc."
            if not label:
                for script in soup.select('script'):
                    script_text = script.string or ''
                    if 'Apple Music' in script_text or 'immanuel' in script_text.lower():
                        # 查找厂牌格式: "LabelName; © 年份" 或 "LabelName; ℗ 年份"
                        match = re.search(
                            r'([A-Za-z][A-Za-z0-9\s&\.\'-]+?)\s*;\s*[©℗]\s*\d{4}',
                            script_text
                        )
                        if match:
                            potential_label = match.group(1).strip()
                            # 清理厂牌名称
                            # 去除开头可能有的换行符
                            potential_label = re.sub(r'^[\n\r]+', '', potential_label)
                            # 如果以 n 开头且后面紧跟大写字母，去除 n
                            if potential_label.startswith('n') and len(potential_label) > 1 and potential_label[1].isupper():
                                potential_label = potential_label[1:]
                            potential_label = potential_label.strip()
                            # 过滤掉无效的匹配
                            if (3 < len(potential_label) < 60 and
                                not any(c in potential_label for c in ['@', '{', '}', 'http'])):
                                label = potential_label
                                break

            # 获取封面
            cover_url = meta_tags.get("og:image", "")
            if not cover_url:
                cover_elem = soup.select_one(".media-artwork-v2 img, [data-testid='album-artwork'] img")
                if cover_elem:
                    cover_url = cover_elem.get("src", "")

            # 清理封面 URL - 保留原始 URL
            cover_url = re.sub(r"\.webp\?.*$", ".jpg", cover_url)

            # 获取曲目列表 - from JSON-LD (tracks field)
            tracklist = []

            if json_ld:
                json_tracks = json_ld.get("tracks", [])
                for idx, track_data in enumerate(json_tracks, 1):
                    if isinstance(track_data, dict):
                        track_title = track_data.get("name", "")
                        # Get duration - may be in track_data directly or nested
                        duration = track_data.get("duration", "")
                        if not duration and track_data.get("audio"):
                            duration = track_data["audio"].get("duration", "")

                        tracklist.append(Track(
                            position=str(idx),
                            title=track_title,
                            duration=self._parse_iso_duration(duration),
                        ))

            # Fallback: try DOM selectors if no JSON-LD tracks
            if not tracklist:
                track_elems = (
                    soup.select(".songs-list-row") or
                    soup.select("[data-testid='track-row']") or
                    soup.select("li.song, .track-list li")
                )
                for idx, track in enumerate(track_elems, 1):
                    track_title = ""

                    # Try different selectors for title
                    for sel in [".songs-list-row__song-name", ".track-name",
                               "[data-testid='track-name']", ".title"]:
                        t = track.select_one(sel)
                        if t:
                            track_title = t.text.strip()
                            break

                    if track_title:
                        tracklist.append(Track(
                            position=str(idx),
                            title=track_title,
                            duration="",
                        ))

            # Final fallback: create placeholder tracks from count
            if not tracklist and track_count > 0:
                for i in range(1, track_count + 1):
                    tracklist.append(Track(
                        position=str(i),
                        title=f"Track {i}",
                        duration="",
                    ))

            # 提取 album_id
            match = re.search(r"/album/[^/]+/(\d+)", url)
            album_id = match.group(1) if match else url

            album = Album(
                title=title,
                artist=artist,
                year=year,
                release_date=release_date,
                genre=genre_list,
                style=style_list,
                label=label,
                tracklist=tracklist,
                cover_url=cover_url,
                source=self.name,
                source_id=album_id,
                source_url=url,
                api_source="applemusic_page",
            )

            return album

        except Exception as e:
            print(f"Failed to parse album page: {e}")
            return None
