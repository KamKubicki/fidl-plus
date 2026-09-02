"""
Utilities for processing Lidl Plus receipts:
- parse_html_receipt()   - parses htmlPrintedReceipt into itemsLine
- build_barcode_index()  - maps barcode -> canonical product name
- normalize_receipts()   - unifies product names across the whole dataset
"""
from __future__ import annotations

import re
from collections import defaultdict


def _price_to_float(val: str) -> float:
    """Parse a price string: '3,55' or '3.55' -> 3.55"""
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


# id="purchase_list_line_N"
_LINE_ID_RE = re.compile(r"^purchase_list_line_\d+$")

# Second line of a product, e.g. "        4 * 0.34 1.36 C" or "   1,486kg x 12.99 19.3 C"
_AMOUNT_LINE_RE = re.compile(r"^\s*[\d.,]+\s*(?:kg|g|szt\.?)?\s*[*x]\s*[\d.,]+", re.IGNORECASE)

# Discount amount at the end of a line, e.g. "   Lidl Plus kupon   -0,44"
_DISCOUNT_AMOUNT_RE = re.compile(r"-\s*([\d]+[.,][\d]{2})\s*$")


def _parse_discount_span(span) -> dict | None:
    """Convert a <span class="discount"> line into an API-shaped discount entry."""
    text = " ".join(span.get_text().split())
    match = _DISCOUNT_AMOUNT_RE.search(text)
    if not match:
        return None

    amount = _price_to_float(match.group(1))
    if amount <= 0:
        return None

    description = text[:match.start()].strip() or "Lidl Plus"
    return {
        "description": description,
        "amount": str(amount).replace(".", ","),
        "promotionId": span.get("data-promotion-id", ""),
    }


def parse_html_receipt(html: str) -> list[dict]:
    """
    Parse htmlPrintedReceipt and return products in the same shape as
    itemsLine from API v3.

    Every span.article carries the attributes:
        data-art-id          - internal product id (not an EAN barcode)
        data-art-description - name
        data-unit-price      - unit price, "3,55"
        data-art-quantity    - quantity (optional, defaults to 1)
        data-tax-type        - A/B/C/D

    A product spans two consecutive span.article lines (name + "qty * price"),
    optionally followed by span.discount lines with Lidl Plus discounts:

        <span class="article" ...>Bulka kajzerka 2</span>
        <span class="article" ...>        4 * 0.34 1.36 C</span>
        <span class="discount" ...>   Lidl Plus kupon        -0,44</span>
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")

    items = []
    current = None

    for span in soup.find_all("span", id=_LINE_ID_RE):
        classes = span.get("class", [])

        if "discount" in classes:
            # A discount always belongs to the most recently parsed product
            if current is None:
                continue
            discount = _parse_discount_span(span)
            if discount:
                current["discounts"].append(discount)
            continue

        if "article" not in classes:
            continue

        desc = span.get("data-art-description")
        if not desc:
            continue

        # The second product line ("4 * 0.34 1.36 C") is a duplicate - skip it.
        if _AMOUNT_LINE_RE.match(span.get_text()):
            continue

        unit_price = _price_to_float(span.get("data-unit-price", "0"))
        quantity   = _price_to_float(span.get("data-art-quantity", "1")) or 1.0

        current = {
            "name":              desc.strip(),
            "currentUnitPrice":  str(unit_price).replace(".", ","),
            "quantity":          str(int(quantity) if quantity == int(quantity) else quantity),
            "isWeight":          False,
            "originalAmount":    str(round(unit_price * quantity, 2)).replace(".", ","),
            "taxGroupName":      span.get("data-tax-type", ""),
            "codeInput":         span.get("data-art-id", ""),
            "discounts":         [],
            "deposit":           None,
            "giftSerialNumber":  None,
            "_parsed_from_html": True,
        }
        items.append(current)

    return items


def build_barcode_index(receipts: list[dict]) -> dict[str, str]:
    """
    Build a mapping: barcode -> most frequently used product name.

    Skips empty barcodes and Lidl's internal ids from HTML receipts,
    which are short numeric strings rather than real EANs.
    """
    barcode_names: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for receipt in receipts:
        for item in receipt.get("itemsLine", []):
            barcode = item.get("codeInput", "").strip()
            name    = item.get("name", "").strip()

            if not barcode or not name:
                continue
            # Skip Lidl internal ids (< 8 digits; an EAN has 8 or 13)
            if re.match(r"^\d{1,7}$", barcode):
                continue

            barcode_names[barcode][name] += 1

    # For each barcode pick the most common name
    index = {}
    for barcode, name_counts in barcode_names.items():
        best_name = max(name_counts, key=name_counts.get)
        index[barcode] = best_name

    return index


def normalize_receipts(receipts: list[dict], barcode_index: dict[str, str]) -> list[dict]:
    """
    Return a copy of the receipts with product names unified according to
    barcode_index. The original name is preserved in _original_name.
    """
    normalized = []
    for receipt in receipts:
        items = receipt.get("itemsLine", [])
        new_items = []
        for item in items:
            barcode = item.get("codeInput", "").strip()
            canonical = barcode_index.get(barcode)
            if canonical and canonical != item.get("name"):
                item = dict(item)
                item["_original_name"] = item["name"]
                item["name"] = canonical
            new_items.append(item)
        if new_items is not items:
            receipt = dict(receipt)
            receipt["itemsLine"] = new_items
        normalized.append(receipt)
    return normalized


def enrich_receipts(receipts: list[dict]) -> list[dict]:
    """
    Entry point - parse HTML receipts and normalize product names.

    Returns the enriched receipts ready for display, together with the
    barcode index used for normalization.
    """
    enriched = []
    for receipt in receipts:
        r = dict(receipt)
        # No itemsLine but an HTML printout is available - parse it
        if not r.get("itemsLine") and r.get("htmlPrintedReceipt"):
            parsed = parse_html_receipt(r["htmlPrintedReceipt"])
            if parsed:
                r["itemsLine"] = parsed
        enriched.append(r)

    # Build the index on the already enriched dataset
    barcode_index = build_barcode_index(enriched)

    # Unify product names
    enriched = normalize_receipts(enriched, barcode_index)

    return enriched, barcode_index
