"""购物车接口用例。

重点在「状态」：同一个商品重复加购是累加还是覆盖？加购数量会不会超过库存？
这些规则如果没写清楚，UI 上就会表现为"加购后数量不对"，而测试要在这里兜住。
"""
from __future__ import annotations

import allure
import pytest

from api.constants import (
    CODE_PARAM_ERROR,
    CODE_PRODUCT_NOT_FOUND,
    CODE_STOCK_NOT_ENOUGH,
    CODE_UNAUTHORIZED,
    P_BAG,
    P_BUBBLE_WATER,
    P_COFFEE,
    P_LEMON,
    P_SOLD_OUT,
)
from api.services import CartApi
from common.asserts import assert_almost_equal, assert_biz_code, assert_biz_success, assert_http_status

pytestmark = [pytest.mark.api, allure.feature("购物车模块")]


@pytest.fixture()
def cart_api(base_url, auth_api):
    """复用已登录客户的 token，但用独立客户端，避免用例之间互相污染 header。"""
    client = CartApi(base_url=base_url)
    client.set_token(auth_api.token)
    yield client
    client.close()


@allure.story("加入购物车")
@allure.title("加购成功，购物车合计金额正确")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_add_to_cart_and_total(cart_api):
    assert_biz_success(cart_api.add(P_BUBBLE_WATER, 2))
    assert_biz_success(cart_api.add(P_COFFEE, 1))

    resp = cart_api.get_cart()
    assert_biz_success(resp)
    items = {i["product_id"]: i for i in resp.data["items"]}
    assert items[P_BUBBLE_WATER]["quantity"] == 2
    assert items[P_COFFEE]["quantity"] == 1
    # 5.9 * 2 + 49.0 * 1 = 60.8
    assert_almost_equal(resp.data["total_amount"], 60.8)


@allure.story("加入购物车")
@allure.title("同一商品重复加购应累加数量，而不是新增一行")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_add_same_product_twice(cart_api):
    cart_api.add(P_BUBBLE_WATER, 2)
    resp = cart_api.add(P_BUBBLE_WATER, 3)

    assert_biz_success(resp)
    assert resp.data["quantity"] == 5, "重复加购应累加为 5"

    items = cart_api.get_cart().data["items"]
    assert len(items) == 1, "同一商品不应出现多行"
    assert items[0]["quantity"] == 5


@allure.story("加入购物车")
@allure.title("加购数量超库存应被拒绝，且购物车数量保持不变")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_add_exceed_stock(cart_api):
    resp = cart_api.add(P_BAG, 9)          # 帆布托特包库存 8
    assert_biz_code(resp, CODE_STOCK_NOT_ENOUGH, "库存不足")

    assert cart_api.get_cart().data["items"] == [], "失败后不应写入购物车"


@allure.story("加入购物车")
@allure.title("累加后超过库存也应被拒绝（边界：8 件可，8+1 不可）")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_add_accumulate_exceed_stock(cart_api):
    assert_biz_success(cart_api.add(P_BAG, 8))
    resp = cart_api.add(P_BAG, 1)
    assert_biz_code(resp, CODE_STOCK_NOT_ENOUGH)

    items = cart_api.get_cart().data["items"]
    assert items[0]["quantity"] == 8, "失败后购物车数量应保持 8"


@allure.story("加入购物车")
@allure.title("售罄商品无法加购")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_add_sold_out_product(cart_api):
    resp = cart_api.add(P_SOLD_OUT, 1)
    assert_biz_code(resp, CODE_STOCK_NOT_ENOUGH)


@allure.story("加入购物车")
@allure.title("数量参数边界：0 和 100 非法，1 和 99 合法")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
@pytest.mark.parametrize("qty, valid", [(1, True), (99, False), (0, False), (-1, False), (100, False)])
def test_add_quantity_boundary(cart_api, qty, valid):
    """
    注意 99 这一条：参数校验通过了，但库存不够 99 件，所以业务上仍然返回「库存不足」。
    这正好说明「参数边界」和「业务边界」是两层校验，用例要分别覆盖。
    """
    resp = cart_api.add(P_COFFEE, qty)
    if valid:
        assert_biz_success(resp)
    elif qty == 99:
        assert_biz_code(resp, CODE_STOCK_NOT_ENOUGH)
    else:
        assert_http_status(resp, 422)
        assert resp.code == CODE_PARAM_ERROR


@allure.story("加入购物车")
@allure.title("未登录加购返回 401")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.p0
def test_add_without_login(base_url):
    client = CartApi(base_url=base_url)
    try:
        resp = client.add(P_BUBBLE_WATER, 1)
        assert_http_status(resp, 401)
        assert resp.code == CODE_UNAUTHORIZED
    finally:
        client.close()


@allure.story("加入购物车")
@allure.title("加购不存在的商品返回 404")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_add_not_exist_product(cart_api):
    resp = cart_api.add(99999, 1)
    assert_http_status(resp, 404)
    assert_biz_code(resp, CODE_PRODUCT_NOT_FOUND)


@allure.story("删除购物车商品")
@allure.title("删除已加购商品成功，重复删除返回业务错误")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_remove_cart_item(cart_api):
    cart_api.add(P_LEMON, 1)
    assert_biz_success(cart_api.remove(P_LEMON))
    assert cart_api.get_cart().data["items"] == []

    again = cart_api.remove(P_LEMON)
    assert_biz_code(again, CODE_PARAM_ERROR, "购物车中无此商品")
