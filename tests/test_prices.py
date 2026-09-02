"""
Tests for price and discount calculations.

The most important one is test_total_amount_is_already_net_of_discounts:
it guards the assumption the rest of the statistics rely on.
"""
import pytest

import app
from receipt_parser import parse_html_receipt

# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [
    ("4,39", 4.39),
    ("4.39", 4.39),
    (4.39, 4.39),
    (None, 0.0),
    ("", 0.0),
    ("not a number", 0.0),
])
def test_parse_price(value, expected):
    assert app.parse_price(value) == expected


# ---------------------------------------------------------------------------
# Per-line discounts
# ---------------------------------------------------------------------------


def test_item_discount_sums_all_discounts():
    item = {"discounts": [{"amount": "1,50"}, {"amount": "0,50"}]}
    assert app.item_discount(item) == 2.0


def test_item_discount_normalizes_sign():
    """The API returns the amount as "1,50" in some places and "-1,50" in others."""
    assert app.item_discount({"discounts": [{"amount": "-1,50"}]}) == 1.5
    assert app.item_discount({"discounts": [{"amount": "1,50"}]}) == 1.5


def test_item_discount_without_discounts():
    assert app.item_discount({}) == 0.0
    assert app.item_discount({"discounts": None}) == 0.0


# ---------------------------------------------------------------------------
# Unit prices
# ---------------------------------------------------------------------------


def test_item_prices_without_discount():
    item = {"currentUnitPrice": "3,99", "quantity": "1", "originalAmount": "3,99"}
    base, promo = app.item_prices(item)
    assert base == 3.99
    assert promo == 3.99


def test_item_prices_divides_discount_by_quantity():
    """A discount is a total for the line; the promo price is per unit."""
    item = {
        "currentUnitPrice": "0,34",
        "quantity": "4",
        "originalAmount": "1,36",
        "discounts": [{"amount": "0,44"}],
    }
    base, promo = app.item_prices(item)
    assert base == 0.34
    assert promo == pytest.approx(0.23)


def test_item_prices_never_go_below_zero():
    item = {
        "currentUnitPrice": "5,00",
        "quantity": "1",
        "originalAmount": "5,00",
        "discounts": [{"amount": "9,00"}],
    }
    _base, promo = app.item_prices(item)
    assert promo == 0.0


def test_item_prices_zero_quantity_does_not_divide_by_zero():
    item = {"currentUnitPrice": "5,00", "quantity": "0", "originalAmount": "5,00"}
    base, promo = app.item_prices(item)
    assert base == 5.0
    assert promo == 5.0


def test_original_amount_for_goods_sold_by_weight():
    """
    For weighed goods unit price times quantity does not reproduce the amount,
    so originalAmount from the API wins.
    """
    item = {"currentUnitPrice": "12,99", "quantity": "1,486", "originalAmount": "19,30"}
    assert app.item_original_amount(item) == 19.30


def test_original_amount_falls_back_to_unit_price_times_quantity():
    item = {"currentUnitPrice": "2,50", "quantity": "2"}
    assert app.item_original_amount(item) == 5.0


# ---------------------------------------------------------------------------
# Receipt totals
# ---------------------------------------------------------------------------


def test_total_amount_is_already_net_of_discounts(api_receipt):
    """
    REGRESSION: totalAmount returned by the API is already NET of discounts.
    Subtracting totalDiscount a second time under-reports spending.

    Verified on a receipt where line amounts minus discounts equal totalAmount
    exactly: 1.36 + 3.99 - 0.44 = 4.91.
    """
    lines = sum(app.item_original_amount(i) for i in api_receipt["itemsLine"])
    discounts = sum(app.item_discount(i) for i in api_receipt["itemsLine"])
    api_receipt["totalAmount"] = round(lines - discounts, 2)

    assert app.receipt_total(api_receipt) == pytest.approx(lines - discounts)
    assert app.receipt_total(api_receipt) == pytest.approx(4.91)


def test_receipt_discount_read_from_total_field(api_receipt):
    assert app.receipt_discount(api_receipt) == 0.44


def test_receipt_discount_summed_from_lines_when_field_missing(api_receipt):
    """Receipts parsed from HTML carry no totalDiscount field."""
    api_receipt.pop("totalDiscount")
    assert app.receipt_discount(api_receipt) == 0.44


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def test_get_stats_sums_discounts(api_receipt):
    stats = app.get_stats([api_receipt])
    assert stats["total_receipts"] == 1
    assert stats["total_discount"] == 0.44
    assert stats["total_spent"] == pytest.approx(49.80)


def test_search_products_returns_both_prices(api_receipt):
    results = app.search_products([api_receipt], "kajzerka")
    assert len(results) == 1
    assert results[0]["base_price"] == 0.34
    assert results[0]["last_price"] == pytest.approx(0.23)


def test_product_history_returns_both_prices(api_receipt):
    history = app.get_product_history([api_receipt], "kajzerka")
    assert len(history) == 1
    assert history[0]["base_price"] == 0.34
    assert history[0]["promo_price"] == pytest.approx(0.23)


def test_top_products_spend_uses_amount_after_discount(api_receipt):
    """Spend per product is what was actually paid, not the shelf price."""
    api_receipt["itemsLine"][0]["quantity"] = "2"
    result = app.get_top_products([api_receipt])
    roll = next(p for p in result["top_by_count"] if p["name"] == "Bułka kajzerka")
    assert roll["spend"] == pytest.approx(0.92)  # 1.36 - 0.44


def test_coupon_stats(api_receipt):
    stats = app.get_coupon_stats([api_receipt])
    assert stats["total_coupons"] == 1
    assert stats["total_discount"] == 0.44
    assert stats["receipts_with_coupon"] == 1


def test_empty_dataset_does_not_raise():
    assert app.get_stats([]) == {}
    assert app.search_products([], "anything") == []
    assert app.get_product_history([], "anything") == []


# ---------------------------------------------------------------------------
# Consistency: HTML and API receipts are computed the same way
# ---------------------------------------------------------------------------


def test_html_receipt_is_computed_like_an_api_one(html_receipt):
    """Lines parsed from HTML go through exactly the same functions as API lines."""
    items = parse_html_receipt(html_receipt)
    receipt = {"id": "X", "date": "2026-07-31T10:00:00", "itemsLine": items}

    assert app.receipt_discount(receipt) == pytest.approx(54.43)  # 0.44 + 53.99

    _base, promo = app.item_prices(items[1])
    assert promo == pytest.approx(36.00)  # 89.99 - 53.99
