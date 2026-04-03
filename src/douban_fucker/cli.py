"""命令行界面"""
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import Album
from .scrapers import get_scraper, get_all_scrapers, SCRAPERS
from .storage import FileStorage
from .utils import downloader
from .utils.downloader import ImageDownloader
from .browser import DoubanBrowser
from .scrapers.rym import RYMScraper

console = Console()


def check_album_completeness(album: Album) -> dict:
    """检查专辑信息完整性"""
    issues = []

    if not album.title:
        issues.append("标题")
    if not album.artist:
        issues.append("艺术家")
    if not album.year:
        issues.append("年份")
    if not album.tracklist:
        issues.append("曲目列表")
    elif len(album.tracklist) == 0:
        issues.append("曲目列表")
    if not album.cover_url:
        issues.append("封面")
    if not album.label:
        issues.append("厂牌")
    if not album.genre:
        issues.append("类型")

    return {
        "is_complete": len(issues) == 0,
        "issues": issues
    }


def _title_keywords_match(title1: str, title2: str) -> float:
    """计算两个标题之间的关键词匹配度 (0.0 - 1.0)"""
    import re
    # 提取英文和中文关键词
    words1 = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', title1.lower())
    words2 = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', title2.lower())
    
    if not words1 or not words2:
        return 0.0
    
    # 计算交集
    common = set(words1) & set(words2)
    # 至少有一半的词匹配
    match_ratio = len(common) / max(len(set(words1)), len(set(words2)))
    return match_ratio


def _build_apple_music_url(artist: str, title: str) -> str:
    """从艺术家和标题构建 Apple Music URL"""
    import re
    # 清理标题
    clean_title = title.lower()
    clean_title = re.sub(r'\s*\(live\)\s*', ' ', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*\(remastered\)\s*', ' ', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*\(deluxe\)\s*', ' ', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'[^\w\s]', '', clean_title)
    clean_title = re.sub(r'\s+', '-', clean_title.strip())
    
    # 清理艺术家
    clean_artist = artist.lower()
    clean_artist = re.sub(r'[^\w\s]', '', clean_artist)
    clean_artist = re.sub(r'\s+', '-', clean_artist.strip())
    
    return f"https://music.apple.com/cn/album/{clean_artist}-{clean_title}/"


def _try_get_apple_music_tracks(apple_scraper, search_query: str, artist_name: str, original_title: str) -> list:
    """尝试从 Apple Music 获取曲目列表，返回曲目列表或 None"""
    import re
    
    # 方法1: 搜索 Apple Music
    results = apple_scraper.search(search_query, limit=10)
    
    if results:
        best_match = None
        best_score = 0.0
        
        for r in results:
            score = 0.0
            result_title = r.album.title
            result_artist = r.album.artist
            
            # 1. 艺术家匹配 (最重要)
            if artist_name:
                if artist_name.lower() in result_artist.lower() or result_artist.lower() in artist_name.lower():
                    score += 0.5
                # 检查艺术家名中的关键部分
                artist_parts = artist_name.split()
                for part in artist_parts:
                    if len(part) > 2 and part.lower() in result_artist.lower():
                        score += 0.2
            
            # 2. 标题关键词匹配
            title_score = _title_keywords_match(original_title, result_title)
            score += title_score * 0.4
            
            # 3. 标题直接包含检查
            title_lower = original_title.lower()
            result_lower = result_title.lower()
            for keyword in ["village vanguard", "vol.", "live", "quartet"]:
                if keyword in title_lower and keyword in result_lower:
                    score += 0.1
            
            if score > best_score:
                best_score = score
                best_match = r
        
        # 如果匹配度超过阈值，获取专辑详情
        if best_match and best_score >= 0.3:
            apple_album = apple_scraper.get_album_by_url(best_match.album.source_url)
            if apple_album and apple_album.tracklist:
                return apple_album.tracklist
    
    # 方法2: 尝试构建直接 URL
    if artist_name and original_title:
        direct_url = _build_apple_music_url(artist_name, original_title)
        try:
            apple_album = apple_scraper.get_album_by_url(direct_url)
            if apple_album and apple_album.tracklist:
                return apple_album.tracklist
        except Exception:
            pass
    
    return None


def supplement_album(album: Album, primary_source: str = None) -> Album:
    """从其他来源补充专辑信息"""
    from .scrapers import get_scraper
    import re

    completeness = check_album_completeness(album)
    # 检查是否缺少简介
    needs_description = not album.description or len(album.description.strip()) < 10

    if completeness["is_complete"] and not needs_description:
        return album

    if not completeness["is_complete"]:
        console.print(f"\n[yellow]信息不完整，缺少: {', '.join(completeness['issues'])}[/yellow]")
        console.print("[dim]尝试从其他来源补充...[/dim]")

    if needs_description:
        console.print("[dim]尝试获取专辑简介...[/dim]")

    # 准备搜索关键词（移除括号内容和特定词汇）
    clean_title = album.title or ''
    original_title = clean_title
    clean_title = re.sub(r'\s*\(Live\)|\s*\(Remastered\)|\s*\(Deluxe\)|\s*\(Live at.*?\)', '', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s*[\(\[].*?[\)\]]', '', clean_title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    if len(clean_title) < 5:
        clean_title = original_title
    search_query = clean_title
    artist_name = album.artist or ''

    console.print(f"[dim]搜索关键词: {search_query}[/dim]")

    # 1. 优先从 MusicBrainz 获取简介（通过 Wikipedia）
    mb_apple_url = None
    mb_cover_url = None
    mb_scraper = None

    if needs_description or not album.tracklist or not album.genre or not album.label or not album.cover_url:
        try:
            mb_scraper = get_scraper("musicbrainz")
            results = mb_scraper.search(search_query, limit=3)
            if results:
                mb_id = results[0].album.source_id
                mb_album = mb_scraper.get_album(mb_id)
                if mb_album:
                    # 保存 MusicBrainz 的 Apple Music URL
                    if mb_album.source_url and "music.apple.com" in mb_album.source_url:
                        mb_apple_url = mb_album.source_url
                    if mb_album.cover_url and not album.cover_url:
                        mb_cover_url = mb_album.cover_url

                    # 优先补充简介（从 Wikipedia）
                    if needs_description and mb_album.description:
                        album.description = mb_album.description
                        console.print(f"[green]从 Wikipedia 补充简介[/green]")
                        needs_description = False

                    # 补充其他基本信息
                    if not album.artist and mb_album.artist:
                        album.artist = mb_album.artist
                        console.print(f"[green]补充艺术家: {album.artist}[/green]")

                    if not album.year and mb_album.year:
                        album.year = mb_album.year
                        console.print(f"[green]补充年份: {album.year}[/green]")

                    if not album.genre and mb_album.genre:
                        album.genre = mb_album.genre
                        console.print(f"[green]补充类型: {', '.join(album.genre)}[/green]")

                    if not album.label and mb_album.label:
                        album.label = mb_album.label
                        console.print(f"[green]补充厂牌: {album.label}[/green]")

                    if not album.country and mb_album.country:
                        album.country = mb_album.country

                    if not album.format and mb_album.format:
                        album.format = mb_album.format

                    if not album.album_type and mb_album.album_type:
                        album.album_type = mb_album.album_type
                        console.print(f"[green]补充专辑类型: {album.album_type}[/green]")
        except Exception as e:
            console.print(f"[dim]MusicBrainz 补充失败: {e}[/dim]")

    # 2. 如果缺少曲目列表，从 Apple Music 获取
    if not album.tracklist or len(album.tracklist) == 0:
        try:
            apple_scraper = get_scraper("applemusic")
            
            # 优先使用 MusicBrainz 中的 Apple Music URL
            if mb_apple_url:
                console.print(f"[dim]使用 MusicBrainz 提供的 Apple Music URL[/dim]")
                apple_album = apple_scraper.get_album_by_url(mb_apple_url)
                if apple_album and apple_album.tracklist:
                    album.tracklist = apple_album.tracklist
                    console.print(f"[green]从 Apple Music 补充曲目: {len(album.tracklist)} 首[/green]")
                    if not album.cover_url and apple_album.cover_url:
                        album.cover_url = apple_album.cover_url
                        console.print(f"[green]补充封面 URL[/green]")
                    # 不再从 Apple Music 获取简介，优先使用 Wikipedia
            else:
                # 使用搜索和 URL 构建
                tracklist = _try_get_apple_music_tracks(apple_scraper, search_query, artist_name, original_title)
                if tracklist:
                    album.tracklist = tracklist
                    console.print(f"[green]从 Apple Music 补充曲目: {len(album.tracklist)} 首[/green]")
                else:
                    console.print("[yellow]无法从 Apple Music 获取曲目列表[/yellow]")
        except Exception as e:
            console.print(f"[dim]Apple Music 补充失败: {e}[/dim]")

    # 3. 如果 Wikipedia 没有获取到简介，尝试从 Discogs 获取
    if needs_description:
        try:
            discogs_scraper = get_scraper("discogs")
            results = discogs_scraper.search(search_query, limit=3)
            if results:
                discogs_id = results[0].album.source_id
                discogs_album = discogs_scraper.get_album(discogs_id)
                if discogs_album and discogs_album.description:
                    album.description = discogs_album.description
                    console.print(f"[green]从 Discogs 补充简介[/green]")
                    needs_description = False
        except Exception as e:
            console.print(f"[dim]Discogs 简介获取失败: {e}[/dim]")

    # 4. 补充封面（如果 MusicBrainz 有的话）
    if not album.cover_url and mb_cover_url:
        album.cover_url = mb_cover_url
        console.print(f"[green]从 MusicBrainz 补充封面 URL[/green]")

    # 最终检查
    completeness = check_album_completeness(album)
    if not completeness["is_complete"]:
        console.print(f"[yellow]仍有信息缺失: {', '.join(completeness['issues'])}[/yellow]")
        console.print("[dim]专辑仍会被保存，部分信息需要手动补充[/dim]")

    # 检查简介获取情况
    if needs_description and not album.description:
        console.print("[yellow]未能获取到专辑简介[/yellow]")
    elif album.description:
        console.print(f"[green]✓ 已获取专辑简介 ({len(album.description)} 字符)[/green]")

    return album


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """豆瓣多功能爬虫 - 自动添加新唱片"""
    pass


@cli.command()
@click.argument("query")
@click.option("--source", "-s", default="all", help="数据源: discogs, rym, musicbrainz, all")
@click.option("--limit", "-l", default=10, help="搜索结果数量")
def search(query: str, source: str, limit: int):
    """搜索专辑"""
    console.print(f"[bold cyan]搜索:[/bold cyan] {query}")
    console.print(f"[dim]来源: {source} | 限制: {limit}[/dim]\n")

    results = []
    sources_to_search = []

    if source == "all":
        sources_to_search = list(SCRAPERS.keys())
    else:
        sources_to_search = [source]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for src in sources_to_search:
            task = progress.add_task(f"搜索 {src}...", total=None)
            try:
                scraper = get_scraper(src)
                src_results = scraper.search(query, limit)
                results.extend(src_results)
            except Exception as e:
                console.print(f"[red]搜索 {src} 失败: {e}[/red]")
            finally:
                progress.update(task, completed=True)

    if not results:
        console.print("[yellow]没有找到结果[/yellow]")
        return

    # 显示结果
    table = Table(title=f"搜索结果 ({len(results)} 个)")
    table.add_column("#", style="dim", width=3)
    table.add_column("标题", style="cyan")
    table.add_column("艺术家", style="green")
    table.add_column("年份", justify="right")
    table.add_column("来源", style="magenta")

    for idx, result in enumerate(results, 1):
        album = result.album
        table.add_row(
            str(idx),
            album.title[:40],
            album.artist[:20],
            str(album.year or "-"),
            result.source,
        )

    console.print(table)
    console.print("\n[dim]使用 'add --index N' 添加专辑，或使用 'add --url URL' 直接添加[/dim]")


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", default=10, help="每个来源搜索结果数量")
def interactive(query: str, limit: int):
    """交互式搜索和添加专辑（推荐）"""
    import os

    console.print(f"[bold cyan]搜索:[/bold cyan] {query}\n")

    results = []
    # 暂时禁用 RYM（需要登录）
    sources_to_search = ["discogs", "musicbrainz", "spotify", "applemusic"]

    console.print(f"[dim]搜索来源: {', '.join(sources_to_search)}[/dim]\n")

    for src in sources_to_search:
        console.print(f"[dim]搜索 {src}...[/dim]")
        try:
            scraper = get_scraper(src)
            src_results = scraper.search(query, limit)
            console.print(f"[dim]  {src}: 找到 {len(src_results)} 个结果[/dim]")
            # 使用元组保存 (来源, 搜索结果)
            for r in src_results:
                results.append((src, r))
        except Exception as e:
            console.print(f"[red]  {src} 失败: {e}[/red]")

    if not results:
        console.print("[yellow]没有找到结果[/yellow]")
        return

    # 显示所有结果
    console.print(f"\n[bold]找到 {len(results)} 个结果，请选择：[/bold]\n")

    # 按来源分组显示
    current_source = None
    numbered_results = []

    for idx, (src, result) in enumerate(results, 1):
        album = result.album

        if src != current_source:
            if current_source:
                console.print()  # 空行分隔
            console.print(f"[bold magenta]{src.upper()}[/bold magenta]")
            current_source = src

        numbered_results.append((idx, result, src))
        console.print(f"  [{idx:2d}] {album.title[:45]} | {album.artist[:15]} | {album.year or '-'}")

    console.print()
    console.print("[cyan]输入编号选择 (1-{})，或按回车退出:[/cyan] ".format(len(results)), end="")

    try:
        choice = input().strip()
        if not choice:
            console.print("[yellow]已取消[/yellow]")
            return

        choice_num = int(choice)
        if choice_num < 1 or choice_num > len(results):
            console.print("[red]无效的选择[/red]")
            return

        # 获取选中的结果
        _, selected_result, src = numbered_results[choice_num - 1]
        album_url = selected_result.album.source_url

        if not album_url:
            console.print("[red]该结果没有 URL，无法添加[/red]")
            return

        console.print(f"\n[green]已选择: {selected_result.album.title}[/green]")
        console.print(f"[dim]来源: {src} | URL: {album_url}[/dim]\n")

        # 添加专辑
        scraper = get_scraper(src)
        album = None

        if "discogs" in album_url:
            album = scraper.get_album_by_url(album_url)
        elif "rateyourmusic" in album_url:
            album = scraper.get_album_by_url(album_url)
        elif "musicbrainz" in album_url:
            album = scraper.get_album_by_url(album_url)
        elif "music.apple.com" in album_url:
            album = scraper.get_album_by_url(album_url)

        if album:
            # 检查并补充信息
            album = supplement_album(album)

            # 下载封面
            if album.cover_url:
                try:
                    img_downloader = ImageDownloader()
                    local_path = img_downloader.download(album.cover_url, album.id)
                    if local_path:
                        album.cover_image = local_path
                except Exception:
                    pass

            # 保存专辑
            storage = FileStorage()
            path = storage.save(album)
            console.print(f"\n[bold green]✓[/bold green] 专辑已保存: {path}")
            console.print(f"[cyan]ID: {album.id}[/cyan]")

            # 询问是否上传
            console.print()
            console.print("[cyan]是否上传到豆瓣？ (y/n):[/cyan] ", end="")
            upload_choice = input().strip().lower()

            if upload_choice == 'y':
                # 检查登录
                if not os.path.exists("data/cookies/douban.json"):
                    console.print("\n[yellow]需要先登录豆瓣...[/yellow]")
                    browser = DoubanBrowser()
                    try:
                        browser.login()
                    finally:
                        browser.close()

                console.print()
                browser = DoubanBrowser()
                try:
                    result_url = browser.upload_album(album)
                    if result_url:
                        console.print(f"[green]唱片已存在: {result_url}[/green]")
                    else:
                        console.print("[yellow]表单已填入，请在浏览器中检查并提交[/yellow]")
                finally:
                    browser.close()
        else:
            console.print("[red]获取专辑信息失败[/red]")

    except ValueError:
        console.print("[red]请输入有效的数字[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")


@cli.command()
@click.option("--index", "-i", type=int, help="从搜索结果中选择")
@click.option("--url", "-u", help="从 URL 添加")
@click.option("--discogs", help="从 Discogs ID 添加")
@click.option("--rym", help="从 RYM 路径添加")
@click.option("--musicbrainz", help="从 MusicBrainz ID 添加")
@click.option("--download-cover/--no-download-cover", default=True, help="是否下载封面")
def add(
    index: Optional[int],
    url: Optional[str],
    discogs: Optional[str],
    rym: Optional[str],
    musicbrainz: Optional[str],
    download_cover: bool,
):
    """添加专辑到本地数据库"""
    storage = FileStorage()
    scraper = None
    album = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("获取专辑信息...", total=None)

        if index:
            console.print("[yellow]请先使用 search 命令搜索，然后使用 add --url 或 --discogs 添加[/yellow]")
            return

        if url:
            # 从 URL 识别来源
            if "discogs" in url:
                scraper = get_scraper("discogs")
                album = scraper.get_album_by_url(url)
            elif "rateyourmusic" in url:
                scraper = get_scraper("rym")
                album = scraper.get_album_by_url(url)
            elif "musicbrainz" in url:
                scraper = get_scraper("musicbrainz")
                album = scraper.get_album_by_url(url)
            elif "music.apple.com" in url or "applemusic" in url:
                scraper = get_scraper("applemusic")
                album = scraper.get_album_by_url(url)
            else:
                console.print("[red]无法识别的 URL 来源[/red]")
                return

        elif discogs:
            scraper = get_scraper("discogs")
            album = scraper.get_album(discogs)

        elif rym:
            scraper = get_scraper("rym")
            album = scraper.get_album(rym)

        elif musicbrainz:
            scraper = get_scraper("musicbrainz")
            album = scraper.get_album(musicbrainz)

        elif spotify:
            scraper = get_scraper("spotify")
            album = scraper.get_album(spotify)

        elif applemusic:
            scraper = get_scraper("applemusic")
            album = scraper.get_album_by_url(applemusic)

        else:
            console.print("[yellow]请提供 --url, --discogs, --rym, --musicbrainz, --spotify 或 --applemusic 参数[/yellow]")
            console.print("[dim]示例: add --musicbrainz f5093c06[/dim]")
            return

        progress.update(task, completed=True)

    if not album:
        console.print("[red]获取专辑信息失败[/red]")
        return

    # 检查并补充专辑信息
    album = supplement_album(album)

    # 先生成 ID，再下载封面
    album.generate_id()

    # 下载封面
    if download_cover and album.cover_url:
        task = progress.add_task("下载封面...", total=None)
        try:
            img_downloader = ImageDownloader()
            local_path = img_downloader.download(album.cover_url, album.id)
            if local_path:
                album.cover_image = local_path
                console.print(f"[green]封面已保存: {local_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]封面下载失败: {e}[/yellow]")
        finally:
            progress.update(task, completed=True)

    # 保存专辑
    try:
        path = storage.save(album)
        console.print(f"[bold green]✓[/bold green] 专辑已保存: {path}")
        console.print(f"[dim]ID: {album.id}[/dim]")
    except Exception as e:
        console.print(f"[red]保存失败: {e}[/red]")


@cli.command()
@click.option("--artist", help="按艺术家筛选")
@click.option("--year", type=int, help="按年份筛选")
@click.option("--genre", help="按类型筛选")
@click.option("--source", help="按来源筛选")
def list(artist: Optional[str], year: Optional[int], genre: Optional[str], source: Optional[str]):
    """列出本地专辑"""
    storage = FileStorage()

    if any([artist, year, genre, source]):
        albums = storage.filter_by(artist=artist, year=year, genre=genre, source=source)
    else:
        albums = storage.list_all()

    if not albums:
        console.print("[yellow]没有找到专辑[/yellow]")
        return

    stats = storage.get_stats()
    console.print(f"[bold]总计:[/bold] {stats['total']} 张专辑\n")

    table = Table(title="本地专辑")
    table.add_column("ID", style="cyan", width=8)
    table.add_column("标题", style="cyan")
    table.add_column("艺术家", style="green")
    table.add_column("年份", justify="right")
    table.add_column("曲目", justify="right")
    table.add_column("来源", style="magenta")

    for album in albums:
        table.add_row(
            album.id,
            album.title[:35],
            album.artist[:15],
            str(album.year or "-"),
            str(album.get_track_count()),
            album.source,
        )

    console.print(table)


@cli.command()
@click.argument("album_id")
def show(album_id: str):
    """显示专辑详情"""
    storage = FileStorage()
    album = storage.load(album_id)

    if not album:
        # 尝试前缀匹配
        all_albums = storage.list_all()
        for a in all_albums:
            if a.id.startswith(album_id):
                album = a
                break

    if not album:
        # 尝试搜索
        albums = storage.search(album_id)
        if albums:
            album = albums[0]
        else:
            console.print(f"[red]专辑不存在: {album_id}[/red]")
            return

    console.print(f"\n[bold cyan]{'='*50}[/bold cyan]")
    console.print(f"[bold]{album.title}[/bold]")
    console.print(f"[green]{album.artist}[/green]")
    console.print(f"[dim]{'='*50}[/dim]\n")

    console.print(f"[yellow]基本信息[/yellow]")
    console.print(f"  ID: {album.id}")
    console.print(f"  年份: {album.year or '-'}")
    console.print(f"  国家: {album.country or '-'}")
    console.print(f"  格式: {album.format or '-'}")
    console.print(f"  厂牌: {album.label or '-'}")
    console.print(f"  Catalog#: {album.catalog_number or '-'}")
    console.print(f"  类型: {', '.join(album.genre) or '-'}")
    console.print(f"  风格: {', '.join(album.style) or '-'}")
    console.print(f"  评分: {album.rating or '-'}")
    console.print(f"  来源: {album.source}")
    console.print(f"  添加时间: {album.added_at.strftime('%Y-%m-%d %H:%M')}")

    if album.cover_image:
        console.print(f"\n[yellow]封面:[/yellow] {album.cover_image}")
    if album.cover_url:
        console.print(f"[dim]原始封面: {album.cover_url}[/dim]")
    if album.source_url:
        console.print(f"[dim]来源URL: {album.source_url}[/dim]")

    if album.tracklist:
        console.print(f"\n[yellow]曲目列表 ({album.get_track_count()} 首, 共 {album.get_total_duration()})[/yellow]")
        for track in album.tracklist:
            position = f"[dim]{track.position}[/dim]" if track.position else "  "
            duration = f"[dim]{track.duration}[/dim]" if track.duration else ""
            console.print(f"  {position:>4}  {track.title} {duration}")

    if album.description:
        console.print(f"\n[yellow]简介:[/yellow]")
        console.print(f"[dim]{album.description[:500]}...[/dim]")


@cli.command()
@click.argument("album_id")
@click.option("--source", "-s", default="discogs", help="数据源")
def sync(album_id: str, source: str):
    """同步专辑信息"""
    storage = FileStorage()
    album = storage.load(album_id)

    if not album:
        console.print(f"[red]专辑不存在: {album_id}[/red]")
        return

    console.print(f"[cyan]同步专辑: {album.title}[/cyan]")
    console.print(f"[dim]当前来源: {album.source}[/dim]")
    console.print(f"[dim]新来源: {source}[/dim]\n")

    scraper = get_scraper(source)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("获取最新信息...", total=None)

        new_album = scraper.get_album(album.source_id)
        if new_album:
            # 保留原有ID
            new_album.id = album.id
            new_album.added_at = album.added_at

            # 下载新封面
            if new_album.cover_url:
                try:
                    img_downloader = ImageDownloader()
                    img_downloader.delete(album.id)
                    local_path = img_downloader.download(new_album.cover_url, new_album.id)
                    if local_path:
                        new_album.cover_image = local_path
                except Exception:
                    pass

            # 保存
            storage.save(new_album)
            console.print(f"[bold green]✓[/bold green] 同步完成")
        else:
            console.print(f"[red]同步失败: 无法获取专辑信息[/red]")


@cli.command()
@click.argument("album_id")
@click.confirmation_option(prompt="确认删除?")
def delete(album_id: str):
    """删除专辑"""
    storage = FileStorage()
    album = storage.load(album_id)

    if not album:
        console.print(f"[red]专辑不存在: {album_id}[/red]")
        return

    # 删除封面
    img_downloader = ImageDownloader()
    img_downloader.delete(album_id)

    # 删除专辑
    storage.delete(album_id)
    console.print(f"[bold green]✓[/bold green] 已删除: {album.title}")


@cli.command()
@click.option("--force", "-f", is_flag=True, help="跳过确认直接删除")
def clear(force: bool):
    """清空所有本地专辑数据"""
    storage = FileStorage()

    albums = storage.list_all()
    if not albums:
        console.print("[yellow]没有专辑数据[/yellow]")
        return

    console.print(f"[bold red]警告：即将删除所有 {len(albums)} 张专辑数据！[/bold red]")
    console.print("[yellow]包括所有专辑文件和封面图片[/yellow]\n")

    if not force:
        console.print("输入 'yes' 确认删除：")
        confirm = input().strip().lower()
        if confirm != "yes":
            console.print("[yellow]已取消[/yellow]")
            return

    count = storage.clear_all(confirm=True)
    if count > 0:
        console.print(f"[bold green]✓[/bold green] 已清空 {count} 张专辑")
    else:
        console.print("[yellow]已取消[/yellow]")


@cli.command()
def stats():
    """显示统计信息"""
    storage = FileStorage()
    img_downloader = ImageDownloader()
    stats = storage.get_stats()

    console.print("[bold]=== 统计数据 ===[/bold]\n")
    console.print(f"[cyan]专辑总数:[/cyan] {stats['total']}")
    console.print(f"[cyan]艺术家数量:[/cyan] {stats['by_artist_count']}")
    console.print(f"[cyan]图片数量:[/cyan] {img_downloader.get_image_count()}")

    console.print(f"\n[cyan]按来源:[/cyan]")
    for source, count in sorted(stats["by_source"].items()):
        console.print(f"  {source}: {count}")

    console.print(f"\n[cyan]按年份 (Top 10):[/cyan]")
    sorted_years = sorted(stats["by_year"].items(), key=lambda x: x[1], reverse=True)[:10]
    for year, count in sorted_years:
        console.print(f"  {year}: {count}")


@cli.command()
def login():
    """登录豆瓣 - 打开浏览器手动登录"""
    console.print("[bold cyan]豆瓣登录[/bold cyan]\n")

    browser = DoubanBrowser()
    try:
        success = browser.login()
        if success:
            console.print("[bold green]登录成功！[/bold green]")
        else:
            console.print("[red]登录失败[/red]")
    finally:
        browser.close()


@cli.command()
def rym_login():
    """登录 RYM (RateYourMusic) - 打开浏览器手动登录"""
    console.print("[bold cyan]RYM 登录[/bold cyan]\n")

    scraper = RYMScraper()
    try:
        success = scraper.login()
        if success:
            console.print("[bold green]登录成功！[/bold green]")
        else:
            console.print("[red]登录失败[/red]")
    finally:
        scraper.close()


@cli.command()
@click.argument("cookies_json", required=False)
def rym_import(cookies_json: Optional[str]):
    """导入 RYM cookies - 从 EditThisCookie 导出的 JSON"""
    console.print("[bold cyan]导入 RYM Cookies[/bold cyan]\n")

    scraper = RYMScraper()
    try:
        if cookies_json:
            success = scraper.import_cookies(cookies_json)
        else:
            console.print("请粘贴 EditThisCookie 导出的 JSON:")
            console.print("(或者使用: rym-import 'JSON字符串')")
            print()
            json_input = input()
            success = scraper.import_cookies(json_input)

        if success:
            console.print("[bold green]✓ Cookies 导入成功！[/bold green]")
        else:
            console.print("[red]✗ Cookies 导入失败[/red]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
    finally:
        scraper.close()


@cli.command()
@click.argument("album_id", required=False)
@click.option("--all", "upload_all", is_flag=True, help="上传所有本地专辑")
def upload(album_id: Optional[str], upload_all: bool):
    """上传专辑到豆瓣"""
    storage = FileStorage()
    browser = DoubanBrowser()

    try:
        if upload_all:
            # 上传所有专辑
            albums = storage.list_all()
            if not albums:
                console.print("[yellow]没有找到本地专辑[/yellow]")
                return

            console.print(f"[cyan]准备上传 {len(albums)} 张专辑到豆瓣[/cyan]\n")

            for album in albums:
                console.print(f"正在上传: {album.title} - {album.artist}")
                result = browser.upload_album(album)
                if result:
                    console.print(f"[green]已存在: {result}[/green]")
                else:
                    console.print("[yellow]需要手动提交表单[/yellow]")

        elif album_id:
            # 上传指定专辑 - 支持前缀匹配
            album = storage.load(album_id)
            if not album:
                # 尝试前缀匹配
                all_albums = storage.list_all()
                for a in all_albums:
                    if a.id.startswith(album_id):
                        album = a
                        break

            if not album:
                # 尝试搜索
                albums = storage.search(album_id)
                if albums:
                    album = albums[0]

            if not album:
                console.print(f"[red]专辑不存在: {album_id}[/red]")
                return

            console.print(f"[cyan]上传专辑:[/cyan] {album.title}")
            console.print(f"[dim]艺术家: {album.artist}[/dim]\n")

            result = browser.upload_album(album)
            if result:
                console.print(f"[green]唱片已存在: {result}[/green]")
                browser.close()
            else:
                console.print("\n[dim]浏览器将保持打开状态[/dim]")
                console.print("[dim]完成后关闭浏览器即可[/dim]\n")
                # 浏览器已由 upload_album 中的 wait_for_selector 保持打开
                # 这里不关闭浏览器，让用户手动操作

        else:
            console.print("[yellow]请提供 album_id 或使用 --all 上传所有专辑[/yellow]")
            console.print("[dim]示例: upload dc44061d[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
        browser.close()
    except Exception as e:
        console.print(f"[red]上传出错: {e}[/red]")
        browser.close()


def main():
    """入口函数"""
    cli()


if __name__ == "__main__":
    main()
