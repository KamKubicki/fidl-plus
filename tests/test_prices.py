"""
Testy obliczeń cen i rabatów.

Najważniejszy jest test_total_amount_jest_juz_po_rabacie - pilnuje założenia,
na którym stoi cała reszta statystyk.
"""
import pytest

import app
from receipt_parser import parse_html_receipt

# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("4,39", 4.39),
    ("4.39", 4.39),
    (4.39, 4.39),
    (None, 0.0),
    ("", 0.0),
    ("nie liczba", 0.0),
])
def test_parse_price(wejscie, oczekiwane):
    assert app.parse_price(wejscie) == oczekiwane


# ---------------------------------------------------------------------------
# Rabaty na pozycji
# ---------------------------------------------------------------------------

def test_item_discount_sumuje_rabaty():
    item = {"discounts": [{"amount": "1,50"}, {"amount": "0,50"}]}
    assert app.item_discount(item) == 2.0


def test_item_discount_normalizuje_znak():
    """API zwraca kwotę raz jako '1,50', raz jako '-1,50'."""
    assert app.item_discount({"discounts": [{"amount": "-1,50"}]}) == 1.5
    assert app.item_discount({"discounts": [{"amount": "1,50"}]}) == 1.5


def test_item_discount_bez_rabatow():
    assert app.item_discount({}) == 0.0
    assert app.item_discount({"discounts": None}) == 0.0


# ---------------------------------------------------------------------------
# Ceny jednostkowe
# ---------------------------------------------------------------------------

def test_item_prices_bez_rabatu():
    item = {"currentUnitPrice": "3,99", "quantity": "1", "originalAmount": "3,99"}
    base, promo = app.item_prices(item)
    assert base == 3.99
    assert promo == 3.99


def test_item_prices_rabat_dzielony_przez_ilosc():
    """Rabat jest kwotą łączną dla pozycji, cena promocyjna jest za sztukę."""
    item = {
        "currentUnitPrice": "0,34",
        "quantity": "4",
        "originalAmount": "1,36",
        "discounts": [{"amount": "0,44"}],
    }
    base, promo = app.item_prices(item)
    assert base == 0.34
    assert promo == pytest.approx(0.23)


def test_item_prices_nie_schodzi_ponizej_zera():
    item = {
        "currentUnitPrice": "5,00",
        "quantity": "1",
        "originalAmount": "5,00",
        "discounts": [{"amount": "9,00"}],
    }
    _base, promo = app.item_prices(item)
    assert promo == 0.0


def test_item_prices_zerowa_ilosc_nie_dzieli_przez_zero():
    item = {"currentUnitPrice": "5,00", "quantity": "0", "originalAmount": "5,00"}
    base, promo = app.item_prices(item)
    assert base == 5.0
    assert promo == 5.0


def test_original_amount_dla_wagi():
    """
    Dla towaru na wagę cena jednostkowa razy ilość nie odtwarza kwoty,
    więc bierzemy originalAmount z API.
    """
    item = {"currentUnitPrice": "12,99", "quantity": "1,486", "originalAmount": "19,30"}
    assert app.item_original_amount(item) == 19.30


def test_original_amount_fallback_gdy_brak():
    item = {"currentUnitPrice": "2,50", "quantity": "2"}
    assert app.item_original_amount(item) == 5.0


# ---------------------------------------------------------------------------
# Sumy paragonu
# ---------------------------------------------------------------------------

def test_total_amount_jest_juz_po_rabacie(receipt_api):
    """
    REGRESJA: totalAmount zwracane przez API jest już PO odliczeniu rabatów.
    Odejmowanie totalDiscount po raz drugi zaniża wydatki.

    Sprawdzamy to na paragonie, gdzie suma pozycji minus rabaty daje
    dokładnie totalAmount: 1,36 + 3,99 - 0,44 = 4,91.
    """
    pozycje = sum(app.item_original_amount(i) for i in receipt_api["itemsLine"])
    rabaty = sum(app.item_discount(i) for i in receipt_api["itemsLine"])
    receipt_api["totalAmount"] = f"{pozycje - rabaty:.2f}".replace(".", ",")

    assert app.receipt_total(receipt_api) == pytest.approx(pozycje - rabaty)
    assert app.receipt_total(receipt_api) == pytest.approx(4.91)


def test_receipt_discount_z_pola_total(receipt_api):
    assert app.receipt_discount(receipt_api) == 0.44


def test_receipt_discount_liczony_z_pozycji_gdy_brak_pola(receipt_api):
    """Paragony sparsowane z HTML nie mają totalDiscount."""
    receipt_api.pop("totalDiscount")
    assert app.receipt_discount(receipt_api) == 0.44


# ---------------------------------------------------------------------------
# Agregacje
# ---------------------------------------------------------------------------

def test_get_stats_sumuje_rabaty(receipt_api):
    stats = app.get_stats([receipt_api])
    assert stats["total_receipts"] == 1
    assert stats["total_discount"] == 0.44
    assert stats["total_spent"] == pytest.approx(49.80)


def test_search_products_zwraca_obie_ceny(receipt_api):
    wyniki = app.search_products([receipt_api], "kajzerka")
    assert len(wyniki) == 1
    assert wyniki[0]["base_price"] == 0.34
    assert wyniki[0]["last_price"] == pytest.approx(0.23)


def test_product_history_zwraca_obie_ceny(receipt_api):
    historia = app.get_product_history([receipt_api], "kajzerka")
    assert len(historia) == 1
    assert historia[0]["base_price"] == 0.34
    assert historia[0]["promo_price"] == pytest.approx(0.23)


def test_top_products_liczy_kwote_po_rabacie(receipt_api):
    """Wydatek na produkt to kwota faktycznie zapłacona, nie cena z półki."""
    receipt_api["itemsLine"][0]["quantity"] = "2"
    wynik = app.get_top_products([receipt_api])
    bulka = next(p for p in wynik["top_by_count"] if p["name"] == "Bułka kajzerka")
    assert bulka["spend"] == pytest.approx(0.92)  # 1,36 - 0,44


def test_coupon_stats(receipt_api):
    stats = app.get_coupon_stats([receipt_api])
    assert stats["total_coupons"] == 1
    assert stats["total_discount"] == 0.44
    assert stats["receipts_with_coupon"] == 1


def test_puste_dane_nie_wywalaja():
    assert app.get_stats([]) == {}
    assert app.search_products([], "cokolwiek") == []
    assert app.get_product_history([], "cokolwiek") == []


# ---------------------------------------------------------------------------
# Spójność: HTML i API liczone tak samo
# ---------------------------------------------------------------------------

def test_paragon_z_html_liczy_sie_tak_samo_jak_z_api(receipt_html):
    """Pozycje z HTML przechodzą przez te same funkcje co pozycje z API."""
    items = parse_html_receipt(receipt_html)
    paragon = {"id": "X", "date": "2026-07-31T10:00:00", "itemsLine": items}

    rabaty = app.receipt_discount(paragon)
    assert rabaty == pytest.approx(54.43)  # 0,44 + 53,99

    _base, promo = app.item_prices(items[1])
    assert promo == pytest.approx(36.00)  # 89,99 - 53,99
