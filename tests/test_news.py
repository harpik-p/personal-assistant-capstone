import unittest
from unittest.mock import patch

from personal_assistant.news import PersonalizedNewsSearch


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Seattle cat opens an art gallery - Example News</title>
<link>https://example.com/story</link><pubDate>Fri, 04 Sep 2026 12:00:00 GMT</pubDate>
<source>Example News</source></item></channel></rss>"""


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return RSS


class NewsTests(unittest.TestCase):
    @patch("personal_assistant.news.urlopen", return_value=FakeResponse())
    def test_digest_is_grouped_and_source_grounded(self, _mock) -> None:
        stories = PersonalizedNewsSearch().news(["art", "AI", "cats", "Seattle", "food"])
        self.assertTrue(stories)
        self.assertEqual(stories[0]["source"], "Example News")
        self.assertEqual(stories[0]["url"], "https://example.com/story")
        self.assertIn("topic", stories[0])


if __name__ == "__main__":
    unittest.main()
