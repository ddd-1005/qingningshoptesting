"""登录页 UI 自动化用例。

UI 用例的原则：只测「UI 层独有的价值」——页面跳转、提示文案、元素状态。
纯业务逻辑（各种异常码）交给接口自动化，否则 UI 用例会又慢又脆。
"""
from __future__ import annotations

import allure
import pytest

from common.config import settings

pytestmark = [pytest.mark.ui, allure.feature("Web UI - 登录")]


@allure.story("登录成功")
@allure.title("正确账号密码登录后跳转商品页并渲染出商品")
@allure.severity(allure.severity_level.BLOCKER)
@pytest.mark.smoke
@pytest.mark.p0
def test_login_success_redirect_to_products(login_page):
    with allure.step("输入正确账号密码并提交"):
        login_page.login(settings.user_name, settings.user_pwd)

    with allure.step("断言跳转到商品页"):
        login_page.wait_url_contains("/products")

    with allure.step("断言商品真的渲染出来了（而不是白屏）"):
        login_page.find("product-list")
        assert len(login_page.find_all("product-card")) == 6


@allure.story("登录失败")
@allure.title("密码错误时提示文案正确，且停留在登录页")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p1
def test_login_wrong_password_shows_error(login_page):
    login_page.login(settings.user_name, "654321")

    with allure.step("等待错误提示出现"):
        login_page.wait_text("error-msg", "用户名或密码错误")
    assert "用户名或密码错误" in login_page.error_message
    assert "/login" in login_page.current_url, "登录失败不应跳转"


@allure.story("登录失败")
@allure.title("账号被锁定时提示专属文案，不能笼统提示密码错误")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_locked_account_shows_specific_message(login_page):
    login_page.login("locked01", "123456")
    login_page.wait_text("error-msg", "账号已被锁定")
    assert "锁定" in login_page.error_message


@allure.story("参数校验")
@allure.title("用户名留空提交时前端应给出明确提示")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.p1
def test_login_empty_username(login_page):
    login_page.login("", "123456")
    login_page.wait_text("error-msg", "参数校验失败")
    assert login_page.error_message != ""
    assert "/login" in login_page.current_url


@allure.story("访问控制")
@allure.title("未登录直接访问商品页应被重定向到登录页")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.p0
def test_direct_access_redirects_to_login(driver, base_url):
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(f"{base_url}/products")
    WebDriverWait(driver, 8).until(lambda d: "/login" in d.current_url)
