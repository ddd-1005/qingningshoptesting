"""全局配置：一份代码，多套环境。

真实项目里至少要有 dev / test / staging 三套环境，所以「地址、账号、超时」这些
绝对不能写死在用例里 —— 这是自动化框架能不能长期维护的第一道分水岭。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _env_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """所有可变项集中在这里，改环境只改环境变量，不动一行用例代码。"""

    # 被测服务地址（由 conftest 动态拉起时会被覆盖）
    base_url: str = os.getenv("MINIMALL_BASE_URL", "http://127.0.0.1:8000")
    # UI 站点地址，通常与接口同域
    ui_base_url: str = os.getenv("MINIMALL_UI_URL", os.getenv("MINIMALL_BASE_URL", "http://127.0.0.1:8000"))

    # 接口默认超时（秒）
    timeout: float = float(os.getenv("MINIMALL_TIMEOUT", "10"))

    # 浏览器：edge / chrome / firefox（Selenium 4.6+ 由 Selenium Manager 自动匹配驱动）
    browser: str = os.getenv("MINIMALL_BROWSER", "edge")
    headless: bool = _env_bool("MINIMALL_HEADLESS", True)
    # UI 显式等待上限（秒）
    ui_timeout: float = float(os.getenv("MINIMALL_UI_TIMEOUT", "12"))

    # 测试账号
    user_name: str = os.getenv("MINIMALL_USER", "test01")
    user_pwd: str = os.getenv("MINIMALL_PWD", "123456")

    # 被测系统数据库（用于「接口 vs 数据库」一致性断言）
    db_path: Path = Path(os.getenv("MINIMALL_DB_PATH", ROOT_DIR / "app" / "data" / "minimall.db"))

    # 产物目录
    report_dir: Path = ROOT_DIR / "allure-results"
    screenshot_dir: Path = ROOT_DIR / "screenshots"


settings = Settings()
settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
