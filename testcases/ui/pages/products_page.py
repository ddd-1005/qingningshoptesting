"""商品列表页对象。"""
from __future__ import annotations

import allure

from testcases.ui.pages.base_page import BasePage


class ProductsPage(BasePage):
    PATH = "/products"

    def load(self) -> "ProductsPage":
        self.open(self.PATH)
        self.find("product-list")
        return self

    # ---------------- 查询 ---------------- #
    @property
    def product_count(self) -> int:
        return len(self.find_all("product-card"))

    @property
    def product_names(self) -> list[str]:
        return [el.text.strip() for el in self.find_all("product-name")]

    @property
    def cart_count(self) -> str:
        return self.text_of("cart-count")

    def has_empty_state(self) -> bool:
        return self.exists("empty-products", timeout=5)

    # ---------------- 操作 ---------------- #
    @allure.step("搜索商品：{keyword}")
    def search(self, keyword: str) -> "ProductsPage":
        self.type("search-input", keyword)
        self.click("search-btn")
        return self

    @allure.step("把商品 {product_id} 加入购物车")
    def add_to_cart(self, product_id: int) -> "ProductsPage":
        self.click(f"add-cart-{product_id}")
        return self

    def wait_cart_count(self, expected: int) -> bool:
        """等购物车角标变成期望值：接口是异步的，不能点完立刻断言。"""
        return self.wait_text("cart-count", str(expected))

    def go_to_cart(self) -> None:
        self.click("go-cart")
