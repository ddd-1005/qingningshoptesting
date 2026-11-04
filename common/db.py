"""数据库校验工具 —— 用来做「接口返回」与「DB 真实状态」的一致性断言。

为什么必须要有这一层？
    只断言接口响应，等于「相信被测系统的说法」。查一次库才知道它到底有没有把
    库存扣掉、订单有没有真正落库。这是面试里区分「会写脚本」和「懂测试」的分水岭。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from common.config import settings


def db_file() -> Path:
    """每次调用都读环境变量：这样 conftest 拉起临时库后，断言层能立刻跟上。"""
    return Path(os.getenv("MINIMALL_DB_PATH", str(settings.db_path)))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_file().as_posix()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def query_one(sql: str, args: tuple = ()) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


def query_all(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


# ---------------- 业务常用的封装 ---------------- #
def get_stock(product_id: int) -> int:
    row = query_one("SELECT stock FROM products WHERE id=?", (product_id,))
    assert row is not None, f"商品 {product_id} 不存在"
    return row["stock"]


def get_price(product_id: int) -> float:
    row = query_one("SELECT price FROM products WHERE id=?", (product_id,))
    assert row is not None, f"商品 {product_id} 不存在"
    return row["price"]


def get_order(order_no: str) -> dict[str, Any] | None:
    return query_one("SELECT * FROM orders WHERE order_no=?", (order_no,))


def get_order_items(order_no: str) -> list[dict[str, Any]]:
    return query_all(
        "SELECT oi.* FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.order_no=?",
        (order_no,),
    )


def count_orders_by_request(request_id: str) -> int:
    row = query_one("SELECT COUNT(1) AS c FROM orders WHERE request_id=?", (request_id,))
    return row["c"] if row else 0
