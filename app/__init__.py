"""fatsapi —— FastAPI 学习项目。

目标：把 `week1/agent_demo` 的 Agent 能力包装成可部署、可并发、可流式返回的后端服务。

分层约定（从第一天就定好）：
    app/main.py        装配层：建 app、挂路由、注册中间件与异常处理器
    app/routers/       编排层：只做「收请求 → 调 service → 返响应」
    app/schemas/       契约层：Pydantic 模型，只描述数据形状
    app/services/      业务层：纯逻辑，可单测，不依赖框架
    app/repositories/  数据层：只做读写
    app/core/          横切：配置、日志、安全、异常
"""

__version__ = "0.1.0"
