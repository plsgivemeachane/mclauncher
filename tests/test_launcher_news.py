import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow, MinecraftHomePanel
from mclauncher.news import MinecraftNewsFeed, NEWS_FEED_URL


class NewsProvider:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def fetch(self):
        if self.error:
            raise RuntimeError(self.error)
        return self.items


def wait_for_news(application, window):
    for _ in range(100):
        application.processEvents()
        if window.news_worker is None:
            return
        QTest.qWait(10)


def test_news_cards_and_launcher_changelog_are_rendered_and_cached(tmp_path):
    application = QApplication.instance() or QApplication([])
    provider = NewsProvider([{
        "title": "Minecraft Java Edition 26.3",
        "url": "https://www.minecraft.net/en-us/article/minecraft-java-edition-26-3",
        "published": "2026-10-01",
    }])
    window = LauncherWindow(data_root=tmp_path / "data", news_provider=provider)
    window.show()
    wait_for_news(application, window)

    window.browse_nav_button.click()
    assert "Minecraft Java Edition 26.3" in window.news_cards.itemAt(0).widget().text()
    assert "Launcher changes" in window.launcher_changelog.text() or "mclauncher" in window.launcher_changelog.text()
    assert window.store.load()["news_items"][0]["title"] == "Minecraft Java Edition 26.3"
    window.home_nav_button.click()
    assert not window.news_heading.isVisible()
    assert not window.launcher_changelog.isVisible()
    window.close()


def test_cached_news_remains_visible_when_feed_fails(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "data"
    first = LauncherWindow(data_root=root, news_provider=NewsProvider([{
        "title": "Cached release",
        "url": "https://www.minecraft.net/en-us/article/cached-release",
        "published": "2026-10-01",
    }]))
    wait_for_news(application, first)
    first.close()

    second = LauncherWindow(data_root=root, news_provider=NewsProvider(error="offline"))
    second.show()
    wait_for_news(application, second)
    second.browse_nav_button.click()
    assert "Cached release" in second.news_cards.itemAt(0).widget().text()
    assert second.isVisible()
    second.close()


def test_empty_or_malformed_feed_keeps_home_usable(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data", news_provider=NewsProvider(["bad"]))
    window.show()
    wait_for_news(application, window)
    window.browse_nav_button.click()
    assert "unavailable offline" in window.news_cards.itemAt(0).widget().text()
    assert window.home_artwork.bundled_background().is_file()
    window.close()


def test_packaged_executable_background_is_used_for_home_rendering(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    executable_dir = tmp_path / "usr" / "lib" / "mclauncher"
    asset = executable_dir / "assets" / "minecraft-home.png"
    asset.parent.mkdir(parents=True)
    pixmap = QPixmap(8, 8)
    pixmap.fill("#a6e175")
    assert pixmap.save(str(asset))
    monkeypatch.setattr(sys, "executable", str(executable_dir / "mclauncher"))

    panel = MinecraftHomePanel()
    panel.show()
    application.processEvents()

    assert panel.bundled_background() == asset
    panel.set_background(None)
    rendered = panel.grab().toImage()
    assert rendered.isNull() is False
    assert rendered.pixelColor(4, 4).green() > rendered.pixelColor(4, 4).red()
    panel.close()


def test_official_feed_contract_parses_release_article(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"""<rss><channel><item><title>Minecraft 26.3</title>
            <link>https://www.minecraft.net/en-us/article/minecraft-26-3</link>
            <pubDate>Tue, 01 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>"""

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("mclauncher.news.urlopen", fake_urlopen)
    assert MinecraftNewsFeed().fetch() == [{
        "title": "Minecraft 26.3",
        "url": "https://www.minecraft.net/en-us/article/minecraft-26-3",
        "published": "2026-10-01",
    }]
    assert seen == {"url": NEWS_FEED_URL, "timeout": 10}
