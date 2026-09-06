from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from html import unescape
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


class PersonalizedNewsSearch:
    """Key-free, link-grounded news discovery through public RSS search feeds."""

    TOPICS = (
        ("Arts & culture", "arts OR culture OR exhibitions OR museums"),
        ("Tech & AI", "technology OR artificial intelligence"),
        ("Cats", "cats OR kittens funny"),
        ("Local bright spots", "Seattle uplifting OR quirky OR community OR celebrates"),
        ("Food", "food OR restaurants OR cooking"),
    )
    NEGATIVE_LOCAL = {
        "killed", "murder", "shooting", "dead", "death", "crash", "assault",
        "crime", "disaster", "tragedy", "war", "fatal", "arrested",
    }

    def news(self, interests: list[str]) -> list[dict[str, str]]:
        stories: list[dict[str, str]] = []
        seen: set[str] = set()
        with ThreadPoolExecutor(max_workers=len(self.TOPICS)) as executor:
            feeds = list(executor.map(self._feed, (query for _, query in self.TOPICS)))
        for (topic, _), items in zip(self.TOPICS, feeds):
            accepted = 0
            for item in items:
                title = item["title"]
                if title.lower() in seen:
                    continue
                if topic == "Local bright spots" and any(
                    word in title.lower() for word in self.NEGATIVE_LOCAL
                ):
                    continue
                if not self._matches_topic(topic, title):
                    continue
                seen.add(title.lower())
                stories.append({**item, "topic": topic})
                accepted += 1
                if accepted == 2:
                    break
        return stories

    @staticmethod
    def _matches_topic(topic: str, title: str) -> bool:
        words = {
            "Arts & culture": ("art", "culture", "museum", "exhibit", "theater", "film", "music"),
            "Tech & AI": ("ai", "artificial intelligence", "technology", "tech"),
            "Cats": ("cat", "cats", "kitten", "kittens"),
            "Local bright spots": ("seattle",),
            "Food": ("food", "restaurant", "cook", "recipe", "chef", "taco", "cuisine"),
        }
        lowered = title.lower()
        if topic == "Food" and any(word in lowered for word in ("inspection", "recall", "outbreak")):
            return False
        return any(re.search(rf"\b{re.escape(word)}\w*\b", lowered) for word in words[topic])

    def activities(self, interests, start, end):
        return []

    @staticmethod
    def _feed(query: str) -> list[dict[str, str]]:
        params = urlencode({"q": f"{query} when:3d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
        request = Request(f"{GOOGLE_NEWS_RSS}?{params}", headers={
            "User-Agent": "PersonalAssistantCapstone/0.1",
        })
        with urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
        items: list[dict[str, str]] = []
        for element in root.findall("./channel/item"):
            raw_title = unescape(element.findtext("title", "")).strip()
            source = element.findtext("source", "Unknown source").strip()
            title = re.sub(rf"\s+-\s+{re.escape(source)}$", "", raw_title).strip()
            published = element.findtext("pubDate", "")
            try:
                published_at = parsedate_to_datetime(published).astimezone(timezone.utc)
                published_value = published_at.isoformat()
            except (TypeError, ValueError):
                published_value = datetime.now(timezone.utc).isoformat()
            if title:
                items.append({
                    "title": title, "url": element.findtext("link", ""),
                    "source": source, "published_at": published_value,
                })
        return items
