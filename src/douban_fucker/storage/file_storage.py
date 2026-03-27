"""本地文件存储模块"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..models import Album
from ..utils import get_config


class FileStorage:
    """本地文件存储"""

    def __init__(self, albums_dir: Optional[str] = None):
        config = get_config()
        self.albums_dir = Path(albums_dir or config.storage.albums_dir)
        self.albums_dir.mkdir(parents=True, exist_ok=True)

    def _get_album_path(self, album_id: str) -> Path:
        """获取专辑文件路径"""
        return self.albums_dir / f"{album_id}.json"

    def _get_index_path(self) -> Path:
        """获取索引文件路径"""
        return self.albums_dir / "index.json"

    def save(self, album: Album) -> str:
        """保存专辑到文件"""
        # 生成短 ID
        album.generate_id()
        album.updated_at = datetime.now()
        path = self._get_album_path(album.id)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(album.to_dict(), f, ensure_ascii=False, indent=2)

        self._update_index(album)
        return str(path)

    def load(self, album_id: str) -> Optional[Album]:
        """从文件加载专辑"""
        path = self._get_album_path(album_id)
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return Album.from_dict(data)

    def delete(self, album_id: str) -> bool:
        """删除专辑"""
        path = self._get_album_path(album_id)
        if path.exists():
            path.unlink()
            self._remove_from_index(album_id)
            return True
        return False

    def clear_all(self, confirm: bool = False) -> int:
        """清空所有专辑数据
        
        Args:
            confirm: 是否确认删除，需要传入 True 才执行
            
        Returns:
            删除的专辑数量
        """
        if not confirm:
            return 0
        
        albums = self.list_all()
        count = 0
        
        for album in albums:
            self.delete(album.id)
            # 同时删除封面图片
            if album.cover_image:
                img_path = Path(album.cover_image)
                if img_path.exists():
                    img_path.unlink()
            count += 1
        
        return count

    def list_all(self) -> List[Album]:
        """列出所有专辑"""
        albums = []
        for json_file in self.albums_dir.glob("*.json"):
            if json_file.name == "index.json":
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                albums.append(Album.from_dict(data))
            except (json.JSONDecodeError, Exception):
                continue
        return sorted(albums, key=lambda a: a.added_at, reverse=True)

    def search(self, query: str, field: Optional[str] = None) -> List[Album]:
        """搜索专辑"""
        query_lower = query.lower()
        all_albums = self.list_all()
        results = []

        for album in all_albums:
            if field:
                value = getattr(album, field, "")
                if query_lower in str(value).lower():
                    results.append(album)
            else:
                # 全文搜索
                searchable = " ".join([
                    album.title,
                    album.artist,
                    " ".join(album.genre),
                    " ".join(album.style),
                    album.label,
                ]).lower()
                if query_lower in searchable:
                    results.append(album)

        return results

    def filter_by(
        self,
        artist: Optional[str] = None,
        year: Optional[int] = None,
        genre: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Album]:
        """按条件筛选专辑"""
        albums = self.list_all()
        results = []

        for album in albums:
            if artist and artist.lower() not in album.artist.lower():
                continue
            if year and album.year != year:
                continue
            if genre and genre.lower() not in " ".join(album.genre + album.style).lower():
                continue
            if source and album.source != source:
                continue
            results.append(album)

        return results

    def exists_by_source_id(self, source: str, source_id: str) -> bool:
        """检查是否已存在相同来源的专辑"""
        albums = self.list_all()
        return any(
            a.source == source and a.source_id == source_id
            for a in albums
        )

    def get_by_source_id(self, source: str, source_id: str) -> Optional[Album]:
        """通过来源ID获取专辑"""
        albums = self.list_all()
        for album in albums:
            if album.source == source and album.source_id == source_id:
                return album
        return None

    def _update_index(self, album: Album) -> None:
        """更新索引文件"""
        index_path = self._get_index_path()
        index = self._load_index()

        index[album.id] = {
            "title": album.title,
            "artist": album.artist,
            "year": album.year,
            "source": album.source,
            "source_id": album.source_id,
            "added_at": album.added_at.isoformat(),
        }

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _remove_from_index(self, album_id: str) -> None:
        """从索引中移除"""
        index_path = self._get_index_path()
        index = self._load_index()

        if album_id in index:
            del index[album_id]
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)

    def _load_index(self) -> dict:
        """加载索引文件"""
        index_path = self._get_index_path()
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get_stats(self) -> dict:
        """获取统计数据"""
        albums = self.list_all()
        stats = {
            "total": len(albums),
            "by_source": {},
            "by_year": {},
            "by_artist_count": len(set(a.artist for a in albums)),
        }

        for album in albums:
            # 按来源统计
            source = album.source or "unknown"
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

            # 按年份统计
            year = str(album.year) if album.year else "unknown"
            stats["by_year"][year] = stats["by_year"].get(year, 0) + 1

        return stats
