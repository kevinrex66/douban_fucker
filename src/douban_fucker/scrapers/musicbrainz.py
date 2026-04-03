"""MusicBrainz 爬虫"""
import time
from typing import List, Optional

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class MusicBrainzScraper(BaseScraper):
    """MusicBrainz 爬虫 (使用官方 API)"""

    name = "musicbrainz"
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self):
        super().__init__()
        config = get_config()
        self.user_agent = config.scrapers.musicbrainz.user_agent
        self.rate_limit = config.scrapers.musicbrainz.rate_limit
        self.delay = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        results = []
        url = f"{self.base_url}/release-group"
        params = {
            "query": query,  # 直接使用查询字符串
            "type": "album",
            "limit": limit,
            "fmt": "json",
        }

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()

                for item in data.get("release-groups", []):
                    album = self._parse_search_result(item)
                    if album:
                        results.append(SearchResult(
                            source=self.name,
                            album=album,
                            relevance=1.0
                        ))

        except Exception as e:
            print(f"MusicBrainz search failed: {e}")

        return results

    def get_album(self, album_id: str) -> Optional[Album]:
        """通过 ID 获取专辑详情"""
        # album_id 在 MusicBrainz 中是 release-group 的 ID
        # 需要先获取对应的 release
        release_group = self._get_release_group(album_id)
        if not release_group:
            return None

        # 获取具体的 release (通常取第一个)
        releases = self._get_releases(album_id)
        release = releases[0] if releases else None

        # 获取封面
        cover_url = self._get_cover_url(album_id)

        return self._build_album(release_group, release, cover_url)

    def _get_release_group(self, rg_id: str) -> Optional[dict]:
        """获取 Release Group 信息"""
        url = f"{self.base_url}/release-group/{rg_id}"
        params = {"fmt": "json", "inc": "artists+url-rels"}

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                return response.json()
        except Exception:
            return None

    def _get_releases(self, rg_id: str) -> List[dict]:
        """获取 Release Group 下的所有 Release"""
        url = f"{self.base_url}/release-group/{rg_id}/releases"
        params = {"fmt": "json", "inc": "artist-credits"}

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
                return data.get("releases", [])
        except Exception:
            return []

    def _get_cover_url(self, mbid: str) -> str:
        """获取 Cover Art Archive 的封面"""
        url = f"https://coverartarchive.org/release-group/{mbid}/front"
        return url

    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过 URL 获取专辑"""
        # MusicBrainz URL 格式: /release-group/{mbid}
        import re
        match = re.search(r"/release-group/([a-f0-9-]+)", url)
        if match:
            return self.get_album(match.group(1))
        return None

    def _parse_search_result(self, data: dict) -> Optional[Album]:
        """解析搜索结果"""
        try:
            # 获取艺术家 - artist-credit 是一个列表，每个元素有 name 和嵌套的 artist 对象
            artists = []
            for credit in data.get("artist-credit", []):
                # 优先使用顶层的 name，否则从嵌套的 artist 对象获取
                name = credit.get("name") or credit.get("artist", {}).get("name", "")
                if name:
                    artists.append(name)
            artist_str = ", ".join(artists) if artists else "Unknown"

            album = Album(
                title=data.get("title", ""),
                artist=artist_str,
                year=int(data.get("first-release-date", "0000")[:4]) if data.get("first-release-date") else None,
                source=self.name,
                source_id=data.get("id", ""),
                source_url=f"https://musicbrainz.org/release-group/{data.get('id', '')}",
                api_source="musicbrainz_api",
            )

            # 获取类型
            if data.get("primary-type"):
                album.format = data.get("primary-type")
            if data.get("secondary-types"):
                album.style = data.get("secondary-types", [])

            return album

        except Exception:
            return None

    def _build_album(
        self,
        release_group: Optional[dict],
        release: Optional[dict],
        cover_url: str
    ) -> Optional[Album]:
        """构建完整专辑对象"""
        if not release_group:
            return None

        try:
            # 获取艺术家 - 优先从 release 获取，否则从 release-group
            artists = []
            artist_credit_source = None

            if release and release.get("artist-credit"):
                artist_credit_source = release.get("artist-credit")
            elif release_group.get("artist-credit"):
                artist_credit_source = release_group.get("artist-credit")

            if artist_credit_source:
                for credit in artist_credit_source:
                    # 优先使用顶层的 name，否则从嵌套的 artist 对象获取
                    name = credit.get("name") or credit.get("artist", {}).get("name", "")
                    if name:
                        artists.append(name)
            artist_str = ", ".join(artists) if artists else "Unknown"

            # 获取发行信息
            label = ""
            catalog_num = ""
            country = ""
            format_str = ""

            if release:
                for label_info in release.get("label-info", []):
                    label = label_info.get("label", {}).get("name", "")
                    catalog_num = label_info.get("catalog-number", "")
                    break

                country = release.get("country", "")
                # 获取 format
                media = release.get("media", [])
                if media and media[0].get("format"):
                    format_str = media[0].get("format", "")
                if not format_str:
                    format_str = release.get("release-group", {}).get("primary-type", "")

            # 获取曲目
            tracklist = self._get_tracklist(release_group.get("id", ""))

            # 获取风格/类型
            genres = []
            styles = []
            for tag in release_group.get("tags", []):
                if tag.get("name"):
                    genres.append(tag["name"])

            # 尝试获取 Wikipedia 简介
            description = ""
            wiki_url = self._get_wikipedia_url(release_group)
            if wiki_url:
                description = self._get_wikipedia_summary(wiki_url)

            # 如果通过关系没找到，尝试直接用标题搜索 Wikipedia
            album_title = release_group.get("title", "")
            if not description and album_title and artist_str:
                description = self._search_wikipedia_by_title(album_title, artist_str)

            album = Album(
                title=release_group.get("title", ""),
                artist=artist_str,
                year=int(release_group.get("first-release-date", "0000")[:4]) if release_group.get("first-release-date") else None,
                genre=genres,
                style=styles,
                label=label,
                catalog_number=catalog_num,
                format=format_str,
                country=country,
                tracklist=tracklist,
                cover_url=cover_url,
                source=self.name,
                source_url=f"https://musicbrainz.org/release-group/{release_group.get('id', '')}",
                source_id=release_group.get("id", ""),
                description=description,
                api_source="musicbrainz_api",
            )

            return album

        except Exception as e:
            print(f"Failed to build album: {e}")
            return None

    def _get_tracklist(self, release_group_id: str) -> List[Track]:
        """获取曲目列表"""
        # 先获取 releases
        releases = self._get_releases(release_group_id)
        if not releases:
            return []

        # 获取第一个 release 的曲目
        first_release = releases[0]
        release_id = first_release.get("id")
        if release_id:
            return self.get_release_tracks(release_id)

        return []

    def get_release_tracks(self, release_id: str) -> List[Track]:
        """获取特定 Release 的曲目列表"""
        url = f"{self.base_url}/release/{release_id}"
        params = {"inc": "recordings", "fmt": "json"}

        try:
            with self._get_client() as client:
                self._rate_limit()
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()

                tracklist = []
                position = 0

                for medium in data.get("media", []):
                    for track in medium.get("tracks", []):
                        position += 1
                        duration_ms = track.get("length")
                        duration = self._ms_to_duration(duration_ms) if duration_ms else ""

                        tracklist.append(Track(
                            position=str(position),
                            title=track.get("title", ""),
                            duration=duration
                        ))

                return tracklist

        except Exception as e:
            print(f"Failed to get tracklist: {e}")
            return []

    def _ms_to_duration(self, ms: int) -> str:
        """毫秒转换为时长字符串"""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _get_wikipedia_url(self, release_group: dict) -> Optional[str]:
        """从 Release Group 中获取 Wikipedia URL"""
        relations = release_group.get("relations", [])
        wiki_url = None
        wikidata_url = None

        for rel in relations:
            rel_type = rel.get("type", "")
            url = rel.get("url", {}).get("resource", "")

            if rel_type == "wikipedia" and url:
                return url  # 直接返回 Wikipedia URL
            elif rel_type == "wikidata" and url:
                wikidata_url = url  # 保存 Wikidata URL 备用

        # 如果有 Wikidata 链接，尝试获取对应的 Wikipedia 链接
        if wikidata_url:
            wiki_url = self._get_wikipedia_from_wikidata(wikidata_url)
            if wiki_url:
                return wiki_url

        return None

    def _get_wikipedia_from_wikidata(self, wikidata_url: str) -> Optional[str]:
        """从 Wikidata URL 获取 Wikipedia URL"""
        import re

        # 提取 Wikidata ID
        match = re.search(r"wikidata\.org/entity/(Q\d+)", wikidata_url)
        if not match:
            return None

        wikidata_id = match.group(1)

        try:
            # 使用 Wikidata API 获取 sitelinks
            api_url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"

            with self._get_client() as client:
                self._rate_limit()
                response = client.get(api_url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    entities = data.get("entities", {})
                    entity = entities.get(wikidata_id, {})
                    sitelinks = entity.get("sitelinks", {})

                    # 优先获取中文 Wikipedia
                    if "zhwiki" in sitelinks:
                        title = sitelinks["zhwiki"].get("title", "")
                        if title:
                            return f"https://zh.wikipedia.org/wiki/{title.replace(' ', '_')}"

                    # 其次英文 Wikipedia
                    if "enwiki" in sitelinks:
                        title = sitelinks["enwiki"].get("title", "")
                        if title:
                            return f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        except Exception:
            pass

        return None

    def _search_wikipedia_by_title(self, title: str, artist: str) -> str:
        """通过专辑标题和艺术家搜索 Wikipedia，优先中文"""
        import re
        import urllib.parse

        # 先尝试中文 Wikipedia
        search_query = f"{title} {artist} 专辑"
        zh_summary = self._search_wikipedia_by_lang(title, artist, search_query, "zh")
        if zh_summary:
            return zh_summary

        # 中文没有则尝试英文
        search_query = f"{title} {artist} album"
        return self._search_wikipedia_by_lang(title, artist, search_query, "en")

    def _search_wikipedia_by_lang(self, title: str, artist: str, search_query: str, lang: str) -> str:
        """在指定语言的 Wikipedia 中搜索"""
        import urllib.parse

        try:
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&format=json&srlimit=5"

            with self._get_client() as client:
                self._rate_limit()
                response = client.get(search_url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    search_results = data.get("query", {}).get("search", [])

                    # 找到最匹配的结果
                    for result in search_results:
                        result_title = result.get("title", "")
                        result_lower = result_title.lower()

                        # 中文 Wikipedia：检查是否包含"专辑"关键词
                        if lang == "zh":
                            if "专辑" in result_title or "專輯" in result_title:
                                # 获取摘要
                                page_title = result_title.replace(" ", "_")
                                summary = self._get_wikipedia_summary_by_title(page_title, lang)
                                if summary:
                                    return summary
                        else:
                            # 英文 Wikipedia：检查标题是否包含专辑名或艺术家
                            title_lower = title.lower()
                            artist_lower = artist.lower()
                            if title_lower in result_lower or artist_lower in result_lower:
                                page_title = result_title.replace(" ", "_")
                                summary = self._get_wikipedia_summary_by_title(page_title, lang)
                                if summary:
                                    return summary

        except Exception:
            pass

        return ""

    def _get_wikipedia_summary_by_title(self, page_title: str, lang: str = "en") -> str:
        """通过 Wikipedia 页面标题获取摘要"""
        try:
            api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{page_title}"

            with self._get_client() as client:
                self._rate_limit()
                response = client.get(api_url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    extract = data.get("extract", "")
                    # 限制长度，避免太长的简介
                    if extract and len(extract) > 1000:
                        extract = extract[:997] + "..."
                    return extract
        except Exception:
            pass

        return ""

    def _get_wikipedia_summary(self, wiki_url: str) -> str:
        """从 Wikipedia URL 获取简介"""
        import re

        # 提取 Wikipedia 页面标题
        match = re.search(r"wikipedia\.org/wiki/(.+)$", wiki_url)
        if not match:
            return ""

        page_title = match.group(1)

        # 使用 Wikipedia API 获取简介
        try:
            # 确定语言版本
            lang_match = re.search(r"^(\w+)\.wikipedia\.org", wiki_url)
            lang = lang_match.group(1) if lang_match else "en"

            api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{page_title}"

            with self._get_client() as client:
                self._rate_limit()
                response = client.get(api_url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    # 获取 extract 字段作为简介
                    extract = data.get("extract", "")
                    if extract:
                        return extract
        except Exception:
            pass

        return ""
