"""对话相关的数据契约。

这个文件是 Day 2 的核心。读的时候注意两件事：

1. **同一个概念可以有两个模型。** `SessionRecord` 是内部存储用的（含密钥），
   `SessionOut` 是对外暴露的（不含）。中间那层转换由 `response_model` 自动完成 ——
   不需要你手写一行 `del data["upstream_api_key"]`。

2. **约束写在类型和 Field 里，不写在函数体里。** 想让 temperature 只能在 0~2 之间？
   声明 `ge=0, le=2` 就够了，不用在函数里写 if 判断。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 对话请求
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """一条对话消息。

    注意 role 的类型不是 `str` 而是 `Literal[...]` —— 这是「枚举式约束」，
    写死在类型里。传 `{"role": "banana"}` 会直接 422，报错信息里还会列出
    所有合法取值。比 `str` + 手写 if 校验干净得多。
    """

    role: Literal["system", "user", "assistant"] = Field(
        ...,
        description="消息角色，只能是这三个之一",
        examples=["user"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="消息正文，不能为空",
        examples=["用一句话介绍 FastAPI"],
    )


class ChatRequest(BaseModel):
    """`POST /chat` 的请求体。

    这里的字段演示了三种「可选性」的写法：

    - `messages` 用 `...` 占位  → **必填**
    - `model` 直接给默认值       → 可选，不传就用默认
    - `session_id` 默认 None     → 可选，且「不传」和「传 null」等价
    """

    messages: list[Message] = Field(
        ...,
        min_length=1,
        description="对话历史，至少一条。最后一条通常是用户本轮输入",
    )
    model: str = Field("deepseek-chat", description="模型名")
    temperature: float = Field(
        0.7, ge=0.0, le=2.0, description="采样温度，0~2"
    )
    max_tokens: int = Field(1024, gt=0, le=8192, description="最大生成 token 数")
    session_id: str | None = Field(
        None, description="不传则新建一个会话；传了则续写该会话"
    )


# ---------------------------------------------------------------------------
# 对话响应
# ---------------------------------------------------------------------------


class Usage(BaseModel):
    """token 用量。嵌套在 ChatResponse 里，演示「模型套模型」。"""

    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)


class ChatResponse(BaseModel):
    """`POST /chat` 的响应体。

    它同时也是接口的 `response_model` —— 意味着**函数返回的任何多余字段都会被丢掉**。
    这不是副作用，是设计：出参的形状由契约决定，不由实现决定。
    """

    session_id: str
    model: str
    reply: str
    usage: Usage
    finish_reason: Literal["stop", "length", "tool_calls"] = Field(
        "stop", description="停止原因；tool_calls 表示模型想调用工具"
    )


# ---------------------------------------------------------------------------
# 会话：内部模型 vs 对外模型（今天最重要的一组对比）
# ---------------------------------------------------------------------------


class SessionRecord(BaseModel):
    """**内部**会话记录 —— 存起来的那一份。

    它带着 `upstream_api_key`，因为服务端真的需要它去调上游模型。
    但这个东西**绝对不能出现在响应里**。

    做法不是手写 `del`，而是让它压根不在对外的模型里 —— 见 SessionOut。
    """

    session_id: str
    title: str
    upstream_api_key: str = Field(..., description="调用上游 LLM 的密钥，禁止外泄")
    created_at: str


class SessionOut(BaseModel):
    """**对外**会话信息 —— 能出去的那一份。

    字段是 SessionRecord 的子集，敏感字段一个都没有。
    接口只要声明 `response_model=SessionOut`，返回 SessionRecord 也安全。

    `from_attributes=True` 让它可以接受任意带同名属性的对象（不只是 dict），
    Day 8 接上 SQLAlchemy 之后，这里可以直传 ORM 实例。
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    created_at: str
