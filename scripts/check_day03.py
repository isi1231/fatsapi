"""Day 3 验证脚本：自定义校验器与泛型响应包装。

运行（在项目根目录）：
    python scripts/check_day03.py

今天要验证的核心命题只有一个：
**Field 表达不了的规则，能不能通过校验器实现，并且行为可预测？**

答案要落在这几组对照上：
    能救的（human → user）         → 静默修正
    救不了的（banana）             → 422
    跨字段的（temperature/top_p）  → 422
    拼错字段的（temprature）        → 422（而不是静默忽略）
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.chat import Message  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

client = TestClient(app)

OK = "✅"
BAD = "❌"
WARN = "⚠️ "


def show(method: str, url: str, note: str = "", **kwargs):
    resp = client.request(method, url, **kwargs)
    flag = OK if resp.status_code < 400 else WARN
    print(f"{flag} {resp.status_code}  {method} {url}")
    if note:
        print(f"      {note}")
    print(f"      {resp.text[:240]}")
    print()
    return resp


def base_body(**overrides) -> dict:
    """一个最小的合法请求体，方便按需覆盖字段。"""
    body = {"messages": [{"role": "user", "content": "你好"}]}
    body.update(overrides)
    return body


def check_execution_order() -> tuple[list[str], bool]:
    """把校验器的执行顺序真跑一遍，而不是背文档。

    做法：在每个钩子里记一行日志，最后按记录顺序打出来。
    另外用一个「长度刚好卡在边界」的字符串来判断
    `str_strip_whitespace` 和 `min_length` 谁先谁后。

    返回 (日志, 边界推断结果)。
    """
    from pydantic import (
        BaseModel as BM,
        ConfigDict as CC,
        Field as F,
        field_validator as fv,
        model_validator as mv,
    )

    def build(log: list[str]):
        """造一个带日志的模型。用工厂函数是为了跑两遍、各记各的日志。"""

        class Demo(BM):
            model_config = CC(str_strip_whitespace=True)
            name: str = F(min_length=2)

            @mv(mode="before")
            @classmethod
            def _mvb(cls, data):
                log.append("① model_validator(before)  ← 原始输入，还是原始 dict")
                return data

            @fv("name", mode="before")
            @classmethod
            def _fvb(cls, v):
                log.append("② field_validator(before)  ← 还没做类型转换")
                return v

            @fv("name", mode="after")
            @classmethod
            def _fva(cls, v):
                log.append("④ field_validator(after)   ← 约束已经检查完了")
                return v

            @mv(mode="after")
            def _mva(self):
                log.append("⑤ model_validator(after)   ← 拿到完整实例")
                return self

        return Demo

    # 第一遍：边界输入，判断 strip 和 min_length 谁先谁后。
    #   报错   → strip 先跑，长度变成 1 < 2
    #   不报错 → strip 后跑，先按长度 5 通过了检查
    strip_runs_first = False
    try:
        build([])(name="  a  ")
    except Exception:
        strip_runs_first = True

    # 第二遍：合法输入，记录完整顺序。
    # （第一遍会在 min_length 处中断，日志到 ② 就没了，所以必须跑两次。）
    order_log: list[str] = []
    build(order_log)(name="  ab  ")

    return order_log, strip_runs_first


def main() -> None:
    failures: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        print(f"{(OK if condition else BAD)} {label}")
        if detail:
            print(f"      {detail}")
        if not condition:
            failures.append(label)

    # ================= 第一部分：field_validator 归一化 =================
    print("=" * 68)
    print("第一部分 · field_validator(mode='before')：能救就救")
    print("=" * 68)
    print()

    r = show("POST", "/chat/validate", "role 传别名 human → 应该被洗成 user",
             json={"messages": [{"role": "human", "content": "你好"}]})
    if r.status_code == 200:
        got = r.json()["data"]["messages"][0]["role"]
        expect("human 被归一化成 user", got == "user",
               f"出口的 role = {got!r}")
        print("      ↑ 同一个字段，进来是 human、出去是 user —— 脏数据在进入业务逻辑前就洗干净了")
    else:
        expect("human 被归一化成 user", False, f"状态码 {r.status_code}")
    print()

    r = show("POST", "/chat/validate", "大小写 + 空格混写：'  AI  ' → assistant",
             json={"messages": [{"role": "  AI  ", "content": "你好"}]})
    if r.status_code == 200:
        got = r.json()["data"]["messages"][0]["role"]
        expect("'  AI  ' 被归一化成 assistant", got == "assistant", f"出口 = {got!r}")
    else:
        expect("'  AI  ' 被归一化成 assistant", False, f"状态码 {r.status_code}")
    print()

    # 关键对照：救不了的必须报错，不能悄悄替换
    r = show("POST", "/chat/validate", "role 传 banana → 映射表里没有，必须报错",
             json={"messages": [{"role": "banana", "content": "你好"}]})
    expect("归一化不了的 role 被拦下（422，而不是被替换成某个默认值）",
           r.status_code == 422 and "system" in r.text,
           "「顺手修正」和「守住底线」不冲突：救不了就必须报错")

    # ================= 第二部分：strip 与 min_length 的配合 =================
    print()
    print("=" * 68)
    print("第二部分 · str_strip_whitespace 与 min_length 的配合")
    print("=" * 68)
    print()

    r = show("POST", "/chat/validate", "content 是三个空格 → strip 后为空",
             json={"messages": [{"role": "user", "content": "   "}]})
    expect("全空格的 content 被拦下（422）",
           r.status_code == 422,
           "这条如果变绿，说明「不能为空」的约束有漏洞")

    r = show("POST", "/chat/validate", "content 首尾有空格 → 应该被去掉",
             json={"messages": [{"role": "user", "content": "  你好  "}]})
    if r.status_code == 200:
        got = r.json()["data"]["messages"][0]["content"]
        expect("首尾空格被 strip", got == "你好", f"出口的 content = {got!r}")
    else:
        expect("首尾空格被 strip", False, f"状态码 {r.status_code}")

    # ================= 第三部分：model_validator 跨字段 =================
    print()
    print("=" * 68)
    print("第三部分 · model_validator：Field 做不到的跨字段规则")
    print("=" * 68)
    print()

    r = show("POST", "/chat/validate",
             "temperature=0 但 top_p=0.5 → 违反联动规则",
             json=base_body(temperature=0, top_p=0.5))
    expect("跨字段规则生效（422）",
           r.status_code == 422 and "top_p" in r.text,
           "两个字段各自都合法（0 在 0~2 内，0.5 在 0~1 内），但组合起来非法")

    r = show("POST", "/chat/validate",
             "temperature=0 且 top_p=1.0 → 合法组合",
             json=base_body(temperature=0, top_p=1.0))
    expect("合法组合放行（200）", r.status_code == 200)

    r = show("POST", "/chat/validate",
             "temperature=0.7 且 top_p=0.5 → 不触发规则（只在 temp=0 时检查）",
             json=base_body(temperature=0.7, top_p=0.5))
    expect("非边界情况不被误伤（200）", r.status_code == 200)

    # ================= 第四部分：extra="forbid" =================
    print()
    print("=" * 68)
    print("第四部分 · extra='forbid'：拼错字段名必须报错")
    print("=" * 68)
    print()

    body = base_body()
    body["temprature"] = 0.5  # 故意拼错 temperature
    r = show("POST", "/chat/validate", "字段名拼错成 temprature",
             json=body)
    expect("未知字段被拒绝（422，而不是静默忽略）",
           r.status_code == 422 and "temprature" in r.text,
           "默认行为是 ignore —— 服务会安然返回 200，而客户端以为参数生效了")

    # ================= 第五部分：ApiResponse 泛型外壳 =================
    print()
    print("=" * 68)
    print("第五部分 · 泛型响应包装 ApiResponse[T]")
    print("=" * 68)
    print()

    r = show("POST", "/chat/validate", "正常请求的响应外壳",
             json=base_body())
    if r.status_code == 200:
        keys = set(r.json().keys())
        expect("响应是 {code, message, data} 三件套",
               keys == {"code", "message", "data"},
               f"实际字段：{sorted(keys)}")
        expect("code=0 表示成功",
               r.json()["code"] == 0 and r.json()["message"] == "校验通过")
        expect("业务数据在 data 里，且是处理后的 ChatRequest",
               set(r.json()["data"].keys()) >= {"messages", "model", "temperature"})

    # 泛型在 OpenAPI 里是否展开成了具体 schema
    components = app.openapi()["components"]["schemas"]
    generic_names = sorted(n for n in components if "ApiResponse" in n)
    print(f"      OpenAPI 里的泛型模型：{generic_names}")
    if generic_names:
        target = generic_names[0]
        data_schema = components[target]["properties"]["data"]
        print(f"      {target} → data 字段的 schema：{data_schema}")
    print()
    expect("泛型被展开成具体 schema（data 指向 ChatRequest）",
           any("ChatRequest" in n for n in generic_names),
           "泛型不是装饰：它让 /docs 里的 data 能展开成真实结构")

    # ================= 第六部分：契约层脱离 HTTP 单独跑 =================
    print()
    print("=" * 68)
    print("第六部分 · 契约层可以脱离 HTTP 单独验证")
    print("=" * 68)
    print()

    m = Message(role="  HUMAN ", content="  你好  ")
    print("      Message(role='  HUMAN ', content='  你好  ')")
    print(f"      → role={m.role!r}   content={m.content!r}")
    print()
    expect("模型本身就能完成归一化，不用启动服务、不用发请求",
           m.role == "user" and m.content == "你好",
           "这就是把 schemas 单独分层的回报：纯逻辑，可以直接单测")

    # ================= 第七部分：校验器执行顺序 =================
    print()
    print("=" * 68)
    print("第七部分 · 校验器的执行顺序（实跑出来的，不是背文档）")
    print("=" * 68)
    print()

    order_log, strip_first = check_execution_order()
    for line in order_log:
        if line.startswith("④"):
            print("      ③ 类型转换 + str_strip_whitespace + 约束检查（无钩子，静默执行）")
        print(f"      {line}")
    print()
    expect("str_strip_whitespace 在 min_length 之前执行",
           strip_first,
           "所以 '  a  ' 被判为长度 1（而不是 5）—— 空白绕不过长度约束")

    # ================= 汇总 =================
    print()
    print("=" * 68)
    if failures:
        print(f"{BAD} 有 {len(failures)} 项未通过：")
        for f in failures:
            print(f"    - {f}")
    else:
        print(f"{OK} 全部断言通过")
    print("=" * 68)
    print()
    print("结论：Field 管单字段的静态约束，校验器管动态规则。")
    print("      before 校验器能修正脏数据，after 校验器能看到整个模型。")
    print("      修正不了的一律报错 —— 不猜、不静默替换。")


if __name__ == "__main__":
    main()
