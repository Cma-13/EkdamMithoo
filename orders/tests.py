import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from .models import Table, Category, KitchenStation, MenuItem, Order, OrderItem, OrderHistory


class RestaurantFlowTests(TestCase):
    def setUp(self):
        self.waiter = User.objects.create_user("waiter", password="pass12345", role=User.ROLE_CHOICES.WAITER)
        self.kitchen = User.objects.create_user("kitchen", password="pass12345", role=User.ROLE_CHOICES.KITCHEN)
        self.billing = User.objects.create_user("billing", password="pass12345", role=User.ROLE_CHOICES.BILLING)
        self.owner = User.objects.create_user("owner", password="pass12345", role=User.ROLE_CHOICES.OWNER)

        self.table = Table.objects.create(name="Table 1")
        category = Category.objects.create(name="Momo")
        self.station = KitchenStation.objects.create(code="steam", name="Steam")
        self.momo = MenuItem.objects.create(category=category, name="Buff Momo", price=180, station=self.station)
        self.chiya = MenuItem.objects.create(category=category, name="Masala Chiya", price=60, station=None)

    # helpers -------------------------------------------------------------
    def place_order(self, items):
        self.client.force_login(self.waiter)
        payload = {"table_id": self.table.id, "items": items}
        return self.client.post(
            reverse("menu_view_url", args=[self.table.id]),
            {"order-items": json.dumps(payload)},
        )

    # login ---------------------------------------------------------------
    def test_login_redirects_each_role(self):
        expected = {
            "waiter": reverse("tables_view_url"),
            "kitchen": reverse("kitchen_dashboard_view_url"),
            "billing": reverse("tables_for_billing_url"),
            "owner": reverse("admin:index"),
        }
        for username, url in expected.items():
            response = self.client.post(reverse("login_view_url"), {"username": username, "password": "pass12345"})
            self.assertRedirects(response, url, fetch_redirect_response=False)
            self.client.logout()

    def test_user_without_role_cannot_log_in(self):
        User.objects.create_user("norole", password="pass12345")
        response = self.client.post(reverse("login_view_url"), {"username": "norole", "password": "pass12345"})
        self.assertRedirects(response, reverse("login_view_url"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_role_is_sent_to_own_dashboard(self):
        self.client.force_login(self.kitchen)
        response = self.client.get(reverse("tables_view_url"))
        self.assertRedirects(response, reverse("kitchen_dashboard_view_url"), fetch_redirect_response=False)

    # ordering ------------------------------------------------------------
    def test_empty_order_is_rejected(self):
        response = self.place_order([])
        self.assertRedirects(response, reverse("menu_view_url", args=[self.table.id]), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)

    def test_place_order_marks_table_occupied(self):
        self.place_order([{"item_id": self.momo.id, "quantity": 2}])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.get().quantity, 2)
        self.assertEqual(self.table.status, "occupied")

    # kitchen -------------------------------------------------------------
    def test_kitchen_dashboard_and_live_view_work_without_station(self):
        self.place_order([{"item_id": self.momo.id, "quantity": 1}, {"item_id": self.chiya.id, "quantity": 1}])
        self.client.force_login(self.kitchen)
        for url in [reverse("kitchen_dashboard_view_url"), reverse("kitchen_dashboard_view_live_url")]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Steam")
            self.assertContains(response, "Unassigned")

        response = self.client.get(reverse("kitchen_dashboard_view_live_url") + "?station_code=steam")
        self.assertContains(response, "Buff Momo")
        self.assertNotContains(response, "Masala Chiya")

    def test_kitchen_cancel_really_cancels(self):
        self.place_order([{"item_id": self.momo.id, "quantity": 1}])
        item = OrderItem.objects.get()
        self.client.force_login(self.kitchen)
        self.client.post(reverse("kitchen_item_view_url", args=[item.id]), {"status": "cancel"})
        item.refresh_from_db()
        self.assertEqual(item.status, OrderItem.ITEM_STATUS.CANCELLED)
        self.assertEqual(item.order.status, Order.ORDER_STATUS.CANCELLED)
        self.assertEqual(self.table.status, "free")

    # full flow + billing ---------------------------------------------------
    @patch("orders.views.print_restaurant_receipt", return_value=False)
    def test_full_flow_ready_served_paid(self, mock_print):
        self.place_order([{"item_id": self.momo.id, "quantity": 2}, {"item_id": self.chiya.id, "quantity": 1}])
        momo_item = OrderItem.objects.get(menu_item=self.momo)
        chiya_item = OrderItem.objects.get(menu_item=self.chiya)

        # kitchen: momo ready, chiya cancelled
        self.client.force_login(self.kitchen)
        self.client.post(reverse("kitchen_item_view_url", args=[momo_item.id]), {"status": "ready"})
        self.client.post(reverse("kitchen_item_view_url", args=[chiya_item.id]), {"status": "cancel"})

        # waiter sees the ready table, serves momo
        self.client.force_login(self.waiter)
        self.assertEqual(self.client.get(reverse("tables_status_live_url")).json()["tables"], [self.table.id])
        self.client.post(reverse("served_confirmation_url", args=[momo_item.id]))
        order = Order.objects.get()
        self.assertEqual(order.status, Order.ORDER_STATUS.SERVED)

        # billing: table ready, total excludes the cancelled chiya
        self.client.force_login(self.billing)
        self.assertEqual(self.client.get(reverse("billing_tables_status_live_url")).json()["tables"], [self.table.id])
        response = self.client.get(reverse("billing_view_url", args=[self.table.id]))
        self.assertEqual(response.context["total"], 360)
        self.assertTrue(response.context["proceed_billing"])

        self.client.post(reverse("billing_paid_view_url", args=[self.table.id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.ORDER_STATUS.BILLED)
        self.assertTrue(OrderHistory.objects.filter(order=order, status=Order.ORDER_STATUS.BILLED).exists())
        self.assertEqual(mock_print.call_args[0][0]["total"], 360)
        self.assertEqual(self.table.status, "free")

        # bill is cleared: nothing left to pay
        response = self.client.get(reverse("billing_view_url", args=[self.table.id]))
        self.assertEqual(response.context["total"], 0)

    def test_cannot_pay_before_everything_is_served(self):
        self.place_order([{"item_id": self.momo.id, "quantity": 1}])
        self.client.force_login(self.billing)
        response = self.client.get(reverse("billing_view_url", args=[self.table.id]))
        self.assertFalse(response.context["proceed_billing"])
        self.client.post(reverse("billing_paid_view_url", args=[self.table.id]))
        self.assertNotEqual(Order.objects.get().status, Order.ORDER_STATUS.BILLED)

    def test_paid_view_rejects_get(self):
        self.client.force_login(self.billing)
        response = self.client.get(reverse("billing_paid_view_url", args=[self.table.id]))
        self.assertEqual(response.status_code, 405)

    # pages render ----------------------------------------------------------
    def test_pages_render(self):
        self.place_order([{"item_id": self.momo.id, "quantity": 1}])
        item = OrderItem.objects.get()
        self.assertEqual(self.client.get(reverse("home_view")).status_code, 200)
        self.client.force_login(self.waiter)
        self.assertEqual(self.client.get(reverse("tables_view_url")).status_code, 200)
        self.assertEqual(self.client.get(reverse("menu_view_url", args=[self.table.id])).status_code, 200)
        self.client.force_login(self.kitchen)
        self.assertEqual(self.client.get(reverse("kitchen_item_view_url", args=[item.id])).status_code, 200)
        self.client.force_login(self.billing)
        self.assertEqual(self.client.get(reverse("tables_for_billing_url")).status_code, 200)
