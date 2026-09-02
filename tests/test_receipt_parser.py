"""Testy parsera paragonów w formacie htmlPrintedReceipt."""
from receipt_parser import parse_html_receipt


def test_parsuje_wszystkie_pozycje(receipt_html):
    """Każdy produkt raz - linie 'ilość * cena' nie mogą tworzyć duplikatów."""
    items = parse_html_receipt(receipt_html)
    assert [i["name"] for i in items] == [
        "Bułka kajzerka",
        "Kawa ziarnista",
        "Melon luz",
        "Kawa ziarnista",
    ]


def test_nie_dubluje_towaru_na_wage(receipt_html):
    """
    Linia wagowa ma format "1,486kg x 12.99" zamiast "1 * 12.99".
    Nierozpoznana trafiała do wyniku jako osobny produkt.
    """
    items = parse_html_receipt(receipt_html)
    melony = [i for i in items if i["name"] == "Melon luz"]
    assert len(melony) == 1
    assert melony[0]["quantity"] == "1.486"
    assert melony[0]["originalAmount"] == "19,3"


def test_wyciaga_rabaty(receipt_html):
    items = parse_html_receipt(receipt_html)
    bulka = items[0]
    assert bulka["discounts"] == [
        {
            "description": "Lidl Plus kupon",
            "amount": "0,44",
            "promotionId": "PROMO-1",
        }
    ]


def test_rabat_trafia_do_wlasciwej_pozycji(receipt_html):
    """
    Ta sama kawa kupiona dwa razy, kupon naliczony tylko na pierwszej.
    Rabat nie może przeciekać na drugą sztukę ani na kolejny produkt.
    """
    items = parse_html_receipt(receipt_html)
    pierwsza_kawa, druga_kawa = items[1], items[3]

    assert pierwsza_kawa["discounts"][0]["amount"] == "53,99"
    assert druga_kawa["discounts"] == []
    assert items[2]["discounts"] == []  # melon między nimi


def test_produkt_bez_rabatu_ma_pusta_liste(receipt_html):
    items = parse_html_receipt(receipt_html)
    assert items[3]["discounts"] == []


def test_pusty_html_nie_wywala():
    assert parse_html_receipt("") == []
    assert parse_html_receipt("<html><body></body></html>") == []
