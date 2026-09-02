"""
Testy endpointów HTTP.

Sprawdzają głównie to, czego testy jednostkowe nie złapią: czy szablony
Jinja2 renderują się bez błędu przy realistycznych danych.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client(receipt_api, receipt_html, tmp_path, monkeypatch):
    """Klient HTTP na podstawionym zbiorze paragonów."""
    paragon_html = {
        "id": "TEST-HTML-1",
        "date": "2026-07-30T12:00:00",
        "store": {"name": "Lidl Testowa 2"},
        "totalAmount": 202.69,
        "htmlPrintedReceipt": receipt_html,
    }

    plik = tmp_path / "paragony.json"
    plik.write_text(json.dumps([receipt_api, paragon_html]), encoding="utf-8")
    monkeypatch.setattr(app, "DATA_FILE", str(plik))

    return TestClient(app.app)


@pytest.mark.parametrize("sciezka", [
    "/",
    "/receipts",
    "/insights",
    "/top-products",
    "/search?q=kajzerka",
    "/search?q=",
    "/product?name=Bu%C5%82ka%20kajzerka",
    "/product?name=",
    "/login",
    "/receipt/TEST-API-1",
    "/receipt/TEST-HTML-1",
    "/receipt/TEST-HTML-1/print",
])
def test_strona_sie_renderuje(client, sciezka):
    odpowiedz = client.get(sciezka)
    assert odpowiedz.status_code == 200, odpowiedz.text[:400]


@pytest.mark.parametrize("sciezka", [
    "/receipt/NIE-ISTNIEJE",
    "/receipt/NIE-ISTNIEJE/print",
    "/receipt/TEST-API-1/print",  # paragon z API nie ma wersji do wydruku
])
def test_brak_zasobu_daje_404(client, sciezka):
    assert client.get(sciezka).status_code == 404


def test_wydruk_nie_odpytuje_zewnetrznych_serwisow(client):
    """
    Numer paragonu pokazujemy tekstem. Generowanie kodu kreskowego przez
    zewnętrzne API wysyłałoby identyfikatory zakupów poza serwer.
    """
    tresc = client.get("/receipt/TEST-HTML-1/print").text
    assert "http://" not in tresc
    assert "https://" not in tresc


def test_szczegoly_paragonu_pokazuja_cene_promocyjna(client):
    tresc = client.get("/receipt/TEST-API-1").text
    assert "Cena promocyjna" in tresc
    assert "0.23 zł" in tresc


def test_login_bez_novnc_nie_pokazuje_przycisku_podgladu(client, monkeypatch):
    monkeypatch.setattr(app, "NOVNC_PORT", "")
    monkeypatch.setattr(app, "NOVNC_URL", "")
    tresc = client.get("/login").text
    assert "novncUrl" not in tresc


def test_login_z_novnc_pokazuje_przycisk_podgladu(client, monkeypatch):
    monkeypatch.setattr(app, "NOVNC_PORT", "6080")
    tresc = client.get("/login").text
    assert ":6080/vnc.html" in tresc


def test_kwoty_renderuja_sie_gdy_api_zwroci_string(client, receipt_api, tmp_path, monkeypatch):
    """
    REGRESJA: szablony robiły "%.2f"|format(totalAmount), co wywalało stronę,
    jeśli API zwróciło kwotę jako "49,80" zamiast liczby.
    """
    receipt_api["totalAmount"] = "49,80"
    plik = tmp_path / "string_amounts.json"
    plik.write_text(json.dumps([receipt_api]), encoding="utf-8")
    monkeypatch.setattr(app, "DATA_FILE", str(plik))

    for sciezka in ("/", "/receipts", "/insights", "/receipt/TEST-API-1"):
        odpowiedz = client.get(sciezka)
        assert odpowiedz.status_code == 200, f"{sciezka}: {odpowiedz.text[:300]}"
    assert "49.80 zł" in client.get("/receipt/TEST-API-1").text
