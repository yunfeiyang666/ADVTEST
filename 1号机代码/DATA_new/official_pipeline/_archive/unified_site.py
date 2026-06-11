"""
兼容入口：站点配置已合并至 advtest_paths（单文件部署更省事）。

请优先：``from advtest_paths import get_site, SiteConfig, invalidate_site_cache``
"""
from advtest_paths import (  # noqa: F401
    FALLBACK_NEO4J_URI,
    SiteConfig,
    get_site,
    invalidate_site_cache,
    print_site_banner,
)

__all__ = [
    "FALLBACK_NEO4J_URI",
    "SiteConfig",
    "get_site",
    "invalidate_site_cache",
    "print_site_banner",
]
