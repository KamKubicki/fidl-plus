"""
Shared test fixtures.

All data here is synthetic. It mirrors the shape of real Lidl Plus receipts
without containing any actual purchases.
"""
import os
import tempfile

import pytest

# Importing app.py creates DATA_DIR, so point it at a throwaway directory:
# tests must never touch or overwrite real data.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="fidl-tests-"))


@pytest.fixture
def html_receipt():
    """
    A receipt in the htmlPrintedReceipt format.

    Covers the four cases the parser has historically got wrong:
    - a product with a Lidl Plus discount,
    - a product without any discount,
    - goods sold by weight ("1,486kg x 12.99" instead of "1 * 12.99"),
    - the same product bought twice, discounted on only one of the lines.
    """
    return """
    <html><body><pre>
<span id="purchase_list_line_1" class="currency" data-currency="zł">2026-07-31</span>
<span id="purchase_list_line_2"></span>
<span id="purchase_list_line_3" class="article" data-art-id="5522370"
      data-art-quantity="4" data-unit-price="0,34" data-tax-type="C"
      data-art-description="Bułka kajzerka">Bułka kajzerka                </span>
<span id="purchase_list_line_4" class="article" data-art-id="5522370"
      data-art-quantity="4" data-unit-price="0,34" data-tax-type="C"
      data-art-description="Bułka kajzerka">                       4 * 0.34 1.36 C</span>
<span id="purchase_list_line_5" class="discount"
      data-promotion-id="PROMO-1">   Lidl Plus kupon             -0,44</span>
<span id="purchase_list_line_6" class="article" data-art-id="0007533"
      data-unit-price="89,99" data-tax-type="A"
      data-art-description="Kawa ziarnista">Kawa ziarnista                </span>
<span id="purchase_list_line_7" class="article" data-art-id="0007533"
      data-unit-price="89,99" data-tax-type="A"
      data-art-description="Kawa ziarnista">                     1 * 89.99 89.99 A</span>
<span id="purchase_list_line_8" class="discount"
      data-promotion-id="PROMO-2">   Lidl Plus kupon            -53,99</span>
<span id="purchase_list_line_9" class="article" data-art-id="0080557"
      data-art-quantity="1,486" data-unit-price="12,99" data-tax-type="C"
      data-art-description="Melon luz">Melon luz                     </span>
<span id="purchase_list_line_10" class="article" data-art-id="0080557"
      data-art-quantity="1,486" data-unit-price="12,99" data-tax-type="C"
      data-art-description="Melon luz">                1,486kg x 12.99 19.3 C</span>
<span id="purchase_list_line_11" class="article" data-art-id="0007533"
      data-unit-price="89,99" data-tax-type="A"
      data-art-description="Kawa ziarnista">Kawa ziarnista                </span>
<span id="purchase_list_line_12" class="article" data-art-id="0007533"
      data-unit-price="89,99" data-tax-type="A"
      data-art-description="Kawa ziarnista">                     1 * 89.99 89.99 A</span>
    </pre></body></html>
    """


@pytest.fixture
def api_receipt():
    """A receipt in the newer API format, with itemsLine already provided."""
    return {
        "id": "TEST-API-1",
        "date": "2026-07-31T18:12:00",
        "store": {"name": "Lidl Testowa 1"},
        "totalAmount": 49.80,
        "totalDiscount": 0.44,
        "couponsUsed": [{"couponTitle": "Kupon testowy"}],
        "itemsLine": [
            {
                "name": "Bułka kajzerka",
                "currentUnitPrice": "0,34",
                "quantity": "4",
                "originalAmount": "1,36",
                "taxGroupName": "C",
                "codeInput": "12345678",
                "discounts": [{"description": "Lidl Plus kupon", "amount": "0,44"}],
            },
            {
                "name": "Mleko",
                "currentUnitPrice": "3,99",
                "quantity": "1",
                "originalAmount": "3,99",
                "taxGroupName": "C",
                "codeInput": "87654321",
                "discounts": [],
            },
        ],
    }
