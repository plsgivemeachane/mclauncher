from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from xml.etree import ElementTree

NEWS_FEED_URL = "https://www.minecraft.net/en-us/feeds/community-content/rss"


def _text(value: str | None) -> str:
    value = html.unescape(value or "")
    return re.sub(r"<[^>]+>", "", value).strip()


class MinecraftNewsFeed:
    """Fetch the public Minecraft.net RSS contract used by the home cards."""

    def fetch(self) -> list[dict[str, str]]:
        request = Request(NEWS_FEED_URL, headers={"User-Agent": "mclauncher/1.0"})
        with urlopen(request, timeout=10) as response:
            payload = response.read()
        root = ElementTree.fromstring(payload)
        items: list[dict[str, str]] = []
        for item in root.findall(".//item")[:6]:
            title = _text(item.findtext("title"))
            link_element = item.find("link")
            if link_element is None:
                link_element = item.find("{http://www.w3.org/2005/Atom}link")
            link = _text(item.findtext("link")) or _text(
                link_element.get("href") if link_element is not None else ""
            )
            if not title or not link or not link.startswith("https://www.minecraft.net/"):
                continue
            published = _text(item.findtext("pubDate"))
            try:
                published = parsedate_to_datetime(published).date().isoformat()
            except (TypeError, ValueError, OverflowError):
                published = published[:32]
            items.append({"title": title[:160], "url": link, "published": published})
        if not items:
            raise ValueError("Minecraft news feed contained no usable articles")
        return items
