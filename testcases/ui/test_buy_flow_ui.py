"""UI 主流程用例：加购 → 结算 → 订单页。

这是 UI 自动化的"冒烟五条"里最值钱的一条：它验证的是前端 + 后端 + 页面的完整串联。
真实项目里这条跑通，就说明核心交易链路没断。
"""
from __future__ import annotations

import allure
import pytest

from api.constants import P_BUBBLE_WATER, P_LEMON

pytestmark = [pytest.mark.ui, allure.feature("Web UI - 购物流程")]


@allure.story("加入购物车")
@allure.title("点击加入购物车后，右上角角标数量实时更新")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.smoke
@pytest.mark.p0
def test_add_to_cart_updates_badge(products_page):
    with allure.step("断言购物车初始为空"):
        products_page.wait_cart_count(0)

    with allure.step("点击第一个商品的「加入购物车」"):
        products_page.add_to_cart(P_BUBBLE_WATER)

    with allure.step("断言角标变成 1（显式等待，不用 sleep）"):
        assert products_page.wait_cart_count(1), "加购后购物车角标未更新"

    with allure.step("重复加购，断言角标累加为 2"):
        products_page.add_to_cart(P_BUBBLE_WATER)
        assert products_page.wait_cart_count(2)


@allure.story("下单主流程")
@allure.title("加购两件不同商品→购物车金额正确→提交订单→订单页可见")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_full_purchase_flow(products_page, cart_page, orders_page):
    with allure.step("加购：气泡水 ¥5.9 ×1，黄柠檬 ¥12.8 ×1"):
        products_page.add_to_cart(P_BUBBLE_WATER)
        assert products_page.wait_cart_count(1)
        products_page.add_to_cart(P_LEMON)
        assert products_page.wait_cart_count(2)

    with allure.step("进入购物车，断言两行商品 + 合计 ¥18.70"):
        products_page.go_to_cart()
        cart_page.wait_url_contains("/cart")
        assert cart_page.row_count == 2
        assert cart_page.wait_total("¥18.70"), f"合计金额不正确：{cart_page.total_text}"

    with allure.step("提交订单，断言跳转到订单页"):
        cart_page.checkout()
        orders_page.wait_url_contains("/orders")

    with allure.step("断言订单页出现 1 笔订单，订单号有业务前缀，金额一致"):
        assert orders_page.order_count == 1
        order_no = orders_page.order_numbers[0]
        assert order_no.startswith("MM"), f"订单号格式异常：{order_no}"
        assert "18.70" in orders_page.first_amount

    with allure.step("回到购物车，断言已清空"):
        cart_page.load()
        assert cart_page.is_empty(), "下单成功后购物车应被清空"


@allure.story("搜索")
@allure.title("搜索无结果时展示空态提示，而不是空白页面")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_search_no_result_shows_empty_state(products_page):
    products_page.search("这个商品不存在xyz")
    assert products_page.has_empty_state(), "无结果时应展示空态文案"
    assert products_page.product_count == 0


@allure.story("搜索")
@allure.title("按关键字搜索能筛出目标商品")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_search_hit(products_page):
    products_page.search("咖啡")
    assert products_page.wait_product_count(1), "搜索结果数量不正确"
    products_page.wait_text("product-name", "冷萃咖啡液 10条装")
    assert products_page.product_count == 1


@allure.story("售罄处理")
@allure.title("售罄商品按钮置灰且不可点击")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_sold_out_button_disabled(products_page):
    btn = products_page.find("add-cart-6")
    assert not btn.is_enabled(), "售罄商品的加购按钮必须置灰"
    assert "已售罄" in btn.text
