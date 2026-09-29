"""通用响应包装（Day 3）。

## 为什么需要统一外壳

如果每个接口的响应形状都不一样，客户端就得为每个接口写一套解析逻辑：
这个接口成功时返回数组、那个返回对象、另一个失败时又换个结构……
调用方迟早崩溃。

统一成 `{code, message, data}` 之后，客户端只需要写一次：

    if resp["code"] == 0: 用 resp["data"]
    else:                 按 resp["message"] 提示用户

## 代价：会出现两套「状态」

这是必须提前约定清楚的，否则团队里一定吵架：

| 层 | 谁负责 | 取值 |
| --- | --- | --- |
| HTTP 状态码 | 传输层 + 框架层 | 200 / 404 / 422 / 500 |
| 业务 code | 业务逻辑层 | 0 成功，非 0 是具体错误 |

本项目的约定：**HTTP 状态码照常表达「请求本身是否被正确处理」，
业务 code 表达「业务上是否成功」**。两者不互相替代。

比如「余额不足」：HTTP 200（请求处理成功了）+ code 1001（业务失败）。
不要为了表达业务失败而返回 HTTP 400 —— 那会让网关、监控、重试逻辑全部误判。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# 泛型参数：T 代表「data 里装的是什么」。
# 它在定义时是空占位符，使用时才被具体类型替换 —— ApiResponse[SessionOut]。
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应外壳。

    继承 `Generic[T]` 之后，这个模型就可以被参数化：
    `ApiResponse[SessionOut]`、`ApiResponse[list[SessionOut]]` 都是合法的类型。

    **参数化不是装饰**：FastAPI 会根据它生成准确的 OpenAPI schema。
    `/docs` 里能看到 data 字段展开成具体结构，而不是一个空对象 ——
    这一点 Day 2 的裸 `dict` 做不到。
    """

    code: int = Field(
        0,
        description="业务状态码，0 表示成功，非 0 为具体业务错误",
        examples=[0],
    )
    message: str = Field(
        "ok",
        description="人类可读的说明，可直接展示给用户",
        examples=["ok"],
    )
    data: T | None = Field(
        None,
        description="业务数据。失败时通常为 null",
    )

    # --- 两个构造函数，让调用处读起来更像业务代码 ---
    # 这不是必须的（直接 ApiResponse(code=0, ...) 也行），
    # 但 ApiResponse.ok(x) 比 ApiResponse(code=0, message="ok", data=x) 清楚得多。

    @classmethod
    def ok(cls, data: T, message: str = "ok") -> "ApiResponse[T]":
        """构造成功响应。"""
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, code: int, message: str) -> "ApiResponse[T]":
        """构造失败响应。`data` 留空。

        注意这里 code 由**调用方**决定，而不是写死。
        具体用什么码，属于业务约定，不属于基础设施 —— 所以不放这里定义。
        """
        return cls(code=code, message=message, data=None)
