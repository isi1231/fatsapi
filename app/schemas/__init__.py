"""Pydantic 契约层。

这一层只回答一个问题：**数据长什么样。**

它不写业务逻辑、不碰数据库、不发请求。因此它天然可复用 ——
请求要用它校验入参，响应要用它裁剪出参，测试里还能直接拿它造数据。

为什么要单独一层：契约是最容易变的东西（前端要加字段、模型要换参数），
把它和业务逻辑混在一起，改一次契约就得动一次逻辑，迟早出事。
"""

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Message,
    SessionOut,
    SessionRecord,
    Usage,
)
from app.schemas.common import ApiResponse

__all__ = [
    "ApiResponse",
    "ChatRequest",
    "ChatResponse",
    "Message",
    "SessionOut",
    "SessionRecord",
    "Usage",
]
