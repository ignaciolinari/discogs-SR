from __future__ import annotations

import unittest
from pathlib import Path

from scraper.parsers import (
    parse_release_detail,
    parse_release_user_list,
    parse_search_results,
    parse_user_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_parse_search_results(self) -> None:
        html = load_fixture("search_page.html")
        releases = parse_search_results(html)
        self.assertEqual(len(releases), 2)

        first = releases[0]
        self.assertEqual(first.release_id, 12345)
        self.assertEqual(first.title, "Album Title")
        self.assertEqual(first.artists, "Some Artist")
        self.assertEqual(first.have_count, 5000)
        self.assertIsNotNone(first.average_rating)
        self.assertAlmostEqual(first.average_rating or 0, 4.5)

    def test_parse_release_detail(self) -> None:
        html = load_fixture("release_page.html")
        detail = parse_release_detail(html)

        self.assertEqual(detail.release_id, 12345)
        self.assertEqual(detail.master_id, 54321)
        self.assertEqual(detail.title, "Album Title")
        self.assertIn("Electronic", detail.genres)
        self.assertIn("House", detail.styles)
        self.assertEqual(len(detail.have_users), 2)
        self.assertIn("collector1", detail.have_users)
        self.assertEqual(len(detail.want_users), 1)
        self.assertEqual(len(detail.reviews), 2)
        self.assertAlmostEqual(detail.reviews[0].rating or 0, 4.5)

    def test_parse_user_profile(self) -> None:
        html = load_fixture("user_page.html")
        profile = parse_user_profile(html, username="reviewer1")

        self.assertEqual(profile.user_id, "reviewer1")
        self.assertEqual(profile.location, "Berlin, Germany")
        self.assertEqual(profile.collection_size, 1234)
        self.assertEqual(profile.wantlist_size, 321)

    def test_parse_release_user_list(self) -> None:
        have_html = load_fixture("release_have_modal.html")
        want_html = load_fixture("release_want_modal.html")

        have_users = parse_release_user_list(have_html)
        want_users = parse_release_user_list(want_html)

        self.assertIn("NewCollector", have_users)
        self.assertIn("SellerProfile", have_users)
        self.assertIn("Collector2", have_users)
        self.assertEqual(len(have_users), len(set(have_users)))

        self.assertIn("NewWantUser", want_users)
        self.assertIn("ExistingWant", want_users)
        self.assertIn("NewCollector", want_users)


if __name__ == "__main__":
    unittest.main()
