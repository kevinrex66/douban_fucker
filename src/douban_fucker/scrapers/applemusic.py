"""Apple Music 爬虫 - iTunes API 搜索 + 页面爬取详情"""
import json
import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class AppleMusicScraper(BaseScraper):
    """Apple Music 爬虫 - 使用 iTunes Search API 搜索，页面爬取获取详情"""

    name = "applemusic"
    base_url = "https://music.apple.com"

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
        """搜索专辑 - 使用 iTunes Search API"""
        results = []
        seen_ids = set()

        encoded_query = query.replace(" ", "+")
        api_url = f"https://itunes.apple.com/search?term={encoded_query}&entity=album&country=cn&limit={limit}"

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(api_url)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    if len(results) >= limit:
                        break

                    collection_id = str(item.get("collectionId", ""))
                    if not collection_id or collection_id in seen_ids:
                        continue
                    seen_ids.add(collection_id)

                    title = item.get("collectionName", "")
                    artist = item.get("artistName", "")
                    if not title:
                        continue

                    # 构建 Apple Music URL（去掉 ?uo=4 后缀）
                    album_url = item.get("collectionViewUrl", "")
                    album_url = re.sub(r"\?uo=\d+$", "", album_url)

                    # 提取发行日期
                    release_date_raw = item.get("releaseDate", "")
                    release_date = str(release_date_raw)[:10] if release_date_raw else ""
                    year = None
                    if release_date:
                        year_match = re.match(r"(\d{4})", release_date)
                        if year_match:
                            year = int(year_match.group(1))

                    # 提取封面 URL（替换为高分辨率）
                    cover_url = item.get("artworkUrl100", "")
                    if cover_url:
                        cover_url = cover_url.replace("100x100bb", "600x600bb")

                    # 提取流派
                    genre = item.get("primaryGenreName", "")
                    genre_list = [genre] if genre else []

                    # 从 copyright 中提取厂牌
                    label = ""
                    copyright_text = item.get("copyright", "")
                    if copyright_text:
                        label_match = re.search(
                            r'[©℗]\s*\d{4}\s+(.+?)(?:\s+under\b|\s*$)',
                            copyright_text
                        )
                        if label_match:
                            label = label_match.group(1).strip().rstrip(",.")

                    album = Album(
                        title=title,
                        artist=artist,
                        year=year,
                        release_date=release_date,
                        genre=genre_list,
                        label=label,
                        cover_url=cover_url,
                        source=self.name,
                        source_id=collection_id,
                        source_url=album_url,
                        api_source="itunes_api",
                    )

                    results.append(SearchResult(
                        source=self.name,
                        album=album,
                        relevance=1.0,
                    ))

        except Exception as e:
            print(f"Apple Music search failed: {e}")

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
                if 'Apple Music' in script_text:
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
                    if not genre_list:
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

            # 从 script 标签中提取厂牌信息
            # 页面 script 中包含 description 字段，格式如:
            #   "2026年3月20日\n4 首歌曲\nBlue Note Records; ℗ 2026 UMG Recordings"
            #   "2026年3月27日\n11 首歌曲\n℗ 2026 Cellar Live under exclusive license to ..."
            #   "1985年3月7日\n1 首歌曲\n℗ 1985 USA for Africa"
            if not label:
                for script in soup.select('script'):
                    script_text = script.string or ''
                    # 提取 description 字段中的版权行
                    desc_match = re.search(
                        r'"description"\s*:\s*"([^"]*[©℗][^"]*)"',
                        script_text
                    )
                    if not desc_match:
                        continue
                    desc_text = desc_match.group(1).replace('\\n', '\n')

                    # 格式1: "LabelName; ℗ YYYY ..." — 厂牌在分号前
                    m = re.search(r'([A-Za-z][A-Za-z0-9\s&\.\'\-,]+?)\s*;\s*[©℗]', desc_text)
                    if m:
                        label = m.group(1).strip()
                        break

                    # 格式2: "℗ YYYY LabelName under ..." 或 "℗ YYYY LabelName"
                    m = re.search(r'[©℗]\s*\d{4}\s+(.+?)(?:\s+under\b|$)', desc_text, re.MULTILINE)
                    if m:
                        label = m.group(1).strip().rstrip(",.")
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

            # 获取专辑简介/描述
            description = ""
            # 方法1: 从 JSON-LD 的 description 字段获取
            if json_ld:
                description = json_ld.get("description", "")
                # 清理描述中的歌曲数量信息，保留简介内容
                if description:
                    # 移除 "X 首歌曲" 这类信息
                    description = re.sub(r'\n?\d+\s*首歌曲\n?', '', description).strip()
                    # 移除发行日期行
                    description = re.sub(r'\n?\d{4}年\d{1,2}月\d{1,2}日\n?', '', description).strip()
                    # 移除版权行 (以 © 或 ℗ 开头)
                    description = re.sub(r'\n?[©℗].*$', '', description, flags=re.MULTILINE).strip()

            # 方法2: 从页面 meta 标签获取
            if not description:
                meta_desc = soup.select_one('meta[name="description"]')
                if meta_desc:
                    description = meta_desc.get("content", "")

            # 方法3: 从页面特定区域获取
            if not description:
                desc_selectors = [
                    ".section__description",
                    "[data-testid='description']",
                    ".album-description",
                    ".description"
                ]
                for selector in desc_selectors:
                    desc_elem = soup.select_one(selector)
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)
                        break

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
                description=description,
                api_source="applemusic_page",
            )

            return album

        except Exception as e:
            print(f"Failed to parse album page: {e}")
            return None
