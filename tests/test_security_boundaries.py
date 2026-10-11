"""Hostile network responses and operational failures at public boundaries."""

from __future__ import annotations

import errno
import io
import json
import runpy
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from coverart_cli import cli, config, core, report, tagging
from coverart_cli.providers import (
    DeezerProvider,
    ITunesProvider,
    LastFmProvider,
    MusicBrainzProvider,
)
from coverart_cli.providers.base import (
    ProviderUnavailable,
    _DeadlineHTTPSHandler,
    _DeadlineResponse,
    _RestrictedRedirectHandler,
    _retry_after_seconds,
)

from .image_fixtures import VALID_JPEG, VALID_PNG  # pyrefly: ignore [missing-import]
from .test_integration import FakeProvider, _make_album  # pyrefly: ignore [missing-import]
from .test_providers import DummyProvider, FakeResponse  # pyrefly: ignore [missing-import]


@pytest.mark.parametrize("port", [0, 80, 444, 8080])
def test_alternative_https_ports_are_blocked_before_network(monkeypatch, port):
    def unexpected_open(*args):
        pytest.fail("disallowed service reached the network")

    monkeypatch.setattr(urllib.request, "build_opener", unexpected_open)
    url = f"https://example.com:{port}/image"
    assert DummyProvider()._http_get(url) is None
    with pytest.raises(urllib.error.HTTPError, match="not allowed"):
        _RestrictedRedirectHandler(frozenset({"example.com"})).redirect_request(
            urllib.request.Request("https://example.com/image"), None, 302, "Found", {}, url
        )


@pytest.mark.parametrize("late_chunk", [b"", b"image"])
def test_download_does_not_accept_bytes_after_body_deadline(monkeypatch, late_chunk):
    clock = [0.0]

    class SlowResponse(FakeResponse):
        def read(self, size=-1):
            pytest.fail("buffer-filling read must not bypass the deadline")

        def read1(self, size):
            clock[0] += 16
            return late_chunk

    monkeypatch.setattr("coverart_cli.providers.base.time.monotonic", lambda: clock[0])
    response = SlowResponse(b"")
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **k: response)
    )
    with pytest.raises(ProviderUnavailable, match="network failure"):
        DummyProvider()._http_get("https://example.com/image", retries=0)


def test_download_checks_deadline_between_small_network_reads(monkeypatch):
    clock = [0.0]
    reads = []

    class TrickleResponse(FakeResponse):
        def read1(self, size):
            reads.append(size)
            clock[0] += 6
            return b"x"

    monkeypatch.setattr("coverart_cli.providers.base.time.monotonic", lambda: clock[0])
    response = TrickleResponse(b"")
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **k: response)
    )
    with pytest.raises(ProviderUnavailable):
        DummyProvider()._http_get("https://example.com/image", retries=0)
    assert len(reads) == 3


@pytest.mark.parametrize("content_length", ["11", "invalid", "10"])
def test_response_length_header_cannot_override_actual_byte_budget(monkeypatch, content_length):
    class HeaderResponse(FakeResponse):
        headers: dict[str, str]

    response = HeaderResponse(b"x" * 11)
    response.headers = {"Content-Length": content_length}
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **k: response)
    )
    assert DummyProvider()._http_get("https://example.com/image", max_bytes=10) is None


def test_final_redirect_url_is_checked_even_for_custom_openers(monkeypatch):
    response = FakeResponse(VALID_JPEG)
    response.url = "https://untrusted.invalid/image"
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: SimpleNamespace(open=lambda *a, **k: response)
    )
    assert DummyProvider()._http_get("https://example.com/image") is None


@pytest.mark.parametrize("value", [None, "nonsense", "not-a-date", object()])
def test_invalid_retry_after_keeps_safe_backoff(value):
    assert _retry_after_seconds({"Retry-After": value}, 2) == 2


def test_allowed_redirect_preserves_https_and_standard_port():
    request = urllib.request.Request("https://example.com/start")
    redirected = _RestrictedRedirectHandler(frozenset({"example.com"})).redirect_request(
        request, None, 302, "Found", {}, "https://example.com:443/image"
    )
    assert redirected is not None
    assert redirected.full_url == "https://example.com:443/image"


@pytest.mark.parametrize("provider_factory", [ITunesProvider, DeezerProvider, MusicBrainzProvider])
@pytest.mark.parametrize("raw", [b"", b"{", b"null", b'"text"'])
def test_catalogue_malformed_response_is_a_miss(provider_factory, raw, monkeypatch):
    provider = provider_factory()
    monkeypatch.setattr(provider, "_http_get", lambda *a, **k: raw)
    assert provider.fetch("Artist", "Album") is None


@pytest.mark.parametrize("payload", [None, {}, {"album": None}, {"error": "invalid"}])
def test_lastfm_schema_and_unknown_errors(payload, monkeypatch):
    provider = LastFmProvider("synthetic-key")
    monkeypatch.setattr(provider, "_http_get", lambda *a, **k: json.dumps(payload).encode())
    if isinstance(payload, dict) and "error" in payload:
        with pytest.raises(ProviderUnavailable, match="unknown"):
            provider.fetch("Artist", "Album")
    else:
        assert provider.fetch("Artist", "Album") is None


@pytest.mark.parametrize("image", [None, "", 4, "https://example.com/image"])
@pytest.mark.parametrize("provider_factory", [ITunesProvider, DeezerProvider])
def test_catalogue_missing_or_too_small_art_is_a_miss(provider_factory, image, monkeypatch):
    provider = provider_factory()
    hit = (
        {"artistName": "Artist", "collectionName": "Album", "artworkUrl100": image}
        if isinstance(provider, ITunesProvider)
        else {"artist": {"name": "Artist"}, "title": "Album", "cover_xl": image}
    )
    field = "results" if isinstance(provider, ITunesProvider) else "data"
    replies = iter([json.dumps({field: [hit]}).encode(), b"tiny"])
    monkeypatch.setattr(provider, "_http_get", lambda *a, **k: next(replies))
    assert provider.fetch("Artist", "Album") is None


@pytest.mark.parametrize("credit", [None, [], [None], [{"name": ""}], [{"artist": None}]])
def test_musicbrainz_rejects_unverifiable_artist_credit(credit):
    assert MusicBrainzProvider._artist_credit_name(credit) is None


def test_itunes_rate_limiter_waits_between_calls(monkeypatch):
    provider = ITunesProvider()
    monkeypatch.setattr("coverart_cli.providers.itunes.time.monotonic", lambda: 1.0)
    waits = []
    monkeypatch.setattr("coverart_cli.providers.itunes.time.sleep", waits.append)
    provider._respect_rate_limit()
    assert waits == [pytest.approx(2.1)]


@pytest.mark.parametrize("key", ["lastfm_key", "user_agent", "missing_csv", "report_html"])
def test_config_rejects_non_string_sensitive_and_output_values(tmp_path, monkeypatch, key):
    monkeypatch.setattr(config, "default_config_paths", lambda: [])
    path = tmp_path / "config.toml"
    path.write_text(f"{key} = 123\n", encoding="utf-8")
    assert config.load_config(path) == {}


@pytest.mark.parametrize("workers", [1, 2])
def test_worker_crash_is_recorded_without_modifying_tracks(tmp_path, monkeypatch, workers):
    album = _make_album(tmp_path, "Artist", "Album", tracks=1)
    track = album / "01.mp3"
    before = track.read_bytes()

    def failure(*a, **k):
        raise OSError("injected read failure")

    monkeypatch.setattr(core, "process_album", failure)
    stats = core.run(core.RunOptions(root=tmp_path, providers=[FakeProvider()], workers=workers))
    assert stats.errors == 1
    assert stats.misses[0][0] == album
    assert track.read_bytes() == before
    assert not (album / "cover.jpg").exists()


@pytest.mark.parametrize("error_code", [errno.EACCES, errno.EMFILE, errno.ENFILE])
def test_traversal_distinguishes_inaccessible_directory_from_resource_exhaustion(
    tmp_path, monkeypatch, error_code
):
    def failure(fd):
        raise OSError(error_code, "injected enumeration failure")

    monkeypatch.setattr(core.fs, "scandir", failure)
    if error_code == errno.EACCES:
        assert core.find_album_dirs(tmp_path) == []
    else:
        with pytest.raises(OSError) as caught:
            core.find_album_dirs(tmp_path)
        assert caught.value.errno == error_code


def test_sidecar_commit_failure_preserves_previous_cover_and_cleans_staging(tmp_path, monkeypatch):
    destination = tmp_path / "cover.jpg"
    destination.write_bytes(VALID_JPEG)

    def failure(*a, **k):
        raise OSError(errno.ENOSPC, "injected commit failure")

    monkeypatch.setattr(tagging.fs, "replace", failure)
    with pytest.raises(OSError):
        tagging.write_sidecar(tmp_path, VALID_PNG)
    assert destination.read_bytes() == VALID_JPEG
    assert not (tmp_path / "cover.png").exists()
    assert not list(tmp_path.glob(".coverart-*"))


def test_report_commit_failure_preserves_previous_report_and_cleans_staging(tmp_path, monkeypatch):
    output = tmp_path / "report.html"
    output.write_text("previous report", encoding="utf-8")

    def failure(*a, **k):
        raise OSError(errno.ENOSPC, "injected commit failure")

    monkeypatch.setattr(report.os, "replace", failure)
    with pytest.raises(OSError):
        report.write_report(tmp_path, output)
    assert output.read_text(encoding="utf-8") == "previous report"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("error", [OSError("missing library"), PermissionError("access denied")])
def test_cli_run_errors_return_failure_without_success_message(
    tmp_path, monkeypatch, capsys, error
):
    monkeypatch.setattr(cli, "load_config", lambda *a: {})

    def failure(*a):
        raise error

    monkeypatch.setattr(cli, "run", failure)
    assert cli.main([str(tmp_path), "--no-lastfm"]) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "SUMMARY" not in captured.out


def test_python_module_entry_point_propagates_exit_status(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda: 2)
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("coverart_cli", run_name="__main__")
    assert caught.value.code == 2


def test_cli_explicit_arguments_stop_at_positional_separator(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["coverart", "--workers=2", "--", "--no-embed"])
    assert cli._explicit_cli_dests(cli.build_parser(), None) == {"workers"}


def test_oversized_ogg_picture_is_rejected_before_base64_allocation(monkeypatch):
    monkeypatch.setattr(tagging, "MAX_ENCODED_PICTURE_BYTES", 8)

    def unexpected_decode(*args, **kwargs):
        pytest.fail("oversized metadata reached the allocating decoder")

    monkeypatch.setattr(tagging.base64, "b64decode", unexpected_decode)
    assert tagging._ogg_picture_size({"metadata_block_picture": ["A" * 12]}) == 0


def test_oversized_cover_is_not_hashed_or_retained_in_validation_cache(monkeypatch):
    monkeypatch.setattr(tagging, "MAX_COVER_BYTES", 8)

    def unexpected_hash(*args):
        pytest.fail("oversized artwork reached hashing")

    monkeypatch.setattr(tagging.hashlib, "sha256", unexpected_hash)
    cache = tagging.CoverValidationCache()
    assert cache.mime(b"x" * 9) is None
    assert len(cache._values) == 0


@pytest.mark.parametrize("phase", ["headers", "chunk-size", "body"])
def test_real_http_parser_cannot_hide_trickle_reads_inside_one_call(monkeypatch, phase):
    clock = [0.0]
    timeouts = []
    headers = (
        b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n"
        if phase == "body"
        else b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    )

    class TrickleRaw(io.RawIOBase):
        def readinto(self, buffer):
            if phase != "headers" and self.header_pending:
                self.header_pending = False
                buffer[: len(headers)] = headers
                return len(headers)
            clock[0] += 6
            # A long chunk-size line used to stay inside readline indefinitely.
            buffer[0] = ord("0") if phase == "chunk-size" else ord("x")
            return 1

        header_pending = True

    raw = TrickleRaw()

    class FakeSocket:
        def gettimeout(self):
            return 15

        def settimeout(self, timeout):
            timeouts.append(timeout)

        def makefile(self, mode, buffering=-1):
            return io.BytesIO() if buffering != 0 else raw

    monkeypatch.setattr("coverart_cli.providers.base.time.monotonic", lambda: clock[0])
    import socket
    from typing import cast

    response = _DeadlineResponse(cast(socket.socket, FakeSocket()))
    with pytest.raises(TimeoutError, match="wall-clock"):
        response.begin()
        response.read(64 * 1024)
    response.close()
    assert raw.closed
    assert timeouts == ([15, 9, 3] if phase == "headers" else [15, 15, 9, 3])


def test_https_deadline_handler_keeps_certificate_and_hostname_verification(monkeypatch):
    import ssl

    handler = _DeadlineHTTPSHandler()
    assert handler.context.verify_mode == ssl.CERT_REQUIRED
    assert handler.context.check_hostname
    captured = {}

    def open_connection(connection, req, **kwargs):
        captured.update(kwargs)
        return "response"

    monkeypatch.setattr(handler, "do_open", open_connection)
    assert handler.https_open(urllib.request.Request("https://example.com")) == "response"
    assert captured["context"] is handler.context


def test_response_rejects_infinite_timeout_and_closes_stream():
    import socket
    from typing import cast

    stream = io.BytesIO()
    sock = SimpleNamespace(gettimeout=lambda: None, makefile=lambda mode: stream)
    with pytest.raises(ValueError, match="finite timeout"):
        _DeadlineResponse(cast(socket.socket, sock))
    assert stream.closed


@pytest.mark.parametrize("code", [errno.EACCES, errno.ENOENT, errno.EMFILE, errno.ENFILE])
def test_component_open_failure_preserves_reachable_albums(tmp_path, monkeypatch, code):
    album = _make_album(tmp_path, "Artist", "Album", tracks=1)
    blocked = tmp_path / "Unavailable"
    blocked.mkdir()
    real_open = core.fs.open

    def guarded_open(path, flags, *args, **kwargs):
        if str(path) == "Unavailable":
            raise OSError(code, "injected component open failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(core.fs, "open", guarded_open)
    if code in {errno.EMFILE, errno.ENFILE}:
        with pytest.raises(OSError) as caught:
            core.find_album_dirs(tmp_path)
        assert caught.value.errno == code
    else:
        assert core.find_album_dirs(tmp_path) == [album]
        stats = core.run(core.RunOptions(root=tmp_path, providers=[FakeProvider()], workers=1))
        assert stats.albums_total == 1 and stats.files_embedded == 1
        assert (album / "cover.jpg").exists()
        assert len(report.scan_library(tmp_path)) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory permissions")
def test_unreadable_child_is_skipped_by_real_filesystem(tmp_path):
    import os

    if os.geteuid() == 0:
        pytest.skip("root bypasses POSIX read permission")
    album = _make_album(tmp_path, "Artist", "Album", tracks=1)
    blocked = tmp_path / "Unavailable"
    blocked.mkdir()
    blocked.chmod(0)
    try:
        assert core.find_album_dirs(tmp_path) == [album]
    finally:
        blocked.chmod(0o700)
