"""Tests for the htmlPrintedReceipt parser."""
from receipt_parser import parse_html_receipt


def test_parses_every_line_once(html_receipt):
    """Each product appears once - "qty * price" lines must not create duplicates."""
    items = parse_html_receipt(html_receipt)
    assert [item["name"] for item in items] == [
        "Bułka kajzerka",
        "Kawa ziarnista",
        "Melon luz",
        "Kawa ziarnista",
    ]


def test_does_not_duplicate_goods_sold_by_weight(html_receipt):
    """
    A weighed line reads "1,486kg x 12.99" rather than "1 * 12.99".
    When unrecognised it used to end up in the result as a separate product.
    """
    items = parse_html_receipt(html_receipt)
    melons = [item for item in items if item["name"] == "Melon luz"]
    assert len(melons) == 1
    assert melons[0]["quantity"] == "1.486"
    assert melons[0]["originalAmount"] == "19,3"


def test_extracts_discounts(html_receipt):
    items = parse_html_receipt(html_receipt)
    assert items[0]["discounts"] == [
        {
            "description": "Lidl Plus kupon",
            "amount": "0,44",
            "promotionId": "PROMO-1",
        }
    ]


def test_discount_is_attached_to_the_right_line(html_receipt):
    """
    The same coffee is bought twice but discounted only on the first line.
    The discount must not leak onto the second one, nor onto the product
    that sits between them.
    """
    items = parse_html_receipt(html_receipt)
    first_coffee, melon, second_coffee = items[1], items[2], items[3]

    assert first_coffee["discounts"][0]["amount"] == "53,99"
    assert second_coffee["discounts"] == []
    assert melon["discounts"] == []


def test_product_without_discount_has_empty_list(html_receipt):
    items = parse_html_receipt(html_receipt)
    assert items[3]["discounts"] == []


def test_empty_html_does_not_raise():
    assert parse_html_receipt("") == []
    assert parse_html_receipt("<html><body></body></html>") == []
