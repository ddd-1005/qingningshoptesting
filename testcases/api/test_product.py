"""商品模块接口用例：分页、搜索、排序、边界值。

这组用例主要演示「边界值分析」怎么落地：
    页码 page 只有下界（>=1），size 有上下界（1~50），
    于是取 0 / 1 / 50 / 51 这些边界点，比"随便传几个数"覆盖度高得多。
"""
from __future__ import annotations

import allure
import pytest

from api.constants import (
    CODE_PARAM_ERROR,
    CODE_PRODUCT_NOT_FOUND,
    P_COFFEE,
    P_SOLD_OUT,
)
from api.services import ProductApi
from common.asserts import (
    assert_biz_code,
    assert_biz_success,
    assert_http_status,
)

pytestmark = [pytest.mark.api, allure.feature("商品模块")]


@pytest.fixture()
def product_api(base_url):
    client = ProductApi(base_url=base_url)
    yield client
    client.close()


@allure.story("商品列表")
@allure.title("默认分页返回全部上架商品，结构与总数正确")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_product_list_default(product_api):
    resp = product_api.list()
    assert_biz_success(resp)
    data = resp.data
    assert data["page"] == 1 and data["size"] == 10
    assert data["total"] == 6, "种子数据应有 6 个上架商品"
    assert len(data["items"]) == 6
    for item in data["items"]:
        assert item["price"] > 0, f"商品「{item['name']}」价格必须大于 0"
        assert item["stock"] >= 0, f"商品「{item['name']}」库存不能为负"


@allure.story("商品列表")
@allure.title("按关键字搜索：命中「咖啡」应只返回 1 条")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_product_search_hit(product_api):
    resp = product_api.list(keyword="咖啡")
    assert_biz_success(resp)
    assert resp.data["total"] == 1
    assert "咖啡" in resp.data["items"][0]["name"]


@allure.story("商品列表")
@allure.title("按关键字搜索：无匹配时返回空列表而不是报错")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_product_search_no_match(product_api):
    resp = product_api.list(keyword="这个商品不存在xyz")
    assert_biz_success(resp)
    assert resp.data["total"] == 0
    assert resp.data["items"] == []


@allure.story("商品列表")
@allure.title("价格升序 / 降序排序结果正确")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
@pytest.mark.parametrize("sort, reverse", [("price_asc", False), ("price_desc", True)])
def test_product_sort_by_price(product_api, sort, reverse):
    resp = product_api.list(sort=sort, size=50)
    assert_biz_success(resp)
    prices = [i["price"] for i in resp.data["items"]]
    expected = sorted(prices, reverse=reverse)
    assert prices == expected, f"排序 {sort} 结果不正确：{prices}"


@allure.story("商品列表")
@allure.title("size 边界值：1 和 50 合法，0 和 51 非法")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
@pytest.mark.parametrize("size, valid", [
    (1, True), (50, True), (0, False), (51, False), (-1, False),
])
def test_product_size_boundary(product_api, size, valid):
    resp = product_api.list(size=size)
    if valid:
        assert_biz_success(resp)
        assert resp.data["size"] == size
        assert len(resp.data["items"]) <= size
    else:
        assert_http_status(resp, 422)
        assert resp.code == CODE_PARAM_ERROR


@allure.story("商品列表")
@allure.title("page 边界值：页码超出范围返回空列表，page=0 非法")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p2
def test_product_page_boundary(product_api):
    assert_biz_success(product_api.list(page=1))

    beyond = product_api.list(page=99)
    assert_biz_success(beyond)
    assert beyond.data["items"] == [], "超出范围的页码应返回空列表"

    invalid = product_api.list(page=0)
    assert_http_status(invalid, 422)
    assert invalid.code == CODE_PARAM_ERROR


@allure.story("商品列表")
@allure.title("非法排序参数应返回业务错误码")
@allure.severity(allure.severity_level.MINOR)
@pytest.mark.p2
def test_product_invalid_sort(product_api):
    resp = product_api.list(sort="drop_table")
    assert_biz_code(resp, CODE_PARAM_ERROR, "排序")


@allure.story("商品详情")
@allure.title("查询存在的商品详情")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_product_detail(product_api):
    resp = product_api.detail(P_COFFEE)
    assert_biz_success(resp)
    assert resp.data["id"] == P_COFFEE
    assert resp.data["name"] == "冷萃咖啡液 10条装"
    assert resp.data["price"] == 49.0


@allure.story("商品详情")
@allure.title("商品不存在返回 404 + 业务码 2001")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_product_detail_not_exist(product_api):
    resp = product_api.detail(99999)
    assert_http_status(resp, 404)
    assert_biz_code(resp, CODE_PRODUCT_NOT_FOUND)


@allure.story("商品详情")
@allure.title("售罄商品仍在列表中展示，但库存为 0")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p2
def test_sold_out_product_visible(product_api):
    resp = product_api.detail(P_SOLD_OUT)
    assert_biz_success(resp)
    assert resp.data["stock"] == 0
