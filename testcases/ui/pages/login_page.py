"""登录页对象。"""
from __future__ import annotations

import allure

from testcases.ui.pages.base_page import BasePage


class LoginPage(BasePage):
    PATH = "/login"

    def load(self) -> "LoginPage":
        self.open(self.PATH)
        self.find("username-input")
        return self

    def input_username(self, username: str) -> "LoginPage":
        self.type("username-input", username)
        return self

    def input_password(self, password: str) -> "LoginPage":
        self.type("password-input", password)
        return self

    def submit(self) -> "LoginPage":
        self.click("login-btn")
        return self

    @allure.step("使用账号 {username} 登录")
    def login(self, username: str, password: str) -> "LoginPage":
        self.input_username(username).input_password(password).submit()
        return self

    @property
    def error_message(self) -> str:
        return self.text_of("error-msg")

    def error_is_visible(self) -> bool:
        return bool(self.error_message)
