import traceback
from django.conf import settings
from escpos.printer import Network

LINE_WIDTH = 32


def two_columns(left, right, fill=" "):
    """Left text and right text on one receipt line."""
    padding = max(1, LINE_WIDTH - len(left) - len(right))
    return f"{left}{fill * padding}{right}\n"


def print_restaurant_receipt(order_data):
    """
    Prints a formatted receipt on a network ESC/POS thermal printer.

    order_data example (see build_receipt_data in views.py):
    {
        "bill_number": "B-00012",
        "table_name": "Table 1",
        "date": "2026-11-03 01:15 PM",
        "payment_method": "Cash",
        "items": [
            {"name": "Momo (Buff)", "price": 360, "qty": 2},
            {"name": "Masala Chiya", "price": 180, "qty": 3},
        ],
        "total": 540,
    }
    Returns True if printed, False if the printer was not reachable.
    """
    try:
        p = Network(
            settings.RECEIPT_PRINTER_HOST,
            settings.RECEIPT_PRINTER_PORT,
            timeout=5,
            profile="TM-T88III",
        )
    except Exception as e:
        print(f"Printer connection failed: {e}")
        return False

    try:
        # Header
        p.set(align="center", bold=True, font="a", double_width=True, double_height=True)
        p.text(f"{settings.RESTAURANT_NAME}\n")

        p.set(align="center", bold=False, font="a", normal_textsize=True)
        p.text(f"{settings.RESTAURANT_ADDRESS}\n")
        p.text(f"Tel: {settings.RESTAURANT_PHONE}\n")
        p.text("-" * LINE_WIDTH + "\n")

        p.set(align="left", bold=False, normal_textsize=True)
        p.text(f"Bill No: {order_data['bill_number']}\n")
        p.text(f"Date: {order_data['date']}\n")
        p.text(f"Table: {order_data['table_name']}\n")
        p.text("-" * LINE_WIDTH + "\n")

        # Items
        p.set(align="left", bold=True, normal_textsize=True)
        p.text("ORDER ITEMS\n")
        p.set(align="left", bold=False, normal_textsize=True)

        for item in order_data["items"]:
            line = f"{item.get('qty', 1)}x {item['name']}"
            p.text(two_columns(line, f"Rs. {item['price']:.2f}", fill="."))

        p.text("-" * LINE_WIDTH + "\n")

        # Total
        # Double height only: double width would not fit larger totals on 32 columns
        p.set(align="right", bold=True, double_height=True)
        p.text(f"TOTAL: Rs. {order_data['total']:.2f}\n")

        p.set(align="left", bold=False, normal_textsize=True)
        p.text(f"Paid by: {order_data['payment_method']}\n")

        # Footer
        p.set(align="center", bold=False, normal_textsize=True)
        p.text("\nThank you for dining with us!\n")

        feedback_url = settings.RECEIPT_FEEDBACK_URL
        if feedback_url:
            p.text("\nScan for Feedback:\n")
            try:
                p.qr(feedback_url)
            except Exception:
                p.text(f"{feedback_url}\n")

        p.text("\n\n")
        p.cut()
        return True

    except Exception:
        print("Print error:")
        traceback.print_exc()
        return False

    finally:
        try:
            p.close()
        except Exception:
            pass
