"""图片下载模块"""
import hashlib
import time
from pathlib import Path
from typing import Optional

import httpx
from ..utils import get_config


class ImageDownloader:
    """专辑图片下载器"""

    def __init__(self, images_dir: Optional[str] = None):
        config = get_config()
        self.images_dir = Path(images_dir or config.storage.images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = config.images.timeout
        self.retry_count = config.images.retry_count

    def download(self, url: str, album_id: str) -> Optional[str]:
        """下载图片并返回本地路径"""
        if not url:
            return None

        # 检查图片是否已存在
        existing = self._get_existing_path(album_id)
        if existing and existing.exists():
            return str(existing)

        # 下载新图片
        for attempt in range(self.retry_count):
            try:
                local_path = self._download_image(url, album_id)
                if local_path:
                    return local_path
            except Exception as e:
                if attempt < self.retry_count - 1:
                    time.sleep(1)
                    continue
                raise e

        return None

    def _download_image(self, url: str, album_id: str) -> Optional[str]:
        """执行下载"""
        import uuid

        # 获取文件扩展名
        ext = self._get_extension(url)

        # 生成文件名 - 如果 album_id 为空则生成随机 ID
        if album_id:
            filename = f"{album_id}{ext}"
        else:
            filename = f"{uuid.uuid4().hex[:8]}{ext}"

        local_path = self.images_dir / filename

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            with open(local_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return str(local_path)

    def _get_extension(self, url: str) -> str:
        """从URL获取文件扩展名"""
        # 尝试从URL中提取
        path = url.split("?")[0]
        if "." in path:
            ext = path.rsplit(".", 1)[-1].lower()
            if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
                return f".{ext}"

        # 默认使用jpg
        return ".jpg"

    def _get_existing_path(self, album_id: str) -> Optional[Path]:
        """检查已存在的图片"""
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            path = self.images_dir / f"{album_id}{ext}"
            if path.exists():
                return path
        return None

    def delete(self, album_id: str) -> bool:
        """删除专辑图片"""
        path = self._get_existing_path(album_id)
        if path:
            path.unlink()
            return True
        return False

    def get_local_path(self, album_id: str) -> Optional[str]:
        """获取本地路径（不下载）"""
        path = self._get_existing_path(album_id)
        return str(path) if path else None

    def get_image_count(self) -> int:
        """获取图片数量"""
        return len(list(self.images_dir.iterdir()))
