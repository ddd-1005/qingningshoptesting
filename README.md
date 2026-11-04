# Mini Mall 青柠商城 · 接口 + Web UI 自动化测试框架

[![CI](https://github.com/ddd-1005/qingningshoptesting/actions/workflows/ci.yml/badge.svg)](https://github.com/ddd-1005/qingningshoptesting/actions/workflows/ci.yml)

一个**可独立运行、可现场演示**的电商系统自动化测试项目：

- **接口自动化**：`requests + pytest`，覆盖登录鉴权、商品、购物车、订单四大模块，共 60+ 条用例
- **Web UI 自动化**：`Selenium 4 + Page Object Model`，覆盖登录、加购、下单、搜索主流程
- **数据一致性断言**：不只断言接口返回，还查数据库验证「库存真的扣了、订单真的落库了」
- **质量专项**：接口幂等、并发重复下单、水平越权，三类容易被漏测的风险点
- **工程化**：Allure 报告、失败自动截图、并行执行、GitHub Actions 持续集成

## 为什么要自带一套被测系统？

真实项目里被测系统由开发提供，测试不该去改它。本项目用 FastAPI 自研了一个轻量电商后端
（`app/` 目录，含网页端），目的是：

1. 完全掌握业务规则，断言才有依据，而不是靠猜；
2. 想造缺陷就造缺陷（比如把库存扣减改成 `stock -= 0`），用来验证用例能不能真的抓到 bug；
3. **面试时可以当场 `uvicorn` 起服务 + 跑用例 + 打开 Allure 报告**，说服力远高于"我做过一个项目"。

## 架构分层

```
┌──────────────────────────────────────────────────────────┐
│  testcases/       用例层：只写「做什么、期望什么」          │
│    api/  ui/                                             │
├──────────────────────────────────────────────────────────┤
│  pages/           UI 页面对象（POM）：定位 + 操作           │
│  api/services.py  接口对象层：一个接口一个方法              │
├──────────────────────────────────────────────────────────┤
│  common/          公共能力层                               │
│    http_client  请求封装 / token 注入 / 日志 / 耗时         │
│    asserts      三层断言（协议 / 业务 / 数据）              │
│    db           数据库校验（一致性断言的底气）              │
│    config       多环境配置                                 │
├──────────────────────────────────────────────────────────┤
│  conftest.py      夹具层：自动拉起被测服务、浏览器、失败截图 │
├──────────────────────────────────────────────────────────┤
│  app/             被测系统（FastAPI + SQLite + 网页端）      │
└──────────────────────────────────────────────────────────┘
```

## 快速开始

```bash
# 1. 建虚拟环境、装依赖
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. 跑接口用例（会自动拉起被测服务，不需要手动启动）
pytest testcases/api -m api

# 3. 跑 UI 用例（首次运行 Selenium 会自动下载浏览器驱动）
pytest testcases/ui -m ui

# 4. 只看报告
allure serve allure-results
```

> 想看着浏览器一步步操作？把 `MINIMALL_HEADLESS` 设为 `false` 再跑 UI 用例。
> 想手动起服务点一点页面？`uvicorn app.main:app --port 8000`，然后访问 http://127.0.0.1:8000

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 全量回归 | `pytest` |
| 冒烟（提测必跑） | `pytest -m smoke` |
| 只跑 P0 核心链路 | `pytest -m p0` |
| 接口用例并行 4 进程 | `pytest testcases/api -n 4` |
| 指定模块 | `pytest testcases/api/test_order.py -v` |
| 生成并查看报告 | `pytest --alluredir=allure-results && allure serve allure-results` |
| 失败重跑（可选插件） | `pip install pytest-rerunfailures && pytest --reruns 2` |

## 用例设计覆盖点

| 模块 | 覆盖内容 |
| --- | --- |
| 登录 | 成功、密码错误、账号不存在、账号锁定、大小写敏感、SQL 注入、参数长度边界、token 伪造 |
| 商品 | 分页、关键字搜索、价格排序、size 边界（0/1/50/51）、页码越界、非法排序参数、商品不存在 |
| 购物车 | 加购、重复加购累加、超库存拦截、累加后超库存、售罄商品、数量边界、未登录、删除与重复删除 |
| 订单 | 端到端主链路、金额精度、空购物车、库存被抢、幂等重复提交、**10 线程并发只成功 1 单**、水平越权 |
| UI | 登录跳转、错误提示、锁定账号专属文案、未登录重定向、加购角标、下单全流程、搜索空态、售罄置灰 |

用例的「测试设计方法」在每条用例的 docstring 里都写了，方便复习：等价类、边界值、场景法、状态迁移。

## 目录结构

```
.
├── app/                     被测系统
│   ├── main.py              FastAPI 应用：接口 + 页面路由
│   └── templates/           网页端 HTML
├── api/
│   ├── services.py          接口对象层（AuthApi / ProductApi / CartApi / OrderApi）
│   └── constants.py         业务错误码与种子数据常量
├── common/
│   ├── config.py            环境配置（全部走环境变量）
│   ├── http_client.py       requests 封装
│   ├── asserts.py           三层断言工具
│   └── db.py                数据库校验
├── testcases/
│   ├── api/                 接口用例 + data/*.yaml
│   └── ui/                  UI 用例 + pages/ 页面对象
├── conftest.py              全局夹具（拉起服务 / 浏览器 / 失败截图）
├── pytest.ini               标记、报告目录、日志
└── .github/workflows/ci.yml GitHub Actions 流水线
```

## CI

推送到 `main` 后自动执行：接口用例并行跑 → UI 用例 headless 跑 → 生成 Allure 报告 → 上传产物。
报告和失败截图都能在 Actions 的 Artifacts 里下载，面试时可以直接贴链接。

## 常见问题

**1. UI 用例报驱动相关错误？**
Selenium 4.6+ 自带 Selenium Manager，会自动下载匹配的驱动，前提是本机已安装 Edge / Chrome。
国内网络下载慢的话，可以手动把 `msedgedriver.exe` 放到 PATH 里。

**2. `allure: command not found`？**
Allure 是独立的命令行工具（不是 pip 包）：`pip install allure-pytest` 只负责生成结果，
查看报告还需要安装 [Allure CLI](https://allurereport.org/docs/install/)，或直接用 CI 里的报告产物。

**3. 用例之间互相影响？**
接口用例每条执行前调用 `/api/test/reset` 重置数据；UI 用例额外清空 localStorage。
真实项目更推荐「每条用例自己造数据」，思路是一样的：**用例必须能单独跑、任意顺序跑**。
