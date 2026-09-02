"""
Narzędzia do przetwarzania paragonów Lidl Plus:
- parse_html_receipt()   - parsuje htmlPrintedReceipt → itemsLine
- build_barcode_index()  - buduje słownik barcode → kanonicznna nazwa
- normalize_receipts()   - ujednolica nazwy produktów w całym zbiorze
"""
from __future__ import annotations

import re
from collections import defaultdict


def _price_to_float(val: str) -> float:
    """'3,55' lub '3.55' → 3.55"""
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


# id="purchase_list_line_N"
_LINE_ID_RE = re.compile(r"^purchase_list_line_\d+$")

# Druga linia produktu, np. "        4 * 0.34 1.36 C" albo "   1,486kg x 12.99 19.3 C"
_AMOUNT_LINE_RE = re.compile(r"^\s*[\d.,]+\s*(?:kg|g|szt\.?)?\s*[*x]\s*[\d.,]+", re.IGNORECASE)

# Kwota rabatu na końcu linii, np. "   Lidl Plus kupon   -0,44"
_DISCOUNT_AMOUNT_RE = re.compile(r"-\s*([\d]+[.,][\d]{2})\s*$")


def _parse_discount_span(span) -> dict | None:
    """Zamienia <span class="discount"> na wpis zgodny z formatem API."""
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
    Parsuje htmlPrintedReceipt i zwraca listę produktów
    w tym samym formacie co itemsLine z API v3.

    Każdy span.article ma atrybuty:
        data-art-id          - wewnętrzny ID produktu (nie barcode EAN)
        data-art-description - nazwa
        data-unit-price      - cena jednostkowa "3,55"
        data-art-quantity    - ilość (opcjonalnie, domyślnie 1)
        data-tax-type        - A/B/C/D

    Produkt zajmuje dwie kolejne linie span.article (nazwa + "ilość * cena"),
    po których mogą wystąpić linie span.discount z rabatami Lidl Plus:

        <span class="article" ...>Bułka kajzerka 2</span>
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
            # Rabat dotyczy ostatnio sparsowanego produktu
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

        # Druga linia produktu ("4 * 0.34 1.36 C") to duplikat - pomijamy.
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
    Buduje słownik: barcode → najczęściej używana nazwa produktu.
    Pomija puste barcody i wewnętrzne ID z HTML paragonów (krótkie cyfry).
    """
    barcode_names: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for receipt in receipts:
        for item in receipt.get("itemsLine", []):
            barcode = item.get("codeInput", "").strip()
            name    = item.get("name", "").strip()

            if not barcode or not name:
                continue
            # Pomijaj wewnętrzne ID Lidla (< 8 cyfr, bo EAN ma 8 lub 13)
            if re.match(r"^\d{1,7}$", barcode):
                continue

            barcode_names[barcode][name] += 1

    # Dla każdego barcode wybierz najczęstszą nazwę
    index = {}
    for barcode, name_counts in barcode_names.items():
        best_name = max(name_counts, key=name_counts.get)
        index[barcode] = best_name

    return index


def normalize_receipts(receipts: list[dict], barcode_index: dict[str, str]) -> list[dict]:
    """
    Zwraca kopię paragonów z ujednoliconymi nazwami produktów
    według barcode_index. Oryginalna nazwa zachowana w _original_name.
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
    Główna funkcja - parsuje HTML paragony i normalizuje nazwy.
    Zwraca wzbogacony zbiór paragonów gotowy do wyświetlenia.
    """
    enriched = []
    for receipt in receipts:
        r = dict(receipt)
        # Jeśli brak itemsLine ale jest htmlPrintedReceipt - sparsuj
        if not r.get("itemsLine") and r.get("htmlPrintedReceipt"):
            parsed = parse_html_receipt(r["htmlPrintedReceipt"])
            if parsed:
                r["itemsLine"] = parsed
        enriched.append(r)

    # Buduj index na już wzbogaconym zbiorze
    barcode_index = build_barcode_index(enriched)

    # Normalizuj nazwy
    enriched = normalize_receipts(enriched, barcode_index)

    return enriched, barcode_index
