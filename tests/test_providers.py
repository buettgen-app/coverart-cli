"""Provider-level smoke tests (no network)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from coverart_cli.providers.base import CoverProvider
from coverart_cli.providers.lastfm import LastFmProvider
from coverart_cli.providers.musicbrainz import MusicBrainzProvider

FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 3000


class DummyProvider(CoverProvider):
    name = "dummy"
    user_agent = "dummy/1.0"
    allowed_hosts = frozenset({"example.com"})

    def fetch(self, artist: str, album: str):
        return None


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.url = "https://example.com/cover.jpg"

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self.payload
        return self.payload[:size]


def test_lastfm_requires_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        LastFmProvider(api_key="")


def test_lastfm_best_image_picks_largest() -> None:
    images = [
        {"size": "small", "#text": "http://example.com/s.jpg"},
        {"size": "large", "#text": "http://example.com/l.jpg"},
        {"size": "extralarge", "#text": "http://example.com/xl.jpg"},
        {"size": "mega", "#text": "http://example.com/mega.jpg"},
    ]
    assert LastFmProvider._best_image(images) == "http://example.com/mega.jpg"


def test_lastfm_best_image_skips_placeholder() -> None:
    placeholder = "https://lastfm.freetls.fastly.net/i/u/2a96cbd8b46e442fc41c2b86b821562f.png"
    images = [{"size": "mega", "#text": placeholder}]
    assert LastFmProvider._best_image(images) is None


def test_lastfm_best_image_empty() -> None:
    assert LastFmProvider._best_image([]) is None
    assert LastFmProvider._best_image([{"size": "small", "#text": ""}]) is None


def test_musicbrainz_escape_strips_lucene_special_chars() -> None:
    assert MusicBrainzProvider._escape('Some "Album" (Deluxe)') == "Some  Album   Deluxe"
    assert MusicBrainzProvider._escape("Foo [Disc 1]") == "Foo  Disc 1"


def test_itunes_provider_instantiable() -> None:
    from coverart_cli.providers import ITunesProvider

    p = ITunesProvider()  # default
    assert p.user_agent
    p2 = ITunesProvider(user_agent="myua/1.0")  # explicit UA also works (regression)
    assert p2.user_agent == "myua/1.0"


def test_deezer_provider_instantiable() -> None:
    from coverart_cli.providers import DeezerProvider

    p = DeezerProvider()
    assert p.user_agent
    p2 = DeezerProvider(user_agent="myua/1.0")
    assert p2.user_agent == "myua/1.0"


def test_deezer_escape_strips_quotes() -> None:
    from coverart_cli.providers import DeezerProvider

    assert DeezerProvider._escape('"Foo" bar') == "Foo  bar"


@pytest.mark.parametrize(
    "mismatch",
    [
        {"artistName": "The Beatles", "collectionName": "Abbey Road"},
        {"artistName": "Pink Floyd", "collectionName": "Revolver"},
        {"artistName": "", "collectionName": "Revolver"},
        {"collectionName": "Revolver"},
    ],
)
def test_itunes_rejects_partial_or_missing_identity_matches(
    mismatch: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import ITunesProvider

    mismatch["artworkUrl100"] = "https://is1-ssl.mzstatic.com/image/100x100bb.jpg"
    payload = json.dumps({"results": [mismatch]}).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("The Beatles", "Revolver") is None
    assert len(urls) == 1


def test_itunes_skips_mismatch_then_accepts_full_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coverart_cli.providers import ITunesProvider

    payload = json.dumps(
        {
            "results": [
                {
                    "artistName": "The Beatles",
                    "collectionName": "Abbey Road",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/bad/100x100bb.jpg",
                },
                {
                    "artistName": "The Beatles",
                    "collectionName": "Revolver",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/good/100x100bb.jpg",
                },
            ]
        }
    ).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload if len(urls) == 1 else FAKE_JPEG

    provider = ITunesProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    result = provider.fetch("The Beatles", "Revolver")
    assert result is not None
    assert result.image_bytes == FAKE_JPEG
    assert all("/bad/" not in url for url in urls)
    assert any("/good/" in url for url in urls)


@pytest.mark.parametrize(
    "mismatch",
    [
        {"artist": {"name": "The Beatles"}, "title": "Abbey Road"},
        {"artist": {"name": "Pink Floyd"}, "title": "Revolver"},
        {"artist": {}, "title": "Revolver"},
        {"title": "Revolver"},
    ],
)
def test_deezer_rejects_partial_or_missing_identity_matches(
    mismatch: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverart_cli.providers import DeezerProvider

    mismatch["cover_xl"] = "https://cdn-images.dzcdn.net/images/cover/bad"
    payload = json.dumps({"data": [mismatch]}).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload

    provider = DeezerProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    assert provider.fetch("The Beatles", "Revolver") is None
    assert len(urls) == 1


def test_deezer_skips_mismatch_then_accepts_full_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coverart_cli.providers import DeezerProvider

    payload = json.dumps(
        {
            "data": [
                {
                    "artist": {"name": "The Beatles"},
                    "title": "Abbey Road",
                    "cover_xl": "https://cdn-images.dzcdn.net/images/cover/bad",
                },
                {
                    "artist": {"name": "The Beatles"},
                    "title": "Revolver",
                    "cover_xl": "https://cdn-images.dzcdn.net/images/cover/good",
                },
            ]
        }
    ).encode()
    urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> bytes:
        urls.append(url)
        return payload if len(urls) == 1 else FAKE_JPEG

    provider = DeezerProvider()
    monkeypatch.setattr(provider, "_http_get", fake_get)

    result = provider.fetch("The Beatles", "Revolver")
    assert result is not None
    assert result.image_bytes == FAKE_JPEG
    assert all("/bad" not in url for url in urls)
    assert any("/good" in url for url in urls)


def test_safe_url_for_log_strips_api_key() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://ws.audioscrobbler.com/2.0/?method=album.getinfo&api_key=SECRET123"
    sanitized = _safe_url_for_log(url)
    assert "SECRET123" not in sanitized
    assert "api_key" not in sanitized
    assert sanitized == "https://ws.audioscrobbler.com/2.0/"


def test_safe_url_for_log_strips_entire_query() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://itunes.apple.com/search?term=Pink+Floyd&entity=album"
    sanitized = _safe_url_for_log(url)
    assert "?" not in sanitized
    assert "term" not in sanitized
    assert sanitized == "https://itunes.apple.com/search"


def test_safe_url_for_log_keeps_path() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    url = "https://coverartarchive.org/release-group/abcd-1234/front-1000"
    sanitized = _safe_url_for_log(url)
    assert sanitized == url  # no query → unchanged


def test_safe_url_for_log_handles_garbage() -> None:
    from coverart_cli.providers.base import _safe_url_for_log

    # Anything urlsplit can parse should round-trip safely; nothing should crash.
    assert "<invalid-url>" not in _safe_url_for_log("https://example.com")
    assert _safe_url_for_log("") == ""


class FakeOpener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def open(self, request: urllib.request.Request, timeout: int) -> FakeResponse:
        return FakeResponse(self.payload)


def test_http_get_rejects_responses_over_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 11)
    )

    result = DummyProvider()._http_get("https://example.com/cover.jpg", max_bytes=10)
    assert result is None


def test_http_get_accepts_responses_at_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: FakeOpener(b"x" * 10)
    )

    result = DummyProvider()._http_get("https://example.com/cover.jpg", max_bytes=10)
    assert result == b"x" * 10


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/cover.jpg",
        "https://example.com.evil.test/cover.jpg",
        "https://127.0.0.1/cover.jpg",
    ],
)
def test_http_get_blocks_urls_outside_provider_policy(url: str) -> None:
    assert DummyProvider()._http_get(url) is None


def test_redirect_handler_blocks_disallowed_host() -> None:
    from coverart_cli.providers.base import _RestrictedRedirectHandler

    handler = _RestrictedRedirectHandler(frozenset({"example.com"}))
    request = urllib.request.Request("https://example.com/start")
    with pytest.raises(urllib.error.HTTPError, match="redirect host is not allowed"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://127.0.0.1/private",
        )
