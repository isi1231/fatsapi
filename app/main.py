"""应用装配层。

这个文件只干三件事，业务逻辑一行都不写：

1. 创建 FastAPI 实例（构造参数会直接渲染进 /docs）
2. 挂载各个路由模块
3. 将来在这里注册中间件、异常处理器（Day 5）

为什么业务代码不写在这里：这个文件是整个应用唯一的「入口」，
它越干净，你定位「路由到底注册在哪」就越快。
"""

from fastapi import FastAPI

from app.routers import health, playground

app = FastAPI(
    # 这三个参数不是装饰，它们会直接出现在 /docs 的页头和 OpenAPI schema 里。
    # 面试时对方如果打开你的 /docs，第一眼看到的就是它们。
    title="fatsapi · Agent 服务后端",
    description=(
        "FastAPI 学习项目。目标：把 `week1/agent_demo` 的 Agent 能力"
        "包装成可部署、可并发、可流式返回的 API 服务。"
    ),
    version="0.1.0",
)

# 挂载路由。每个 router 自己带着 prefix 和 tags，
# 所以这里不需要再重复写一遍路径前缀。
app.include_router(health.router)
app.include_router(playground.router)


@app.get("/", tags=["meta"], summary="根路径")
async def root() -> dict[str, str]:
    """给个落地页 —— 服务起来了总得有地方确认一下，顺手把文档地址告诉你。"""
    return {"message": "服务已启动", "docs": "/docs"}
