"""
Proxy route tests to ensure requests are forwarded and hooks are applied.
"""

from __future__ import annotations

import json
import asyncio
import urllib.error
from typing import Dict

from fastapi.testclient import TestClient

from app.api.routes import proxy as proxy_module
from app.core.config import get_settings
from app.main import app


def test_proxy_crawl_applies_hooks(monkeypatch):
    """
    Ensure /crawl proxy forwards payload and applies request/response hooks.
    """
    settings = get_settings()
    original_base = settings.upstream_base_url
    settings.upstream_base_url = "http://upstream.test"

    async def intercept_request(payload: Dict) -> Dict:
        modified = dict(payload)
        modified["hooked"] = True
        return modified

    async def intercept_response(payload: Dict) -> Dict:
        modified = dict(payload)
        modified["response_hooked"] = True
        return modified

    async def fake_outbound(url: str, method: str, payload: Dict, headers: Dict[str, str], timeout: float):
        assert url == "http://upstream.test/crawl"
        assert method == "POST"
        assert payload.get("hooked") is True
        response_body = json.dumps({"echo": payload}).encode("utf-8")
        result = {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "content": response_body,
        }
        return result

    monkeypatch.setattr(proxy_module, "intercept_crawl_request", intercept_request)
    monkeypatch.setattr(proxy_module, "intercept_crawl_response", intercept_response)
    monkeypatch.setattr(proxy_module, "_perform_outbound_request", fake_outbound)

    client = TestClient(app)
    response = client.post("/crawl", json={"urls": ["https://example.com"]})
    body = response.json()

    assert response.status_code == 200
    assert body["echo"]["hooked"] is True
    assert body["response_hooked"] is True

    settings.upstream_base_url = original_base


def test_build_response_parses_json_with_capitalized_content_type():
    """
    Ensure JSON hooks run even when upstream headers use canonical casing.
    """
    hook_called = False

    async def hook(payload: Dict) -> Dict:
        nonlocal hook_called
        hook_called = True
        payload["response_hooked"] = True
        return payload

    upstream_payload = {"status": "ok"}
    response = asyncio.run(
        proxy_module._build_response_from_upstream(
            upstream_status=200,
            upstream_headers={"Content-Type": "application/json"},
            upstream_content=json.dumps(upstream_payload).encode("utf-8"),
            json_hook=hook,
        )
    )
    body = json.loads(response.body)

    assert hook_called is True
    assert body["response_hooked"] is True
    assert body["status"] == "ok"


def test_proxy_task_applies_hook(monkeypatch):
    """
    Ensure /task/{task_id} proxy forwards and applies response hook.
    """
    settings = get_settings()
    original_base = settings.upstream_base_url
    settings.upstream_base_url = "http://upstream.test"

    async def intercept_task(payload: Dict) -> Dict:
        modified = dict(payload)
        modified["task_hooked"] = True
        return modified

    async def fake_outbound(url: str, method: str, payload: Dict | None, headers: Dict[str, str], timeout: float):
        assert url == "http://upstream.test/task/demo123"
        assert method == "GET"
        response_body = json.dumps({"status": "ok"}).encode("utf-8")
        result = {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "content": response_body,
        }
        return result

    monkeypatch.setattr(proxy_module, "intercept_task_response", intercept_task)
    monkeypatch.setattr(proxy_module, "_perform_outbound_request", fake_outbound)

    client = TestClient(app)
    response = client.get("/task/demo123")
    body = response.json()

    assert response.status_code == 200
    assert body["task_hooked"] is True
    assert body["status"] == "ok"

    settings.upstream_base_url = original_base


def test_intercept_crawl_response_adds_media():
    """
    Ensure intercept_crawl_response adds enhanced_media when HTML is present.
    """
    from app.services import proxy_hooks

    payload = {
        "results": [
            {"html": '<html><body><img src="image.png"/><div style="background-image:url(bg.png)"></div></body></html>'}
        ]
    }
    updated = proxy_hooks._enhance_results(payload["results"])
    assert updated[0].get("enhanced_media")


def test_intercept_task_response_adds_media():
    """
    Ensure intercept_task_response enhances task payloads.
    """
    from app.services import proxy_hooks

    payload = {
        "result": {"html": '<html><body><img src="image.png"/></body></html>'}
    }
    enhanced = asyncio.run(proxy_hooks.intercept_task_response(payload.copy()))
    # Validate that enhanced_media was added
    result_payload = enhanced
    assert result_payload["result"].get("enhanced_media")


def test_enhance_results_can_exclude_media():
    """
    Ensure media exclusion patterns filter enhanced_media entries.
    """
    from app.services import proxy_hooks

    payload = {
        "results": [
            {
                "html": '<img src="https://example.com/keep.jpg"/>'
                '<img src="https://example.com/secret-tracking.png"/>'
            }
        ]
    }
    enhanced = proxy_hooks._enhance_results(
        payload["results"],
        exclude_patterns=["tracking"],
    )
    items = enhanced[0].get("enhanced_media") or []
    urls = [m.get("src_url") for m in items]
    assert "https://example.com/secret-tracking.png" not in urls
    assert "https://example.com/keep.jpg" in urls


def test_intercept_crawl_response_respects_exclude_patterns():
    """
    Ensure intercept_crawl_response drops media that match exclusion patterns (e.g., wp-content/plugins).
    """
    from app.services import proxy_hooks

    payload = {
        "results": [
            {
                "html": '<img src="https://site.com/wp-content/plugins/foo/bar.png"/>'
                '<img src="https://site.com/uploads/keep.jpg"/>'
            }
        ]
    }
    enhanced = asyncio.run(
        proxy_hooks.intercept_crawl_response(
            payload.copy(),
            media_extraction=True,
            extract_media_from_css=False,
            exclude_patterns=[r"wp-content/plugins"],
        )
    )
    items = enhanced["results"][0].get("enhanced_media") or []
    urls = {m.get("src_url") for m in items}
    assert "https://site.com/wp-content/plugins/foo/bar.png" not in urls
    assert "https://site.com/uploads/keep.jpg" in urls


def test_intercept_crawl_response_extracts_network_media():
    """
    Ensure media can be extracted directly from network_requests when enabled.
    """
    from app.services import proxy_hooks

    payload = {
        "results": [
            {
                "network_requests": [
                    {"url": "https://example.com/keep.jpg", "mimeType": "image/jpeg"},
                    {"url": "https://example.com/clip.mp4", "mimeType": "video/mp4"},
                    {"url": "https://example.com/podcast.mp3", "mimeType": "audio/mpeg"},
                ]
            }
        ]
    }
    enhanced = asyncio.run(
        proxy_hooks.intercept_crawl_response(
            payload.copy(),
            media_extraction=True,
            extract_media_from_network_requests=True,
        )
    )
    items = enhanced["results"][0].get("enhanced_media") or []
    urls = {m.get("src_url") for m in items}
    kinds = {m.get("media_type") for m in items}
    assert urls == {
        "https://example.com/keep.jpg",
        "https://example.com/clip.mp4",
        "https://example.com/podcast.mp3",
    }
    assert kinds == {"image", "video", "audio"}


def test_enhanced_media_flags_merge_sources():
    """
    Ensure enhanced_media entries carry source flags and merge when duplicated across sources.
    """
    from app.services import proxy_hooks

    payload = {
        "results": [
            {
                "html": '<img src="https://example.com/foo.jpg"/>',
                "network_requests": [
                    {"url": "https://example.com/foo.jpg", "mimeType": "image/jpeg"},
                ],
            }
        ]
    }
    enhanced = asyncio.run(
        proxy_hooks.intercept_crawl_response(
            payload.copy(),
            media_extraction=True,
            extract_media_from_network_requests=True,
        )
    )
    item = (enhanced["results"][0].get("enhanced_media") or [])[0]
    assert item["src_url"] == "https://example.com/foo.jpg"
    assert item["found_in_html"] is True
    assert item["found_in_network_requests"] is True
    assert item["found_in_css"] is False


def test_proxy_crawl_surfaces_upstream_error(monkeypatch):
    """
    Ensure upstream errors return 502 with URL context.
    """
    settings = get_settings()
    original_base = settings.upstream_base_url
    settings.upstream_base_url = "http://upstream.test"

    async def fake_outbound(url: str, method: str, payload: Dict, headers: Dict[str, str], timeout: float):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(proxy_module, "_perform_outbound_request", fake_outbound)

    client = TestClient(app)
    response = client.post("/crawl", json={"urls": ["https://example.com"]})
    body = response.json()

    assert response.status_code == 502
    assert "Upstream request failed" in body.get("error", "")
    assert "http://upstream.test/crawl" in body.get("error", "")

    settings.upstream_base_url = original_base
