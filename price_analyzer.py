"""
Analizator cen produktów z paragonów Lidl Plus
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import statistics


class PriceAnalyzer:
    """Analizuje zmiany cen produktów z paragonów"""

    def __init__(self):
        self.products = defaultdict(list)  # product_name -> list of (date, price, quantity, ticket_id)

    def add_tickets(self, tickets: List[Dict]):
        """
        Dodaje paragony do analizy

        Args:
            tickets: Lista paragonów z API
        """
        for ticket in tickets:
            self._process_ticket(ticket)

    def _process_ticket(self, ticket: Dict):
        """Przetwarza pojedynczy paragon"""
        ticket_id = ticket.get('id', '')
        date_str = ticket.get('date', '')

        # Parsuj datę
        try:
            # Format: "2025-12-23T10:30:00" lub "2025-12-23T10:30:00+00:00"
            ticket_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            ticket_date = datetime.now()

        # Przetwórz produkty z paragonu
        items = ticket.get('itemsLine', [])

        if not items:
            # Brak szczegółów - prawdopodobnie to tylko lista paragonów bez szczegółów
            return

        for item in items:
            product_name = item.get('name', '').strip()
            if not product_name:
                continue

            # Pobierz cenę i ilość (API zwraca jako string z przecinkiem!)
            current_unit_price_str = item.get('currentUnitPrice', '0')
            quantity_str = item.get('quantity', '1')
            original_amount_str = item.get('originalAmount', '0')

            # Konwertuj z formatu polskiego (przecinek) na float
            try:
                current_unit_price = float(current_unit_price_str.replace(',', '.'))
            except (ValueError, AttributeError):
                current_unit_price = 0.0

            try:
                quantity = float(quantity_str.replace(',', '.'))
            except (ValueError, AttributeError):
                quantity = 1.0

            try:
                original_amount = float(original_amount_str.replace(',', '.'))
            except (ValueError, AttributeError):
                original_amount = current_unit_price * quantity

            # Oblicz zniżkę jeśli była
            discounts = item.get('discounts', [])
            total_discount = 0.0
            for discount in discounts:
                try:
                    discount_amount = float(discount.get('amount', '0').replace(',', '.'))
                    total_discount += discount_amount
                except (ValueError, AttributeError):
                    pass

            # Zapisz informacje o produkcie
            self.products[product_name].append({
                'date': ticket_date,
                'price': current_unit_price,
                'quantity': quantity,
                'ticket_id': ticket_id,
                'original_amount': original_amount,
                'discount': total_discount,
                'is_weight': item.get('isWeight', False)
            })

    def get_product_history(self, product_name: str) -> List[Dict]:
        """
        Pobiera historię cen dla produktu

        Args:
            product_name: Nazwa produktu

        Returns:
            Lista zakupów danego produktu posortowana po dacie
        """
        if product_name not in self.products:
            return []

        history = sorted(self.products[product_name], key=lambda x: x['date'])
        return history

    def get_all_products(self) -> List[str]:
        """
        Zwraca listę wszystkich produktów

        Returns:
            Lista nazw produktów
        """
        return sorted(self.products.keys())

    def get_price_statistics(self, product_name: str) -> Optional[Dict]:
        """
        Oblicza statystyki cen dla produktu

        Args:
            product_name: Nazwa produktu

        Returns:
            Dict ze statystykami (min, max, średnia, etc.)
        """
        history = self.get_product_history(product_name)

        if not history:
            return None

        prices = [item['price'] for item in history]
        quantities = [item['quantity'] for item in history]

        stats = {
            'product_name': product_name,
            'total_purchases': len(history),
            'total_quantity': sum(quantities),
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': statistics.mean(prices),
            'median_price': statistics.median(prices),
            'first_purchase': history[0]['date'],
            'last_purchase': history[-1]['date'],
            'price_change': history[-1]['price'] - history[0]['price'],
            'price_change_percent': ((history[-1]['price'] - history[0]['price']) / history[0]['price'] * 100) if history[0]['price'] > 0 else 0
        }

        # Oblicz zmienność cen
        if len(prices) > 1:
            stats['price_std_dev'] = statistics.stdev(prices)
        else:
            stats['price_std_dev'] = 0

        return stats

    def get_price_changes(self, min_change_percent: float = 5.0) -> List[Dict]:
        """
        Znajduje produkty z największymi zmianami cen

        Args:
            min_change_percent: Minimalny procent zmiany ceny

        Returns:
            Lista produktów z największymi zmianami
        """
        changes = []

        for product_name in self.products.keys():
            stats = self.get_price_statistics(product_name)

            if stats and abs(stats['price_change_percent']) >= min_change_percent:
                changes.append(stats)

        # Sortuj po procentowej zmianie ceny (malejąco po wartości bezwzględnej)
        changes.sort(key=lambda x: abs(x['price_change_percent']), reverse=True)

        return changes

    def get_products_by_frequency(self, min_purchases: int = 3) -> List[Dict]:
        """
        Znajduje najczęściej kupowane produkty

        Args:
            min_purchases: Minimalna liczba zakupów

        Returns:
            Lista produktów posortowana po częstości zakupów
        """
        frequent_products = []

        for product_name in self.products.keys():
            stats = self.get_price_statistics(product_name)

            if stats and stats['total_purchases'] >= min_purchases:
                frequent_products.append(stats)

        # Sortuj po liczbie zakupów
        frequent_products.sort(key=lambda x: x['total_purchases'], reverse=True)

        return frequent_products

    def generate_report(self, output_file: str = "price_report.txt"):
        """
        Generuje raport tekstowy z analizy cen

        Args:
            output_file: Ścieżka do pliku wyjściowego
        """
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("RAPORT ANALIZY CEN PRODUKTÓW LIDL PLUS\n")
            f.write("=" * 80 + "\n\n")

            # Podsumowanie
            f.write(f"Liczba unikalnych produktów: {len(self.products)}\n")

            total_purchases = sum(len(items) for items in self.products.values())
            f.write(f"Całkowita liczba zakupów: {total_purchases}\n\n")

            # Produkty z największymi zmianami cen
            f.write("\n" + "=" * 80 + "\n")
            f.write("PRODUKTY Z NAJWIĘKSZYMI ZMIANAMI CEN (min. 5%)\n")
            f.write("=" * 80 + "\n\n")

            price_changes = self.get_price_changes(min_change_percent=5.0)

            if price_changes:
                for item in price_changes[:20]:  # Top 20
                    change_direction = "↑" if item['price_change'] > 0 else "↓"
                    f.write(f"\n{item['product_name']}\n")
                    f.write(f"  Pierwsza cena: {item['min_price']:.2f} zł\n")
                    f.write(f"  Ostatnia cena: {item['max_price']:.2f} zł\n")
                    f.write(f"  Zmiana: {change_direction} {item['price_change_percent']:.1f}% ({item['price_change']:.2f} zł)\n")
                    f.write(f"  Liczba zakupów: {item['total_purchases']}\n")
            else:
                f.write("Brak produktów ze znaczącymi zmianami cen.\n")

            # Najczęściej kupowane produkty
            f.write("\n" + "=" * 80 + "\n")
            f.write("NAJCZĘŚCIEJ KUPOWANE PRODUKTY (min. 3 zakupy)\n")
            f.write("=" * 80 + "\n\n")

            frequent = self.get_products_by_frequency(min_purchases=3)

            if frequent:
                for item in frequent[:20]:  # Top 20
                    f.write(f"\n{item['product_name']}\n")
                    f.write(f"  Liczba zakupów: {item['total_purchases']}\n")
                    f.write(f"  Całkowita ilość: {item['total_quantity']}\n")
                    f.write(f"  Średnia cena: {item['avg_price']:.2f} zł\n")
                    f.write(f"  Zakres cen: {item['min_price']:.2f} - {item['max_price']:.2f} zł\n")
                    if item['price_std_dev'] > 0:
                        f.write(f"  Zmienność cen: ±{item['price_std_dev']:.2f} zł\n")
            else:
                f.write("Brak produktów kupowanych wielokrotnie.\n")

            # Statystyki dla wszystkich produktów
            f.write("\n" + "=" * 80 + "\n")
            f.write("STATYSTYKI WSZYSTKICH PRODUKTÓW\n")
            f.write("=" * 80 + "\n\n")

            all_stats = []
            for product_name in self.products.keys():
                stats = self.get_price_statistics(product_name)
                if stats:
                    all_stats.append(stats)

            all_stats.sort(key=lambda x: x['product_name'])

            for stats in all_stats:
                f.write(f"\n{stats['product_name']}\n")
                f.write(f"  Zakupiono: {stats['total_purchases']} razy (łącznie {stats['total_quantity']} szt.)\n")
                f.write(f"  Cena: {stats['min_price']:.2f} - {stats['max_price']:.2f} zł (śr. {stats['avg_price']:.2f} zł)\n")

                if stats['total_purchases'] > 1:
                    change_direction = "↑" if stats['price_change'] > 0 else "↓"
                    f.write(f"  Zmiana ceny: {change_direction} {stats['price_change_percent']:.1f}%\n")

        print(f"\nRaport zapisany do: {output_file}")

    def generate_csv_report(self, output_file: str = "price_data.csv"):
        """
        Generuje raport CSV ze wszystkimi danymi

        Args:
            output_file: Ścieżka do pliku CSV
        """
        import csv

        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)

            # Nagłówki
            writer.writerow([
                'Produkt',
                'Data zakupu',
                'Cena jednostkowa',
                'Ilość',
                'Kwota',
                'Zniżka',
                'ID paragonu'
            ])

            # Dane
            for product_name in sorted(self.products.keys()):
                history = self.get_product_history(product_name)

                for item in history:
                    writer.writerow([
                        product_name,
                        item['date'].strftime('%Y-%m-%d %H:%M:%S'),
                        f"{item['price']:.2f}",
                        item['quantity'],
                        f"{item['original_amount']:.2f}",
                        f"{item['discount']:.2f}",
                        item['ticket_id']
                    ])

        print(f"Dane CSV zapisane do: {output_file}")
