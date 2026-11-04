"""订单列表页对象。"""
from __future__ import annotations

from testcases.ui.pages.base_page import BasePage


class OrdersPage(BasePage):
    PATH = "/orders"

    def load(self) -> "OrdersPage":
        self.open(self.PATH)
        return self

    @property
    def order_count(self) -> int:
        """等待订单列表渲染完成，避免"页面还没加载就数元素"。"""
        self.wait_url_contains("/orders")
        self.find("order-list")
        return len(self.find_all("order-item"))

    @property
    def order_numbers(self) -> list[str]:
        return [el.text.strip() for el in self.find_all("order-no")]

    @property
    def first_amount(self) -> str:
        return self.text_of("order-amount")

    def is_empty(self) -> bool:
        return self.exists("empty-orders", timeout=5)
