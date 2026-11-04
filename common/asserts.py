"""断言工具箱 —— 用例里只写「期望什么」，不写「怎么比」。

分三层，这是接口自动化的核心思想：
  1) 协议层：HTTP 状态码（401/404 这类）
  2) 业务层：code / msg（业务错误码）
  3) 数据层：字段结构、值、以及「接口返回 vs 数据库落库」是否一致
只断言第 1 层是不够的 —— 接口返回 200 但库存没扣，线上就是资损。
"""
from __future__ import annotations

from typing import Any

from common.http_client import ApiResponse


def assert_http_status(resp: ApiResponse, expected: int) -> None:
    assert resp.status_code == expected, (
        f"HTTP 状态码期望 {expected}，实际 {resp.status_code}；响应体：{resp.body}"
    )


def assert_biz_success(resp: ApiResponse) -> None:
    """业务成功：HTTP 200 + code == 0。"""
    assert resp.status_code == 200, f"HTTP 状态码期望 200，实际 {resp.status_code}，响应：{resp.body}"
    assert resp.code == 0, f"业务码期望 0，实际 {resp.code}（{resp.msg}）"


def assert_biz_code(resp: ApiResponse, expected_code: int, expected_msg: str | None = None) -> None:
    """业务失败：断言错误码，必要时模糊匹配提示文案（文案会改，所以默认只比对关键词）。"""
    assert resp.code == expected_code, f"业务码期望 {expected_code}，实际 {resp.code}（{resp.msg}）"
    if expected_msg:
        assert expected_msg in resp.msg, f"提示语应包含「{expected_msg}」，实际「{resp.msg}」"


def assert_schema(data: Any, spec: dict[str, type | dict]) -> None:
    """轻量结构校验：只校验「关键字段存在且类型对」，比 jsonschema 更好维护。

    spec 示例：{"token": str, "user": {"id": int, "username": str}}
    """
    assert isinstance(data, dict), f"期望 dict，实际 {type(data).__name__}: {data}"
    for key, expected in spec.items():
        assert key in data, f"响应缺少字段「{key}」，实际字段：{list(data)}"
        if isinstance(expected, dict):
            assert_schema(data[key], expected)
        else:
            assert isinstance(data[key], expected), (
                f"字段「{key}」类型期望 {expected.__name__}，实际 {type(data[key]).__name__}"
            )


def assert_almost_equal(actual: float, expected: float, tol: float = 1e-6) -> None:
    """金额比较必须带容差 —— 浮点数直接 == 会偶发失败（这是真实的坑）。"""
    assert abs(actual - expected) <= tol, f"金额期望 {expected}，实际 {actual}"


def assert_increasing(values: list[float]) -> None:
    assert values == sorted(values), f"期望升序，实际 {values}"
