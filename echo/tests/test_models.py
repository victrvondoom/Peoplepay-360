import pytest

from echo.models import normalize_source_url


def test_source_url_normalization_removes_tracking_and_fragment():
    assert normalize_source_url(
        "HTTPS://Example.COM:443/report/?utm_source=mail&b=2&a=1#summary"
    ) == "https://example.com/report?a=1&b=2"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "example.com/page", "file:///etc/passwd"])
def test_source_url_normalization_rejects_non_http_or_relative_urls(url):
    with pytest.raises(ValueError):
        normalize_source_url(url)
