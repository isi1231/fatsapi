# Day 3 · 自定义校验器与泛型响应包装

> 产出：`app/schemas/common.py`（`ApiResponse[T]`）、
> `app/schemas/chat.py`（`normalize_role` + `check_sampling_consistency`）、
> `POST /chat/validate`
> 验收：能写出一条 Field 表达不了的规则，并让它在正确的时机生效

---

## 一、先问：Field 到底缺什么

Day 2 我们让 Field 干了所有活，但有三类规则它**天生做不到**：

| 类型 | 例子 | 为什么 Field 不行 |
| --- | --- | --- |
| **跨字段** | `temperature=0` 时 `top_p` 必须为 1 | Field 只能看到自己那一个字段 |
| **需要判断类型** | 把 `"human"` 修正成 `"user"` | 约束只能「拒绝」，不能「修正」 |
| **依赖外部状态** | 这个 session_id 必须属于当前用户 | 需要查数据库，Field 拿不到上下文 |

今天的三个工具，正好一人管一类：

```
@field_validator(mode="before")   →  修正脏数据（能救就救）
@field_validator(mode="after")    →  依赖「已转换好类型」的单字段规则
@model_validator(mode="after")    →  跨字段规则
```

---

## 二、`mode="before"` 和 `mode="after"` 的区别

这是今天最容易记混的地方。先看实跑出来的执行顺序：

```
① model_validator(before)  ← 原始输入，还是原始 dict
② field_validator(before)  ← 还没做类型转换
③ 类型转换 + str_strip_whitespace + 约束检查（无钩子，静默执行）
④ field_validator(after)   ← 约束已经检查完了
⑤ model_validator(after)   ← 拿到完整实例
```

**关键在 ③ 这一步。** `Literal` 校验、`min_length`、`ge/le` 全在这里发生。
所以：

- 写在 **before** 的代码 → **跑在 `Literal` 校验之前**，脏数据还有救
- 写在 **after** 的代码 → 跑在之后，那时 `"human"` 早就被判非法了

这就是为什么 `normalize_role` 必须用 `mode="before"`：

```python
@field_validator("role", mode="before")
@classmethod
def normalize_role(cls, value: object) -> object:
    if isinstance(value, str):
        normalized = _ROLE_ALIASES.get(value.strip().lower())
        if normalized is not None:
            return normalized
    return value
```

实测效果 —— 同一个字段，**进来是 `human`，出去是 `user`**：

```
请求  {"messages": [{"role": "human", "content": "你好"}]}
响应  {"code":0,"message":"校验通过","data":{"messages":[{"role":"user",...}]}}
```

连 `"  AI  "`（带空格、大写）也能洗成 `assistant` —— 因为 `strip().lower()` 在那里。

### 三个容易写错的地方

**① 为什么参数和返回值类型都是 `object`？**
因为在 before 阶段输入可能是**任何类型**。你写 `value: str` 是在撒谎，而且 `isinstance` 检查也没了意义。用 `object` 才是诚实的，它也在提醒你：**必须先判断类型**。

**② 归一化不了怎么办？原样返回。**
```python
return value        # 不在映射表里 → 原样交回去
```
`"banana"` 出去后会被 `Literal` 拒绝 → 422，报错里还列出所有合法值。

**能救的救，救不了必须报错。** 绝不能悄悄替换成某个默认值 —— 那会让客户端以为自己的输入被接受了，实际数据已经变了。

**③ `@classmethod` 不能省。**
Pydantic v2 要求 `field_validator` 装饰的函数是类方法。忘了加会在**定义类的时候**就报错，不会拖到运行时。

---

## 三、`model_validator`：跨字段规则

`ChatRequest` 里加了一条：

```python
@model_validator(mode="after")
def check_sampling_consistency(self) -> "ChatRequest":
    if self.temperature == 0 and self.top_p != 1.0:
        raise ValueError("temperature=0 表示贪心解码，此时 top_p 必须为 1.0"
                         f"（当前 temperature=0, top_p={self.top_p}）")
    return self
```

实测：

| 输入 | 结果 | 为什么 |
| --- | --- | --- |
| `temperature=0, top_p=0.5` | 422 | 各自合法，**组合**非法 |
| `temperature=0, top_p=1.0` | 200 | 合法组合 |
| `temperature=0.7, top_p=0.5` | 200 | 规则只在 `temp=0` 时检查，不误伤 |

两个细节：

**(1) `mode="after"` 必须 `return self`。**
此时它拿到的是一个**已经构造好的模型实例**，所以能直接 `self.temperature`。
但 `return` 不能忘 —— 忘了返回 None，Pydantic 会报错。这是最常见的手误。

**(2) 一个必须知道的缺点：`loc` 精度会下降。**

对比两种校验收到的报错：

```json
// 字段级（Literal 校验）
{"type":"literal_error","loc":["body","messages",0,"role"], ...}
//                                                ↑ 一路定位到具体字段

// 模型级（model_validator）
{"type":"value_error","loc":["body"], "msg":"Value error, temperature=0 ..."}
//                                ↑ 只到 body，看不到是哪个字段的问题
```

`loc` 只到 `["body"]`，客户端没法靠 `loc` 做字段高亮，只能去读 `msg`。

**这是跨字段校验的固有代价** —— 既然规则牵涉多个字段，就没有「某一个」字段可以归咎。
如果你很在意客户端的错误定位体验，可以考虑：把校验信息同时塞进 `msg` 的结构化部分，
或者干脆用自定义异常 + Day 5 的异常处理器统一包装。

---

## 四、`str_strip_whitespace` 与 `min_length` 的配合

```python
model_config = ConfigDict(str_strip_whitespace=True)

content: str = Field(..., min_length=1, max_length=10_000)
```

**这两行必须一起写，少一行就有漏洞。**

实测：传 `{"content": "   "}`（三个空格）→ **422**：

```json
{"type":"string_too_short","loc":["body","messages",0,"content"],
 "msg":"String should have at least 1 character","input":"   ","ctx":{"min_length":1}}
```

从执行顺序可以解释为什么能拦住：`str_strip_whitespace` 在 **③** 阶段、
`min_length` 检查也在 **③**，但 strip 在前 —— 空格先被去掉，
字符串变成 `""`，长度 0 < 1，检查失败。

**没有 `str_strip_whitespace` 会怎样？** 传 `"   "` 长度是 3，`min_length=1` 判定通过，
你拿到一个内容全是空格的"消息"。这种数据一旦进了数据库或者发给模型，就是脏数据。

> 📌 记住这个组合：**`str_strip_whitespace=True` + `min_length=1`** ——
> 「非空字符串」约束以后一律这么写。

---

## 五、`extra="forbid"`：拼错字段名必须报错

```python
model_config = ConfigDict(extra="forbid")
```

Pydantic 的**默认行为是 `ignore`**：多余的字段静默丢弃。这对**对外接口**来说很危险：

```python
# 客户端想传 temperature，拼错成了 temprature
{"messages": [...], "temprature": 1.5}
```

- 默认（ignore）：服务返回 200，客户端以为参数生效了，实际用的是默认值 0.7 —— **排查这种 bug 能耗掉一下午**
- `extra="forbid"`：直接 422

```json
{"type":"extra_forbidden","loc":["body","temprature"],
 "msg":"Extra inputs are not permitted","input":0.5}
```

**注意这里和 Day 2 的一个呼应：**

| 方向 | 多余字段的默认行为 |
| --- | --- |
| **入参**（请求体，默认 `ignore`） | 静默丢弃 → 所以我们要主动改成 `forbid` |
| **出参**（`response_model`） | 静默丢弃 → 这正是安全特性，不用改 |

一边要防呆，一边要防泄漏。同一个机制，两个方向，取舍相反。

---

## 六、泛型响应包装 `ApiResponse[T]`

### 为什么要统一外壳

如果每个接口的成功/失败结构都不一样，客户端就得为每个接口写一套解析逻辑。
统一成 `{code, message, data}` 后，客户端只写一次。

### 写法

```python
T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(0)
    message: str = Field("ok")
    data: T | None = Field(None)

    @classmethod
    def ok(cls, data: T, message: str = "ok") -> "ApiResponse[T]":
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, code: int, message: str) -> "ApiResponse[T]":
        return cls(code=code, message=message, data=None)
```

用起来：

```python
@router.post("/validate", response_model=ApiResponse[ChatRequest])
async def validate_request(payload: ChatRequest) -> ApiResponse[ChatRequest]:
    return ApiResponse.ok(payload, message="校验通过")
```

### 泛型不是装饰 —— 有实测证据

`/docs` 里 `data` 字段**真的展开成了具体结构**。从 OpenAPI schema 里直接读出来：

```
OpenAPI 里的泛型模型：['ApiResponse_ChatRequest_']
ApiResponse_ChatRequest_ → data 字段：
  {'anyOf': [{'$ref': '#/components/schemas/ChatRequest'}, {'type': 'null'}], ...}
```

Pydantic 为**每个具体参数化**生成一个独立 schema（`ApiResponse_ChatRequest_`），
`data` 指向 `ChatRequest`。所以调用方在 `/docs` 里能看到 `data` 的完整字段说明，
而不是一个空的 `{}`。

**如果不参数化**（直接写 `response_model=ApiResponse`），`data` 就会退化成无约束的任意类型。
所以 `[T]` 这个方括号一定要带上。

### 重要约定：两套「状态」怎么分工

引入 `code` 之后，系统里就有两套状态表达了。这个必须提前约定，否则团队一定吵架：

| 层 | 管什么 | 取值 |
| --- | --- | --- |
| **HTTP 状态码** | 请求本身有没有被正确处理 | 200 / 404 / 422 / 500 |
| **业务 code** | 业务逻辑上成功没有 | 0 成功，非 0 是具体错误 |

**「余额不足」应该返回 HTTP 200 + code 1001，而不是 HTTP 400。**

理由很实在：如果你用 4xx 表达业务失败，网关、监控告警、客户端的自动重试逻辑
全都会把它当成「请求有问题」来处理 —— 但请求其实一点问题都没有。

---

## 七、422 里的 `type` 速查（Day 2 + Day 3 实测汇总）

| `type` | 触发场景 | 由谁产生 |
| --- | --- | --- |
| `missing` | 必填项没传 | 框架 |
| `int_parsing` | 字符串转 int 失败 | 框架 |
| `string_too_short` | 短于 `min_length`（strip 之后） | 框架 |
| `too_short` | 列表短于 `min_length` | 框架 |
| `literal_error` | 值不在 `Literal` 里 | 框架 |
| `less_than_equal` | 超过 `le` 上限 | 框架 |
| **`extra_forbidden`** | **传了未声明的字段** | **`extra="forbid"`** |
| **`value_error`** | **model_validator 抛 ValueError** | **你的 `raise`** |

最后一行有个实用推论：**看到 `value_error` 且 `loc` 只到 `["body"]`，
就是自定义的跨字段校验拦下的。** 这类报错的 `msg` 是你自己写的文案，
所以请务必写清楚 —— 它是客户端唯一能拿到的线索。

---

## 八、验收：五组对照实验

服务你自己起着，对着 <http://127.0.0.1:8000/docs> 的 `POST /chat/validate` 试下面五组。
每一组代表一种「命运」：

| 你传的 | 预期结果 | 谁干的 |
| --- | --- | --- |
| `"role": "human"` | 变成 `user` | `normalize_role`（before） |
| `"role": "banana"` | 422 `literal_error` | `Literal` |
| `"content": "   "` | 422 `string_too_short` | strip + `min_length` |
| `temperature=0, top_p=0.5` | 422 `value_error`（loc 只到 body） | `check_sampling_consistency`（after） |
| `"temprature": 1`（拼错） | 422 `extra_forbidden` | `extra="forbid"` |

一条命令全跑一遍：

```bash
python scripts/check_day03.py
```

---

## 九、验收清单

- [ ] 能说出 `before` / `after` 分别在执行顺序的哪一步
- [ ] 能解释为什么 `normalize_role` 必须是 `before`（用 `after` 会怎样）
- [ ] 知道 `model_validator(mode="after")` 必须 `return self`
- [ ] 知道跨字段校验的 `loc` 只到 `["body"]`，这是固有代价
- [ ] 能说出没有 `str_strip_whitespace` 时「非空」约束的漏洞
- [ ] 知道入参默认 `ignore` 多余字段、出参默认丢弃 —— 方向相反，取舍相反
- [ ] 能写一个带泛型参数的 `response_model`，并说清 `[T]` 为什么不能省
- [ ] `python scripts/check_day03.py` 全绿

---

## 十、今天的 5 个知识点（面试会问的形态）

1. **Pydantic v2 的校验时机是可以选的**：`before` 在类型转换和约束之前，
   `after` 在其之后。想做数据清洗必须用 `before`。
2. **Field 与 validator 的分工**：静态单字段约束用 Field，动态/跨字段用 validator。
   能用 Field 表达的就别写 validator —— 声明式的约束能自动进文档。
3. **校验器只做两件事**：修正，或报错。不做第三件事（比如静默替换成默认值）。
4. **泛型模型在 OpenAPI 里会展开成独立 schema**，这是 `ApiResponse[Foo]` 比
   `ApiResponse` 值钱的地方。
5. **HTTP 状态码与业务 code 是两层语义**，不要用 4xx 表达业务失败。

### 顺带说一句：这个技能直接迁移到 LLM structured output

`week1/agent_demo` 里的 `parse_json_response()` 是在**事后**用代码校验模型输出。
而今天学的东西可以换个方向用：

> 把 Pydantic 模型转成 JSON Schema 喂给模型（OpenAI 的 `response_format` /
> tool calling 的 `parameters`），**让模型在生成时就受约束**。

同一套模型定义，既能校验 HTTP 请求，又能约束模型输出。
这就是为什么值得把 `schemas/` 单独分一层 —— Day 4 讲工具调用时你会再见到它。

---

## 十一、埋下的伏笔

| 伏笔 | 什么时候填 |
| --- | --- |
| `ApiResponse` 目前只用在 `/chat/validate` 一个接口上 | Day 5 统一错误格式后铺开到所有接口 |
| `fail(code, message)` 里的 code 还没有具体定义 | Day 5 定义业务错误码 |
| `value_error` 的 `msg` 里塞了中文说明，但结构不统一 | Day 5 用自定义异常 + 异常处理器统一 |
| `model_validator` 拿不到数据库 | Day 4 依赖注入才是「需要外部上下文」的正解 |
| `ApiResponse[ChatRequest]` 回显了完整请求 | Day 7 接真模型后，回显会换成真正的回复 |

---

**下一步（Day 4）**：依赖注入 `Depends` —— FastAPI 的灵魂，也是面试第一高频。
核心问题是：**「取当前登录用户」这件事，怎么做到业务代码里一行鉴权逻辑都不写？**
