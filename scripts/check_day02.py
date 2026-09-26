"""Day 2 验证脚本：请求体、校验、以及 response_model 到底做了什么。

运行（在项目根目录）：
    python scripts/check_day02.py

核心看点有两个，都在「会话」那一段：
  ① 服务端**确实**存了一个带密钥的对象（脚本会直接把内部记录打出来给你看）
  ② 但 HTTP 响应里**一个字段都没有**泄漏
  两者对照，才能证明 response_model 是真的在运行时裁剪，而不是「文档声明」。
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers.chat import _SESSIONS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

client = TestClient(app)

OK = "✅"
BAD = "❌"
WARN = "⚠️ "


def show(method: str, url: str, note: str = "", **kwargs):
    """发请求并打印结果，返回 response。"""
    resp = client.request(method, url, **kwargs)
    flag = OK if resp.status_code < 400 else WARN
    print(f"{flag} {resp.status_code}  {method} {url}")
    if note:
        print(f"      {note}")
    print(f"      {resp.text[:230]}")
    print()
    return resp


def check_missing_field_behavior() -> bool:
    """反向验证：response_model 声明了某字段，但函数返回值里没有它，会怎样？

    做法是现场搭一个最小 app —— 不改项目代码就能验证框架行为。
    这个技巧值得记住：怀疑框架「到底是不是这么干的」时，搭个 10 行的最小复现，
    比翻文档快得多。

    预期：不是静默补个 null，而是直接抛 ResponseValidationError。
    """
    from fastapi import FastAPI
    from fastapi.exceptions import ResponseValidationError
    from pydantic import BaseModel

    class Pair(BaseModel):
        a: int
        b: int

    demo_app = FastAPI()

    @demo_app.get("/only-a", response_model=Pair)
    async def only_a():
        return {"a": 1}  # 故意不返回 b

    try:
        TestClient(demo_app).get("/only-a")
    except ResponseValidationError as exc:
        print(f"      抛出异常：{type(exc).__name__}")
        lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip()][:3]
        for line in lines:
            print(f"      {line[:140]}")
        print()
        return True
    print("      没有抛异常 —— 与预期不符")
    print()
    return False


def main() -> None:
    failures: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        """关键断言。失败会记进 failures，最后统一汇报。"""
        print(f"{(OK if condition else BAD)} {label}")
        if detail:
            print(f"      {detail}")
        if not condition:
            failures.append(label)

    print("=" * 68)
    print("第一部分 · 请求体与校验")
    print("=" * 68)
    print()

    # ---- 正常请求 ----
    body = {
        "messages": [
            {"role": "system", "content": "你是一个简洁的助手"},
            {"role": "user", "content": "用一句话介绍 FastAPI"},
        ],
        "model": "deepseek-chat",
        "temperature": 0.7,
    }
    r = show("POST", "/chat", "合法请求：请求体被模型校验通过，返回骨架回复", json=body)
    expect("返回 200 且响应形状符合 ChatResponse",
           r.status_code == 200
           and set(r.json().keys()) == {"session_id", "model", "reply", "usage", "finish_reason"},
           f"响应字段：{sorted(r.json().keys()) if r.status_code == 200 else '—'}")

    r = show("POST", "/chat", "只传必填字段：optional 的 model/temperature 走默认值",
             json={"messages": [{"role": "user", "content": "hi"}]})
    expect("temperature 缺省时默认 0.7，model 默认 deepseek-chat",
           r.status_code == 200 and r.json()["model"] == "deepseek-chat")

    # ---- 故意传错：全部应该在进入函数前被拦下 ----
    print("-" * 68)
    print("以下是故意传错的，全部应该在「进入你的函数之前」被拦下")
    print("-" * 68)
    print()

    r = show("POST", "/chat", "messages 为空数组 → 违反 min_length=1",
             json={"messages": []})
    expect("空 messages 被拦下（422）", r.status_code == 422)

    r = show("POST", "/chat", "role 传了不存在的值 → 报错会列出所有合法取值",
             json={"messages": [{"role": "banana", "content": "hi"}]})
    expect("非法 role 被拦下（422）",
           r.status_code == 422 and "system" in r.text)

    r = show("POST", "/chat", "temperature=5 越界 → ge/le 约束生效",
             json={"messages": [{"role": "user", "content": "hi"}], "temperature": 5})
    expect("越界的 temperature 被拦下（422）", r.status_code == 422)

    r = show("POST", "/chat", "content 为空串 → min_length=1 生效",
             json={"messages": [{"role": "user", "content": ""}]})
    expect("空 content 被拦下（422）", r.status_code == 422)

    r = show("POST", "/chat", "完全不传请求体 → 直接 422",
             )
    expect("缺请求体被拦下（422）", r.status_code == 422)

    print()
    print("=" * 68)
    print("第二部分 · response_model 到底在不在运行时生效")
    print("=" * 68)
    print()

    r = show("POST", "/chat/sessions", "创建会话（注意响应里有没有密钥）",
             json={"title": "关于 FastAPI 的第一次对话"})
    sid = r.json().get("session_id", "") if r.status_code == 200 else ""

    expect("响应 JSON 的字段**恰好**是 SessionOut 声明的三个",
           set(r.json().keys()) == {"session_id", "title", "created_at"},
           f"实际字段：{sorted(r.json().keys())}")
    expect("响应里搜不到任何密钥痕迹",
           "SECRET" not in r.text and "api_key" not in r.text)

    print()
    print("↑ 上面是「响应」。下面是同一时刻「服务端内存里」的真实对象：")
    print()

    internal = _SESSIONS.get(sid)
    if internal is None:
        expect("内部存储中能找到这个会话", False, "拿不到内部对象，无法对照")
    else:
        print(f"    内部对象类型：{type(internal).__name__}")
        print(f"    内部对象字段：{sorted(internal.model_dump().keys())}")
        print(f"    内部对象的密钥：{internal.upstream_api_key}")
        print()
        expect("内部对象**确实**带着 upstream_api_key",
               "upstream_api_key" in internal.model_dump(),
               "证明不是「我们忘了设密钥」，而是「响应按契约裁剪了」")
        expect("而对外响应里没有这个字段",
               "upstream_api_key" not in r.json(),
               "同一个对象，进出的形状由 response_model 决定")

    # ---- 路径参数约束 ----
    print()
    r = show("GET", f"/chat/sessions/{sid}", "路径参数正常")
    expect("按 ID 查到会话，且仍无密钥泄漏",
           r.status_code == 200 and "api_key" not in r.text)

    r = show("GET", "/chat/sessions/abc", "ID 短于 min_length=8 → 422（连存储都不会查）")
    expect("过短的 session_id 被拦下（422）", r.status_code == 422)

    r = show("GET", "/chat/sessions/000000000000",
             "格式合法但不存在 → 404（业务判断，不是 422）")
    expect("不存在的会话返回 404 而非 422", r.status_code == 404)

    r = show("GET", "/chat/sessions", "列表接口：response_model=list[SessionOut]")
    expect("列表中每一项都被裁剪，无密钥泄漏",
           r.status_code == 200 and "api_key" not in r.text)

    # ---- Header / Cookie ----
    print()
    print("=" * 68)
    print("第三部分 · Header 与 Cookie")
    print("=" * 68)
    print()

    r = show("GET", "/chat/whoami", "不带头 → X-Client-Id 是必填的，422")
    expect("缺 X-Client-Id 被拦下（422）", r.status_code == 422)

    r = show("GET", "/chat/whoami", "带上头 → 下划线 x_client_id 自动匹配 x-client-id",
             headers={"X-Client-Id": "cli-demo-001", "User-Agent": "check-day02/1.0"})
    expect("带上 X-Client-Id 后 200",
           r.status_code == 200 and r.json()["client_id"] == "cli-demo-001")

    r = show("GET", "/chat/whoami", "同时带上 Cookie",
             headers={"X-Client-Id": "cli-demo-001"},
             cookies={"session_token": "tok-abc"})
    expect("Cookie 被读到", r.status_code == 200 and r.json()["has_session_token"] is True)

    # ---- 补充：response_model 的反向坑 ----
    print()
    print("=" * 68)
    print("第四部分 · response_model 的反向坑：声明了但没返回")
    print("=" * 68)
    print()

    expect("缺字段时会抛 ResponseValidationError（不是静默通过）",
           check_missing_field_behavior(),
           "所以「我明明定义了字段，响应里却没有」的原因只有一个：函数没返回它")

    # ---- 汇总 ----
    print("=" * 68)
    if failures:
        print(f"{BAD} 有 {len(failures)} 项未通过：")
        for f in failures:
            print(f"    - {f}")
    else:
        print(f"{OK} 全部断言通过")
    print("=" * 68)
    print()
    print("结论：校验发生在函数执行之前；response_model 在运行时裁剪出参。")
    print("      两件事都是「声明式」——你只描述形状，框架负责执行。")


if __name__ == "__main__":
    main()
