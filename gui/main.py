"""
豆瓣专辑上传工具 - Web 可视化界面
FastAPI 后端
"""
import sys
import os
import subprocess
import json
import tempfile
import webbrowser
import threading
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 添加原项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 项目路径
PROJECT_DIR = Path(__file__).parent.parent
GUI_DIR = Path(__file__).parent

# 切换工作目录到项目根目录，确保相对路径（data/albums 等）正确
os.chdir(str(PROJECT_DIR))

app = FastAPI(title="豆瓣专辑上传工具", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== 数据模型 ==============

class SearchResult(BaseModel):
    id: str
    title: str
    artist: str
    year: Optional[str] = None
    cover_url: Optional[str] = None
    source: str
    source_url: str


class AlbumDetail(BaseModel):
    id: str
    title: str
    artist: str
    year: Optional[str] = None
    cover_url: Optional[str] = None
    source: str
    source_url: str
    tracklist: List[dict] = []
    genre: List[str] = []
    label: Optional[str] = None
    description: Optional[str] = None


class UploadStatus(BaseModel):
    success: bool
    message: str
    douban_url: Optional[str] = None


# ============== API 路由 ==============

@app.get("/")
async def root():
    """返回前端页面"""
    return FileResponse(GUI_DIR / "index.html")


@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    # 检查豆瓣登录
    cookies_file = PROJECT_DIR / "data" / "cookies" / "douban.json"
    douban_logged_in = cookies_file.exists()

    # 检查环境
    env_ok = True
    env_errors = []

    try:
        from douban_fucker.scrapers import get_scraper
        get_scraper("musicbrainz")
    except Exception as e:
        env_ok = False
        env_errors.append(f"MusicBrainz: {str(e)}")

    return {
        "douban_logged_in": douban_logged_in,
        "env_ok": env_ok,
        "env_errors": env_errors
    }


@app.post("/api/login")
async def login_douban():
    """打开豆瓣登录页面"""
    try:
        # 运行 workflow.sh login
        result = subprocess.run(
            [str(GUI_DIR / "run_workflow.sh"), "login"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_DIR),
            timeout=300
        )
        return {"success": True, "message": "请在浏览器中完成登录"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search")
async def search_albums(q: str, source: str = "all", limit: int = 10):
    """搜索专辑"""
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="搜索关键词太短")

    try:
        # 调用原项目的搜索功能
        # 优先 Apple Music（有封面），后 MusicBrainz
        am_results = []
        mb_results = []

        if source == "all" or source == "applemusic":
            try:
                am_results = await search_applemusic(q, limit)
            except Exception as e:
                print(f"Apple Music 搜索失败: {e}")

        if source == "all" or source == "musicbrainz":
            try:
                mb_results = await search_musicbrainz(q, limit)
            except Exception as e:
                print(f"MusicBrainz 搜索失败: {e}")

        # 先加 Apple Music，再加 MusicBrainz
        results = am_results + mb_results

        # 去重：优先保留 Apple Music（通过标题+艺术家去重，MusicBrainz 匹配到相同的就跳过）
        seen = set()
        unique_results = []
        for r in results:
            key = (r.title.lower(), r.artist.lower())
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        return [r.model_dump() for r in unique_results[:limit]]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def search_musicbrainz(query: str, limit: int) -> List[SearchResult]:
    """从 MusicBrainz 搜索"""
    from douban_fucker.scrapers.musicbrainz import MusicBrainzScraper

    scraper = MusicBrainzScraper()
    raw_results = scraper.search(query, limit)

    results = []
    for r in raw_results:
        results.append(SearchResult(
            id=r.album.source_id or "",
            title=r.album.title,
            artist=r.album.artist,
            year=str(r.album.year) if r.album.year else None,
            cover_url=r.album.cover_url,
            source="musicbrainz",
            source_url=r.album.source_url or f"https://musicbrainz.org/release-group/{r.album.source_id}"
        ))

    return results


async def search_applemusic(query: str, limit: int) -> List[SearchResult]:
    """从 Apple Music 搜索"""
    from douban_fucker.scrapers.applemusic import AppleMusicScraper

    scraper = AppleMusicScraper()
    raw_results = scraper.search(query, limit)

    results = []
    for r in raw_results:
        results.append(SearchResult(
            id=r.album.source_id or "",
            title=r.album.title,
            artist=r.album.artist,
            year=str(r.album.year) if r.album.year else None,
            cover_url=r.album.cover_url,
            source="applemusic",
            source_url=r.album.source_url or ""
        ))

    return results


@app.get("/api/album/{source}/{album_id}")
async def get_album_detail(source: str, album_id: str):
    """获取专辑详情"""
    try:
        album = None

        if source == "musicbrainz":
            from douban_fucker.scrapers.musicbrainz import MusicBrainzScraper
            scraper = MusicBrainzScraper()
            album = scraper.get_album(album_id)

        elif source == "applemusic":
            from douban_fucker.scrapers.applemusic import AppleMusicScraper
            scraper = AppleMusicScraper()
            # AppleMusic 用 get_album_by_url，需要构建 URL
            # album_id 实际上是 collectionId
            url = f"https://music.apple.com/cn/album/id{album_id}"
            album = scraper.get_album_by_url(url)

        if not album:
            raise HTTPException(status_code=404, detail="专辑不存在")

        return {
            "id": album.id or album_id,
            "title": album.title,
            "artist": album.artist,
            "year": str(album.year) if album.year else None,
            "cover_url": album.cover_url,
            "source": source,
            "source_url": album.source_url or "",
            "tracklist": [
                {
                    "position": t.position,
                    "title": t.title,
                    "duration": t.duration
                }
                for t in (album.tracklist or [])
            ],
            "genre": album.genre or [],
            "label": album.label,
            "description": album.description
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add")
async def add_album(source: str, album_id: str, upload_to_douban: bool = True):
    """添加专辑到本地并可选上传豆瓣"""
    try:
        import tempfile
        import shutil
        import re
        from pathlib import Path
        from douban_fucker.storage import FileStorage
        from douban_fucker.scrapers.musicbrainz import MusicBrainzScraper
        from douban_fucker.scrapers.applemusic import AppleMusicScraper
        from douban_fucker.utils.downloader import ImageDownloader

        # 1. 获取专辑信息
        album = None

        if source == "musicbrainz":
            scraper = MusicBrainzScraper()
            album = scraper.get_album(album_id)
            # 获取完整 URL
            album_url = f"https://musicbrainz.org/release-group/{album_id}"
        elif source == "applemusic":
            scraper = AppleMusicScraper()
            album_url = f"https://music.apple.com/cn/album/id{album_id}"
            album = scraper.get_album_by_url(album_url)

        if not album:
            return {"success": False, "message": "无法获取专辑信息"}

        # 2. 补充信息
        from douban_fucker.cli import supplement_album
        album = supplement_album(album)

        # 3. 下载封面
        if album.cover_url:
            try:
                img_downloader = ImageDownloader()
                album.generate_id()
                local_path = img_downloader.download(album.cover_url, album.id)
                if local_path:
                    album.cover_image = local_path
            except Exception as e:
                print(f"封面下载失败: {e}")

        # 4. 保存到本地
        storage = FileStorage()
        save_path = storage.save(album)

        result = {
            "success": True,
            "message": f"专辑已保存: {album.title}",
            "album_id": album.id,
            "saved_path": str(save_path)
        }

        # 5. 上传豆瓣 - 后台启动独立进程，让浏览器窗口正常弹出
        if upload_to_douban:
            cookies_file = PROJECT_DIR / "data" / "cookies" / "douban.json"
            if not cookies_file.exists():
                return {
                    **result,
                    "douban_status": "need_login",
                    "message": "专辑已保存，需要先登录豆瓣"
                }

            try:
                # 用 Popen 启动独立进程，不阻塞、不捕获输出
                # 这样 Playwright 浏览器窗口可以正常弹出
                upload_script = f"""
import sys, os
os.chdir('{PROJECT_DIR}')
sys.path.insert(0, '{PROJECT_DIR}/src')
from douban_fucker.browser import DoubanBrowser
from douban_fucker.storage import FileStorage
storage = FileStorage()
album = storage.load('{album.id}')
if album:
    browser = DoubanBrowser()
    try:
        result = browser.upload_album(album)
        if result:
            print('唱片已存在:', result)
        else:
            print('表单已填入，请在浏览器中检查并提交')
            import time
            time.sleep(300)
    except Exception as e:
        print('上传出错:', e)
        import time
        time.sleep(300)
"""
                subprocess.Popen(
                    [sys.executable, "-c", upload_script],
                    cwd=str(PROJECT_DIR),
                )
                result["douban_status"] = "manual"
                result["message"] = "浏览器已打开，请在浏览器中检查并提交表单"

            except Exception as e:
                result["douban_status"] = "error"
                result["message"] = f"启动上传失败: {str(e)}"

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/albums")
async def list_albums():
    """列出本地所有专辑"""
    try:
        from douban_fucker.storage import FileStorage
        storage = FileStorage()
        albums = storage.list_all()

        return [
            {
                "id": a.id,
                "title": a.title,
                "artist": a.artist,
                "year": str(a.year) if a.year else None,
                "cover_url": a.cover_url,
                "source": a.source,
                "added_at": a.added_at.isoformat() if a.added_at else None
            }
            for a in albums
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== 静态文件 ==============

# @app.get("/assets/{path:path}")
# async def serve_assets(path: str):
#     return FileResponse(GUI_DIR / "assets" / path)


# ============== 启动函数 ==============

def open_browser():
    """延迟打开浏览器"""
    import time
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:18901")


def run():
    """启动服务"""
    # 启动浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动服务器
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=18901,
        log_level="info"
    )


if __name__ == "__main__":
    run()
