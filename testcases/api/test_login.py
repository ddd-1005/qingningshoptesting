"""登录模块接口用例。

设计思路（面试可讲）：
    - 正常场景只写必要的几条，重点铺在异常与边界上；
    - 异常用例用「等价类 + 数据驱动」，把用例数据放 YAML，代码只写一份；
    - 不只断言 code，还要断言「提示语」和「拿到的 token 真的能用」。
"""
from __future__ import annotations

from pathlib import Path

import allure
import pytest
import yaml

from api.constants import CODE_LOGIN_FAILED, CODE_PARAM_ERROR, CODE_UNAUTHORIZED
from common.asserts import assert_biz_code, assert_biz_success, assert_http_status, assert_schema

DATA_FILE = Path(__file__).parent / "data" / "login_cases.yaml"
LOGIN_CASES = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))

pytestmark = [pytest.mark.api, allure.feature("用户模块")]


@allure.story("登录成功")
@allure.title("正确账号密码登录成功，返回可直接使用的 token")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_login_success(anon_api):
    with allure.step("调用登录接口"):
        resp = anon_api.login("test01", "123456")

    with allure.step("校验响应结构与业务码"):
        assert_biz_success(resp)
        assert_schema(resp.data, {
            "token": str,
            "user": {"id": int, "username": str, "nickname": str},
        })
        assert resp.data["user"]["username"] == "test01"

    with allure.step("校验 token 真的可用于鉴权（而不是随便返回一个字符串）"):
        anon_api.set_token(resp.data["token"])
        me = anon_api.me()
        assert_biz_success(me)
        assert me.data["username"] == "test01"


@allure.story("登录失败")
@allure.title("异常登录场景：{case[title]}")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
@pytest.mark.parametrize("case", LOGIN_CASES, ids=[c["case_id"] for c in LOGIN_CASES])
def test_login_failed_cases(anon_api, case):
    resp = anon_api.login(case["username"], case["password"])
    assert_biz_code(resp, case["expect_code"], case["expect_msg"])
    assert resp.data is None, "登录失败时不应返回任何数据"


@allure.story("登录失败")
@allure.title("登录失败不返回 token，也无法用空 token 访问受保护接口")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_login_failed_then_access_denied(anon_api):
    resp = anon_api.login("test01", "wrong_password")
    assert_biz_code(resp, CODE_LOGIN_FAILED)

    # 关键：失败后不应产生任何可用凭证
    assert anon_api.me().code == CODE_UNAUTHORIZED


@allure.story("参数校验")
@allure.title("账号密码参数校验：{desc}")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
@pytest.mark.parametrize("payload, bad_field, desc", [
    ({"username": "abc", "password": "123456"}, "username", "用户名少于 4 位"),
    ({"username": "a" * 21, "password": "123456"}, "username", "用户名超过 20 位"),
    ({"username": "test01", "password": "12345"}, "password", "密码少于 6 位"),
    ({"username": "test01", "password": "1" * 21}, "password", "密码超过 20 位"),
    ({"username": "test01"}, "password", "缺少密码字段"),
    ({"password": "123456"}, "username", "缺少用户名字段"),
    ({"username": 12345678, "password": "123456"}, "username", "用户名传数字类型"),
])
def test_login_param_validation(anon_api, payload, bad_field, desc):
    with allure.step(f"提交非法参数：{desc}"):
        resp = anon_api.post("/api/auth/login", json=payload)

    assert_http_status(resp, 422)
    assert resp.code == CODE_PARAM_ERROR
    fields = [e["field"] for e in resp.data["errors"]]
    assert bad_field in fields, f"期望 {bad_field} 报错，实际报错字段：{fields}"


@allure.story("鉴权")
@allure.title("伪造 / 过期 token 访问受保护接口应返回 401")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
@pytest.mark.parametrize("fake_token", ["", "fake-token-123", "Bearer", "a" * 64])
def test_invalid_token_rejected(anon_api, fake_token):
    anon_api.session.headers["Authorization"] = f"Bearer {fake_token}"
    resp = anon_api.me()
    assert_http_status(resp, 401)
    assert resp.code == CODE_UNAUTHORIZED
