"""业务常量：错误码集中管理。

用例里写 `assert resp.code == 1003` 是最难维护的写法——3 个月后没人记得 1003 是什么。
统一收在这里，和被测系统的定义一一对应。
"""

# 成功
CODE_OK = 0
# 通用
CODE_PARAM_ERROR = 1001        # 参数校验失败（HTTP 422）
CODE_UNAUTHORIZED = 1002       # 未登录 / token 失效（HTTP 401）
CODE_LOGIN_FAILED = 1003       # 用户名或密码错误
CODE_ACCOUNT_LOCKED = 1004     # 账号被锁定
# 商品
CODE_PRODUCT_NOT_FOUND = 2001  # 商品不存在（HTTP 404）
CODE_STOCK_NOT_ENOUGH = 2002   # 库存不足
# 购物车 / 订单
CODE_CART_EMPTY = 2004         # 购物车为空
CODE_ORDER_NOT_FOUND = 3001    # 订单不存在（HTTP 404）

# 种子数据（见 app/main.py SEED_PRODUCTS）
P_BUBBLE_WATER = 1     # 青柠气泡水 ¥5.9 库存 120
P_COFFEE = 2           # 冷萃咖啡液 ¥49.0 库存 60
P_LEMON = 3            # 黄柠檬 ¥12.8 库存 200
P_MOUSE_PAD = 4        # 青柠鼠标垫 ¥29.9 库存 15
P_BAG = 5              # 帆布托特包 ¥79.0 库存 8
P_SOLD_OUT = 6         # 限量联名马克杯 ¥129.0 库存 0（已售罄）
