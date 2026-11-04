"""接口用例公共夹具：每条用例执行前把数据重置成种子状态。

为什么必须做数据隔离？
    假设上一条用例把「青柠气泡水」的库存买光了，下一条用例就会莫名其妙失败，
    而你 staring 十分钟也找不到原因 —— 这是新手写自动化最常见的坑。
    正确做法：要么每条用例重置数据，要么每条用例自己造自己的数据。
    这里用「重置」这种最省事的方案（真实项目里更推荐后者：用例自带数据）。
"""
from __future__ import annotations

import pytest
import requests


@pytest.fixture(autouse=True)
def reset_data(base_url):
    resp = requests.post(f"{base_url}/api/test/reset", timeout=5)
    assert resp.status_code == 200, "测试数据重置失败，请确认被测服务以 MINIMALL_TEST_MODE=1 启动"
    yield
