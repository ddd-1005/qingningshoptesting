"""pytest 全局夹具（fixture）——整个框架的「电源总闸」。

一次 pytest 会话里发生了这些事：
    1. 找一个空闲端口，用临时数据库把被测服务（uvicorn）拉起来
    2. 等 /health 可访问，才算环境就绪（避免"服务还没起完就开跑"的经典翻车）
    3. 提供分层夹具：匿名客户端 / 已登录客户端 / 浏览器
    4. 用例失败时自动截图并塞进 Allure 报告
    5. 会话结束：关浏览器、杀进程、删临时库

这就是"测试环境自动化"，面试官很爱问的一环。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest
import requests

from common.config import ROOT_DIR, settings

# 本机服务不走系统代理（否则 requests 会把 127.0.0.1 的请求也发给代理，导致诡异 404）
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")

# --------------------------------------------------------------------------- #
# 一、被测服务
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(base_url: str, proc: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:                       # 服务已退出 → 立刻报错并给出日志
            raise RuntimeError(f"被测服务启动失败，退出码 {proc.returncode}:\n{proc.stdout.read()}")
        try:
            if requests.get(f"{base_url}/health", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"被测服务 {timeout}s 内未就绪")


@pytest.fixture(scope="session")
def sut(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    """拉起一套「干净的」被测系统：独立端口 + 独立数据库，跑完即销毁。"""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    db_path = tmp_path_factory.mktemp("sut") / "minimall.db"

    env = os.environ.copy()
    env["MINIMALL_DB_PATH"] = str(db_path)
    env["MINIMALL_TEST_MODE"] = "1"        # 打开 /api/test/reset
    env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    _wait_healthy(base_url, proc)

    # 让断言层（common.db）指向同一个库
    os.environ["MINIMALL_DB_PATH"] = str(db_path)
    yield {"base_url": base_url, "db_path": db_path, "proc": proc}

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(sut) -> str:
    return sut["base_url"]


# --------------------------------------------------------------------------- #
# 二、接口客户端（分匿名 / 已登录，避免用例里反复登录）
# --------------------------------------------------------------------------- #
@pytest.fixture()
def anon_api(base_url) -> Iterator:
    from api.services import AuthApi
    client = AuthApi(base_url=base_url)
    yield client
    client.close()


@pytest.fixture()
def auth_api(base_url) -> Iterator:
    """已登录的客户端：等价于"测试账号已登录"这个前置条件。"""
    from api.services import AuthApi
    client = AuthApi(base_url=base_url)
    resp = client.login_and_hold(settings.user_name, settings.user_pwd)
    assert resp.code == 0, f"夹具登录失败：{resp.body}"
    yield client
    client.close()


# --------------------------------------------------------------------------- #
# 三、浏览器（Selenium 4.6+ 由 Selenium Manager 自动下载匹配的驱动）
# --------------------------------------------------------------------------- #
def _build_driver():
    browser = settings.browser.lower()
    if browser == "chrome":
        from selenium.webdriver import Chrome, ChromeOptions as Options
    elif browser == "firefox":
        from selenium.webdriver import Firefox, FirefoxOptions as Options
    else:
        from selenium.webdriver import Edge, EdgeOptions as Options

    options = Options()
    if settings.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,960")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")   # CI 容器里 /dev/shm 太小会导致浏览器崩溃
    options.add_argument("--lang=zh-CN")

    # 浏览器装在非标准路径时（比如 CI 上手动安装的 Chrome），用环境变量指定
    binary = os.getenv("MINIMALL_BROWSER_BINARY")
    if binary:
        options.binary_location = binary

    if browser == "chrome":
        return Chrome(options=options)
    if browser == "firefox":
        return Firefox(options=options)
    return Edge(options=options)


@pytest.fixture(scope="session")
def driver() -> Iterator:
    drv = _build_driver()
    drv.implicitly_wait(0)          # 一律用显式等待，隐式等待会让失败变慢且难定位
    drv.maximize_window()
    yield drv
    drv.quit()


# --------------------------------------------------------------------------- #
# 四、失败自动截图 + 报文，直接进 Allure 报告
# --------------------------------------------------------------------------- #
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    if report.when != "call" or not report.failed:
        return

    drv = item.funcargs.get("driver")
    if drv is None:
        return
    try:
        ts = time.strftime("%H%M%S")
        shot = settings.screenshot_dir / f"FAILED_{item.name}_{ts}.png"
        drv.save_screenshot(str(shot))
        try:
            import allure
            allure.attach(drv.get_screenshot_as_png(), name="失败截图",
                          attachment_type=allure.attachment_type.PNG)
            allure.attach(drv.page_source, name="页面源码",
                          attachment_type=allure.attachment_type.HTML)
            allure.attach(drv.current_url, name="失败时 URL",
                          attachment_type=allure.attachment_type.TEXT)
        except ImportError:
            pass
    except Exception as exc:            # 截图失败不能掩盖真正的失败原因
        print(f"[warn] 截图失败：{exc}")


# --------------------------------------------------------------------------- #
# 五、给 Allure 报告补环境信息（报告首页"环境"面板）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def allure_environment(sut) -> None:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    (settings.report_dir / "environment.properties").write_text(
        f"被测系统=Mini Mall 青柠商城\n"
        f"服务地址={sut['base_url']}\n"
        f"浏览器={settings.browser}（headless={settings.headless}）\n"
        f"Python={sys.version.split()[0]}\n"
        f"执行时间={time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )
