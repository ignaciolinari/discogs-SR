from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

import requests

from scraper.auth import CookieFileLoader, load_headers_from_file


class CookieFileLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.base_path = Path(self._tempdir.name)
        self._sleep_for_fs_tick()

    def _sleep_for_fs_tick(self) -> None:
        time.sleep(0.05)

    def _write(self, name: str, content: str) -> Path:
        path = self.base_path / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_refreshes_on_change(self) -> None:
        cookies_file = self._write(
            "cookies.json",
            json.dumps(
                [
                    {
                        "name": "session",
                        "value": "abc123",
                        "domain": ".discogs.com",
                        "path": "/",
                    }
                ]
            ),
        )

        loader = CookieFileLoader(cookies_file, reload_interval=0.02)
        session = requests.Session()

        loader.apply(session, force=True)
        self.assertEqual(session.cookies.get("session"), "abc123")

        self._sleep_for_fs_tick()
        cookies_file.write_text(
            json.dumps(
                [
                    {
                        "name": "session",
                        "value": "xyz789",
                        "path": "/",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self._sleep_for_fs_tick()

        loader.apply(session)
        self.assertEqual(session.cookies.get("session"), "xyz789")

    def test_supports_netscape_format(self) -> None:
        cookies_file = self._write(
            "cookies.txt",
            """# Netscape HTTP Cookie File
.discogs.com\tTRUE\t/\tFALSE\t0\ttoken\tvalue123
""",
        )

        loader = CookieFileLoader(cookies_file, reload_interval=None)
        session = requests.Session()

        loader.apply(session, force=True)
        self.assertEqual(session.cookies.get("token"), "value123")


class HeaderLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.base_path = Path(self._tempdir.name)

    def test_load_headers_from_file(self) -> None:
        headers_file = self.base_path / "headers.json"
        headers_file.write_text(
            json.dumps({"X-Test": "value", "Accept-Language": "es-AR"}),
            encoding="utf-8",
        )

        headers = load_headers_from_file(headers_file)
        self.assertEqual(headers["X-Test"], "value")
        self.assertEqual(headers["Accept-Language"], "es-AR")


if __name__ == "__main__":  # pragma: no cover - manual execution
    unittest.main()
