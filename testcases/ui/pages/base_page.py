"""页面对象基类（Page Object Model 的底座）。

POM 解决什么问题？
    如果每个用例都写 driver.find_element(By.ID, "username").send_keys(...)，
    一旦前端把 id 改了，几十个用例全部挂掉。POM 把「元素定位 + 页面操作」封装成对象，
    用例只写 page.login("test01", "123456") —— 改版时只改一个文件。

两个工程细节（面试常问）：
    1. 定位统一用 data-testid：不依赖文案（文案会变）、不依赖 class（样式会变）、
       不依赖 DOM 层级（改版会变）。这是前端自动化最稳的约定。
    2. 全部用显式等待（WebDriverWait），禁用隐式等待和 sleep：
       sleep 会让用例变慢且照样不稳定，隐式等待会让「元素不存在」的用例白等十几秒。”
"""
from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from common.config import settings


class BasePage:
    def __init__(self, driver: WebDriver, base_url: str | None = None):
        self.driver = driver
        self.base_url = (base_url or settings.ui_base_url).rstrip("/")
        self.timeout = settings.ui_timeout

    # ---------------- 导航 ---------------- #
    def open(self, path: str = "/"):
        self.driver.get(f"{self.base_url}{path}")
        return self

    @property
    def current_url(self) -> str:
        return self.driver.current_url

    # ---------------- 定位 ---------------- #
    @staticmethod
    def _selector(test_id: str) -> tuple[str, str]:
        return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'

    def find(self, test_id: str, timeout: float | None = None) -> WebElement:
        """等到元素「可见」再返回；超时会抛 TimeoutException 并带上定位信息。"""
        return WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.visibility_of_element_located(self._selector(test_id)),
            message=f"元素 [data-testid={test_id}] 在 {timeout or self.timeout}s 内不可见",
        )

    def find_all(self, test_id: str) -> list[WebElement]:
        return self.driver.find_elements(*self._selector(test_id))

    def exists(self, test_id: str, timeout: float = 3) -> bool:
        """只判断存在性（不抛异常），用于「不应出现某元素」的断言。"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(self._selector(test_id))
            )
            return True
        except Exception:
            return False

    def wait_gone(self, test_id: str, timeout: float | None = None) -> bool:
        return WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.invisibility_of_element_located(self._selector(test_id)),
            message=f"元素 [data-testid={test_id}] 预期消失但仍可见",
        )

    # ---------------- 操作 ---------------- #
    def click(self, test_id: str) -> None:
        self.find(test_id).click()

    def type(self, test_id: str, text: str, clear: bool = True) -> None:
        el = self.find(test_id)
        if clear:
            el.clear()
        el.send_keys(text)

    def text_of(self, test_id: str) -> str:
        return self.find(test_id).text.strip()

    # ---------------- 等待 ---------------- #
    def wait_text(self, test_id: str, expected: str, timeout: float | None = None) -> bool:
        """等某元素文案变成期望值 —— 比 time.sleep(2) 稳得多，也快得多。"""
        return WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.text_to_be_present_in_element(self._selector(test_id), expected),
            message=f"元素 [data-testid={test_id}] 文案未在预期时间内变为「{expected}」",
        )

    def wait_url_contains(self, fragment: str, timeout: float | None = None) -> bool:
        return WebDriverWait(self.driver, timeout or self.timeout).until(
            EC.url_contains(fragment),
            message=f"URL 未在预期时间内包含「{fragment}」，当前 {self.current_url}",
        )

    # ---------------- 列表渲染等待 ----------------
    def wait_first(self, test_ids: list[str], timeout: float | None = None) -> str:
        """等这组元素中任意一个出现。

        页面是异步渲染的，"加载完成"有两种合法结果：有数据（商品卡片）或者空态提示。
        只等其中一种，遇到另一种就会白等到超时。
        """
        def _probe(driver):
            for tid in test_ids:
                if driver.find_elements(*self._selector(tid)):
                    return tid
            return False

        return WebDriverWait(self.driver, timeout or self.timeout).until(
            _probe, message=f"元素 {test_ids} 在预期时间内均未出现")

    def wait_count(self, test_id: str, expected: int, timeout: float | None = None) -> bool:
        """等某类元素的数量变成期望值 —— 列表渲染完成才能数数量。"""
        return WebDriverWait(self.driver, timeout or self.timeout).until(
            lambda d: len(d.find_elements(*self._selector(test_id))) == expected,
            message=f"元素 [data-testid={test_id}] 数量未在预期时间内变为 {expected}",
        )
