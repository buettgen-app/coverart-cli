"""MusicBrainz + Cover Art Archive provider."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse

from coverart_cli.providers.base import CoverProvider, ProviderResult, _default_user_agent
from coverart_cli.tagging import MIN_COVER_BYTES

log = logging.getLogger(__name__)

MB_API = "https://musicbrainz.org/ws/2/"
CAA_API = "https://coverartarchive.org/"
# MusicBrainz requires 1 req/s. Be polite.
MB_MIN_DELAY = 1.1


class MusicBrainzProvider(CoverProvider):
    name = "musicbrainz"
    allowed_hosts = frozenset({
        "musicbrainz.org",
        "coverartarchive.org",
        "archive.org",
        ".archive.org",
    })

    def __init__(self, user_agent: str | None = None, search_limit: int = 5) -> None:
        # MusicBrainz REQUIRES a meaningful UA with contact info; nudge users.
        ua = user_agent or _default_user_agent()
        if "contact" not in ua.lower() and "@" not in ua and "https://" not in ua:
            log.debug("musicbrainz UA should include contact info per their TOS")
        self.user_agent = ua
        self.search_limit = search_limit
        self._last_request = 0.0
        self._rate_lock = threading.Lock()

    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        self._respect_rate_limit()
        rgs = self._search_release_groups(artist, album)
        if not rgs:
            return None
        for rg in rgs:
            mbid = rg.get("id")
            if not mbid:
                continue
            caa_url = f"{CAA_API}release-group/{mbid}/front-1000"
            img = self._http_get(caa_url, timeout=25)
            if img and len(img) >= MIN_COVER_BYTES:
                return ProviderResult(image_bytes=img, source=self.name, image_url=caa_url)
        return None

    def _search_release_groups(self, artist: str, album: str) -> list[dict]:
        query = f'artist:"{self._escape(artist)}" AND release:"{self._escape(album)}"'
        url = MB_API + "release-group/?" + urllib.parse.urlencode({
            "query": query,
            "fmt": "json",
            "limit": str(self.search_limit),
        })
        raw = self._http_get(url)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data.get("release-groups", [])

    @staticmethod
    def _escape(s: str) -> str:
        # MusicBrainz Lucene-style query — escape special chars
        for ch in ('"', "\\", "(", ")", "[", "]", "{", "}"):
            s = s.replace(ch, " ")
        return s.strip()

    def _respect_rate_limit(self) -> None:
        # Serialise across threads — MusicBrainz allows ≤1 request per second per IP.
        with self._rate_lock:
            elapsed = time.time() - self._last_request
            if elapsed < MB_MIN_DELAY:
                time.sleep(MB_MIN_DELAY - elapsed)
            self._last_request = time.time()
