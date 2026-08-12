"""
Fidl Plus - Web UI
Uruchom: python app.py
Otwórz:  http://localhost:8000
"""
import json
import os
import subprocess
import sys
import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lidl_api import LidlPlusAPI
from receipt_parser import enrich_receipts

app = FastAPI(title="Fidl Plus")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Filtry Jinja2
from urllib.parse import quote
templates.env.filters["urlencode"] = lambda s: quote(str(s), safe="")
templates.env.filters["tojson"]    = lambda v: json.dumps(v, ensure_ascii=False)

# Stan synchronizacji - współdzielony między wątkami
sync_state = {
    "running": False,
    "count": 0,
    "total": 0,
    "error": None,
    "done": False,
}

TOKENS_FILE = "lidl_tokens.json"
DATA_FILE = "wszystkie_paragony_szczegoly.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_api() -> Optional[LidlPlusAPI]:
    """Wczytaj API z zapisanych tokenów."""
    if not os.path.exists(TOKENS_FILE):
        return None
    api = LidlPlusAPI(country="PL")
    if api.load_tokens(TOKENS_FILE):
        return api
    return None


def load_receipts() -> list:
    """Wczytaj paragony z pliku cache, sparsuj HTML i znormalizuj nazwy."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        receipts, _ = enrich_receipts(raw)
        return receipts
    return []


def save_receipts(receipts: list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(receipts, f, ensure_ascii=False, indent=2)


def parse_price(val) -> float:
    """Bezpieczna konwersja ceny (może być '4,39' lub 4.39)."""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def get_stats(receipts: list) -> dict:
    if not receipts:
        return {}
    total_spent = sum(parse_price(r.get("totalAmount", 0)) for r in receipts)
    dates = [r["date"][:10] for r in receipts if r.get("date")]
    stores = [r.get("store", {}).get("name", "") for r in receipts if r.get("store")]
    store_counts = defaultdict(int)
    for s in stores:
        store_counts[s] += 1
    fav_store = max(store_counts, key=store_counts.get) if store_counts else "-"

    # Kupony i oszczędności
    total_coupons = sum(len(r.get("couponsUsed", [])) for r in receipts)
    total_discount = sum(parse_price(r.get("totalDiscount", 0)) for r in receipts)

    # Średnia przerwa
    from datetime import date as date_type
    unique_dates = sorted({d for d in dates})
    if len(unique_dates) > 1:
        date_objs = [date_type.fromisoformat(d) for d in unique_dates]
        gaps = [(date_objs[i+1]-date_objs[i]).days for i in range(len(date_objs)-1)]
        avg_gap = sum(gaps) / len(gaps)
    else:
        avg_gap = 0

    return {
        "total_receipts": len(receipts),
        "total_spent": total_spent,
        "fav_store": fav_store,
        "date_from": min(dates) if dates else "-",
        "date_to": max(dates) if dates else "-",
        "total_coupons": total_coupons,
        "total_discount": total_discount,
        "avg_gap": avg_gap,
    }


def get_insights(receipts: list) -> dict:
    """Dane do strony /insights."""
    from datetime import datetime as dt

    # Heatmap: godzina x dzień tygodnia -> liczba wizyt
    heatmap = defaultdict(int)
    day_names = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]
    for r in receipts:
        try:
            d = dt.fromisoformat(r["date"])
            heatmap[f"{d.weekday()}_{d.hour}"] += 1
        except Exception:
            pass

    # Wydatki miesięczne
    monthly = defaultdict(float)
    monthly_visits = defaultdict(int)
    for r in receipts:
        month = r.get("date", "")[:7]
        if month:
            monthly[month] += parse_price(r.get("totalAmount", 0))
            monthly_visits[month] += 1
    months_sorted = sorted(monthly.keys())

    # Pie VAT
    vat_labels = {"A": "23% VAT", "B": "8% VAT", "C": "5% VAT", "D": "0% VAT"}
    vat_spend = defaultdict(float)
    for r in receipts:
        for t in r.get("taxes", []) or []:
            key = t.get("taxGroupName", "?")
            if key in vat_labels:
                vat_spend[key] += parse_price(t.get("taxableAmount", 0))

    # Top 10 najdroższych paragonów
    top_receipts = sorted(
        [r for r in receipts if r.get("id")],
        key=lambda r: parse_price(r.get("totalAmount", 0)),
        reverse=True
    )[:10]

    return {
        "heatmap": dict(heatmap),
        "day_names": day_names,
        "months": months_sorted,
        "monthly_amounts": [round(monthly[m], 2) for m in months_sorted],
        "monthly_visits": [monthly_visits[m] for m in months_sorted],
        "vat_labels": [vat_labels.get(k, k) for k in sorted(vat_spend)],
        "vat_amounts": [round(vat_spend[k], 2) for k in sorted(vat_spend)],
        "top_receipts": top_receipts,
    }


def get_top_products(receipts: list) -> dict:
    """Dane do strony /top-products."""
    product_count = defaultdict(float)
    product_spend = defaultdict(float)
    product_last_price = {}
    price_history = defaultdict(list)

    for r in receipts:
        date = r.get("date", "")[:10]
        for item in r.get("itemsLine", []):
            name = item.get("name", "")
            bc = item.get("codeInput", "")
            if not name:
                continue
            qty = parse_price(item.get("quantity", 1)) or 1
            p = parse_price(item.get("currentUnitPrice", 0))
            product_count[name] += qty
            product_spend[name] += p * qty
            product_last_price[name] = p
            if p > 0 and bc and len(bc) >= 8:
                price_history[name].append((date, p))

    # Ranking ilościowy
    top_by_count = sorted(
        [{"name": k, "count": int(v), "spend": round(product_spend[k], 2),
          "last_price": round(product_last_price.get(k, 0), 2)}
         for k, v in product_count.items() if v >= 2],
        key=lambda x: -x["count"]
    )[:20]

    # Największa zmienność cen
    volatility = []
    for name, history in price_history.items():
        if len(history) < 3:
            continue
        prices = [p for _, p in history]
        mn, mx = min(prices), max(prices)
        if mn == 0:
            continue
        pct = (mx - mn) / mn * 100
        if pct < 5:
            continue
        # Pierwsza i ostatnia cena
        history_sorted = sorted(history)
        first_p = history_sorted[0][1]
        last_p = history_sorted[-1][1]
        volatility.append({
            "name": name,
            "min_price": round(mn, 2),
            "max_price": round(mx, 2),
            "first_price": round(first_p, 2),
            "last_price": round(last_p, 2),
            "change_pct": round(pct, 1),
            "count": len(history),
        })
    volatility.sort(key=lambda x: -x["change_pct"])

    return {
        "top_by_count": top_by_count,
        "volatility": volatility[:20],
    }


def get_coupon_stats(receipts: list) -> dict:
    """Statystyki kuponów."""
    from collections import Counter
    coupon_titles = Counter()
    total_discount = 0.0
    receipts_with_coupon = 0

    for r in receipts:
        coupons = r.get("couponsUsed", [])
        if coupons:
            receipts_with_coupon += 1
        for c in coupons:
            title = c.get("couponTitle") or c.get("title") or "?"
            coupon_titles[title] += 1
        total_discount += parse_price(r.get("totalDiscount", 0))

    return {
        "total_coupons": sum(coupon_titles.values()),
        "unique_coupons": len(coupon_titles),
        "receipts_with_coupon": receipts_with_coupon,
        "total_discount": round(total_discount, 2),
        "top_coupons": coupon_titles.most_common(10),
    }


def get_product_history(receipts: list, name_query: str) -> list:
    """Zwróć historię cen produktu pasującego do zapytania."""
    name_query_lower = name_query.lower()
    history = []
    for receipt in receipts:
        date = receipt.get("date", "")[:10]
        store = receipt.get("store", {}).get("name", "")
        for item in receipt.get("itemsLine", []):
            item_name = item.get("name", "")
            if name_query_lower in item_name.lower():
                history.append({
                    "date": date,
                    "name": item_name,
                    "price": parse_price(item.get("currentUnitPrice", 0)),
                    "store": store,
                    "receipt_id": receipt.get("id", ""),
                })
    history.sort(key=lambda x: x["date"])
    return history


def search_products(receipts: list, query: str) -> list:
    """Znajdź unikalne produkty pasujące do zapytania."""
    query_lower = query.lower()
    seen = {}
    for receipt in receipts:
        for item in receipt.get("itemsLine", []):
            name = item.get("name", "")
            if query_lower in name.lower():
                key = name.lower()
                price = parse_price(item.get("currentUnitPrice", 0))
                if key not in seen:
                    seen[key] = {"name": name, "last_price": price, "count": 1}
                else:
                    seen[key]["count"] += 1
                    seen[key]["last_price"] = price
    results = sorted(seen.values(), key=lambda x: x["count"], reverse=True)
    return results[:50]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    receipts = load_receipts()
    stats = get_stats(receipts)
    coupon_stats = get_coupon_stats(receipts)
    recent = sorted(receipts, key=lambda r: r.get("date", ""), reverse=True)[:20]
    logged_in = os.path.exists(TOKENS_FILE)
    return templates.TemplateResponse(request=request, name="index.html", context={
        "request": request,
        "stats": stats,
        "coupon_stats": coupon_stats,
        "recent": recent,
        "logged_in": logged_in,
    })


@app.get("/receipts", response_class=HTMLResponse)
async def receipts_list(
    request: Request,
    page: int = Query(1, ge=1),
    store: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    receipts = load_receipts()

    # Filtrowanie
    if store:
        receipts = [r for r in receipts if store.lower() in r.get("store", {}).get("name", "").lower()]
    if date_from:
        receipts = [r for r in receipts if r.get("date", "")[:10] >= date_from]
    if date_to:
        receipts = [r for r in receipts if r.get("date", "")[:10] <= date_to]

    receipts = sorted(receipts, key=lambda r: r.get("date", ""), reverse=True)

    per_page = 25
    total = len(receipts)
    pages = max(1, (total + per_page - 1) // per_page)
    receipts_page = receipts[(page - 1) * per_page : page * per_page]

    # Lista sklepów do filtra
    all_stores = sorted({r.get("store", {}).get("name", "") for r in load_receipts() if r.get("store")})

    return templates.TemplateResponse(request=request, name="receipts.html", context={
        "request": request,
        "receipts": receipts_page,
        "page": page,
        "pages": pages,
        "total": total,
        "store": store,
        "date_from": date_from,
        "date_to": date_to,
        "all_stores": all_stores,
        "parse_price": parse_price,
    })


@app.get("/receipt/{receipt_id}", response_class=HTMLResponse)
async def receipt_detail(request: Request, receipt_id: str):
    receipts = load_receipts()
    receipt = next((r for r in receipts if r.get("id") == receipt_id), None)
    if not receipt:
        return HTMLResponse("Paragon nie znaleziony", status_code=404)
    items = receipt.get("itemsLine", [])
    for item in items:
        item["_price"] = parse_price(item.get("currentUnitPrice", 0))
        item["_qty"] = parse_price(item.get("quantity", 1))

    # Paragon bez itemsLine - może mieć htmlPrintedReceipt
    html_receipt = receipt.get("htmlPrintedReceipt") if not items else None

    return templates.TemplateResponse(request=request, name="receipt_detail.html", context={
        "request": request,
        "receipt": receipt,
        "items": items,
        "html_receipt": html_receipt,
        "coupons": receipt.get("couponsUsed", []),
        "parse_price": parse_price,
    })


@app.get("/insights", response_class=HTMLResponse)
async def insights(request: Request):
    receipts = load_receipts()
    data = get_insights(receipts)
    return templates.TemplateResponse(request=request, name="insights.html", context={
        "request": request,
        **data,
        "parse_price": parse_price,
    })


@app.get("/top-products", response_class=HTMLResponse)
async def top_products(request: Request):
    receipts = load_receipts()
    data = get_top_products(receipts)
    return templates.TemplateResponse(request=request, name="top_products.html", context={
        "request": request,
        **data,
    })


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("")):
    receipts = load_receipts()
    results = search_products(receipts, q) if q else []
    return templates.TemplateResponse(request=request, name="search.html", context={
        "request": request,
        "q": q,
        "results": results,
    })


@app.get("/product", response_class=HTMLResponse)
async def product(request: Request, name: str = Query("")):
    receipts = load_receipts()
    history = get_product_history(receipts, name) if name else []

    # Dane do wykresu
    chart_labels = [h["date"] for h in history]
    chart_prices = [h["price"] for h in history]
    chart_stores = [h["store"] for h in history]

    avg = sum(chart_prices) / len(chart_prices) if chart_prices else 0
    min_price = min(chart_prices) if chart_prices else 0
    max_price = max(chart_prices) if chart_prices else 0

    return templates.TemplateResponse(request=request, name="product.html", context={
        "request": request,
        "name": name,
        "history": history,
        "chart_labels": json.dumps(chart_labels),
        "chart_prices": json.dumps(chart_prices),
        "chart_stores": json.dumps(chart_stores),
        "avg": avg,
        "min_price": min_price,
        "max_price": max_price,
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "status": ""})


@app.post("/login/start", response_class=HTMLResponse)
async def login_start(request: Request):
    """Uruchom browser_login.py w tle i zwróć status."""
    def run_login():
        subprocess.run(
            [sys.executable, "browser_login.py"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
    thread = threading.Thread(target=run_login, daemon=True)
    thread.start()
    return HTMLResponse("""
        <div id="login-status" class="status-running"
             hx-get="/login/status" hx-trigger="every 2s" hx-swap="outerHTML">
            Otwieranie Chrome... zaloguj się w oknie przeglądarki.
        </div>
    """)


@app.get("/login/status", response_class=HTMLResponse)
async def login_status():
    if os.path.exists(TOKENS_FILE):
        # Sprawdź czy token jest świeży (zmodyfikowany w ostatnich 5 min)
        mtime = os.path.getmtime(TOKENS_FILE)
        age = datetime.now().timestamp() - mtime
        if age < 300:
            return HTMLResponse("""
                <div id="login-status" class="status-ok">
                    Zalogowano! <a href="/">Przejdź do dashboardu</a>
                    &nbsp;|&nbsp; <a href="/sync">Pobierz paragony</a>
                </div>
            """)
    return HTMLResponse("""
        <div id="login-status" class="status-running"
             hx-get="/login/status" hx-trigger="every 2s" hx-swap="outerHTML">
            Czekam na zalogowanie...
        </div>
    """)


@app.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    return templates.TemplateResponse(request=request, name="sync.html", context={"request": request})


@app.post("/sync/start", response_class=HTMLResponse)
async def sync_start():
    """Pobierz paragony z API w tle."""
    if sync_state["running"]:
        return HTMLResponse("""
            <div id="sync-status" class="status-running"
                 hx-get="/sync/status" hx-trigger="every 2s" hx-swap="outerHTML">
                Synchronizacja już trwa...
            </div>
        """)

    def run_sync():
        sync_state["running"] = True
        sync_state["count"] = 0
        sync_state["total"] = 0
        sync_state["error"] = None
        sync_state["done"] = False
        try:
            api = load_api()
            if not api:
                sync_state["error"] = "Brak tokenów - zaloguj się najpierw."
                return
            try:
                api.refresh_access_token()
                api.save_tokens(TOKENS_FILE)
            except Exception:
                pass

            # Pobierz listę wszystkich paragonów
            tickets = api.get_all_tickets(max_pages=100)
            tickets = [t for t in tickets if t.get("id")]
            sync_state["total"] = len(tickets)

            # Wczytaj istniejące żeby nie pobierać ponownie
            existing = {}
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, encoding="utf-8") as f:
                    for r in json.load(f):
                        if r.get("id"):
                            existing[r["id"]] = r

            detailed = []
            for ticket in tickets:
                tid = ticket["id"]
                if tid in existing:
                    detailed.append(existing[tid])
                else:
                    try:
                        detail = api.get_ticket_details(tid)
                        detailed.append(detail)
                    except Exception:
                        detailed.append(ticket)
                sync_state["count"] = len(detailed)
                # Zapisuj co 10 paragonów żeby status był aktualny
                if len(detailed) % 10 == 0:
                    save_receipts(detailed)

            save_receipts(detailed)
            sync_state["done"] = True

        except Exception as e:
            sync_state["error"] = str(e)
        finally:
            sync_state["running"] = False

    threading.Thread(target=run_sync, daemon=True).start()
    return HTMLResponse("""
        <div id="sync-status" class="status-running"
             hx-get="/sync/status" hx-trigger="every 2s" hx-swap="outerHTML">
            Pobieranie paragonów...
        </div>
    """)


@app.get("/sync/status", response_class=HTMLResponse)
async def sync_status():
    if sync_state.get("error"):
        return HTMLResponse(f"""
            <div id="sync-status" class="alert alert-warn">
                Błąd: {sync_state["error"]}
            </div>
        """)

    if sync_state.get("done"):
        count = sync_state["count"]
        return HTMLResponse(f"""
            <div id="sync-status" class="status-ok">
                Pobrano {count} paragonów.
                <a href="/">Przejdź do dashboardu</a>
            </div>
        """)

    if sync_state.get("running"):
        count = sync_state["count"]
        total = sync_state["total"]
        pct = int(count / total * 100) if total else 0
        return HTMLResponse(f"""
            <div id="sync-status" class="status-running"
                 hx-get="/sync/status" hx-trigger="every 2s" hx-swap="outerHTML">
                <div style="margin-bottom:.5rem">
                    Pobieranie: {count} / {total} paragonów ({pct}%)
                </div>
                <div style="background:#fde68a;border-radius:4px;height:8px;overflow:hidden;">
                    <div style="background:#92400e;height:100%;width:{pct}%;transition:width .5s;"></div>
                </div>
            </div>
        """)

    # Nie trwa - pokaż ostatni wynik
    count = len(load_receipts())
    if count:
        return HTMLResponse(f"""
            <div id="sync-status" class="status-ok">
                Dane aktualne: {count} paragonów w bazie.
                <a href="/">Dashboard</a>
            </div>
        """)
    return HTMLResponse("""
        <div id="sync-status" style="color:var(--muted);font-size:.9rem">
            Kliknij "Rozpocznij pobieranie" aby pobrać paragony.
        </div>
    """)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import webbrowser
    print("\n" + "="*50)
    print("  Fidl Plus - Web UI")
    print("  http://localhost:8000")
    print("="*50 + "\n")
    webbrowser.open("http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
