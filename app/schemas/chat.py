"""对话相关的数据契约。

这个文件是 Day 2 的核心。读的时候注意两件事：

1. **同一个概念可以有两个模型。** `SessionRecord` 是内部存储用的（含密钥），
   `SessionOut` 是对外暴露的（不含）。中间那层转换由 `response_model` 自动完成 ——
   不需要你手写一行 `del data["upstream_api_key"]`。

2. **约束写在类型和 Field 里，不写在函数体里。** 想让 temperature 只能在 0~2 之间？
   声明 `ge=0, le=2` 就够了，不用在函数里写 if 判断。
"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# 别名映射表：把客户端可能传来的各种写法，统一成标准值
# ---------------------------------------------------------------------------

_ROLE_ALIASES: dict[str, str] = {
    "sys": "system",
    "human": "user",
    "ai": "assistant",
    "bot": "assistant",
}

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

    # 模型级配置：自动去掉字符串两侧的空白。
    # 别小看这一行 —— 它和下面的 min_length=1 配合起来才严密：
    # 没有它，客户端传一个 "   "（三个空格）就能绕过「不能为空」的检查。
    # 见 scripts/check_day03.py 的对应断言。
    model_config = ConfigDict(str_strip_whitespace=True)

    # ---------------- 自定义校验器 ----------------

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> object:
        """把常见别名归一化成标准值。**能救就救，救不了就报错。**

        三个关键点：

        **① 为什么用 `mode="before"`。**
        默认的 `mode="after"` 在类型转换和 `Literal` 校验**之后**才跑 —— 那时
        `"human"` 早就被判非法、直接 422 了，你的归一化代码根本没机会执行。
        `mode="before"` 在一切之前跑，收到的还是原始输入，所以救得回来。

        **② 为什么参数和返回类型都是 `object`。**
        因为在 `before` 阶段输入可能是任何类型（字符串、数字、None……），
        不能假设它是 str。用 `object` 是诚实的写法，也提醒你**必须先做类型判断**。

        **③ 归一化不了就原样返回。**
        `"banana"` 不在映射表里，原样返回 → 交给 `Literal` 去拒绝 → 422。
        「顺手修正」和「严守底线」不冲突：能自动救的救，救不了的必须报错，
        绝不能悄悄替换成一个"看起来差不多"的值。
        """
        if isinstance(value, str):
            normalized = _ROLE_ALIASES.get(value.strip().lower())
            if normalized is not None:
                return normalized
        return value


class ChatRequest(BaseModel):
    """`POST /chat` 的请求体。

    这里的字段演示了三种「可选性」的写法：

    - `messages` 用 `...` 占位  → **必填**
    - `model` 直接给默认值       → 可选，不传就用默认
    - `session_id` 默认 None     → 可选，且「不传」和「传 null」等价

    Day 3 在这个模型上追加了两样 Field 表达不了的东西：
    `extra="forbid"`（拒绝未知字段）和 `check_sampling_consistency`
    （temperature 与 top_p 的联动规则）。
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
    top_p: float = Field(1.0, gt=0.0, le=1.0, description="核采样阈值，0~1")
    session_id: str | None = Field(
        None, description="不传则新建一个会话；传了则续写该会话"
    )

    # extra="forbid"：请求体里出现**未声明**的字段时直接 422，而不是静默忽略。
    #
    # 为什么重要：默认行为是 ignore（悄悄丢掉），客户端把 "temprature" 拼错时，
    # 你的服务会安然返回 200，而他以为参数生效了 —— 这种 bug 极难排查。
    # 对外接口宁可报错，也不要"假装收到了"。
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def check_sampling_consistency(self) -> "ChatRequest":
        """跨字段校验：`temperature=0` 时 `top_p` 必须为 1.0。

        **这就是 Field 做不到的事。**

        `Field` 只能描述「单个字段自身的约束」（`ge`/`le`/`min_length`……）。
        但「A 取某值时 B 必须取某值」这种规则，本质上需要**同时看到两个字段** ——
        只有 model_validator 能做。

        `mode="after"` 表示它在一个**已经构造好的模型实例**上运行，
        所以可以直接 `self.temperature`。也因此必须 `return self` ——
        忘了返回就是返回 None，Pydantic 会报错。

        （另一个可选值是 `mode="before"`，那时拿到的是原始 dict，
        可以在模型构造之前改写数据。Day 3 用 after 就够。）
        """
        if self.temperature == 0 and self.top_p != 1.0:
            raise ValueError(
                "temperature=0 表示贪心解码，此时 top_p 必须为 1.0"
                f"（当前 temperature=0, top_p={self.top_p}）"
            )
        return self


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
