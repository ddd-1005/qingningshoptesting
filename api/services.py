"""接口对象层（Service Object / API Object）

把「某个接口怎么调」收敛到一个类里，用例只表达「我要登录」「我要下单」。
好处：接口一旦改字段，只改这一层；用例几乎不用动。
"""
from __future__ import annotations

from common.http_client import ApiResponse, HttpClient


class AuthApi(HttpClient):
    def login(self, username: str, password: str) -> ApiResponse:
        return self.post("/api/auth/login", json={"username": username, "password": password})

    def me(self) -> ApiResponse:
        return self.get("/api/auth/me")

    def login_and_hold(self, username: str, password: str) -> ApiResponse:
        """登录成功则把 token 挂到当前会话上，后续请求自动带 Authorization。"""
        resp = self.login(username, password)
        if resp.code == 0 and resp.data:
            self.set_token(resp.data["token"])
        return resp


class ProductApi(HttpClient):
    def list(self, **params) -> ApiResponse:
        return self.get("/api/products", params=params)

    def detail(self, product_id: int) -> ApiResponse:
        return self.get(f"/api/products/{product_id}")


class CartApi(HttpClient):
    def add(self, product_id: int, quantity: int = 1) -> ApiResponse:
        return self.post("/api/cart/items",
                         json={"product_id": product_id, "quantity": quantity})

    def get_cart(self) -> ApiResponse:
        # 注意：不能把方法命名为 get，否则会覆盖 HttpClient.get(path) 造成递归调用
        return self.get("/api/cart")

    def remove(self, product_id: int) -> ApiResponse:
        return self.delete(f"/api/cart/items/{product_id}")


class OrderApi(HttpClient):
    def create(self, request_id: str | None = None) -> ApiResponse:
        return self.post("/api/orders", json={"request_id": request_id})

    def list(self) -> ApiResponse:
        return self.get("/api/orders")

    def detail(self, order_no: str) -> ApiResponse:
        return self.get(f"/api/orders/{order_no}")
