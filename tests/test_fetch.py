import pytest

from src import config, fetch


class FakeResponse:
    def __init__(self, status_code=200, text="<html></html>", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers if headers is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_sends_browser_user_agent(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    fetch.get("https://example.test/page")

    assert captured["headers"]["User-Agent"] == config.USER_AGENT
    assert captured["timeout"] == config.REQUEST_TIMEOUT_S


def test_passes_query_params(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    fetch.get("https://example.test/", {"showDate": "2026-08-05"})
    assert captured["params"] == {"showDate": "2026-08-05"}


def test_sleeps_between_requests(monkeypatch):
    slept = []
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

    fetch.get("https://example.test/")
    assert slept == [config.REQUEST_DELAY_S]


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return FakeResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    assert fetch.get("https://example.test/") == "<html>ok</html>"
    assert calls["n"] == 3


def test_raises_after_max_retries(monkeypatch):
    def always_fails(url, params=None, headers=None, timeout=None):
        raise ConnectionError("boom")

    monkeypatch.setattr(fetch.requests, "get", always_fails)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(ConnectionError):
        fetch.get("https://example.test/")


def test_4xx_fails_fast_without_retry(monkeypatch):
    calls = {"n": 0}

    def blocked(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse(status_code=403)

    monkeypatch.setattr(fetch.requests, "get", blocked)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError):
        fetch.get("https://example.test/")
    assert calls["n"] == 1


def test_5xx_is_retried(monkeypatch):
    calls = {"n": 0}

    def failing(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse(status_code=500)

    monkeypatch.setattr(fetch.requests, "get", failing)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(fetch.requests.HTTPError):
        fetch.get("https://example.test/")
    assert calls["n"] == config.MAX_RETRIES


def test_programming_error_propagates_without_retry(monkeypatch):
    calls = {"n": 0}

    def buggy(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        raise TypeError("bug")

    monkeypatch.setattr(fetch.requests, "get", buggy)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(TypeError):
        fetch.get("https://example.test/")
    assert calls["n"] == 1


def test_no_sleep_after_final_failed_attempt(monkeypatch):
    slept = []

    def always_fails(url, params=None, headers=None, timeout=None):
        raise ConnectionError("boom")

    monkeypatch.setattr(fetch.requests, "get", always_fails)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

    with pytest.raises(ConnectionError):
        fetch.get("https://example.test/")

    assert len(slept) == config.MAX_RETRIES - 1


def test_429_then_200_returns_body(monkeypatch):
    calls = {"n": 0}

    def flaky(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=429)
        return FakeResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    assert fetch.get("https://example.test/") == "<html>ok</html>"
    assert calls["n"] == 2


def test_429_honors_retry_after_header(monkeypatch):
    slept = []
    calls = {"n": 0}

    def flaky(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=429, headers={"Retry-After": "3"})
        return FakeResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

    fetch.get("https://example.test/")
    assert slept[0] == 3


def test_429_without_retry_after_uses_cooldown_fallback(monkeypatch):
    slept = []
    calls = {"n": 0}

    def flaky(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=429)
        return FakeResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

    fetch.get("https://example.test/")
    assert slept[0] == config.RATE_LIMIT_COOLDOWN_S


def test_persistent_429_raises_after_max_429_retries(monkeypatch):
    calls = {"n": 0}

    def always_429(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse(status_code=429)

    monkeypatch.setattr(fetch.requests, "get", always_429)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(fetch.requests.HTTPError):
        fetch.get("https://example.test/")

    assert calls["n"] == config.MAX_429_RETRIES + 1


def test_429_does_not_consume_transport_retry_budget(monkeypatch):
    # Several 429s followed by a transport ConnectionError should still get
    # the full MAX_RETRIES transport attempts — the 429s must not have
    # decremented that budget.
    calls = {"n": 0}

    def sequence(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            return FakeResponse(status_code=429)
        raise ConnectionError("boom")

    monkeypatch.setattr(fetch.requests, "get", sequence)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(ConnectionError):
        fetch.get("https://example.test/")

    # 2 429s, then MAX_RETRIES transport attempts (all ConnectionError).
    assert calls["n"] == 2 + config.MAX_RETRIES
