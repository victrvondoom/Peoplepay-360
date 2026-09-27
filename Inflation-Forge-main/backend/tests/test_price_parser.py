import asyncio

import httpx

from backend.services.inflation.collector import CityPriceCollector, parse_price_rows


def test_parser_reads_current_city_price_rows():
    html = """
    <table>
      <tr><td>Milk (Regular, 1 Liter)</td><td class="priceValue"><span class="first_currency">$1.77</span></td></tr>
      <tr><td>Eggs (12, Large Size)</td><td class="priceValue"><span class="first_currency">$5.37</span></td></tr>
    </table>
    """
    rows = parse_price_rows(html)

    assert [(row.label, row.price_usd) for row in rows] == [
        ("Milk (Regular, 1 Liter)", 1.77),
        ("Eggs (12, Large Size)", 5.37),
    ]


def test_parser_reads_archived_currency_layout():
    html = """
    <tr><td>Apartment (1 bedroom) in City Centre</td>
    <td class="priceValue"><span class="first_currency">3,790.68&nbsp;$</span></td></tr>
    """
    rows = parse_price_rows(html)

    assert rows[0].price_usd == 3790.68


def test_parser_ignores_non_price_table_content():
    assert parse_price_rows("<tr><td>Contributors</td><td>127</td></tr>") == []


def test_parser_accepts_live_reader_markdown():
    markdown = """
| Markets | Edit | Range |
| --- | --- | --- |
| Milk (Regular, 1 Liter) | $1.12 | 0.84-1.32 |
| Fresh White Bread (1 lb Loaf) | $4.75 | 3.00-8.00 |
| Apartment (1 bedroom) in City Centre | $2,145.50 | 1,900-3,000 |
"""

    rows = parse_price_rows(markdown)

    assert [(row.label, row.price_usd) for row in rows] == [
        ("Milk (Regular, 1 Liter)", 1.12),
        ("Fresh White Bread (1 lb Loaf)", 4.75),
        ("Apartment (1 bedroom) in City Centre", 2145.5),
    ]


def test_current_fetch_uses_reader_when_publisher_returns_503():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "www.numbeo.com":
            return httpx.Response(503, request=request)
        return httpx.Response(200, text="| Milk (Regular, 1 Liter) | $1.12 |", request=request)

    async def fetch() -> str:
        collector = CityPriceCollector(timeout_s=2)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await collector._get_current(
                client,
                "https://www.numbeo.com/cost-of-living/in/Austin?displayCurrency=USD",
                "austin",
            )
        assert collector.reader_fallback_ok
        return response.text

    assert "$1.12" in asyncio.run(fetch())
    assert requested[1].startswith("https://r.jina.ai/http://www.numbeo.com/")
