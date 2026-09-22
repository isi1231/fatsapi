"""健康检查路由。

为什么单独开一个文件，而不是塞进 main.py：

健康检查是「运维接口」，和业务无关。生产环境里负载均衡器 / K8s 探针
只会访问这一个路径，把它独立出来，便于将来做路径级的路由规则、
限流豁免、以及「这个接口要不要鉴权」的判断。

两个接口的区别（Day 18 部署时你会真的用到）：
    /health   存活检查（liveness）—— 进程还在吗？挂了就重启
    /health/ready  就绪检查（readiness）—— 现在能收流量吗？依赖都通吗？
    差别在于：数据库连不上时，进程是活的（/health 该返回 200），
    但不该接收流量（/health/ready 该返回 503）。
"""

from fastapi import APIRouter

# prefix 统一加前缀，避免每个路由都手写。tags 决定它在 /docs 里归到哪一组。
router = APIRouter(prefix="/health", tags=["health"])


# 注意路径写的是 "" 而不是 "/"。
# 写 "/" 会得到 "/health/"，此时访问 /health 会触发 307 重定向。
# 虽然 FastAPI 默认会帮你跳转，但多一次往返不是好事，而且有些客户端不跟重定向。
@router.get("", summary="存活检查", response_description="服务存活")
async def health() -> dict[str, str]:
    """返回 200 就代表进程活着。

    这里的返回类型注解 `dict[str, str]` 不只是给类型检查器看的 ——
    FastAPI 会拿它生成 OpenAPI 文档里的响应示例。
    """
    return {"status": "ok"}


@router.get("/ready", summary="就绪检查")
async def ready() -> dict:
    """判断能不能接收流量。

    现在还没有任何外部依赖，所以写死 ok。
    Day 8 接上数据库后，这里会真实探测连接，探测失败返回 503。
    """
    return {
        "status": "ok",
        "checks": {"database": "not_configured"},
    }
