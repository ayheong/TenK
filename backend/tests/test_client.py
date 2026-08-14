import httpx
import pytest
import respx

from app.edgar.client import Client, TokenBucket

URL = "https://example.com/data.json"


def test_token_bucket_waits_when_tokens_exhausted() -> None:
    current_time = [0.0]
    sleeps = []

    def time_func() -> float:
        return current_time[0]

    def sleep_func(seconds: float) -> None:
        sleeps.append(seconds)
        current_time[0] += seconds

    bucket = TokenBucket(
        rate=10.0, capacity=1, time_func=time_func, sleep_func=sleep_func
    )

    bucket.acquire()  # consumes the initial token, no wait
    bucket.acquire()  # bucket empty, waits for a token to refill

    assert sleeps == [pytest.approx(0.1)]


def test_token_bucket_does_not_wait_within_capacity() -> None:
    sleeps = []
    bucket = TokenBucket(
        rate=10.0,
        capacity=3,
        time_func=lambda: 0.0,
        sleep_func=lambda s: sleeps.append(s),
    )

    for _ in range(3):
        bucket.acquire()

    assert sleeps == []


@respx.mock
def test_get_json_retries_on_429_then_succeeds() -> None:
    respx.get(URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    sleeps = []
    client = Client(
        rate_limiter=TokenBucket(rate=10.0, sleep_func=lambda s: None),
        sleep_func=lambda s: sleeps.append(s),
    )

    assert client.get_json(URL) == {"ok": True}
    assert sleeps == [1.0]


@respx.mock
def test_get_json_backs_off_exponentially() -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps = []
    client = Client(
        rate_limiter=TokenBucket(rate=10.0, sleep_func=lambda s: None),
        sleep_func=lambda s: sleeps.append(s),
    )

    assert client.get_json(URL) == {"ok": True}
    assert sleeps == [1.0, 2.0]


@respx.mock
def test_get_json_raises_after_max_retries() -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))
    client = Client(
        rate_limiter=TokenBucket(rate=10.0, sleep_func=lambda s: None),
        max_retries=2,
        sleep_func=lambda s: None,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.get_json(URL)


@respx.mock
def test_get_json_raises_immediately_for_non_retryable_status() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    client = Client(rate_limiter=TokenBucket(rate=10.0, sleep_func=lambda s: None))

    with pytest.raises(httpx.HTTPStatusError):
        client.get_json(URL)

    assert route.call_count == 1


@respx.mock
def test_get_text_returns_response_body() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>filing</html>"))
    client = Client(rate_limiter=TokenBucket(rate=10.0, sleep_func=lambda s: None))

    assert client.get_text(URL) == "<html>filing</html>"
