import pytest

from app.errors import ParseError
from app.services.parser import WebsiteParser
from tests.conftest import load_fixture

BASE = "https://books.toscrape.com"
parser = WebsiteParser()


def test_parse_listing_fields_and_normalization():
    page = parser.parse_listing(load_fixture("listing.html"), f"{BASE}/index.html")
    assert [b.id for b in page.books] == [
        "a-light-in-the-attic_1000", "second-sample-title_999", "third-sample-title_998",
    ]
    first = page.books[0]
    assert first.title == "A Light in the Attic"  # full title from the `title` attr, not truncated text
    assert first.price == 51.77 and first.currency == "GBP"
    assert first.rating == 3 and first.in_stock is True
    assert first.url == f"{BASE}/catalogue/a-light-in-the-attic_1000/index.html"
    assert first.image_url == f"{BASE}/media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg"
    assert page.total_results == 3 and page.has_next is False


def test_parse_listing_tolerates_missing_optional_fields():
    second, third = parser.parse_listing(load_fixture("listing.html"), f"{BASE}/index.html").books[1:]
    assert second.title == "Second Sample Title"  # whitespace collapsed
    assert second.rating is None and second.image_url is None
    assert third.rating == 5 and third.in_stock is False
    assert third.price == 53.74 and third.currency == "GBP"  # survives 'Â£' mojibake


def test_parse_listing_categories():
    page = parser.parse_listing(load_fixture("listing.html"), f"{BASE}/index.html")
    assert [(c.id, c.name) for c in page.category_links] == [("travel_2", "Travel"), ("poetry_23", "Poetry")]


def test_empty_listing_is_valid_but_empty():
    page = parser.parse_listing(load_fixture("empty_listing.html"), f"{BASE}/index.html")
    assert page.books == [] and page.total_results == 0


def test_malformed_listing_raises():
    with pytest.raises(ParseError):
        parser.parse_listing(load_fixture("malformed.html"), f"{BASE}/index.html")


def test_parse_item_full():
    url = f"{BASE}/catalogue/a-light-in-the-attic_1000/index.html"
    item = parser.parse_item(load_fixture("item.html"), url)
    assert item.id == "a-light-in-the-attic_1000"
    assert item.title == "A Light in the Attic"
    assert item.category == "Poetry"
    assert item.price == 51.77 and item.price_excl_tax == 51.77 and item.tax == 0.0
    assert item.upc == "a897fe39b1053632"
    assert item.stock_count == 22 and item.in_stock is True
    assert item.number_of_reviews == 0 and item.rating == 3
    assert item.description == "A sample description written for this test fixture. It spans multiple lines."
    assert item.image_url == f"{BASE}/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg"


def test_parse_item_missing_fields_does_not_crash():
    item = parser.parse_item(load_fixture("item_minimal.html"), f"{BASE}/catalogue/bare-bones_5/index.html")
    assert item.title == "Bare Bones" and item.category == "Mystery"
    assert item.description is None and item.price is None and item.upc is None
    assert item.image_url is None and item.stock_count is None


def test_malformed_item_raises():
    with pytest.raises(ParseError):
        parser.parse_item(load_fixture("malformed.html"), f"{BASE}/catalogue/x_1/index.html")
