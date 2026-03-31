"""豆瓣浏览器操作模块"""
import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from ..models import Album
from ..utils import get_config
from .session import SessionManager


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

            # 流派 (p_116)
            if album.genre:
                genre = album.genre[0] if album.genre else ""
                if genre:
                    self._select_from_dropdown("p_116", genre)

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
            print("等待您点击【下一步】...")
            print("（检测到封面上传页面后会自动上传封面）")

            # 使用 Playwright 的等待机制
            max_wait = 60  # 最多等待60秒

            try:
                # 等待封面上传 input 元素出现
                # 豆瓣的封面上传页面有 input[type='file']
                print("等待封面上传页面...")
                file_input = self.page.wait_for_selector(
                    "input[type='file']",
                    timeout=max_wait * 1000  # 转换为毫秒
                )

                if file_input:
                    print("找到封面上传页面!")

                    # 上传封面图片
                    if album.cover_image:
                        cover_path = Path(album.cover_image)
                        if cover_path.exists():
                            print(f"上传封面图片: {cover_path}")
                            file_input.set_input_files(str(cover_path))
                            time.sleep(3)
                            print("封面已上传，请检查并提交")
                            return
                        else:
                            print(f"封面文件不存在: {cover_path}")
                            return
                    else:
                        print("未找到封面图片")
                        return

            except Exception as wait_e:
                error_msg = str(wait_e)
                if "timeout" in error_msg.lower():
                    print("等待封面上传页面超时（60秒）")
                    print("请在浏览器中手动点击【下一步】上传封面")
                else:
                    print(f"等待时出错: {wait_e}")

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

            # 流派 (p_116)
            if album.genre:
                genre = album.genre[0] if album.genre else ""
                if genre:
                    self._select_from_dropdown("p_116", genre)

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

    def _select_from_dropdown(self, field_id: str, value: str) -> bool:
        """从下拉框选择值"""
        try:
            # 点击下拉框触发选择
            dropdown = self.page.query_selector(f"[data-id='{field_id}']")
            if dropdown:
                dropdown.click()
                time.sleep(0.5)

            # 查找包含值的选项并点击
            option = self.page.query_selector(f"li[data-val='{value}']")
            if not option:
                # 尝试模糊匹配
                options = self.page.query_selector_all("ul[class*='dropdown'] li")
                for opt in options:
                    opt_text = opt.text_content() or ""
                    if value.lower() in opt_text.lower():
                        option = opt
                        break

            if option:
                option.click()
                time.sleep(0.3)
                return True

        except Exception:
            pass
        return False

    def get_page(self) -> Optional[Page]:
        """获取当前页面（用于手动操作）"""
        return self.page
