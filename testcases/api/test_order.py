"""订单模块 —— 核心链路用例（P0）。

这组用例是整个项目的"技术含量担当"，覆盖三件事：
  1. 端到端主链路：加购 → 下单 → 查订单，并且**校验数据库真的落库了**
  2. 幂等：同一个 request_id 重复提交只生成一单、只扣一次库存
  3. 并发：用户连点 10 次提交，只能成功 1 单（防重复下单 / 防超卖）
面试被问"你的自动化怎么保证不是只跑了表面"，答案就在这个文件里。
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import allure
import pytest

from api.constants import (
    CODE_CART_EMPTY,
    CODE_ORDER_NOT_FOUND,
    CODE_STOCK_NOT_ENOUGH,
    CODE_UNAUTHORIZED,
    P_BAG,
    P_BUBBLE_WATER,
    P_COFFEE,
    P_LEMON,
)
from api.services import AuthApi, CartApi, OrderApi
from common import db
from common.asserts import (
    assert_almost_equal,
    assert_biz_code,
    assert_biz_success,
    assert_http_status,
    assert_schema,
)

pytestmark = [pytest.mark.api, allure.feature("订单模块")]


@pytest.fixture()
def cart_api(base_url, auth_api):
    client = CartApi(base_url=base_url)
    client.set_token(auth_api.token)
    yield client
    client.close()


@pytest.fixture()
def order_api(base_url, auth_api):
    client = OrderApi(base_url=base_url)
    client.set_token(auth_api.token)
    yield client
    client.close()


@allure.story("下单主链路")
@allure.title("加购→下单→查订单：金额、库存、订单表、购物车四处状态一致")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_create_order_end_to_end(cart_api, order_api):
    with allure.step("准备数据：加购 2 件气泡水 + 1 件黄柠檬"):
        assert_biz_success(cart_api.add(P_BUBBLE_WATER, 2))
        assert_biz_success(cart_api.add(P_LEMON, 1))
        stock_water_before = db.get_stock(P_BUBBLE_WATER)
        stock_lemon_before = db.get_stock(P_LEMON)

    with allure.step("提交订单"):
        resp = order_api.create(request_id=f"REQ-{uuid.uuid4().hex[:8]}")
        assert_biz_success(resp)
        assert_schema(resp.data, {"order_no": str, "total_amount": float, "status": str})
        order_no = resp.data["order_no"]
        assert order_no.startswith("MM"), "订单号应有业务前缀，便于对账定位"

    with allure.step("断言 1：金额 = 各商品单价 × 数量之和"):
        assert_almost_equal(resp.data["total_amount"], 5.9 * 2 + 12.8)

    with allure.step("断言 2：数据库里真的有这张订单，且明细正确"):
        order_row = db.get_order(order_no)
        assert order_row is not None, f"订单 {order_no} 未落库"
        assert order_row["status"] == "created"
        assert_almost_equal(order_row["total_amount"], 24.6)
        items = db.get_order_items(order_no)
        assert len(items) == 2, "订单明细应有 2 行"

    with allure.step("断言 3：库存按购买数量扣减（防「接口成功但库存没扣」的资损类缺陷）"):
        assert db.get_stock(P_BUBBLE_WATER) == stock_water_before - 2
        assert db.get_stock(P_LEMON) == stock_lemon_before - 1

    with allure.step("断言 4：下单后购物车被清空"):
        assert cart_api.get_cart().data["items"] == []

    with allure.step("断言 5：订单列表与详情能查到同一笔订单"):
        listed = order_api.list()
        assert_biz_success(listed)
        assert order_no in [o["order_no"] for o in listed.data["items"]]
        detail = order_api.detail(order_no)
        assert_biz_success(detail)
        assert len(detail.data["items"]) == 2


@allure.story("下单主链路")
@allure.title("金额精度：5.9 × 3 应为 17.70，不出现浮点误差")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_order_amount_precision(cart_api, order_api):
    cart_api.add(P_BUBBLE_WATER, 3)
    resp = order_api.create()
    assert_biz_success(resp)
    assert_almost_equal(resp.data["total_amount"], 17.7)
    assert resp.data["total_amount"] == round(resp.data["total_amount"], 2), "金额必须保留 2 位小数"


@allure.story("下单校验")
@allure.title("购物车为空时不允许下单")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_order_with_empty_cart(order_api):
    resp = order_api.create()
    assert_biz_code(resp, CODE_CART_EMPTY, "购物车为空")


@allure.story("下单校验")
@allure.title("未登录下单返回 401")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.p0
def test_order_without_login(base_url):
    client = OrderApi(base_url=base_url)
    try:
        resp = client.create()
        assert_http_status(resp, 401)
        assert resp.code == CODE_UNAUTHORIZED
    finally:
        client.close()


@allure.story("库存竞争")
@allure.title("下单时库存已被他人买完，应拦截并保留购物车数据")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_order_stock_grabbed_by_others(base_url, cart_api, order_api):
    with allure.step("用户 A 把仅剩 8 件的托特包全部加购"):
        assert_biz_success(cart_api.add(P_BAG, 8))

    with allure.step("用户 B 抢先下单买走全部库存"):
        other = AuthApi(base_url=base_url)
        other.login_and_hold("test02", "123456")
        other_cart = CartApi(base_url=base_url)
        other_cart.set_token(other.token)
        assert_biz_success(other_cart.add(P_BAG, 8))
        other_order = OrderApi(base_url=base_url)
        other_order.set_token(other.token)
        assert_biz_success(other_order.create())
        assert db.get_stock(P_BAG) == 0
        other.close()
        other_cart.close()
        other_order.close()

    with allure.step("用户 A 再提交订单 → 应提示库存不足"):
        resp = order_api.create()
        assert_biz_code(resp, CODE_STOCK_NOT_ENOUGH, "库存不足")

    with allure.step("关键断言：失败不能扣库存、不能生成订单、购物车数据要保留"):
        assert db.get_stock(P_BAG) == 0, "下单失败不应再扣库存（也不能扣成负数）"
        assert len(order_api.list().data["items"]) == 0, "用户 A 不应看到任何订单"
        assert len(cart_api.get_cart().data["items"]) == 1, "失败后购物车不应被清空，否则用户要重新加购"


@allure.story("幂等")
@allure.title("同一 request_id 重复提交只生成一单，库存只扣一次")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_order_idempotent(cart_api, order_api):
    cart_api.add(P_BUBBLE_WATER, 2)
    stock_before = db.get_stock(P_BUBBLE_WATER)
    request_id = f"REQ-{uuid.uuid4().hex[:8]}"

    first = order_api.create(request_id=request_id)
    assert_biz_success(first)
    assert first.data["idempotent"] is False

    second = order_api.create(request_id=request_id)
    assert_biz_success(second)
    assert second.data["idempotent"] is True, "重复提交应命中幂等逻辑"
    assert second.data["order_no"] == first.data["order_no"], "幂等返回的必须是同一张订单"

    assert db.count_orders_by_request(request_id) == 1, "数据库不应出现两张订单"
    assert db.get_stock(P_BUBBLE_WATER) == stock_before - 2, "库存只能扣一次"


@allure.story("并发")
@allure.title("用户连点 10 次提交订单，只允许成功 1 单")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_order_concurrent_submit(base_url, cart_api, auth_api):
    cart_api.add(P_COFFEE, 1)
    stock_before = db.get_stock(P_COFFEE)

    def submit(_: int):
        client = OrderApi(base_url=base_url)
        client.set_token(auth_api.token)
        try:
            r = client.create(request_id=f"REQ-{uuid.uuid4().hex[:10]}")
            return r.code
        finally:
            client.close()

    barrier = threading.Barrier(10)

    def submit_synced(i: int):
        barrier.wait()          # 10 个线程同时起跑，最大化制造并发
        return submit(i)

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(submit_synced, range(10)))

    success = codes.count(0)
    assert success == 1, f"并发提交应只成功 1 次，实际成功 {success} 次；返回码分布：{codes}"
    assert db.get_stock(P_COFFEE) == stock_before - 1, "库存只应扣减 1 件"
    assert len(auth_api.get("/api/orders").data["items"]) == 1, "只应生成 1 张订单"


@allure.story("越权")
@allure.title("用户 B 无法查看用户 A 的订单（水平越权）")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_order_cross_user_access(base_url, cart_api, order_api):
    cart_api.add(P_LEMON, 1)
    order_no = order_api.create().data["order_no"]

    other = AuthApi(base_url=base_url)
    other.login_and_hold("test02", "123456")
    try:
        resp = other.get(f"/api/orders/{order_no}")
        assert_http_status(resp, 404)
        assert_biz_code(resp, CODE_ORDER_NOT_FOUND)
    finally:
        other.close()
