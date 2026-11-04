"""HTTP 客户端封装 —— 接口自动化的「地基」。

为什么不直接在用例里写 requests.post(...)？
  1) 每个用例重复写 URL、超时、headers、token，改一次要改 N 处；
  2) 出问题时没有统一日志，排查全靠 print；
  3) 断言对象是「原始 Response」，用例里到处是 r.json()["data"]["token"]，可读性差。

这一层做了 4 件事：拼 URL、注入 token、记录耗时与报文、把响应包装成可读对象。
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import requests

from common.config import settings

logger = logging.getLogger("minimall.http")

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


class ApiResponse:
    """对 requests.Response 的轻量包装，让用例读起来像自然语言。"""

    def __init__(self, resp: requests.Response, elapsed_ms: float):
        self._resp = resp
        self.elapsed_ms = elapsed_ms
        self.status_code = resp.status_code
        self.text = resp.text
        try:
            self.body: dict[str, Any] = resp.json()
        except ValueError:                     # 非 JSON 响应（比如网关报错页）
            self.body = {"_raw": resp.text}

    @property
    def code(self) -> int | None:
        return self.body.get("code")

    @property
    def msg(self) -> str:
        return self.body.get("msg", "")

    @property
    def data(self) -> Any:
        return self.body.get("data")

    def __repr__(self) -> str:                 # pytest 失败时直接看到报文，不用再复现
        return (f"<ApiResponse {self.status_code} code={self.code} "
                f"msg={self.msg!r} {self.elapsed_ms:.0f}ms>")


class HttpClient:
    """带会话复用与 token 注入的客户端。

    - 用 Session 复用 TCP 连接，跑几百条用例时显著减少握手开销；
    - 默认带 Content-Type / Accept，避免每个用例重复写 header；
    - token 失效（401）时可选择自动重登，这是很多团队踩过的坑。
    """

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.timeout = timeout or settings.timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MiniMall-QA/1.0 (+pytest)",
        })
        self.token: str | None = None
        # 坑点：机器上配了 HTTP_PROXY 时，requests 会把 127.0.0.1 的请求也丢给代理，
        # 表现是「同一个接口 POST 能通、GET 返回 404」这种诡异现象。
        # 访问本机服务必须绕过系统代理，否则排查一整天都找不到原因。
        if urlparse(self.base_url).hostname in _LOCAL_HOSTS:
            self.session.trust_env = False

    # ---------------- 鉴权 ---------------- #
    def set_token(self, token: str) -> None:
        self.token = token
        self.session.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        self.token = None
        self.session.headers.pop("Authorization", None)

    # ---------------- 核心请求 ---------------- #
    def request(self, method: str, path: str, **kwargs) -> ApiResponse:
        url = f"{self.base_url}{path}"
        payload = {k: v for k, v in kwargs.items() if k in {"json", "params", "data"}}
        logger.info("→ %s %s %s", method.upper(), url,
                    json.dumps(payload, ensure_ascii=False) if payload else "")
        resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        elapsed = resp.elapsed.total_seconds() * 1000
        result = ApiResponse(resp, elapsed)
        logger.info("← %s %s %.0fms", result.status_code, result.text[:300], elapsed)
        return result

    def get(self, path: str, **kwargs) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self.session.close()
