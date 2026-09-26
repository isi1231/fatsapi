"""对话路由（Day 2）。

今天要搞明白的核心问题是 **「参数到底从哪里来」**。FastAPI 的判定顺序是：

    1. 出现在路径 {} 里                → 路径参数（Path）
    2. 类型是 Pydantic 模型            → 请求体（Body）
    3. 用 Body() / Header() / Cookie() → 按你显式声明的来
    4. 以上都不是                      → 查询参数（Query）

第 2 条是今天的重点：**只要参数类型是 BaseModel 的子类，它就是请求体**，
不需要任何额外声明。Day 1 的 playground 里都是标量参数，所以全是查询参数；
这里一旦换成模型，来源自然就变了。
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Cookie, Header, HTTPException, Path

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    SessionOut,
    SessionRecord,
    Usage,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# 内存里的会话存储。
# ⚠️ 这是临时方案：进程一重启就全没了，多开一个 worker 还会各存各的。
# Day 8 会换成真正的数据库，到时候这个字典会被删掉。
_SESSIONS: dict[str, SessionRecord] = {}


def _new_session_id() -> str:
    """生成 12 位十六进制会话 ID。长度大于 Path 里声明的 min_length=8。"""
    return uuid4().hex[:12]


def _now() -> str:
    """统一用 UTC ISO 8601，避免时区问题。"""
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    """极粗的 token 估算，只为让骨架有数据可返回。

    ⚠️ 这不是真实分词。Day 7 接上真模型后，用量会直接读上游返回的 usage 字段。
    """
    return max(1, len(text) // 2)


# ---------------------------------------------------------------------------
# POST /chat —— 请求体 + response_model
# ---------------------------------------------------------------------------


@router.post("", response_model=ChatResponse, summary="对话（骨架，尚未接入模型）")
async def chat(payload: ChatRequest) -> ChatResponse:
    """接收对话请求，返回一条**假回复**。

    这个接口就是 Day 11 那个流式接口的同步版本。现在它只做一件事：
    证明「请求体的校验和类型转换已经全部完成」。

    注意 `payload: ChatRequest` 这个写法 —— 类型是 Pydantic 模型，
    于是它自动成了请求体。你在函数体里拿到的 `payload` 是**已经校验过**的对象，
    `payload.temperature` 一定在 0~2 之间，`payload.messages` 一定非空，
    每条消息的 role 一定是那三个之一。这些都不用你写。

    `response_model=ChatResponse` 则负责出参：函数返回什么类型都行，
    响应一定是 ChatResponse 的形状。
    """
    session_id = payload.session_id or _new_session_id()

    # 找出最后一条用户消息，纯粹为了让假回复看起来有点内容。
    last_user = next(
        (m for m in reversed(payload.messages) if m.role == "user"), None
    )
    preview = (last_user.content[:40] + "…") if last_user and len(last_user.content) > 40 else (
        last_user.content if last_user else "（没有 user 消息）"
    )

    prompt_text = "".join(m.content for m in payload.messages)

    return ChatResponse(
        session_id=session_id,
        model=payload.model,
        reply=f"[骨架回复] 收到 {len(payload.messages)} 条消息，最后一条是：{preview}",
        usage=Usage(
            prompt_tokens=_estimate_tokens(prompt_text),
            completion_tokens=12,
            total_tokens=_estimate_tokens(prompt_text) + 12,
        ),
        finish_reason="stop",
    )


# ---------------------------------------------------------------------------
# 会话相关 —— 今天的重头戏：response_model 如何挡住敏感字段
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionOut, summary="创建会话")
async def create_session(
    title: str = Body(..., embed=True, description="会话标题"),
) -> SessionRecord:
    """创建一个会话。

    **看两处地方，这是今天的核心：**

    ① 返回值类型写的是 `-> SessionRecord`，而且函数**真的返回了 SessionRecord 实例** ——
       它身上带着 `upstream_api_key`。

    ② 但装饰器上声明了 `response_model=SessionOut`。

    结果：响应 JSON 里**没有** upstream_api_key。不是因为它被删了，
    而是因为 Pydantic 按 SessionOut 重新构造了一份输出，没声明的字段根本不会被写出来。

    换句话说：**敏感字段不是被「过滤」掉的，是从来就没进入输出模型。**

    顺便注意 `Body(..., embed=True)`：`title` 是个标量（str），单个标量参数默认
    会被当成查询参数，加 `Body(embed=True)` 才把它变成请求体 `{"title": "..."}`。
    """
    session_id = _new_session_id()

    record = SessionRecord(
        session_id=session_id,
        title=title,
        # 故意写成一个一眼就知道不能外泄的假密钥，
        # 方便你在响应里反复确认「它真的没出去」。
        upstream_api_key="sk-SECRET-do-not-leak-1234567890",
        created_at=_now(),
    )
    _SESSIONS[session_id] = record

    return record


@router.get("/sessions/{session_id}", response_model=SessionOut, summary="查询会话")
async def get_session(
    session_id: str = Path(
        ...,
        min_length=8,
        description="会话 ID（至少 8 位）",
        examples=["a1b2c3d4e5f6"],
    ),
) -> SessionRecord:
    """按 ID 取会话。

    路径参数也可以带约束：`min_length=8` 写在 `Path()` 里，
    传个短 ID 会直接 422，连存储都不会查。

    返回的仍是带密钥的 SessionRecord，出去时被裁剪成 SessionOut。
    """
    record = _SESSIONS.get(session_id)
    if record is None:
        # 404 是「业务层」的判断：格式没问题，只是这个东西不存在。
        # 这和 422 有本质区别 —— 422 是框架层拦下来的，你的函数根本没执行。
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    return record


@router.get("/sessions", response_model=list[SessionOut], summary="会话列表")
async def list_sessions() -> list[SessionRecord]:
    """列出全部会话。

    注意 `response_model=list[SessionOut]` —— response_model 可以是**列表**。
    同样地，列表中每一项都会按 SessionOut 裁剪。
    """
    return list(_SESSIONS.values())


# ---------------------------------------------------------------------------
# Header / Cookie —— 参数还能从这两个地方来
# ---------------------------------------------------------------------------


@router.get("/whoami1", summary="读取 Header 与 Cookie")
async def whoami(
    # 参数名写 x_client_id，FastAPI 会自动去找请求头 "x-client-id"
    # （下划线转横线，且不区分大小写）。
    # 想用别的名字就显式写 alias="X-Client-Id"。
    x_client_id: str = Header(..., description="客户端标识，请求头 X-Client-Id"),
    user_agent: str | None = Header(None, description="浏览器会自动带上"),
    # Cookie 的名字不做转换，参数名就是 cookie 名。
    session_token: str | None = Cookie(None, description="可选：会话令牌"),
) -> dict:
    """这个接口没有请求体、没有路径参数，参数来自请求头和 Cookie。

    ⚠️ 一个重要区别：**Header/Cookie 里的值全是字符串**。
    如果你写 `retry_count: int = Header(0)`，FastAPI 会帮你转成 int，
    转不了就 422。所以放心用类型注解，转换和校验一样是自动的。

    真实场景里，`X-Client-Id` 这种头通常就是 Day 15 要做的 API Key 鉴权的雏形。
    """
    return {
        "client_id": x_client_id,
        "user_agent": user_agent,
        "has_session_token": session_token is not None,
    }

# @router.get("/whoami2", summary="读取 Header 与 Cookie")
# async def whoami(
#     # 参数名写 x_client_id，FastAPI 会自动去找请求头 "x-client-id"
#     # （下划线转横线，且不区分大小写）。
#     # 想用别的名字就显式写 alias="X-Client-Id"。
#     x_client_id: str = Header(..., description="客户端标识，请求头 X-Client-Id"),
#     user_agent: str | None = Header(None, description="浏览器会自动带上"),
#     # Cookie 的名字不做转换，参数名就是 cookie 名。
#     session_token: str  = Cookie( description="必填：会话令牌"),
# ) -> dict:
#     """这个接口没有请求体、没有路径参数，参数来自请求头和 Cookie。

#     ⚠️ 一个重要区别：**Header/Cookie 里的值全是字符串**。
#     如果你写 `retry_count: int = Header(0)`，FastAPI 会帮你转成 int，
#     转不了就 422。所以放心用类型注解，转换和校验一样是自动的。

#     真实场景里，`X-Client-Id` 这种头通常就是 Day 15 要做的 API Key 鉴权的雏形。
#     """
#     return {
#         "client_id": x_client_id,
#         "user_agent": user_agent,
#         "has_session_token": session_token is not None,
#     }
