"""Day 1 验证脚本：把今天写的接口真实打一遍。

运行（在项目根目录）：
    python scripts/check_day01.py

它用的是 FastAPI 自带的 TestClient —— 底层是 ASGI 直调，
**不需要真的启动服务器、不占端口**，但走的是和真实请求完全一样的
路由匹配 → 参数校验 → 依赖注入 全流程。

所以：状态码和报错内容都是真的，可以直接拿来当「我确实验证过」的证据。
"""

import sys
import warnings
from pathlib import Path

# ---- 为什么需要这三行 ----
# 直接执行 `python scripts/check_day01.py` 时，Python 会把**脚本所在目录**
# （也就是 scripts/）放进 sys.path[0]，而不会放当前工作目录。
# 结果就是 `import app` 找不到包 —— 你在 agent_demo 的 test/ 上踩过同一个坑。
# 这里显式把项目根目录插到最前面，脚本就能在任何地方被正确执行。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# FastAPI 0.141 的 TestClient 会发一条 httpx 相关的弃用警告，
# 与今天的内容无关，先静音，保持输出干净。
# 注意它必须在 import fastapi 之前执行，否则警告已经打出来了。
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# 让中文在 Windows 终端里正常输出
sys.stdout.reconfigure(encoding="utf-8")

client = TestClient(app)


def call(method: str, url: str, note: str = "", follow: bool = True) -> None:
    """发一个请求，把状态码和响应体打出来。

    follow=False 时不自动跟随重定向，这样才能看到真实的 3xx 状态码。
    """
    resp = client.request(method, url, follow_redirects=follow)
    flag = "✅" if resp.status_code < 400 else "⚠️ "
    print(f"{flag} {resp.status_code}  {method} {url}")
    if note:
        print(f"     说明：{note}")
    print(f"     {resp.text[:220]}")
    print()


def main() -> None:
    print("=" * 64)
    print("Day 1 验收：接口逐个打一遍")
    print("=" * 64)
    print()

    # ---- 正常路径 ----
    call("GET", "/", "根路径，确认服务活着")
    call("GET", "/health", "存活检查，返回 200 即代表进程正常")
    call("GET", "/health/ready", "就绪检查，目前依赖为空所以写死 ok")
    call("GET", "/playground/hello/砚", "路径参数，URL 里的值直接进函数")
    call("GET", "/playground/squares/3?offset=10",
         "路径参数 n=3 且 查询参数 offset=10，两者同时生效")
    call("GET", "/playground/messages?session_id=s1&limit=2",
         "查询参数：session_id 必填，limit=2 控制分页")

    # ---- 故意传错：这是今天的重点观察对象 ----
    print("-" * 64)
    print("下面是故意传错的，重点看状态码和报错内容")
    print("-" * 64)
    print()

    call("GET", "/playground/squares/abc",
         "n 声明为 int，传 abc 转不了 → 422（不是 500！）")
    call("GET", "/playground/messages",
         "缺必填的 session_id → 422，报错里会点名是谁缺了")

    # 尾斜杠：Starlette 默认开启 redirect_slashes，
    # 会先 307 跳到无斜杠版本，而不是直接 404。
    # 想让这条 307 现形，必须关掉「自动跟随重定向」。
    call("GET", "/playground/hello/砚/",
         "多了个尾斜杠 → 307 跳转（不跟随才看得见真实状态码）",
         follow=False)
    call("GET", "/playground/hello/砚/",
         "同一路径，客户端跟随重定向后才拿到 200 —— 代价是多一次往返")

    print("=" * 64)
    print("结论：所有校验都发生在进入你的函数之前，")
    print("      你的代码永远不会拿到一个非法值。")
    print("=" * 64)


if __name__ == "__main__":
    main()
