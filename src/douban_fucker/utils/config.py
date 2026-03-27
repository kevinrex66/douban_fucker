"""配置管理模块"""
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class StorageConfig(BaseModel):
    base_dir: str = "./data"
    albums_dir: str = "./data/albums"
    images_dir: str = "./data/images"


class DiscogsConfig(BaseModel):
    enabled: bool = True
    api_key: str = ""
    user_agent: str = "DoubanFucker/1.0"


class RYMConfig(BaseModel):
    enabled: bool = True
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class MusicBrainzConfig(BaseModel):
    enabled: bool = True
    user_agent: str = "DoubanFucker/1.0 (https://github.com/example/douban-fucker)"
    rate_limit: int = 1


class SpotifyConfig(BaseModel):
    enabled: bool = True
    client_id: str = ""
    client_secret: str = ""


class AppleMusicConfig(BaseModel):
    enabled: bool = True
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"


class ScrapersConfig(BaseModel):
    discogs: DiscogsConfig = DiscogsConfig()
    rym: RYMConfig = RYMConfig()
    musicbrainz: MusicBrainzConfig = MusicBrainzConfig()
    spotify: SpotifyConfig = SpotifyConfig()
    applemusic: AppleMusicConfig = AppleMusicConfig()


class ImagesConfig(BaseModel):
    enabled: bool = True
    retry_count: int = 3
    timeout: int = 30
    preferred_size: str = "600"


class RequestConfig(BaseModel):
    timeout: int = 30
    max_retries: int = 3
    delay: float = 1.0


class DoubanBrowserConfig(BaseModel):
    headless: bool = False
    slow_mo: int = 100
    timeout: int = 30000


class DoubanConfig(BaseModel):
    enabled: bool = True
    cookies_file: str = "./data/cookies/douban.json"
    base_url: str = "https://music.douban.com"
    browser: DoubanBrowserConfig = DoubanBrowserConfig()


class Config(BaseModel):
    storage: StorageConfig = StorageConfig()
    scrapers: ScrapersConfig = ScrapersConfig()
    images: ImagesConfig = ImagesConfig()
    request: RequestConfig = RequestConfig()
    douban: DoubanConfig = DoubanConfig()


_config: Optional[Config] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置文件"""
    global _config

    if _config is not None:
        return _config

    if config_path is None:
        # 查找配置文件
        current_dir = Path.cwd()
        possible_paths = [
            current_dir / "config.yaml",
            current_dir / "config.yml",
            Path(__file__).parent.parent.parent.parent / "config.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                config_path = str(path)
                break

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _config = Config(**data) if data else Config()
    else:
        _config = Config()

    # 确保目录存在
    _ensure_directories(_config)

    return _config


def _ensure_directories(config: Config) -> None:
    """确保必要目录存在"""
    for dir_path in [config.storage.albums_dir, config.storage.images_dir]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """获取当前配置"""
    global _config
    if _config is None:
        return load_config()
    return _config


def reset_config() -> None:
    """重置配置（用于测试）"""
    global _config
    _config = None
