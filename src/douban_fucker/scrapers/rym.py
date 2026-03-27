"""RateYourMusic (RYM) 爬虫 - 浏览器自动化版本"""
import re
import time
from typing import List, Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup

from ..models import Album, SearchResult, Track
from ..utils import get_config
from .base import BaseScraper


class RYMScraper(BaseScraper):
    """RateYourMusic 爬虫 - 使用 Playwright 浏览器自动化"""

    name = "rym"
    base_url = "https://rateyourmusic.com"
    search_url = "https://rateyourmusic.com/search"

    def __init__(self):
        super().__init__()
        config = get_config()
        self.cookies_file = "./data/cookies/rym.json"
        self.timeout = config.request.timeout * 1000  # 转换为毫秒
        self._browser = None
        self._context = None
        self._page = None

    def _get_browser(self) -> Browser:
        """获取或创建浏览器实例"""
        if self._browser is None:
            playwright = sync_playwright().start()
            self._browser = playwright.chromium.launch(headless=False, slow_mo=100)
        return self._browser

    def _get_context(self) -> BrowserContext:
        """获取或创建浏览器上下文"""
        if self._context is None:
            browser = self._get_browser()
            self._context = browser.new_context()
        return self._context

    def _get_page(self) -> Page:
        """获取或创建页面"""
        if self._page is None:
            context = self._get_context()
            self._page = context.new_page()
        return self._page

    def close(self):
        """关闭浏览器"""
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None

    def ensure_logged_in(self) -> bool:
        """确保已登录 RYM，如果未登录则弹出浏览器让你手动登录"""
        context = self._get_context()

        # 尝试加载保存的 cookies
        import json
        from pathlib import Path
        cookies_path = Path(self.cookies_file)

        if cookies_path.exists():
            try:
                with open(cookies_path, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                print("已加载保存的 RYM cookies")
            except Exception:
                pass

        # 检查是否已登录
        page = self._get_page()
        page.goto(self.base_url, timeout=self.timeout)
        time.sleep(2)

        if self._is_logged_in():
            print("已登录 RYM")
            return True

        # 需要登录
        print("=" * 50)
        print("RYM 需要登录，请手动登录")
        print("登录后程序会自动保存 cookies")
        print("=" * 50)

        return self._wait_for_login()

    def _is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            page = self._get_page()

            # 检查页面上的登录状态元素
            # 登录后会有用户菜单
            user_menu = page.query_selector(".user_menu, .nav_user, a[href*='/user/']")
            if user_menu:
                return True

            # 检查 cookies
            cookies = self._get_context().cookies()
            cookie_names = {c["name"] for c in cookies}
            # RYM 登录后的 cookies
            if "rym_session" in cookie_names or "rym_token" in cookie_names:
                return True

            # 检查 URL 是否包含登录相关
            if "login" in page.url.lower():
                return False

            return False
        except Exception:
            return False

    def _wait_for_login(self, timeout: int = 120) -> bool:
        """等待登录完成"""
        page = self._get_page()
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._is_logged_in():
                # 保存 cookies
                self._save_cookies()
                print("登录成功，Cookies 已保存")
                return True
            time.sleep(1)

        return False

    def _save_cookies(self):
        """保存 cookies 到文件"""
        import json
        from pathlib import Path

        cookies_path = Path(self.cookies_file)
        cookies_path.parent.mkdir(parents=True, exist_ok=True)

        cookies = self._get_context().cookies()
        with open(cookies_path, "w") as f:
            json.dump(cookies, f)

    def import_cookies(self, cookies_json: str = None):
        """
        手动导入 cookies

        Args:
            cookies_json: cookies 的 JSON 字符串（EditThisCookie Export 格式）
        """
        import json
        from pathlib import Path

        cookies_path = Path(self.cookies_file)
        cookies_path.parent.mkdir(parents=True, exist_ok=True)

        if cookies_json is None:
            print("请输入 cookies JSON 字符串（EditThisCookie Export 格式）:")
            cookies_json = input().strip()

        if not cookies_json:
            print("未输入 cookies")
            return False

        try:
            data = json.loads(cookies_json)

            # EditThisCookie 格式转换
            if data and isinstance(data, list) and len(data) > 0:
                for cookie in data:
                    # 添加缺失的字段
                    if not cookie.get("domain"):
                        cookie["domain"] = ".rateyourmusic.com"
                    cookie["path"] = cookie.get("path", "/")
                    cookie["secure"] = cookie.get("secure", True)
                    cookie["httpOnly"] = cookie.get("httpOnly", False)

                    # 转换 sameSite 值
                    same_site = cookie.get("sameSite", "Lax")
                    if same_site == "no_restriction":
                        same_site = None  # Playwright 使用 None 而不是 "no_restriction"
                    cookie["sameSite"] = same_site

            with open(cookies_path, "w") as f:
                json.dump(data, f)

            print(f"✓ Cookies 已保存到: {cookies_path}")

            # 验证
            context = self._get_context()
            context.add_cookies(data)

            page = self._get_page()
            page.goto(self.base_url, timeout=self.timeout)
            time.sleep(2)

            if self._is_logged_in():
                print("✓ Cookies 验证成功！")
                return True
            else:
                print("✗ Cookies 可能无效，请检查是否包含登录 session")
                return False

        except json.JSONDecodeError as e:
            print(f"✗ JSON 解析失败: {e}")
            return False
        except Exception as e:
            print(f"✗ 错误: {e}")
            return False

    def login(self) -> bool:
        """
        登录 RYM - 打开浏览器让你手动登录

        Returns:
            True: 登录成功
            False: 登录失败
        """
        try:
            page = self._get_page()

            # 访问 RYM
            print("正在打开 RYM...")
            page.goto(self.base_url, timeout=self.timeout)
            time.sleep(2)

            if self._is_logged_in():
                print("已经登录 RYM")
                self._save_cookies()
                return True

            print("=" * 50)
            print("请在打开的浏览器中手动登录 RYM 账号")
            print("登录成功后程序会自动保存会话")
            print("=" * 50)

            if self._wait_for_login():
                return True
            else:
                print("登录超时")
                return False

        except Exception as e:
            print(f"登录过程出错: {e}")
            return False

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """搜索专辑"""
        if not self.ensure_logged_in():
            print("未登录 RYM，无法搜索")
            return []

        results = []
        page = self._get_page()

        try:
            url = f"{self.search_url}/albums?q={query}&type=a"
            print(f"搜索: {query}")
            page.goto(url, timeout=self.timeout)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # 解析搜索结果
            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            results_elems = soup.select(".page_result")
            for elem in results_elems[:limit]:
                album = self._parse_search_result(elem)
                if album:
                    results.append(SearchResult(
                        source=self.name,
                        album=album,
                        relevance=1.0
                    ))

            print(f"找到 {len(results)} 个结果")

        except Exception as e:
            print(f"RYM search failed: {e}")

        return results

    def get_album(self, album_id: str) -> Optional[Album]:
        """通过 ID 获取专辑详情"""
        url = f"{self.base_url}/album/{album_id}"
        return self.get_album_by_url(url)

    def get_album_by_url(self, url: str) -> Optional[Album]:
        """通过 URL 获取专辑详情"""
        if not self.ensure_logged_in():
            return None

        page = self._get_page()

        try:
            print(f"获取专辑: {url}")
            page.goto(url, timeout=self.timeout)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            return self._parse_album_page(soup, url)

        except Exception as e:
            print(f"RYM album fetch failed: {e}")

        return None

    def _parse_search_result(self, elem) -> Optional[Album]:
        """解析搜索结果元素"""
        try:
            # 获取标题和链接
            title_elem = elem.select_one(".album_title a")
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)
            album_url = title_elem.get("href", "")
            if album_url and not album_url.startswith("http"):
                album_url = self.base_url + album_url

            # 获取艺术家
            artist_elem = elem.select_one(".album_artist")
            artist = artist_elem.get_text(strip=True) if artist_elem else "Unknown"
            # 移除 "by " 前缀
            if artist.startswith("by "):
                artist = artist[3:]

            # 获取年份
            year_text = elem.select_one(".album_year")
            year = None
            if year_text:
                year_match = re.search(r"\d{4}", year_text.get_text())
                if year_match:
                    year = int(year_match.group())

            # 获取封面
            cover_elem = elem.select_one(".cover img")
            cover_url = ""
            if cover_elem:
                cover_url = cover_elem.get("data-src") or cover_elem.get("src", "")

            # 提取 album_id
            album_id = album_url.replace(self.base_url, "").strip("/")

            album = Album(
                title=title,
                artist=artist,
                year=year,
                cover_url=cover_url,
                source=self.name,
                source_url=album_url,
                source_id=album_id,
                api_source="rym_browser",
            )

            return album

        except Exception as e:
            print(f"Failed to parse search result: {e}")
            return None

    def _parse_album_page(self, soup: BeautifulSoup, url: str) -> Optional[Album]:
        """解析专辑详情页面"""
        try:
            # 获取标题
            title_elem = soup.select_one(".album_title")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"

            # 获取艺术家
            artist_elem = soup.select_one(".album_artists a")
            artist = artist_elem.get_text(strip=True) if artist_elem else "Unknown"

            # 获取发行信息
            info_elems = soup.select(".section_info li")
            year = None
            label = ""
            catalog_num = ""
            format_str = ""
            country = ""

            for elem in info_elems:
                text = elem.get_text(strip=True)
                if "Release Date" in text or "Original Release:" in text:
                    year_match = re.search(r"\d{4}", text)
                    if year_match:
                        year = int(year_match.group())
                elif "Label:" in text or "Record Label:" in text:
                    label = text.split(":", 1)[-1].strip()
                elif "Catalog#:" in text:
                    catalog_num = text.split(":", 1)[-1].strip()
                elif "Format:" in text:
                    format_str = text.split(":", 1)[-1].strip()
                elif "Country:" in text:
                    country = text.split(":", 1)[-1].strip()

            # 获取封面
            cover_elem = soup.select_one(".cover img")
            cover_url = ""
            if cover_elem:
                cover_url = cover_elem.get("src") or cover_elem.get("data-src", "")

            # 获取风格/类型
            genres = []
            styles = []
            genre_elems = soup.select(".genre a")
            style_elems = soup.select(".style a")
            genres = [e.get_text(strip=True) for e in genre_elems]
            styles = [e.get_text(strip=True) for e in style_elems]

            # 获取曲目列表
            tracklist = []
            track_elems = soup.select(".tracklist .track, .track_list .track")
            for idx, track in enumerate(track_elems, 1):
                position_elem = track.select_one(".track_number, .track_position")
                title_elem = track.select_one(".track_title, .track_name")
                duration_elem = track.select_one(".track_length, .track_duration")

                tracklist.append(Track(
                    position=position_elem.get_text(strip=True) if position_elem else str(idx),
                    title=title_elem.get_text(strip=True) if title_elem else "",
                    duration=duration_elem.get_text(strip=True) if duration_elem else ""
                ))

            # 获取描述/简介
            description = ""
            desc_elem = soup.select_one(".section_description")
            if desc_elem:
                description = desc_elem.get_text(strip=True)

            # 提取 album_id
            album_id = url.replace(self.base_url, "").strip("/")

            album = Album(
                title=title,
                artist=artist,
                year=year,
                genre=genres,
                style=styles,
                label=label,
                catalog_number=catalog_num,
                format=format_str,
                country=country,
                tracklist=tracklist,
                cover_url=cover_url,
                source=self.name,
                source_url=url,
                source_id=album_id,
                description=description,
                api_source="rym_browser",
            )

            print(f"解析完成: {title}")
            print(f"  曲目数: {len(tracklist)}")

            return album

        except Exception as e:
            print(f"Failed to parse album page: {e}")
            return None

    def _extract_album_id_from_url(self, url: str) -> str:
        """从 URL 提取专辑 ID"""
        match = re.search(r"/album/([^/]+)", url)
        if match:
            return match.group(1)
        return url
