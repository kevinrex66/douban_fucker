"""豆瓣浏览器操作模块"""
import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from ..models import Album
from ..utils import get_config
from .session import SessionManager

# 英文流派 -> 豆瓣流派下拉框选项 映射表
# 豆瓣实际下拉选项 (14个):
#   Blues 布鲁斯, Classical 古典, Easy Listening 轻音乐, Electronic 电子,
#   Folk 民谣, Funk/Soul/R&B 放克/灵魂/R&B, Jazz 爵士, Latin 拉丁,
#   Pop 流行, Rap 说唱, Reggae 雷鬼, Rock 摇滚, Soundtrack 原声, World 世界音乐
# 映射值使用英文部分，_select_from_dropdown 会用子串匹配找到对应选项
GENRE_TO_DOUBAN = {
    # === 大分类直接映射 ===
    "blues": "Blues",
    "classical": "Classical",
    "easy listening": "Easy Listening",
    "electronic": "Electronic",
    "folk": "Folk",
    "funk / soul": "Funk/Soul/R&B",
    "funk/soul": "Funk/Soul/R&B",
    "funk": "Funk/Soul/R&B",
    "soul": "Funk/Soul/R&B",
    "r&b": "Funk/Soul/R&B",
    "rhythm & blues": "Funk/Soul/R&B",
    "jazz": "Jazz",
    "latin": "Latin",
    "pop": "Pop",
    "rap": "Rap",
    "hip hop": "Rap",
    "hip-hop": "Rap",
    "reggae": "Reggae",
    "rock": "Rock",
    "soundtrack": "Soundtrack",
    "stage & screen": "Soundtrack",
    "world": "World",
    "world music": "World",
    # === Discogs 大分类 ===
    "folk, world, & country": "Folk",
    "non-music": "Electronic",
    "children's": "Pop",
    "brass & military": "Classical",
    # === Rock 子分类 ===
    "indie rock": "Rock",
    "alternative rock": "Rock",
    "post-rock": "Rock",
    "progressive rock": "Rock",
    "psychedelic rock": "Rock",
    "garage rock": "Rock",
    "hard rock": "Rock",
    "grunge": "Rock",
    "shoegaze": "Rock",
    "noise rock": "Rock",
    "post-punk": "Rock",
    "punk rock": "Rock",
    "punk": "Rock",
    "hardcore punk": "Rock",
    "new wave": "Rock",
    "folk rock": "Rock",
    # === Metal -> Rock (豆瓣无独立金属分类) ===
    "metal": "Rock",
    "heavy metal": "Rock",
    "death metal": "Rock",
    "black metal": "Rock",
    "thrash metal": "Rock",
    "doom metal": "Rock",
    # === Pop 子分类 ===
    "indie pop": "Pop",
    "synth-pop": "Pop",
    "dream pop": "Pop",
    "art pop": "Pop",
    "k-pop": "Pop",
    "j-pop": "Pop",
    "disco": "Pop",
    "chanson": "Pop",
    # === Electronic 子分类 ===
    "dance": "Electronic",
    "techno": "Electronic",
    "house": "Electronic",
    "ambient": "Electronic",
    "drum and bass": "Electronic",
    "dubstep": "Electronic",
    "idm": "Electronic",
    "trip hop": "Electronic",
    "downtempo": "Electronic",
    "trance": "Electronic",
    "edm": "Electronic",
    "industrial": "Electronic",
    "noise": "Electronic",
    "experimental": "Electronic",
    "avant-garde": "Electronic",
    # === Jazz 子分类 ===
    "bossa nova": "Jazz",
    "bebop": "Jazz",
    "swing": "Jazz",
    "free jazz": "Jazz",
    "cool jazz": "Jazz",
    "hard bop": "Jazz",
    "post-bop": "Jazz",
    "fusion": "Jazz",
    "smooth jazz": "Jazz",
    "acid jazz": "Jazz",
    "avant-garde jazz": "Jazz",
    "vocal jazz": "Jazz",
    "contemporary jazz": "Jazz",
    "big band": "Jazz",
    "dixieland": "Jazz",
    "modal jazz": "Jazz",
    "soul jazz": "Jazz",
    "spiritual jazz": "Jazz",
    # === Classical 子分类 ===
    "opera": "Classical",
    "baroque": "Classical",
    "romantic": "Classical",
    "modern classical": "Classical",
    "contemporary classical": "Classical",
    "chamber music": "Classical",
    "symphony": "Classical",
    "choral": "Classical",
    # === Folk 子分类 ===
    "singer-songwriter": "Folk",
    "americana": "Folk",
    "acoustic": "Folk",
    "country": "Folk",
    "bluegrass": "Folk",
    "new age": "Easy Listening",
    "spoken word": "Easy Listening",
    # === Funk/Soul/R&B 子分类 ===
    "gospel": "Funk/Soul/R&B",
    "neo soul": "Funk/Soul/R&B",
    "motown": "Funk/Soul/R&B",
    # === Reggae 子分类 ===
    "ska": "Reggae",
    "dub": "Reggae",
    "dancehall": "Reggae",
    # === Latin 子分类 ===
    "flamenco": "Latin",
    "samba": "Latin",
    "salsa": "Latin",
    "tango": "Latin",
    # === World 子分类 ===
    "afrobeat": "World",
    "african": "World",
    "celtic": "World",
    # === Blues 子分类 ===
    "rhythm and blues": "Blues",
    "delta blues": "Blues",
    "chicago blues": "Blues",
    "electric blues": "Blues",
}

# 专辑类型 -> 豆瓣专辑类型 映射表
# 豆瓣专辑类型选项: 专辑, 单曲, EP, 精选集, 合集, 现场专辑, 原声带, 混音
ALBUM_TYPE_TO_DOUBAN = {
    "album": "专辑",
    "single": "单曲",
    "ep": "EP",
    "compilation": "精选集",
    "soundtrack": "原声带",
    "live": "现场专辑",
    "remix": "混音",
    "mixtape": "合集",
    "mixtape/street": "合集",
    "dj-mix": "混音",
    "broadcast": "专辑",
    "mini-album": "EP",
    "demo": "专辑",
    "interview": "专辑",
    "spokenword": "专辑",
    "audiobook": "专辑",
    "audio drama": "专辑",
}


class DoubanBrowser:
    """豆瓣浏览器操作类"""

    def __init__(self):
        self.config = get_config().douban
        self.session = SessionManager()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def _get_browser_args(self) -> dict:
        """获取浏览器配置"""
        return {
            "headless": self.config.browser.headless,
            "slow_mo": self.config.browser.slow_mo,
        }

    def launch(self) -> None:
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(**self._get_browser_args())
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def close(self) -> None:
        """关闭浏览器"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if hasattr(self, "playwright"):
            self.playwright.stop()
        self.browser = None
        self.context = None
        self.page = None

    def login(self) -> bool:
        """
        登录豆瓣 - 打开浏览器让你手动登录

        Returns:
            True: 登录成功
            False: 登录失败
        """
        self.launch()

        try:
            print("正在打开豆瓣音乐...")
            self.page.goto("https://music.douban.com", timeout=self.config.browser.timeout)
            time.sleep(2)

            if self._is_logged_in():
                print("已经登录了豆瓣账号")
                cookies = self.context.cookies()
                self.session.save_cookies(cookies)
                return True

            print("=" * 50)
            print("请在打开的浏览器中手动登录豆瓣账号")
            print("登录成功后程序会自动保存会话")
            print("=" * 50)

            if self._wait_for_login():
                cookies = self.context.cookies()
                self.session.save_cookies(cookies)
                print("登录成功！Cookies 已保存")
                return True
            else:
                print("登录超时")
                return False

        except Exception as e:
            print(f"登录过程出错: {e}")
            return False

    def _is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            cookies = self.context.cookies()
            cookie_names = {c["name"] for c in cookies}
            if "dbcl2" in cookie_names:
                return True
            return False
        except Exception:
            return False

    def _wait_for_login(self, timeout: int = 120) -> bool:
        """等待登录完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._is_logged_in():
                return True
            time.sleep(1)
        return False

    def ensure_logged_in(self) -> bool:
        """确保已登录，如果未登录则要求重新登录"""
        cookies = self.session.load_cookies()
        if cookies and self.session.is_valid(cookies):
            self.launch()
            self.context.add_cookies(cookies)

            try:
                self.page.goto("https://music.douban.com", timeout=self.config.browser.timeout)
                time.sleep(1)

                if self._is_logged_in():
                    return True

                self.close()
            except Exception:
                self.close()

        print("需要登录豆瓣...")
        return self.login()

    def upload_album(self, album: Album) -> Optional[str]:
        """
        上传专辑到豆瓣

        Args:
            album: 专辑对象

        Returns:
            豆瓣页面 URL 或 None
        """
        # 确保已登录（会打开浏览器）
        logged_in = self.ensure_logged_in()
        if not logged_in:
            print("登录失败，无法上传")
            return None

        try:
            # 1. 先检查唱片是否已存在
            print("检查唱片是否已存在...")
            self.page.goto("https://music.douban.com", timeout=self.config.browser.timeout)
            time.sleep(1)

            search_input = self.page.query_selector("#inp-query")
            if search_input:
                search_input.fill(album.title)
                time.sleep(0.5)

                search_btn = self.page.query_selector("input[type='submit']")
                if search_btn:
                    search_btn.click()
                else:
                    search_input.press("Enter")

                time.sleep(2)

                existing_subject = self._check_existing_album(album)
                if existing_subject:
                    print(f"唱片已存在: {existing_subject}")
                    return existing_subject

            print("唱片不存在，准备添加...")

            # 2. 进入添加页面
            print("访问添加页面...")
            self.page.goto("https://music.douban.com/new_subject", timeout=self.config.browser.timeout)
            time.sleep(2)

            # 3. 在"添加新的唱片"表单中填写专辑名
            print("填写专辑名...")
            if not self._fill_new_subject_title(album):
                print("填写专辑名失败")
                return None

            time.sleep(0.5)

            # 4. 点击"添加无条形码的唱片"链接
            print("点击添加链接...")
            if not self._click_add_no_barcode_link():
                print("未找到添加链接")
                print("当前页面URL:", self.page.url)
                return None

            # 等待表单页面加载
            time.sleep(2)

            # 5. 填写表单（基本信息，不上传封面）
            print("填写专辑信息...")
            self._fill_album_form_basic(album)

            print(f"\n专辑 '{album.title}' 表单已填入")
            print("请在浏览器中点击【下一步】上传封面")
            print("浏览器将保持打开状态，等待您点击后自动上传封面...")

            # 6. 等待用户点击"下一步"，然后处理封面上传页面
            self._wait_and_handle_cover_upload(album)

            return None

        except Exception as e:
            print(f"上传失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _fill_album_form_basic(self, album: Album) -> None:
        """填写专辑基本信息（不包含封面上传）"""
        try:
            # 唱片名 (p_27)
            title_input = self.page.query_selector("#p_27")
            if title_input:
                title_input.fill(album.title)
                print(f"填写标题: {album.title}")

            # 艺术家 (p_48 - 第一个输入框)
            artist_input = self.page.query_selector("#p_48_0")
            if not artist_input:
                artist_input = self.page.query_selector("input[name='p_48']")
            if artist_input:
                artist_input.fill(album.artist)

            # 发行时间 (p_51) - 优先使用完整日期
            if album.release_date:
                date_input = self.page.query_selector("#p_51")
                if date_input:
                    date_input.fill(album.release_date)
                    print(f"填写发行日期: {album.release_date}")
            elif album.year:
                year_input = self.page.query_selector("#p_51")
                if year_input:
                    year_input.fill(str(album.year))

            # 厂牌/出版者 (p_50)
            if album.label:
                label_input = self.page.query_selector("#p_50")
                if label_input:
                    label_input.fill(album.label)
                    print(f"填写厂牌: {album.label}")

            # 介质类型 (p_49) - 需要点击下拉选择
            if album.format:
                format_map = {
                    "cd": "CD",
                    "vinyl": "黑胶",
                    "digital": "数字(Digital)",
                    "cassette": "磁带",
                }
                format_value = format_map.get(album.format.lower(), album.format)
                self._select_from_dropdown("p_49", format_value)

            # ========== 诊断: 打印下拉框 DOM 结构 ==========
            self._dump_dropdown_html(["p_116", "p_57", "p_49"])
            # ========== 诊断结束 ==========

            # 流派 (p_116) - 映射英文流派到豆瓣中文
            douban_genre = self._map_genre_to_douban(album.genre)
            if douban_genre:
                if self._select_from_dropdown("p_116", douban_genre):
                    print(f"选择流派: {douban_genre}")
                else:
                    print(f"流派下拉选择失败: {douban_genre}")

            # 专辑类型 (p_57) - 映射到豆瓣类型
            douban_type = self._map_album_type_to_douban(album)
            if douban_type:
                if self._select_from_dropdown("p_57", douban_type):
                    print(f"选择专辑类型: {douban_type}")
                else:
                    print(f"专辑类型下拉选择失败: {douban_type}")

            # 曲目列表 (p_52_other - textarea)
            if album.tracklist:
                tracklist_text = "\n".join([
                    f"{t.position}. {t.title}" + (f" {t.duration}" if t.duration else "")
                    for t in album.tracklist
                ])
                tracklist_ta = self.page.query_selector("textarea[name='p_52_other']")
                if tracklist_ta:
                    tracklist_ta.fill(tracklist_text)
                    print(f"填写曲目: {len(album.tracklist)} 首")

            # 简介 (p_28_other - textarea)
            if album.description:
                desc_ta = self.page.query_selector("textarea[name='p_28_other']")
                if desc_ta:
                    desc_ta.fill(album.description[:500])

            # 参考资料 (p_152_other - textarea)
            if album.source_url:
                ref_ta = self.page.query_selector("textarea[name='p_152_other']")
                if ref_ta:
                    ref_ta.fill(album.source_url)

        except Exception as e:
            print(f"填写表单时出错: {e}")

    def _wait_and_handle_cover_upload(self, album: Album) -> None:
        """等待用户点击下一步，然后处理封面上传页面"""
        try:
            print("\n" + "="*50)
            print("表单已填写完成！")
            print("请在浏览器中点击【下一步】进入封面上传页面")
            print("点击后程序会自动上传封面")
            print("="*50 + "\n")

            # 无限循环等待封面上传页面出现
            print("等待封面上传页面...")
            file_input = None
            check_interval = 0.5  # 每0.5秒检查一次

            while file_input is None:
                try:
                    # 检查是否有文件上传输入框
                    file_input = self.page.query_selector("input[type='file']")

                    if file_input:
                        print("\n✓ 检测到封面上传页面!")
                        break

                    # 检查是否还在表单页面（通过检查特定的表单元素）
                    # 如果还在表单页面，继续等待
                    time.sleep(check_interval)

                except Exception:
                    time.sleep(check_interval)
                    continue

            # 找到封面上传页面后，上传封面
            if file_input and album.cover_image:
                cover_path = Path(album.cover_image)
                # 再次验证封面文件是否真实存在
                if cover_path.exists() and cover_path.stat().st_size > 0:
                    print(f"正在上传封面: {cover_path.name}")
                    file_input.set_input_files(str(cover_path))
                    time.sleep(2)
                    print("✓ 封面已上传")
                    print("\n" + "="*50)
                    print("请检查封面是否正确")
                    print("确认无误后，请手动点击【提交】按钮")
                    print("浏览器将保持打开状态等待您操作")
                    print("="*50)
                else:
                    print(f"✗ 封面文件不存在或无效: {cover_path}")
                    print("请手动上传封面")
            elif not album.cover_image:
                print("✗ 未找到封面图片，请手动上传")

        except Exception as e:
            print(f"处理封面上传时出错: {e}")

    def _check_existing_album(self, album: Album) -> Optional[str]:
        """检查专辑是否已存在（标题+艺术家双重验证）"""
        try:
            # 从搜索结果中提取每条结果的标题、艺术家、链接
            results = self.page.evaluate("""() => {
                const items = [];
                // 豆瓣搜索结果中每个条目通常包含 subject 链接
                const links = document.querySelectorAll('a[href*="/subject/"]');
                for (const link of links) {
                    const href = link.getAttribute('href') || '';
                    if (!/\\/subject\\/\\d+/.test(href)) continue;
                    const title = (link.textContent || '').trim();
                    if (!title) continue;
                    // 获取父容器的全部文本，用于提取艺术家信息
                    let container = link.closest('tr, .item, .result, li, dd, td');
                    if (!container) container = link.parentElement?.parentElement;
                    const contextText = container ? container.textContent.trim() : '';
                    items.push({ href, title, context: contextText.substring(0, 300) });
                }
                return items;
            }""")

            for item in (results or []):
                href = item.get("href", "")
                result_title = item.get("title", "")
                context = item.get("context", "")

                if not self._title_matches(album.title, result_title):
                    continue

                # 验证艺术家是否匹配
                if album.artist and not self._artist_matches(album.artist, context):
                    print(f"  标题匹配但艺术家不符，跳过: {result_title}")
                    continue

                if not href.startswith("http"):
                    href = f"https://music.douban.com{href}"
                return href
        except Exception as e:
            print(f"  检查已存在唱片时出错: {e}")
        return None

    def _title_matches(self, our_title: str, result_title: str) -> bool:
        """检查标题是否匹配（严格）"""
        t1 = our_title.lower().strip()
        t2 = result_title.lower().strip()

        if not t1 or not t2:
            return False

        # 完全相同
        if t1 == t2:
            return True

        # 去掉括号内容后比较
        t1_clean = re.sub(r'\s*[\(\[（][^)\]）]*[\)\]）]', '', t1).strip()
        t2_clean = re.sub(r'\s*[\(\[（][^)\]）]*[\)\]）]', '', t2).strip()
        if t1_clean and t2_clean and t1_clean == t2_clean:
            return True

        # 关键词匹配 - 过滤停用词后要求 90% 以上匹配
        stop_words = {'the', 'a', 'an', 'of', 'at', 'on', 'in', 'and', 'or', 'for'}
        words1 = {w for w in re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', t1) if len(w) > 1 and w not in stop_words}
        words2 = {w for w in re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', t2) if len(w) > 1 and w not in stop_words}

        if not words1 or not words2:
            return False

        common = words1 & words2
        match_ratio = len(common) / max(len(words1), len(words2))
        return match_ratio >= 0.9

    def _artist_matches(self, our_artist: str, context_text: str) -> bool:
        """检查艺术家是否出现在搜索结果上下文中"""
        if not our_artist:
            return True  # 没有艺术家信息则跳过验证

        context_lower = context_text.lower()
        artist_lower = our_artist.lower().strip()

        # 完整名字出现在上下文中
        if artist_lower in context_lower:
            return True

        # 去掉常见后缀再试（如 "Jr.", "Trio", "Quartet"）
        artist_clean = re.sub(r'\s+(jr\.?|sr\.?|trio|quartet|quintet|sextet|orchestra|band|ensemble)$', '', artist_lower, flags=re.IGNORECASE).strip()
        if artist_clean and artist_clean in context_lower:
            return True

        # 姓氏匹配（取最后一个词作为姓氏，至少3个字符）
        parts = artist_lower.split()
        if len(parts) >= 2:
            surname = parts[-1].rstrip('.')
            if len(surname) >= 3 and surname in context_lower:
                # 姓氏匹配但需要至少名字首字母也出现
                first_initial = parts[0][0]
                if first_initial in context_lower:
                    return True

        return False

    def _click_add_no_barcode(self) -> bool:
        """点击添加无条形码按钮（已废弃，保留用于兼容性）"""
        return self._click_add_no_barcode_link()

    def _fill_new_subject_title(self, album: Album) -> bool:
        """在 new_subject 页面填写专辑名到"添加新的唱片"表单"""
        try:
            # 豆瓣 new_subject 页面结构：
            # 1. 顶部有搜索框 (#inp-query)
            # 2. 下方有"添加新的唱片"表单，其中的输入框才是目标

            # 方法1: 查找包含"唱片名"标签的输入框
            labels = self.page.query_selector_all("label")
            for label in labels:
                label_text = label.text_content() or ""
                if "唱片名" in label_text or "专辑名" in label_text:
                    # 找到 label 后的输入框
                    input_in_label = label.query_selector("input")
                    if input_in_label:
                        input_in_label.fill(album.title)
                        time.sleep(0.5)
                        print(f"已填写专辑名: {album.title}")
                        return True

                    # 查找 label 的 for 属性指向的输入框
                    for_attr = label.get_attribute("for")
                    if for_attr:
                        target_input = self.page.query_selector(f"#{for_attr}")
                        if target_input:
                            target_input.fill(album.title)
                            time.sleep(0.5)
                            print(f"已填写专辑名: {album.title}")
                            return True

            # 方法2: 查找有 placeholder "唱片名"的输入框
            all_inputs = self.page.query_selector_all("input[type='text']")
            for inp in all_inputs:
                placeholder = inp.get_attribute("placeholder") or ""
                if "唱片名" in placeholder or "专辑名" in placeholder:
                    inp.fill(album.title)
                    time.sleep(0.5)
                    print(f"已填写专辑名: {album.title}")
                    return True

            # 方法3: 查找表单内的输入框（排除搜索框）
            search_input = self.page.query_selector("#inp-query")
            for inp in all_inputs:
                if inp != search_input:
                    # 检查是否是搜索框的兄弟元素或父元素
                    is_search = False
                    try:
                        # 检查输入框的最近 form 祖先
                        form_ancestor = inp.evaluate("""el => {
                            let parent = el.closest('form');
                            if (parent) {
                                let html = parent.innerHTML || '';
                                return html.includes('搜索') || html.includes('query') || html.includes('search');
                            }
                            return false;
                        }""")
                        is_search = form_ancestor
                    except:
                        pass

                    if not is_search:
                        inp.fill(album.title)
                        time.sleep(0.5)
                        print(f"已填写专辑名: {album.title}")
                        return True

            print("未找到专辑名输入框")
            return False

        except Exception as e:
            print(f"填写专辑名出错: {e}")
            return False

    def _click_add_no_barcode_link(self) -> bool:
        """点击'添加无条形码的唱片'链接"""
        try:
            # 方法1: 查找包含"无条形码"文本的链接
            links = self.page.query_selector_all("a")
            for link in links:
                text = link.text_content() or ""
                if "无条形码" in text or "无条码" in text:
                    href = link.get_attribute("href")
                    if href:
                        print(f"找到添加链接: {text}")
                        link.click()
                        time.sleep(2)
                        return True

            # 方法2: 查找包含"无条形码"的任何元素
            elements = self.page.query_selector_all("[href*='no_uid'], [onclick*='no_uid']")
            for elem in elements:
                text = elem.text_content() or ""
                href = elem.get_attribute("href") or ""
                if "无条形码" in text or "no_uid" in href:
                    print(f"找到 no_uid 链接")
                    elem.click()
                    time.sleep(2)
                    return True

            # 方法3: 查找添加按钮
            buttons = self.page.query_selector_all("button, input[type='submit'], a[class*='btn']")
            for btn in buttons:
                text = (btn.text_content() or "").strip()
                value = btn.get_attribute("value") or ""
                if "添加" in text or "添加" in value or "无条形码" in text:
                    print(f"找到添加按钮: {text or value}")
                    btn.click()
                    time.sleep(2)
                    return True

            # 方法4: 尝试直接访问无条码添加页面
            print("尝试直接访问添加页面...")
            self.page.goto("https://music.douban.com/subject/no_uid/", timeout=self.config.browser.timeout)
            time.sleep(2)
            return True

        except Exception as e:
            print(f"点击添加链接失败: {e}")
            return False

    def _fill_album_form(self, album: Album) -> None:
        """填写专辑表单

        豆瓣添加唱片表单字段:
        - p_27: 唱片名 (title)
        - p_56: 又名 (aka)
        - p_48: 表演者/艺术家 (artist)
        - p_116: 流派 (genre) - 需要点击选择
        - p_57: 专辑类型 - 需要点击选择
        - p_49: 介质 (format) - 需要点击选择
        - p_51: 发行时间 (release date)
        - p_50: 出版者/厂牌 (label)
        - p_55: 碟片数
        - p_54: ISRC
        - p_52_other: 曲目 (textarea)
        - p_28_other: 简介 (textarea)
        - p_152_other: 参考资料 (textarea)
        """
        try:
            # 1. 上传封面图片 (如果有本地文件)
            if album.cover_image:
                cover_path = Path(album.cover_image)
                if cover_path.exists():
                    print(f"上传封面图片: {cover_path}")
                    file_input = self.page.query_selector("input[type='file']")
                    if file_input:
                        file_input.set_input_files(str(cover_path))
                        time.sleep(2)  # 等待图片上传

            # 2. 唱片名 (p_27)
            title_input = self.page.query_selector("#p_27")
            if title_input:
                title_input.fill(album.title)
                print(f"填写标题: {album.title}")

            # 艺术家 (p_48 - 第一个输入框)
            artist_input = self.page.query_selector("#p_48_0")
            if not artist_input:
                artist_input = self.page.query_selector("input[name='p_48']")
            if artist_input:
                artist_input.fill(album.artist)

            # 发行时间 (p_51) - 优先使用完整日期
            if album.release_date:
                date_input = self.page.query_selector("#p_51")
                if date_input:
                    date_input.fill(album.release_date)
                    print(f"填写发行日期: {album.release_date}")
            elif album.year:
                year_input = self.page.query_selector("#p_51")
                if year_input:
                    year_input.fill(str(album.year))

            # 厂牌/出版者 (p_50)
            if album.label:
                label_input = self.page.query_selector("#p_50")
                if label_input:
                    label_input.fill(album.label)

            # 介质类型 (p_49) - 需要点击下拉选择
            if album.format:
                format_map = {
                    "cd": "CD",
                    "vinyl": "黑胶",
                    "digital": "数字(Digital)",
                    "cassette": "磁带",
                }
                format_value = format_map.get(album.format.lower(), album.format)
                self._select_from_dropdown("p_49", format_value)

            # 流派 (p_116) - 映射英文流派到豆瓣中文
            douban_genre = self._map_genre_to_douban(album.genre)
            if douban_genre:
                self._select_from_dropdown("p_116", douban_genre)

            # 专辑类型 (p_57) - 映射到豆瓣类型
            douban_type = self._map_album_type_to_douban(album)
            if douban_type:
                self._select_from_dropdown("p_57", douban_type)

            # 曲目列表 (p_52_other - textarea)
            if album.tracklist:
                tracklist_text = "\n".join([
                    f"{t.position}. {t.title}" + (f" {t.duration}" if t.duration else "")
                    for t in album.tracklist
                ])
                tracklist_ta = self.page.query_selector("textarea[name='p_52_other']")
                if tracklist_ta:
                    tracklist_ta.fill(tracklist_text)

            # 简介 (p_28_other - textarea)
            if album.description:
                desc_ta = self.page.query_selector("textarea[name='p_28_other']")
                if desc_ta:
                    desc_ta.fill(album.description[:500])

            # 参考资料 (p_152_other - textarea)
            # 通常填写来源 URL
            if album.source_url:
                ref_ta = self.page.query_selector("textarea[name='p_152_other']")
                if ref_ta:
                    ref_ta.fill(album.source_url)

        except Exception as e:
            print(f"填写表单时出错: {e}")

    def _dump_dropdown_html(self, field_ids: list) -> None:
        """诊断: 打印下拉框相关元素的 HTML 结构"""
        print("\n" + "=" * 60)
        print(">>> 下拉框 DOM 诊断 <<<")
        print("=" * 60)
        for field_id in field_ids:
            html = self.page.evaluate("""(fieldId) => {
                const results = [];

                // 1. 查找 id 完全匹配的元素
                const exact = document.getElementById(fieldId);
                if (exact) {
                    results.push(`[#${fieldId}] tag=${exact.tagName} type=${exact.type||''} outerHTML=${exact.outerHTML.substring(0, 300)}`);
                    // 如果是 select，列出所有 option
                    if (exact.tagName === 'SELECT') {
                        for (let opt of exact.options) {
                            results.push(`  option: value="${opt.value}" text="${opt.text}"`);
                        }
                    }
                }

                // 2. 查找 id 包含 fieldId 的所有元素
                const partials = document.querySelectorAll(`[id*="${fieldId}"]`);
                for (let el of partials) {
                    if (el.id !== fieldId) {
                        results.push(`[id*=${fieldId}] id=${el.id} tag=${el.tagName} class=${el.className} outerHTML=${el.outerHTML.substring(0, 200)}`);
                    }
                }

                // 3. 查找 name 包含 fieldId 的元素
                const byName = document.querySelectorAll(`[name*="${fieldId}"]`);
                for (let el of byName) {
                    results.push(`[name*=${fieldId}] name=${el.name} tag=${el.tagName} type=${el.type||''} outerHTML=${el.outerHTML.substring(0, 200)}`);
                }

                // 4. 查找 data-id 匹配的元素
                const byDataId = document.querySelectorAll(`[data-id="${fieldId}"]`);
                for (let el of byDataId) {
                    results.push(`[data-id=${fieldId}] tag=${el.tagName} class=${el.className} outerHTML=${el.outerHTML.substring(0, 200)}`);
                }

                // 5. 查找父容器（如果有 label）
                const labels = document.querySelectorAll('label');
                for (let label of labels) {
                    const forAttr = label.getAttribute('for');
                    if (forAttr && forAttr.includes(fieldId)) {
                        results.push(`[label for=${forAttr}] text="${label.textContent.trim()}" outerHTML=${label.outerHTML.substring(0, 200)}`);
                        // 看看 label 的兄弟/父元素
                        const parent = label.parentElement;
                        if (parent) {
                            results.push(`  parent: tag=${parent.tagName} class=${parent.className} innerHTML前200=${parent.innerHTML.substring(0, 200)}`);
                        }
                    }
                }

                return results.length > 0 ? results : ['未找到任何匹配元素'];
            }""", field_id)
            print(f"\n--- {field_id} ---")
            for line in html:
                print(f"  {line}")
        print("=" * 60 + "\n")

    def _select_from_dropdown(self, field_id: str, value: str) -> bool:
        """从豆瓣自定义下拉框选择值

        豆瓣下拉框 DOM 结构:
          div.item.dropdown.single
            label[for=field_id]    -- 字段标签
            div.opts-group
              div.selector.single
                label.selected     -- 触发器，显示当前选中值（如"请选择"）
                input[type=hidden][name=field_id]  -- 存储实际值
              ul (展开后出现)
                li                 -- 各选项
        """
        try:
            # 1. 通过 JS 拿到触发器的 ElementHandle（Playwright 对象）
            trigger = self.page.evaluate_handle("""(fieldId) => {
                const input = document.querySelector(`input[name="${fieldId}"]`);
                if (!input) return null;
                const container = input.closest('.dropdown');
                if (container) return container.querySelector('label.selected');
                const selector = input.closest('.selector');
                if (selector) return selector.querySelector('label.selected');
                return null;
            }""", field_id).as_element()

            if not trigger:
                print(f"  [{field_id}] 未找到下拉触发器")
                return False

            # 2. 用 Playwright 点击触发器展开下拉
            trigger.click()
            time.sleep(0.8)

            # 3. 通过 JS 找到容器内的所有 li，返回文本列表用于匹配
            options_info = self.page.evaluate("""(fieldId) => {
                const input = document.querySelector(`input[name="${fieldId}"]`);
                if (!input) return [];
                const container = input.closest('.dropdown');
                if (!container) return [];
                const items = container.querySelectorAll('li');
                return Array.from(items).map((li, i) => ({
                    index: i,
                    text: li.textContent.trim()
                }));
            }""", field_id)

            if not options_info:
                print(f"  [{field_id}] 下拉展开后未找到 li 选项")
                return False

            # 4. 在返回的选项列表中找匹配项
            match_index = None
            match_text = ""
            value_lower = value.lower()

            # 精确匹配
            for opt in options_info:
                if opt["text"] == value:
                    match_index = opt["index"]
                    match_text = opt["text"]
                    break

            # 子串匹配: 选项文本包含 value（如 "Jazz 爵士" 包含 "Jazz"）
            if match_index is None:
                for opt in options_info:
                    if value in opt["text"]:
                        match_index = opt["index"]
                        match_text = opt["text"]
                        break

            # 不区分大小写子串匹配
            if match_index is None:
                for opt in options_info:
                    text_lower = opt["text"].lower()
                    if value_lower in text_lower or text_lower in value_lower:
                        match_index = opt["index"]
                        match_text = opt["text"]
                        break

            if match_index is None:
                all_texts = [o["text"] for o in options_info]
                print(f"  [{field_id}] 未匹配到 '{value}'，可用选项: {all_texts}")
                # 点击页面空白处关闭下拉
                self.page.click("body", position={"x": 0, "y": 0}, force=True)
                return False

            # 5. 用 Playwright 点击匹配的 li（通过 JS 获取 ElementHandle）
            li_handle = self.page.evaluate_handle("""(args) => {
                const [fieldId, index] = args;
                const input = document.querySelector(`input[name="${fieldId}"]`);
                if (!input) return null;
                const container = input.closest('.dropdown');
                if (!container) return null;
                const items = container.querySelectorAll('li');
                return items[index] || null;
            }""", [field_id, match_index]).as_element()

            if li_handle:
                li_handle.click()
                time.sleep(0.3)
                print(f"  [{field_id}] 选中: {match_text}")
                return True
            else:
                print(f"  [{field_id}] 获取 li 元素失败")
                return False

        except Exception as e:
            print(f"  [{field_id}] 下拉框选择出错: {e}")
        return False

    def _map_genre_to_douban(self, genres: list) -> str:
        """将英文流派列表映射到豆瓣流派名称"""
        if not genres:
            return ""

        for genre in genres:
            genre_lower = genre.lower().strip()
            # 精确匹配
            if genre_lower in GENRE_TO_DOUBAN:
                return GENRE_TO_DOUBAN[genre_lower]

        # 如果没有精确匹配，尝试子字符串匹配
        for genre in genres:
            genre_lower = genre.lower().strip()
            for key, douban_val in GENRE_TO_DOUBAN.items():
                if key in genre_lower or genre_lower in key:
                    return douban_val

        # 如果流派已经是中文（可能来自其他源），尝试反查映射
        # 豆瓣下拉选项的中文部分
        chinese_to_douban = {
            "布鲁斯": "Blues", "蓝调": "Blues", "古典": "Classical",
            "轻音乐": "Easy Listening", "电子": "Electronic", "民谣": "Folk",
            "放克": "Funk/Soul/R&B", "灵魂": "Funk/Soul/R&B", "灵魂乐": "Funk/Soul/R&B",
            "爵士": "Jazz", "爵士乐": "Jazz", "拉丁": "Latin",
            "流行": "Pop", "说唱": "Rap", "嘻哈": "Rap",
            "雷鬼": "Reggae", "摇滚": "Rock",
            "原声": "Soundtrack", "原声带": "Soundtrack",
            "世界音乐": "World",
        }
        for genre in genres:
            if genre in chinese_to_douban:
                return chinese_to_douban[genre]

        print(f"  未找到流派映射: {genres}")
        return ""

    def _map_album_type_to_douban(self, album: Album) -> str:
        """将专辑类型映射到豆瓣专辑类型"""
        # 优先使用 album_type 字段
        if album.album_type:
            type_lower = album.album_type.lower().strip()
            if type_lower in ALBUM_TYPE_TO_DOUBAN:
                return ALBUM_TYPE_TO_DOUBAN[type_lower]

        # 从 style (MusicBrainz secondary-types) 中提取
        if album.style:
            for s in album.style:
                s_lower = s.lower().strip()
                if s_lower in ALBUM_TYPE_TO_DOUBAN:
                    return ALBUM_TYPE_TO_DOUBAN[s_lower]

        # 默认返回 "专辑"（如果有 album_type 但未匹配）
        if album.album_type:
            print(f"  未找到专辑类型映射: {album.album_type}, 默认使用 '专辑'")
            return "专辑"

        return ""

    def get_page(self) -> Optional[Page]:
        """获取当前页面（用于手动操作）"""
        return self.page
