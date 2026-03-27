"""爬虫模块"""
from .base import BaseScraper
from .discogs import DiscogsScraper
from .rym import RYMScraper
from .musicbrainz import MusicBrainzScraper
from .spotify import SpotifyScraper
from .applemusic import AppleMusicScraper

# 可用的爬虫列表
SCRAPERS = {
    "discogs": DiscogsScraper,
    "rym": RYMScraper,
    "musicbrainz": MusicBrainzScraper,
    "spotify": SpotifyScraper,
    "applemusic": AppleMusicScraper,
}


def get_scraper(name: str) -> BaseScraper:
    """获取指定名称的爬虫"""
    scraper_class = SCRAPERS.get(name.lower())
    if scraper_class:
        return scraper_class()
    raise ValueError(f"Unknown scraper: {name}")


def get_all_scrapers() -> list:
    """获取所有可用的爬虫"""
    return [cls() for cls in SCRAPERS.values()]


__all__ = [
    "BaseScraper",
    "DiscogsScraper",
    "RYMScraper",
    "MusicBrainzScraper",
    "SpotifyScraper",
    "AppleMusicScraper",
    "SCRAPERS",
    "get_scraper",
    "get_all_scrapers",
]
