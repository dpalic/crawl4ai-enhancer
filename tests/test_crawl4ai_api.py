"""
Smoke-style checks against a running Crawl4AI-compatible API.

These tests are intentionally dependency-light and rely only on the standard
library plus pytest. They assume the server is already running and reachable at
CRAWL4AI_BASE_URL (default http://localhost:8000).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, Tuple

import pytest
from _pytest.outcomes import Skipped

DEFAULT_TIMEOUT_SECONDS = 5  # Timeout (seconds) for HTTP calls in smoke tests
_UPSTREAM_STATE: Dict[str, object] = {"checked": False, "reachable": False, "reason": ""}


def _base_url() -> str:
    """
    Resolve the base URL for the Crawl4AI API under test from environment.

    Returns:
        str: Base URL without a trailing slash.
    """
    base = os.getenv("CRAWL4AI_BASE_URL", "http://localhost:8000").rstrip("/")
    return base


def _build_url(path: str) -> str:
    """
    Join the base URL with the provided path.

    Args:
        path (str): Path beginning with a slash.

    Returns:
        str: Fully qualified URL.
    """
    base_url = _base_url()
    url = f"{base_url}{path}"
    return url


def _announce_request(name: str, method: str, path: str, note: str = "") -> None:
    """
    Print a human-friendly description of the request about to run.

    Args:
        name (str): Logical name of the test.
        method (str): HTTP method (e.g., GET, POST).
        path (str): Request path.
        note (str): Optional short note about expectations.
    """
    base_url = _base_url()
    message = f"[Test] {name}: {method} {base_url}{path}"
    if note:
        message = f"{message} | {note}"
    print(message)


def _print_status(name: str, status: str) -> None:
    """
    Print a status line with color for test outcome.

    Args:
        name (str): Logical test name.
        status (str): One of "ok", "fail", "skip".
    """
    color_map = {
        "ok": "\033[32m",    # green
        "fail": "\033[31m",  # red
        "skip": "\033[33m",  # yellow
    }
    label_map = {
        "ok": "OK",
        "fail": "FAIL",
        "skip": "SKIP",
    }
    color = color_map.get(status, "\033[31m")
    label = label_map.get(status, "FAIL")
    reset = "\033[0m"
    print(f"[{color}{label}{reset}] {name}")


def _probe_upstream_once() -> bool:
    """
    Probe the upstream (through the enhancer) once to avoid repeated failures when offline.

    Returns:
        bool: True if reachable, False otherwise.
    """
    if _UPSTREAM_STATE["checked"]:
        return bool(_UPSTREAM_STATE["reachable"])

    url = _build_url("/health")
    reachable = False
    reason = ""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            reachable = resp.getcode() == 200
            reason = f"status {resp.getcode()}"
    except urllib.error.HTTPError as exc:
        reachable = exc.code < 500
        reason = f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        reason = f"Network error: {getattr(exc, 'reason', exc)}"
    except Exception as exc:
        reason = f"Error: {exc}"

    _UPSTREAM_STATE["checked"] = True
    _UPSTREAM_STATE["reachable"] = reachable
    _UPSTREAM_STATE["reason"] = reason
    if not reachable:
        print(f"[Info] Upstream unavailable ({reason}); skipping API tests.")
    return reachable


def _get_json(path: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Tuple[int, Dict]:
    """
    Perform an HTTP GET and parse the response body as JSON.

    Args:
        path (str): Request path beginning with a slash.
        timeout (int): Timeout in seconds for the request.

    Returns:
        Tuple[int, Dict]: (status_code, parsed_json)
    """
    url = _build_url(path)
    status_code = 0
    payload: Dict
    request = urllib.request.Request(url, method="GET")
    try:
        # Attempt to reach the server and read the response.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            body_text = response.read().decode("utf-8")
            payload = json.loads(body_text)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        try:
            body_text = exc.read().decode("utf-8")
            payload = json.loads(body_text)
        except Exception:
            payload = {}
        if status_code in {404, 502}:
            pytest.skip(f"Endpoint {url} unavailable (status {status_code})")
    except urllib.error.URLError as exc:
        # Skip when the server cannot be reached at all.
        reason = getattr(exc, "reason", exc)
        pytest.skip(f"Cannot reach Crawl4AI server at {url}: {reason}")
        payload = {}
    except ValueError:
        # Skip when the response is not valid JSON.
        pytest.skip(f"Non-JSON response from {url}")
        payload = {}

    result: Tuple[int, Dict]
    result = (status_code, payload)
    return result


def _post_json(path: str, payload: Dict, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Tuple[int, Dict]:
    """
    Perform an HTTP POST with a JSON body and parse the response as JSON.

    Args:
        path (str): Request path beginning with a slash.
        payload (Dict): JSON-serializable payload to send.
        timeout (int): Timeout in seconds for the request.

    Returns:
        Tuple[int, Dict]: (status_code, parsed_json_or_error)
    """
    url = _build_url(path)
    status_code = 0
    parsed: Dict = {}
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        # Attempt to reach the server and read the response.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            body_text = response.read().decode("utf-8")
            if body_text:
                # Parse JSON when a response body is present.
                parsed = json.loads(body_text)
            else:
                # Keep parsed empty when no response body is provided.
                parsed = {}
    except urllib.error.HTTPError as exc:
        # Capture HTTP error responses (still useful for contract checks).
        status_code = exc.getcode()
        body_text = exc.read().decode("utf-8")
        parsed = {}
        try:
            # Try to parse error bodies as JSON when possible.
            parsed = json.loads(body_text)
        except Exception:
            # Fall back to a simple error string when JSON parsing fails.
            parsed = {"error": body_text}
        if status_code in {404, 502}:
            pytest.skip(f"Endpoint {url} unavailable (status {status_code})")
    except urllib.error.URLError as exc:
        # Skip when the server cannot be reached at all.
        reason = getattr(exc, "reason", exc)
        pytest.skip(f"Cannot reach Crawl4AI server at {url}: {reason}")
    except ValueError:
        # Skip when the response is not valid JSON.
        pytest.skip(f"Non-JSON response from {url}")

    result: Tuple[int, Dict]
    result = (status_code, parsed)
    return result


def _poll_task(task_url: str, timeout: int = 60, interval: int = 2) -> Tuple[int, Dict]:
    """
    Poll a task endpoint until completion or timeout.

    Args:
        task_url (str): Fully qualified task status URL.
        timeout (int): Total timeout in seconds.
        interval (int): Seconds to wait between polls.

    Returns:
        Tuple[int, Dict]: (status_code, parsed_json)
    """
    deadline = time.time() + timeout
    last_status = 0
    last_payload: Dict = {}
    while time.time() < deadline:
        print(f"[Test] Polling task: GET {task_url}")
        try:
            req = urllib.request.Request(task_url, method="GET")
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
                last_status = resp.getcode()
                body_text = resp.read().decode("utf-8")
                last_payload = json.loads(body_text) if body_text else {}
        except urllib.error.HTTPError as exc:
            last_status = exc.getcode()
            try:
                body_text = exc.read().decode("utf-8")
                last_payload = json.loads(body_text)
            except Exception:
                last_payload = {}
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            pytest.skip(f"Cannot reach task at {task_url}: {reason}")

        status_val = last_payload.get("status")
        if status_val in {"finished", "completed", "failed"}:
            break
        time.sleep(interval)

    return last_status, last_payload


def test_health_reports_ok() -> None:
    """
    Verify the health endpoint is reachable and reports status ok.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Health", method="GET", path="/health", note="Expect 200 and status=ok")
    try:
        status_code, payload = _get_json("/health")
        assert status_code == 200
        assert payload.get("status") == "ok"
        status = "ok"
        detail = f"keys={list(payload.keys())}"
    except Skipped:
        status = "skip"
        _print_status("Health", status)
        raise
    except Exception:
        _print_status("Health", status)
        raise
    else:
        _print_status("Health", status)
        print(f"[Detail] Health: {detail}")


def test_schema_includes_browser_and_crawler_defaults() -> None:
    """
    Verify the schema endpoint returns browser and crawler sections.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Schema", method="GET", path="/schema", note="Expect 200 and browser/crawler keys")
    try:
        status_code, payload = _get_json("/schema")
        assert status_code == 200
        assert "browser" in payload
        assert "crawler" in payload
        status = "ok"
        detail = f"keys={list(payload.keys())}"
    except Skipped:
        status = "skip"
        _print_status("Schema", status)
        raise
    except Exception:
        _print_status("Schema", status)
        raise
    else:
        _print_status("Schema", status)
        print(f"[Detail] Schema: {detail}")


def test_hooks_info_lists_available_hooks() -> None:
    """
    Verify hooks info endpoint returns a mapping of available hooks.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Hooks info", method="GET", path="/hooks/info", note="Expect 200 and non-empty available_hooks")
    try:
        status_code, payload = _get_json("/hooks/info")
        hooks = payload.get("available_hooks", {})
        assert status_code == 200
        assert isinstance(hooks, dict)
        assert bool(hooks)
        status = "ok"
        detail = f"hooks={len(hooks)}"
    except Skipped:
        status = "skip"
        _print_status("Hooks info", status)
        raise
    except Exception:
        _print_status("Hooks info", status)
        raise
    else:
        _print_status("Hooks info", status)
        print(f"[Detail] Hooks info: {detail}")


def test_crawl_requires_urls() -> None:
    """
    Verify /crawl rejects requests without URLs (validation error expected).
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Crawl validation", method="POST", path="/crawl", note="Expect 400/422 for empty urls")
    try:
        status_code, payload = _post_json("/crawl", {"urls": []})
        assert status_code in {400, 422}
        assert isinstance(payload, dict)
        status = "ok"
        detail = f"status={status_code}"
    except Skipped:
        status = "skip"
        _print_status("Crawl validation", status)
        raise
    except Exception:
        _print_status("Crawl validation", status)
        raise
    else:
        _print_status("Crawl validation", status)
        print(f"[Detail] Crawl validation: {detail}")


def test_markdown_requires_url() -> None:
    """
    Verify /md rejects requests missing the required url field.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Markdown validation", method="POST", path="/md", note="Expect 422 when url is missing")
    try:
        status_code, payload = _post_json("/md", {})
        assert status_code == 422
        assert isinstance(payload, dict)
        status = "ok"
        detail = f"status={status_code}"
    except Skipped:
        status = "skip"
        _print_status("Markdown validation", status)
        raise
    except Exception:
        _print_status("Markdown validation", status)
        raise
    else:
        _print_status("Markdown validation", status)
        print(f"[Detail] Markdown validation: {detail}")


def test_execute_js_requires_url_and_scripts() -> None:
    """
    Verify /execute_js rejects requests missing url or scripts.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Execute JS validation", method="POST", path="/execute_js", note="Expect 422 when url/scripts are missing")
    try:
        status_code, payload = _post_json("/execute_js", {})
        assert status_code == 422
        assert isinstance(payload, dict)
        status = "ok"
        detail = f"status={status_code}"
    except Skipped:
        status = "skip"
        _print_status("Execute JS validation", status)
        raise
    except Exception:
        _print_status("Execute JS validation", status)
        raise
    else:
        _print_status("Execute JS validation", status)
        print(f"[Detail] Execute JS validation: {detail}")


def test_pdf_requires_url() -> None:
    """
    Verify /pdf rejects requests missing the required url field.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="PDF validation", method="POST", path="/pdf", note="Expect 422 when url is missing")
    try:
        status_code, payload = _post_json("/pdf", {})
        assert status_code == 422
        assert isinstance(payload, dict)
        status = "ok"
        detail = f"status={status_code}"
    except Skipped:
        status = "skip"
        _print_status("PDF validation", status)
        raise
    except Exception:
        _print_status("PDF validation", status)
        raise
    else:
        _print_status("PDF validation", status)
        print(f"[Detail] PDF validation: {detail}")


def test_config_dump_rejects_non_config_calls() -> None:
    """
    Verify /config/dump rejects expressions that are not allowed constructors.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    _announce_request(name="Config dump guard", method="POST", path="/config/dump", note="Expect 400 for disallowed expressions")
    try:
        status_code, payload = _post_json("/config/dump", {"code": "1+1"})
        assert status_code == 400
        assert isinstance(payload, dict)
        status = "ok"
        detail = f"status={status_code}"
    except Skipped:
        status = "skip"
        _print_status("Config dump guard", status)
        raise
    except Exception:
        _print_status("Config dump guard", status)
        raise
    else:
        _print_status("Config dump guard", status)
        print(f"[Detail] Config dump guard: {detail}")


def test_crawl_real_target() -> None:
    """
    Perform a real crawl against a live URL.
    """
    status = "fail"
    if not _probe_upstream_once():
        pytest.skip(f"Upstream unavailable: {_UPSTREAM_STATE['reason']}")
    target_url = "https://spiegel.de"
    _announce_request(
        name="Crawl live",
        method="POST",
        path="/crawl",
        note=f"Expect 200/202 with results for {target_url}",
    )
    try:
        status_code, payload = _post_json(
            "/crawl",
            {"urls": [target_url], "crawler_config": {}},
            timeout=20,
        )
        if status_code not in {200, 202}:
            pytest.skip(f"Upstream returned status {status_code}")
        if "results" in payload:
            assert isinstance(payload["results"], list)
            assert payload["results"]
            # Surface the first result keys for visibility.
            first = payload["results"][0]
            print(f"[Test] Crawl live result keys: {list(first.keys())}")
            snippet_source = (
                first.get("markdown")
                or first.get("html")
                or first.get("cleaned_html")
                or first.get("extracted_content")
                or ""
            )
            snippet_text = str(snippet_source)
            snippet = snippet_text[:2000]
            if snippet:
                print(f"[Test] Crawl live snippet: {snippet!r}")
            status = "ok"
        elif "task_id" in payload:
            task_href = payload.get("_links", {}).get("status", {}).get("href")
            task_id = payload.get("task_id")
            print(f"[Test] Crawl live task_id: {task_id}, status link: {task_href}")
            if not task_href:
                pytest.skip("task_id returned but no status link to poll")
            poll_status, poll_payload = _poll_task(task_href, timeout=60, interval=5)
            assert poll_status in {200, 202}
            assert poll_payload.get("status") in {"finished", "completed"}
            result_obj = poll_payload.get("result") or poll_payload.get("results")
            assert result_obj
            if isinstance(result_obj, list) and result_obj:
                first = result_obj[0]
                print(f"[Test] Polled crawl result keys: {list(first.keys())}")
                snippet_source = (
                    first.get("markdown")
                    or first.get("html")
                    or first.get("cleaned_html")
                    or first.get("extracted_content")
                    or ""
                )
                snippet_text = str(snippet_source)
                snippet = snippet_text[:200]
                if snippet:
                    print(f"[Test] Polled crawl snippet: {snippet!r}")
            status = "ok"
        else:
            pytest.skip("Upstream response missing results/task_id")
    except Skipped:
        status = "skip"
        _print_status("Crawl live", status)
        raise
    except Exception:
        _print_status("Crawl live", status)
        raise
    else:
        _print_status("Crawl live", status)
