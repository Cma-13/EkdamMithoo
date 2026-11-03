# EkdamMithoo – Restaurant Management System

**एकदम मीठो** ("really tasty") is a restaurant management system for a Nepali restaurant, built with Django.
It connects the whole restaurant in one app: customers see the menu and book tables on the website, waiters take orders,
the kitchen cooks from a live screen, the cashier takes payment and prints the receipt, and the owner sees sales and bookings.

---

## What it does

The app has a public website and four staff dashboards. Each staff member logs in and lands on the page for their role.

| Who | What they do |
|---|---|
| **Customers** (website, no login) | See today's favourite dishes and the full menu with prices, and book a table |
| **Waiter** | Picks a table, builds the order from the menu, gets an alert when food is ready, marks it served |
| **Kitchen** | Sees every dish being prepared, grouped by station and sorted by priority, marks it ready or cancels it |
| **Billing** | Sees which tables are ready to pay, takes payment (Cash, eSewa, Khalti or Fonepay) and prints the receipt |
| **Owner** | Sees revenue, top dishes, payment split, every bill, and confirms table bookings |

### How an order moves through the restaurant

```
Waiter places order ──► Kitchen sees it (Preparing)
                              │
                     marks Ready (or Cancels)
                              │
Waiter's table blinks ◄───────┘
Waiter serves, marks Served ──► Billing's table blinks when everything is served
                                         │
                              Cashier takes payment ──► Bill saved, receipt printed,
                                                        table is free again,
                                                        owner's numbers update
```

- Screens refresh every 5 seconds, so nobody has to reload the page to see new orders or ready food.
- The order status (Pending, Partially Served, Served, Billed) updates itself from its items using Django signals,
  and every change is saved in an order history.
- A table can only be billed once every item is served. Cancelled items never reach the bill.
- One bill covers all orders of a table visit, even if the customer ordered in several rounds.

---

## Features

**Website**
- Menu, prices, descriptions and photos come from the database. The owner changes them in admin and the website updates.
- Featured dishes ("Today's favourites") are picked with a tick box in admin.
- Online table booking with checks: no past dates, only up to 30 days ahead, only during opening hours,
  1 to 20 guests, and a valid Nepali phone number.

**Staff**
- Role-based login: waiter, kitchen, billing and owner each get their own pages. Opening another role's page sends you back to your own.
- Table grid with live status: free, occupied or reserved, plus a blink when food is ready (waiter) or the table is ready to pay (billing).
- Kitchen view filtered by station (steam, grill, main kitchen and so on), with priority and order time.
- Payment by Cash, eSewa, Khalti or Fonepay. Every payment is saved as a bill with a bill number, method and cashier.
- Thermal receipt printing over the network (ESC/POS), with a reprint button.
- Owner dashboard: revenue, number of bills, average bill, items sold, cancelled items, daily revenue chart,
  payment method split, top 5 dishes and live counts (tables occupied, items in the kitchen, bookings today).
- Bill history with date and payment filters, and a reservations page with Confirm, Arrived and Cancel.
- Styled confirmation dialogs instead of browser pop-ups, and works on phones and tablets.

**Code**
- 18 automated tests covering the full order flow, billing, owner pages, website menu and bookings.

---

## Tech stack

| Part | Used |
|---|---|
| Backend | Python, Django 6 |
| Database | SQLite |
| Frontend | Django templates, Tailwind CSS, vanilla JavaScript (polling with `fetch`) |
| Receipt printing | python-escpos (network ESC/POS printer) |
| Images | Pillow (menu photos) |

---

## Run it on your computer

You need **Python 3.12 or newer** and Git. The commands below are for Windows (Command Prompt).

```cmd
git clone https://github.com/Cma-13/RMS.git
cd RMS

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py create_tables --n 12
python manage.py create_basic_menuitems
python manage.py setup_website_menu
python manage.py create_demo_staff

python manage.py runserver
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

Open **http://127.0.0.1:8000** for the website. Click **Staff login** and use one of the demo accounts:

| Username | Password | Role |
|---|---|---|
| `waiter` | `demo12345` | Waiter |
| `kitchen` | `demo12345` | Kitchen |
| `billing` | `demo12345` | Billing |
| `owner` | `demo12345` | Owner (can also open Django admin) |

**Tip:** open each role in a different browser (or a private window) to watch an order move from waiter to kitchen to billing live.

### What the setup commands do

| Command | What it does |
|---|---|
| `create_tables --n 12` | Creates tables "Table 1" to "Table 12" |
| `create_basic_menuitems` | Adds kitchen stations, categories and 18 Nepali dishes |
| `setup_website_menu` | Adds descriptions, photos and featured dishes for the website (safe to run again) |
| `create_demo_staff` | Creates one login for each role (use `--password` to choose your own) |

### Run the tests

```cmd
python manage.py test
```

### Receipt printing (optional)

Receipts are sent to a network thermal printer at `127.0.0.1:9100`. Without a printer, payments still work and the app shows a
"printer not reachable" note. To see receipts without a real printer, run an ESC/POS printer emulator in Docker:

```cmd
docker run -d --name escpos-netprinter -p 9100:9100 -p 8081:80 gilbertfl/escpos-netprinter:3.2
```

Then open **http://localhost:8081** to see each printed receipt.

### Settings you can change

In `config/settings.py`: restaurant name, address, phone, opening hours, how far ahead bookings are allowed,
and the receipt printer address. To change the big photo on the website, put a photo at
`orders/static/orders/images/website-hero.jpg`.

---

## Project structure

```
RMS/
├── accounts/          Custom user with roles, login and logout
├── config/            Django settings and main URLs
└── orders/            The restaurant app
    ├── models.py      Table, Category, MenuItem, Order, OrderItem, OrderHistory, Bill, Reservation
    ├── views.py       Website, waiter, kitchen, billing and owner pages
    ├── forms.py       Table booking form and its checks
    ├── signals.py     Keeps order status in sync with its items
    ├── utils.py       Receipt printing
    ├── decorators.py  Role-based access
    ├── management/    Setup commands
    ├── templates/     All pages
    └── tests.py       Automated tests
```

---

## Known limitations

- Live updates use polling every 5 seconds, not WebSockets.
- eSewa, Khalti and Fonepay are recorded as the payment method. No money moves through the app itself.
- Bills are not IRD-certified tax invoices.
- SQLite is fine for a demo. A real restaurant would use PostgreSQL.

---

## Author

**Seema Singdan**, BSc. CSIT, Asian School of Management and Technology, Kathmandu
GitHub: [Cma-13](https://github.com/Cma-13)
