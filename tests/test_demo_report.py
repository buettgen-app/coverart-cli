"""Offline checks for demo generation's network and thumbnail budgets."""

from __future__ import annotations

import base64
import io

from PIL import Image

from coverart_cli.providers import ProviderResult
from coverart_cli.report import MAX_THUMB_DIMENSION
from docs import make_demo_report


def test_demo_rejects_invalid_provider_image(monkeypatch) -> None:
    provider = make_demo_report.ITunesProvider()
    monkeypatch.setattr(
        provider, "fetch", lambda *a: ProviderResult(b"not an image", "itunes", "fixture")
    )
    assert make_demo_report.fetch_itunes("Artist", "Album", provider) is None


def test_demo_uses_bounded_thumbnail(monkeypatch) -> None:
    output = io.BytesIO()
    Image.new("RGB", (1024, 1024), "navy").save(output, format="PNG")
    provider = make_demo_report.ITunesProvider()
    monkeypatch.setattr(
        provider, "fetch", lambda *a: ProviderResult(output.getvalue(), "itunes", "fixture")
    )
    uri = make_demo_report.fetch_itunes("Artist", "Album", provider)
    assert uri is not None
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as image:
        assert max(image.size) <= MAX_THUMB_DIMENSION


def test_demo_reuses_provider_and_enforces_total_budget(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(make_demo_report, "REPO_ROOT", tmp_path)
    providers = []

    def fake_fetch(artist, album, provider):
        providers.append(provider)
        return "x" * make_demo_report.MAX_REPORT_THUMB_BYTES

    captured = []

    def fake_build(entries, **kw):
        captured.extend(entries)
        return "demo"

    monkeypatch.setattr(make_demo_report, "fetch_itunes", fake_fetch)
    monkeypatch.setattr(make_demo_report, "build_report", fake_build)
    make_demo_report.main()
    assert len(providers) > 1 and len({id(p) for p in providers}) == 1
    assert all(e.has_cover and e.source != "none" for e in captured[:-2])
    assert captured[1].cover_data_uri is None
    assert (
        sum(len(e.cover_data_uri or "") for e in captured)
        <= make_demo_report.MAX_REPORT_THUMB_BYTES
    )
