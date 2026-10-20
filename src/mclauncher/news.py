"""Compatibility surface for the retired launcher news feed."""

NEWS_FEED_URL = "https://www.minecraft.net/en-us/feeds/community-content/rss"


class MinecraftNewsFeed:
    """Retired provider retained only for source compatibility."""

    def fetch(self) -> list[dict[str, str]]:
        return []
