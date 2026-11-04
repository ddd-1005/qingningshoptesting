"""UI 用例的公共夹具。

三条纪律（新手最容易踩的坑都在这）：
    1. 每条用例开始前清空 localStorage + 重置后端数据 —— 否则上一条用例的登录态/购物车会串味；
    2. 用例里不写 driver.find_element，全部通过 Page 对象操作；
    3. 任何"点完立刻断言"的地方都要用显式等待，因为页面是异步渲染的。
"""
from __future__ import annotations

import pytest
import requests

from common.config import settings
from testcases.ui.pages.cart_page import CartPage
from testcases.ui.pages.login_page import LoginPage
from testcases.ui.pages.orders_page import OrdersPage
from testcases.ui.pages.products_page import ProductsPage


@pytest.fixture(autouse=True)
def clean_state(driver, base_url):
    """重置后端数据 + 清空浏览器存储，保证每条用例都在同一起点。"""
    requests.post(f"{base_url}/api/test/reset", timeout=5)
    driver.get(f"{base_url}/login")
    driver.execute_script("localStorage.clear(); sessionStorage.clear();")
    yield


@pytest.fixture()
def login_page(driver, base_url) -> LoginPage:
    return LoginPage(driver, base_url).load()


@pytest.fixture()
def logged_in(driver, base_url) -> LoginPage:
    """已通过 UI 真实登录的状态（前置条件写在夹具里，用例只关注自己要验证的事）。"""
    page = LoginPage(driver, base_url).load()
    page.login(settings.user_name, settings.user_pwd)
    page.wait_url_contains("/products")
    return page


@pytest.fixture()
def products_page(driver, base_url, logged_in) -> ProductsPage:
    return ProductsPage(driver, base_url).load()


@pytest.fixture()
def cart_page(driver, base_url) -> CartPage:
    return CartPage(driver, base_url)


@pytest.fixture()
def orders_page(driver, base_url) -> OrdersPage:
    return OrdersPage(driver, base_url)
