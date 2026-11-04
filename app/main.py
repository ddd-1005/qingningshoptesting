"""
青柠商城 Mini Mall —— 被测系统（SUT, System Under Test）

这是一个自研的轻量电商后端 + 网页端，只为「自动化测试项目」提供真实、可控的被测对象：
  - 有真实业务规则（登录鉴权、库存扣减、限购、下单幂等）
  - 有真实数据落库（SQLite），可以断言「接口返回」与「数据库状态」是否一致
  - 有网页端（登录 / 商品 / 购物车 / 订单），可以跑 Selenium UI 自动化

启动方式：
    uvicorn app.main:app --port 8000

设计说明（面试可讲）：
    真实项目里被测系统由开发提供，测试不应该「改」它。这里自研是为了让你能：
    1) 完全掌握业务规则，断言才有依据；
    2) 想造什么缺陷就造什么缺陷（比如把库存扣减写成 -=0），用来验证用例能不能抓到 bug。
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
DB_PATH = Path(os.getenv("MINIMALL_DB_PATH", BASE_DIR / "data" / "minimall.db"))
# 测试专用开关：为 1 时才暴露 /api/test/reset 这类「造数/清数」接口
TEST_MODE = os.getenv("MINIMALL_TEST_MODE", "0") == "1"

_db_lock = threading.Lock()
# token -> {"user_id": int, "expire_at": float}；内存态即可，重启失效（本身也是一个可测点）
_tokens: dict[str, dict[str, Any]] = {}

# 业务错误码（统一响应体 code 字段）
CODE_OK = 0
CODE_PARAM_ERROR = 1001
CODE_UNAUTHORIZED = 1002
CODE_LOGIN_FAILED = 1003
CODE_ACCOUNT_LOCKED = 1004
CODE_PRODUCT_NOT_FOUND = 2001
CODE_STOCK_NOT_ENOUGH = 2002
CODE_CART_EMPTY = 2004
CODE_ORDER_NOT_FOUND = 3001


# --------------------------------------------------------------------------- #
# 数据库
# --------------------------------------------------------------------------- #
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    nickname TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'   -- active / locked
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL,
    category TEXT NOT NULL DEFAULT '默认',
    status TEXT NOT NULL DEFAULT 'on'       -- on / off
);
CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    UNIQUE (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    request_id TEXT UNIQUE,                  -- 幂等键
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL
);
"""

SEED_USERS = [
    ("test01", "123456", "测试小柠", "active"),
    ("test02", "123456", "测试小檬", "active"),
    ("locked01", "123456", "被锁定的账号", "locked"),
]
SEED_PRODUCTS = [
    ("青柠气泡水 330ml", 5.9, 120, "饮料"),
    ("冷萃咖啡液 10条装", 49.0, 60, "饮料"),
    ("黄柠檬 2斤装", 12.8, 200, "生鲜"),
    ("青柠鼠标垫 大号", 29.9, 15, "数码周边"),
    ("帆布托特包", 79.0, 8, "箱包"),
    ("限量联名马克杯", 129.0, 0, "周边"),
]


def init_db(reset: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with _db_lock, get_conn() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(1) FROM users").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO users(username, password, nickname, status) VALUES (?,?,?,?)",
                SEED_USERS,
            )
            conn.executemany(
                "INSERT INTO products(name, price, stock, category) VALUES (?,?,?,?)",
                SEED_PRODUCTS,
            )
        conn.commit()


# --------------------------------------------------------------------------- #
# 统一响应体：{"code": 0, "msg": "success", "data": ...}
# --------------------------------------------------------------------------- #
def ok(data: Any = None, msg: str = "success") -> JSONResponse:
    return JSONResponse({"code": CODE_OK, "msg": msg, "data": data})


def fail(code: int, msg: str, http_status: int = 200) -> JSONResponse:
    """
    业务失败统一走 HTTP 200 + code != 0（很多国内团队的约定）。
    另一方面 401/404 这类「协议层」错误仍用真实 HTTP 状态码，用例要能区分这两种。
    """
    return JSONResponse({"code": code, "msg": msg, "data": None}, status_code=http_status)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """新写法（FastAPI 0.9x 起 on_event 已废弃）：启动时初始化数据库。"""
    init_db()
    yield


app = FastAPI(title="青柠商城 Mini Mall", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request, exc: RequestValidationError):
    """把 FastAPI 默认的 422 结构包装成统一响应体，前端/测试都能按同一套规则解析。"""
    errors = [
        {"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        {"code": CODE_PARAM_ERROR, "msg": "参数校验失败", "data": {"errors": errors}},
        status_code=422,
    )


# --------------------------------------------------------------------------- #
# 鉴权
# --------------------------------------------------------------------------- #
def current_user(authorization: str | None) -> sqlite3.Row | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    info = _tokens.get(authorization.removeprefix("Bearer ").strip())
    if not info or info["expire_at"] < time.time():
        return None
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (info["user_id"],)).fetchone()


# --------------------------------------------------------------------------- #
# 请求模型（pydantic 做参数校验，边界值用例就是围绕这些约束设计的）
# --------------------------------------------------------------------------- #
class LoginBody(BaseModel):
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=6, max_length=20)


class CartItemBody(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=99)


class OrderBody(BaseModel):
    request_id: str | None = Field(default=None, max_length=64)  # 幂等键


# --------------------------------------------------------------------------- #
# 基础接口
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok", "ts": int(time.time())}


@app.post("/api/auth/login")
def login(body: LoginBody):
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
    if user is None:
        return fail(CODE_LOGIN_FAILED, "用户名或密码错误")
    if user["status"] == "locked":
        return fail(CODE_ACCOUNT_LOCKED, "账号已被锁定，请联系客服")
    if user["password"] != body.password:  # 演示项目不做加密，真实项目必须是哈希比对
        return fail(CODE_LOGIN_FAILED, "用户名或密码错误")
    token = uuid.uuid4().hex
    _tokens[token] = {"user_id": user["id"], "expire_at": time.time() + 7200}
    return ok({"token": token, "user": {"id": user["id"], "username": user["username"],
                                       "nickname": user["nickname"]}})


@app.get("/api/auth/me")
def me(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "登录已失效，请重新登录", http_status=401)
    return ok({"id": user["id"], "username": user["username"], "nickname": user["nickname"]})


@app.get("/api/products")
def list_products(
    keyword: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    sort: str = Query(default="id"),
):
    if sort not in {"id", "price_asc", "price_desc"}:
        return fail(CODE_PARAM_ERROR, "不支持的排序方式")
    where, args = "WHERE status='on'", []
    if keyword:
        where += " AND name LIKE ?"
        args.append(f"%{keyword}%")
    order_by = {"id": "id ASC", "price_asc": "price ASC", "price_desc": "price DESC"}[sort]
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(1) FROM products {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT id,name,price,stock,category FROM products {where} "
            f"ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*args, size, (page - 1) * size],
        ).fetchall()
    return ok({"total": total, "page": page, "size": size,
               "items": [dict(r) for r in rows]})


@app.get("/api/products/{product_id}")
def product_detail(product_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id,name,price,stock,category,status FROM products WHERE id=?",
                           (product_id,)).fetchone()
    if row is None:
        return fail(CODE_PRODUCT_NOT_FOUND, "商品不存在", http_status=404)
    return ok(dict(row))


# --------------------------------------------------------------------------- #
# 购物车
# --------------------------------------------------------------------------- #
@app.post("/api/cart/items")
def add_to_cart(body: CartItemBody, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)
    with _db_lock, get_conn() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=? AND status='on'",
                               (body.product_id,)).fetchone()
        if product is None:
            return fail(CODE_PRODUCT_NOT_FOUND, "商品不存在或已下架", http_status=404)
        exist = conn.execute("SELECT quantity FROM cart_items WHERE user_id=? AND product_id=?",
                             (user["id"], body.product_id)).fetchone()
        new_qty = body.quantity + (exist["quantity"] if exist else 0)
        if new_qty > product["stock"]:
            return fail(CODE_STOCK_NOT_ENOUGH, f"库存不足，当前仅剩 {product['stock']} 件")
        if exist:
            conn.execute("UPDATE cart_items SET quantity=? WHERE user_id=? AND product_id=?",
                         (new_qty, user["id"], body.product_id))
        else:
            conn.execute("INSERT INTO cart_items(user_id, product_id, quantity) VALUES (?,?,?)",
                         (user["id"], body.product_id, body.quantity))
        conn.commit()
    return ok({"product_id": body.product_id, "quantity": new_qty})


@app.get("/api/cart")
def get_cart(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.product_id, p.name, p.price, c.quantity, p.stock "
            "FROM cart_items c JOIN products p ON p.id=c.product_id WHERE c.user_id=?",
            (user["id"],),
        ).fetchall()
    items = [dict(r) for r in rows]
    return ok({"items": items,
               "total_amount": round(sum(i["price"] * i["quantity"] for i in items), 2)})


@app.delete("/api/cart/items/{product_id}")
def remove_cart_item(product_id: int, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)
    with _db_lock, get_conn() as conn:
        cur = conn.execute("DELETE FROM cart_items WHERE user_id=? AND product_id=?",
                           (user["id"], product_id))
        conn.commit()
    if cur.rowcount == 0:
        return fail(CODE_PARAM_ERROR, "购物车中无此商品")
    return ok({"deleted": product_id})


# --------------------------------------------------------------------------- #
# 订单（核心链路：校验库存 -> 扣减 -> 建单 -> 清空购物车，全部在一个事务里）
# --------------------------------------------------------------------------- #
@app.post("/api/orders")
def create_order(body: OrderBody, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)

    # 幂等：同一个 request_id 重复提交，直接返回上次的订单，不重复扣库存
    if body.request_id:
        with get_conn() as conn:
            exist = conn.execute("SELECT * FROM orders WHERE request_id=? AND user_id=?",
                                 (body.request_id, user["id"])).fetchone()
        if exist:
            return ok({"order_no": exist["order_no"], "total_amount": exist["total_amount"],
                       "status": exist["status"], "idempotent": True})

    with _db_lock, get_conn() as conn:
        cart = conn.execute(
            "SELECT c.product_id, c.quantity, p.price, p.stock, p.name "
            "FROM cart_items c JOIN products p ON p.id=c.product_id WHERE c.user_id=?",
            (user["id"],),
        ).fetchall()
        if not cart:
            return fail(CODE_CART_EMPTY, "购物车为空，无法下单")

        total = 0.0
        snapshot = []
        for item in cart:
            # 条件更新：只有库存充足才扣减成功，从根上避免并发超卖
            cur = conn.execute(
                "UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                (item["quantity"], item["product_id"], item["quantity"]),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return fail(CODE_STOCK_NOT_ENOUGH,
                            f"「{item['name']}」库存不足，当前仅剩 {item['stock']} 件")
            total += item["price"] * item["quantity"]
            snapshot.append((item["product_id"], item["name"], item["price"], item["quantity"]))

        total = round(total, 2)
        order_no = "MM" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
        cur = conn.execute(
            "INSERT INTO orders(order_no, user_id, total_amount, status, request_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (order_no, user["id"], total, "created", body.request_id,
             datetime.now().isoformat(timespec="seconds")),
        )
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items(order_id, product_id, product_name, price, quantity) "
            "VALUES (?,?,?,?,?)",
            [(order_id, *s) for s in snapshot],
        )
        conn.execute("DELETE FROM cart_items WHERE user_id=?", (user["id"],))
        conn.commit()
    return ok({"order_no": order_no, "total_amount": total, "status": "created",
               "idempotent": False})


@app.get("/api/orders")
def list_orders(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT order_no, total_amount, status, created_at FROM orders "
            "WHERE user_id=? ORDER BY id DESC", (user["id"],),
        ).fetchall()
    return ok({"items": [dict(r) for r in rows]})


@app.get("/api/orders/{order_no}")
def order_detail(order_no: str, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    if user is None:
        return fail(CODE_UNAUTHORIZED, "请先登录", http_status=401)
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_no=? AND user_id=?",
                             (order_no, user["id"])).fetchone()
        if order is None:
            return fail(CODE_ORDER_NOT_FOUND, "订单不存在", http_status=404)
        items = conn.execute("SELECT product_id, product_name, price, quantity "
                             "FROM order_items WHERE order_id=?", (order["id"],)).fetchall()
    data = dict(order)
    data["items"] = [dict(i) for i in items]
    return ok(data)


# --------------------------------------------------------------------------- #
# 测试专用：重置数据（只在 MINIMALL_TEST_MODE=1 时注册，生产不会存在）
# --------------------------------------------------------------------------- #
if TEST_MODE:

    @app.post("/api/test/reset")
    def test_reset():
        """清空购物车/订单，并把库存恢复成种子值，保证用例之间互不污染。"""
        with _db_lock, get_conn() as conn:
            conn.execute("DELETE FROM order_items")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM cart_items")
            for idx, (_, _, stock, _) in enumerate(SEED_PRODUCTS, start=1):
                conn.execute("UPDATE products SET stock=? WHERE id=?", (stock, idx))
            conn.commit()
        return ok({"reset": True})


# --------------------------------------------------------------------------- #
# 网页端（Selenium 的被测页面）
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return RedirectResponse("/login")


def _page(name: str) -> FileResponse:
    return FileResponse(TEMPLATE_DIR / name, media_type="text/html")


@app.get("/login", response_class=FileResponse)
def page_login():
    return _page("login.html")


@app.get("/products", response_class=FileResponse)
def page_products():
    return _page("products.html")


@app.get("/cart", response_class=FileResponse)
def page_cart():
    return _page("cart.html")


@app.get("/orders", response_class=FileResponse)
def page_orders():
    return _page("orders.html")
