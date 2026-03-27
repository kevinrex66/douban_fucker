"""专辑数据模型"""
import hashlib
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


def generate_short_id(title: str = "", artist: str = "") -> str:
    """生成短 ID，更易读易输入"""
    # 使用标题和艺术家的组合来生成短哈希
    source = f"{artist}:{title}".strip()
    if not source:
        source = str(uuid.uuid4())
    
    # 生成 6 位字符的短 ID
    hash_bytes = hashlib.sha256(source.encode()).digest()
    # 使用 base62 编码 (a-z, A-Z, 0-9)
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    short_id = "".join(chars[b % len(chars)] for b in hash_bytes[:6])
    return short_id


class Track(BaseModel):
    """曲目模型"""
    position: str = ""  # 碟片/曲目位置，如 "1", "A1", "2-1"
    title: str
    duration: str = ""  # 时长，如 "3:45"


class Album(BaseModel):
    """专辑模型"""
    id: str = ""  # 短 ID，由 generate_id() 生成
    title: str = ""
    artist: str = ""
    year: Optional[int] = None
    release_date: str = ""  # 完整发行日期，如 "2026-03-20"

    # 风格/类型信息
    genre: List[str] = Field(default_factory=list)  # 流派，如 "爵士乐"
    style: List[str] = Field(default_factory=list)  # 风格，如 "Post-Bop"

    # 发行信息
    label: str = ""  # 发行商/厂牌
    catalog_number: str = ""

    # 格式
    format: str = ""  # CD, Vinyl, Digital, etc.
    country: str = ""  # 发行国家

    # 曲目信息
    tracklist: List[Track] = Field(default_factory=list)

    # 图片
    cover_image: str = ""  # 本地图片路径
    cover_url: str = ""  # 原始图片URL

    # 来源信息
    source: str = ""  # discogs, rym, musicbrainz
    source_url: str = ""
    source_id: str = ""

    # 元数据
    added_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    # 附加信息
    description: str = ""
    rating: Optional[float] = None  # 评分
    api_source: str = "unknown"  # 详细来源

    def generate_id(self) -> None:
        """生成短 ID"""
        if not self.id:
            self.id = generate_short_id(self.title, self.artist)

    def to_dict(self) -> dict:
        """转换为字典用于JSON存储"""
        data = self.model_dump()
        data["added_at"] = self.added_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Album":
        """从字典加载"""
        if isinstance(data.get("added_at"), str):
            data["added_at"] = datetime.fromisoformat(data["added_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)

    def get_track_count(self) -> int:
        """获取曲目数量"""
        return len(self.tracklist)

    def get_total_duration(self) -> str:
        """计算总时长"""
        total_seconds = 0
        for track in self.tracklist:
            if track.duration:
                parts = track.duration.replace(",", ".").split(":")
                try:
                    if len(parts) == 2:
                        total_seconds += int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        total_seconds += int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except (ValueError, IndexError):
                    continue

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def format_tracklist(self) -> str:
        """格式化曲目列表"""
        if not self.tracklist:
            return "无曲目信息"
        lines = []
        for track in self.tracklist:
            if track.position:
                lines.append(f"{track.position}. {track.title} {track.duration}")
            else:
                lines.append(f"{track.title} {track.duration}")
        return "\n".join(lines)


class SearchResult(BaseModel):
    """搜索结果"""
    source: str
    album: Album
    relevance: float = 1.0  # 相关度
