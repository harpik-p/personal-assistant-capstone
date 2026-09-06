from __future__ import annotations

from datetime import date, datetime, timedelta
from html import unescape
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SPL_EVENTS_ICAL = "https://www.trumba.com/calendars/kalendaro.ics"
PARENTMAP_API = "https://www.parentmap.com/wp-json/tribe/events/v1/events"


def _unfold_ical(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _clean(value: str) -> str:
    value = value.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";")
    value = re.sub(r"<[^>]+>", " ", unescape(value))
    return " ".join(value.split())


class SeattleActivitySearch:
    """Free live family-event search using Seattle Public Library's public feed."""

    KEYWORDS = {
        "physical": ("movement", "dance", "yoga", "fitness", "parkour", "sports", "active"),
        "creative": ("art", "craft", "creative", "draw", "paint", "maker", "sew"),
        "science": ("science", "stem", "space", "chemistry", "robot", "engineering", "pokemon"),
        "food": ("cook", "food", "bake", "cuisine", "kitchen"),
    }
    EXCLUDED_TITLE_TERMS = (
        "adult", "author talk", "genealogy", "tax help", "citizenship",
        "job help", "legal clinic", "book group", "toddler", "baby", "preschool",
    )

    def news(self, interests: list[str]) -> list[dict[str, str]]:
        return []

    def activities(self, interests: list[str], start: date, end: date) -> list[dict[str, str]]:
        request = Request(SPL_EVENTS_ICAL, headers={"User-Agent": "PersonalAssistantCapstone/0.1"})
        with urlopen(request, timeout=30) as response:
            events = self._parse(response.read().decode("utf-8", "replace"))
        preference_text = " ".join(interests).lower()
        candidates: list[tuple[int, dict[str, str]]] = []
        for event in events:
            day = self._event_date(event.get("DTSTART", ""))
            if day is None or not start <= day <= end or day.weekday() < 5:
                continue
            title = _clean(event.get("SUMMARY", "Untitled event"))
            description = _clean(event.get("DESCRIPTION", ""))
            haystack = f"{title} {description}".lower()
            if any(term in title.lower() for term in self.EXCLUDED_TITLE_TERMS):
                continue
            if not self._suitable_age(haystack):
                continue
            score, matches = self._score(haystack, preference_text)
            if not any(match in self.KEYWORDS for match in matches):
                continue
            url = event.get("URL") or event.get("X-TRUMBA-LINK") or "https://www.spl.org/event-calendar"
            candidates.append((score, {
                "title": title,
                "date": day.isoformat(),
                "url": url,
                "location": _clean(event.get("LOCATION", "Seattle Public Library")),
                "source": "Seattle Public Library",
                "reason": f"Matches: {', '.join(matches)}; scheduled on a weekend.",
            }))
        candidates.extend(self._parentmap(interests, start, end))
        candidates.sort(key=lambda item: (-item[0], item[1]["date"], item[1]["title"]))
        unique: list[dict[str, str]] = []
        seen: set[str] = set()
        for _, event in candidates:
            key = event["title"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(event)
        return unique[:12]

    def _parentmap(self, interests: list[str], start: date,
                   end: date) -> list[tuple[int, dict[str, str]]]:
        events: list[dict[str, object]] = []
        saturday = start + timedelta(days=(5 - start.weekday()) % 7)
        while saturday <= end:
            sunday = min(saturday + timedelta(days=1), end)
            params = urlencode({
                "start_date": saturday.isoformat(), "end_date": sunday.isoformat(),
                "per_page": 100,
            })
            request = Request(f"{PARENTMAP_API}?{params}", headers={
                "User-Agent": "PersonalAssistantCapstone/0.1",
            })
            with urlopen(request, timeout=30) as response:
                page = json.loads(response.read().decode("utf-8", "replace"))
                events.extend(page.get("events", []))
            saturday += timedelta(days=7)
        preferences = " ".join(interests).lower()
        results: list[tuple[int, dict[str, str]]] = []
        nearby = {"seattle", "shoreline", "bellevue", "kirkland", "mercer island"}
        for event in events:
            try:
                day = date.fromisoformat(str(event["start_date"])[:10])
            except (KeyError, ValueError):
                continue
            if day.weekday() < 5:
                continue
            title = _clean(str(event.get("title", "Untitled event")))
            if any(term in title.lower() for term in self.EXCLUDED_TITLE_TERMS):
                continue
            venue = event.get("venue") if isinstance(event.get("venue"), dict) else {}
            city = str(venue.get("city", "Seattle")).lower()
            if city and city not in nearby:
                continue
            categories = " ".join(
                str(item.get("name", "")) for item in event.get("categories", [])
                if isinstance(item, dict)
            )
            description = _clean(str(event.get("description", "")))
            haystack = f"{title} {description} {categories}".lower()
            score, matches = self._score(haystack, preferences)
            if not any(match in self.KEYWORDS for match in matches):
                continue
            location = _clean(str(venue.get("venue") or venue.get("city") or "Seattle area"))
            results.append((score + 1, {
                "title": title, "date": day.isoformat(), "url": str(event.get("url", "")),
                "location": location, "source": "ParentMap",
                "reason": f"Matches: {', '.join(matches)}; family event on a weekend.",
            }))
        return results

    @classmethod
    def _score(cls, text: str, preferences: str) -> tuple[int, list[str]]:
        score = 0
        matches: list[str] = []
        for category, words in cls.KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(word)}\w*\b", text) for word in words) and any(
                re.search(rf"\b{re.escape(word)}\w*\b", preferences) for word in words
            ):
                score += 3
                matches.append(category)
        if any(audience in text for audience in ("children", "kids", "families", "family", "tween")):
            score += 2
            matches.append("children's event")
        return score, matches

    @staticmethod
    def _suitable_age(text: str) -> bool:
        ranges = re.findall(r"ages?\s+(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})", text)
        if ranges:
            return any(int(low) <= 9 and int(high) >= 7 for low, high in ranges)
        return any(term in text for term in ("children", "kids", "family", "families", "tween", "teen"))

    @staticmethod
    def _event_date(value: str) -> date | None:
        raw = value.split(":", 1)[-1]
        try:
            return datetime.strptime(raw[:8], "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _parse(text: str) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in _unfold_ical(text):
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT" and current is not None:
                events.append(current)
                current = None
            elif current is not None and ":" in line:
                key, value = line.split(":", 1)
                simple_key = key.split(";", 1)[0]
                if simple_key in {
                    "SUMMARY", "LOCATION", "DTSTART", "DESCRIPTION", "URL", "X-TRUMBA-LINK"
                }:
                    current[simple_key] = value
        return events
