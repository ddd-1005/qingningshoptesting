"""购物车页对象。"""
from __future__ import annotations

import allure

from testcases.ui.pages.base_page import BasePage


class CartPage(BasePage):
    PATH = "/cart"

    def load(self) -> "CartPage":
        self.open(self.PATH)
        # 购物车是异步渲染的：要么有商品行，要么是空态，等出现任意一个再继续
        self.wait_first(["cart-row", "cart-empty"])
        return self

    @property
    def row_count(self) -> int:
        return len(self.find_all("cart-row"))

    @property
    def total_text(self) -> str:
        return self.text_of("cart-total")

    def is_empty(self) -> bool:
        return self.exists("cart-empty", timeout=5)

    def wait_total(self, expected: str) -> bool:
        return self.wait_text("cart-total", expected)

    @allure.step("提交订单")
    def checkout(self) -> None:
        self.click("checkout-btn")
