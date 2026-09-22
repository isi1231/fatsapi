"""参数练习路由（Day 1）。

今天只搞明白一件事：**客户端发来的数据，是怎么进到你的函数参数里的。**

FastAPI 的判定规则非常朴素，记住这一条就够了：

    参数名出现在路径字符串的 {} 里  →  路径参数（Path）
    参数名没出现在路径里            →  查询参数（Query）

注意：**有没有默认值，不影响这个判定**。
`skip: int = 0` 和 `limit: int` 都是查询参数，区别只是一个可选一个必填。

同理，类型注解也不影响判定，它只决定「怎么转换、怎么校验、文档里长什么样」。
"""

from fastapi import APIRouter

router = APIRouter(prefix="/playground", tags=["playground"])


@router.get("/hello/{name}", summary="路径参数：字符串")
async def hello(name: str) -> dict[str, str]:
    """URL 里的 {name} 会直接传进函数的 name 参数。

    试一下：/playground/hello/砚
    """
    return {"message": f"你好，{name}"}


@router.get("/squares/{n}", summary="路径参数 + 查询参数")
async def squares(n: int, offset: int = 0) -> dict:
    """两种参数同时出现，正好对比。

    - `n`       在路径里，是**路径参数**，而且声明成 int → 自动转换 + 校验
    - `offset`  不在路径里，是**查询参数**，有默认值 → 可选

    试一下这个必错：/playground/squares/abc
    你会拿到 422，而不是 500 —— 因为校验发生在进入你的函数**之前**，
    你的代码根本不会被执行，也不存在「拿到一个非法值」的可能。
    """
    return {
        "n": n,
        "offset": offset,
        "squares": [i * i + offset for i in range(1, n + 1)],
    }


@router.get("/messages", summary="查询参数：必填 + 可选")
async def list_messages(
    session_id: str,
    role: str | None = None,
    skip: int = 0,
    limit: int = 10,
) -> dict:
    """模拟「分页查询某个会话的消息」，贴近后面 Agent 项目里要写的接口。

    四个参数的类型签名，就是四种不同的「必填/可选」状态：

    - `session_id: str`            没有默认值 → **必填**
    - `role: str | None = None`    默认 None  → 可选，可以不传
    - `skip: int = 0`              默认 0     → 可选，不传就是 0
    - `limit: int = 10`            默认 10    → 可选

    一个必填的都没有会怎样？访问 /playground/messages 试试，会收到 422，
    错误信息里会明确告诉你缺了 session_id。

    另外注意 `str | None` 这个写法：它是 Python 3.10+ 的联合类型语法，
    等价于旧版的 `Optional[str]`。FastAPI 能读懂它，生成的文档里
    role 会被标成「非必填」。
    """
    # 造一段假数据，让接口有东西返回。Day 8 之后这里会换成真实的数据库查询。
    fake_messages = [
        {
            "id": i,
            "role": "user" if i % 2 else "assistant",
            "content": f"第 {i} 条消息",
        }
        for i in range(1, 21)
    ]

    if role is not None:
        fake_messages = [m for m in fake_messages if m["role"] == role]

    return {
        "session_id": session_id,
        "total": len(fake_messages),
        "skip": skip,
        "limit": limit,
        "items": fake_messages[skip : skip + limit],
    }
