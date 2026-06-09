import pytest

from src.local_llm.search import (
    BraveSearchClient,
    BraveSearchError,
    BRAVE_SEARCH_ENDPOINT,
    SearchResult,
)


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeHTTP:
    def __init__(self, resp: _FakeResp):
        self.resp = resp
        self.calls: list[dict] = []

    def get(self, url, params, headers):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.resp


def test_search_returns_results_and_sends_api_key():
    http = _FakeHTTP(
        _FakeResp(
            200,
            {
                "web": {
                    "results": [
                        {
                            "title": "PLTR Q2 2026",
                            "url": "https://example.com/a",
                            "description": "earnings beat",
                        },
                        {
                            "title": "NVDA China",
                            "url": "https://example.com/b",
                            "description": "export licence",
                        },
                    ]
                }
            },
        )
    )
    client = BraveSearchClient("brave-key-xyz", http_client=http)

    out = client.search("PLTR earnings", count=2)

    assert out == [
        SearchResult("PLTR Q2 2026", "https://example.com/a", "earnings beat"),
        SearchResult("NVDA China", "https://example.com/b", "export licence"),
    ]
    assert http.calls == [
        {
            "url": BRAVE_SEARCH_ENDPOINT,
            "params": {"q": "PLTR earnings", "count": 2},
            "headers": {
                "Accept": "application/json",
                "X-Subscription-Token": "brave-key-xyz",
            },
        }
    ]


def test_search_clamps_count_into_1_to_10():
    http = _FakeHTTP(_FakeResp(200, {"web": {"results": []}}))
    client = BraveSearchClient("k", http_client=http)

    client.search("q", count=99)
    assert http.calls[-1]["params"]["count"] == 10

    client.search("q", count=0)
    assert http.calls[-1]["params"]["count"] == 1


def test_search_raises_on_non_200():
    http = _FakeHTTP(_FakeResp(429, text="rate limited"))
    client = BraveSearchClient("k", http_client=http)

    with pytest.raises(BraveSearchError) as ei:
        client.search("q")
    assert "429" in str(ei.value)


def test_empty_api_key_rejected():
    with pytest.raises(BraveSearchError):
        BraveSearchClient("")


def test_search_handles_empty_web_block():
    http = _FakeHTTP(_FakeResp(200, {}))
    client = BraveSearchClient("k", http_client=http)
    assert client.search("q") == []


def test_search_wraps_transport_error_as_brave_search_error():
    class _BrokenHTTP:
        def get(self, *a, **kw):
            raise ConnectionError("network unreachable")

    client = BraveSearchClient("k", http_client=_BrokenHTTP())
    with pytest.raises(BraveSearchError) as ei:
        client.search("q")
    assert "network unreachable" in str(ei.value)


def test_search_wraps_json_parse_error_as_brave_search_error():
    class _BadJsonResp:
        status_code = 200
        text = "not json"

        def json(self):
            raise ValueError("not valid JSON")

    class _BadJsonHTTP:
        def get(self, *a, **kw):
            return _BadJsonResp()

    client = BraveSearchClient("k", http_client=_BadJsonHTTP())
    with pytest.raises(BraveSearchError) as ei:
        client.search("q")
    assert "not valid JSON" in str(ei.value)
