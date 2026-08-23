"""Apple Music / iTunes Search API provider — no key required."""
from __future__ import annotations

import json
import logging
import urllib.parse

from coverart_cli.providers.base import CoverProvider, ProviderResult, _default_user_agent
from coverart_cli.tagging import MIN_COVER_BYTES

log = logging.getLogger(__name__)

ITUNES_SEARCH = "https://itunes.apple.com/search"


class ITunesProvider(CoverProvider):
    """Search Apple's public iTunes catalogue. Returns the largest available artwork."""

    name = "itunes"
    allowed_hosts = frozenset({"itunes.apple.com", ".mzstatic.com"})

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or _default_user_agent()

    def fetch(self, artist: str, album: str) -> ProviderResult | None:
        params = {
            "term": f"{artist} {album}",
            "entity": "album",
            "limit": "5",
            "media": "music",
        }
        raw = self._http_get(ITUNES_SEARCH + "?" + urllib.parse.urlencode(params))
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        artist_l = artist.lower()
        album_l = album.lower()
        for hit in data.get("results", []):
            hit_artist = (hit.get("artistName") or "").lower()
            hit_album = (hit.get("collectionName") or "").lower()
            # accept the result if either field matches strongly
            artist_match = artist_l in hit_artist or hit_artist in artist_l
            album_match = album_l in hit_album or hit_album in album_l
            if not artist_match and not album_match:
                continue
            url = hit.get("artworkUrl100")
            if not url:
                continue
            # iTunes returns 100x100; ask for 1000x1000 by swapping the suffix.
            hi_res = url.replace("100x100bb", "1000x1000bb").replace(
                "100x100", "1000x1000"
            )
            img = self._http_get(hi_res, timeout=25)
            if img and len(img) >= MIN_COVER_BYTES:
                return ProviderResult(image_bytes=img, source=self.name, image_url=hi_res)
        return None
