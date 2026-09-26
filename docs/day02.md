# Day 2 · 请求体、Pydantic 模型与 response_model

> 产出：`app/schemas/chat.py`、`app/routers/chat.py`
> 验收：能读懂 422 的 `loc`；能说清 `response_model` 在运行时做了什么；
> 能让一个带密钥的对象安全地穿过接口而不泄漏

---

## 一、参数的四个来源：一条判定链

Day 1 只用了两种来源（路径、查询）。今天把剩下的补齐。FastAPI 的判定**按顺序**进行：

| 顺序 | 条件 | 判定为 | 从哪取 |
| --- | --- | --- | --- |
| 1 | 名字出现在路径 `{}` 里 | 路径参数 | URL 路径 |
| 2 | **类型是 `BaseModel` 子类** | **请求体** | JSON body |
| 3 | 显式用了 `Body()` / `Header()` / `Cookie()` | 按声明的来 | 对应位置 |
| 4 | 以上都不是 | 查询参数 | URL query string |

**第 2 条是今天的核心。** 看 Day 1 和今天的对比：

```python
# Day 1：标量参数 → 判定链走到第 4 条 → 查询参数
async def list_messages(session_id: str, limit: int = 10): ...

# Day 2：模型参数 → 在判定链第 2 条就被截住 → 请求体
async def chat(payload: ChatRequest): ...
```

**你不需要写任何标记**，把类型从 `str` 换成 `ChatRequest`，它自己就变成请求体了。
这就是「类型注解驱动一切」的又一处体现。

---

## 二、`Field()` 的三种「必填 / 可选」写法

`app/schemas/chat.py` 里的 `ChatRequest` 正好演示了三种：

```python
messages: list[Message] = Field(..., min_length=1)   # ... → 必填
model: str = Field("deepseek-chat")                  # 有默认值 → 可选
session_id: str | None = Field(None)                 # 默认 None → 可选，且允许传 null
```

| 写法 | 必填？ | 传 `null` 会怎样 |
| --- | --- | --- |
| `Field(...)` | 必填 | 422 |
| `Field("默认值")` | 可选 | 422（类型是 `str`，不接受 null） |
| `Field(None)` + 类型 `str \| None` | 可选 | 接受，值为 `None` |

**第三行那个 `| None` 不能省。** 只写 `session_id: str = None`，Pydantic v2 会认为你在声明一个「类型是 str 但默认值是 None」的矛盾字段 —— 传 null 进来会 422。类型和默认值必须一致。

### 约束写在 Field 里，不写在函数体里

```python
temperature: float = Field(0.7, ge=0.0, le=2.0)
max_tokens: int = Field(1024, gt=0, le=8192)
content: str = Field(..., min_length=1, max_length=10_000)
messages: list[Message] = Field(..., min_length=1)
```

行数一样多，但区别很大：

| | 写在 Field 里 | 写在函数体里 |
| --- | --- | --- |
| 违反时 | 422，**函数不执行** | 你得自己 raise |
| 文档 | 自动带上约束 | 无 |
| 复用 | 请求、响应、测试共用 | 只在那一处 |

---

## 三、`Literal`：把枚举写进类型

```python
role: Literal["system", "user", "assistant"]
```

传错时返回的报错是**主动列出所有合法值**的：

```json
{"type": "literal_error",
 "loc": ["body", "messages", 0, "role"],
 "msg": "Input should be 'system', 'user' or 'assistant'",
 "input": "banana"}
```

比 `role: str` + 手写 `if role not in (...): raise` 干净得多，而且客户端拿到的报错自带文档。

再看 `loc`：`["body", "messages", 0, "role"]` —— 它一路指到了**数组的第 0 个元素**。
请求嵌套多深，`loc` 就能定位多深。这是 422 里最该学会读的字段。

---

## 四、★ `response_model` 到底做了什么（今天的重点）

先说结论，再说证据。

**结论：`response_model` 不是文档声明，它是运行时的出参过滤器。**
函数返回的对象会被 Pydantic 按 `response_model` **重新构造一遍**，
没声明的字段**压根不会被写进输出**。

### 实测对照

`POST /chat/sessions` 这个接口，函数签名和实现是这样的：

```python
@router.post("/sessions", response_model=SessionOut)      # ← 对外：3 个字段
async def create_session(title: str = Body(..., embed=True)) -> SessionRecord:   # ← 返回：4 个字段
    record = SessionRecord(
        session_id=session_id,
        title=title,
        upstream_api_key="sk-SECRET-do-not-leak-1234567890",   # ← 敏感
        created_at=_now(),
    )
    _SESSIONS[session_id] = record
    return record          # ← 返回的是带密钥的那个对象
```

跑 `python scripts/check_day02.py`，同一时刻的两个视角：

**① HTTP 响应（客户端看到的）：**
```json
{"session_id":"bc4462e4f657","title":"关于 FastAPI 的第一次对话","created_at":"2026-09-26T05:06:51+00:00"}
```
字段恰好是 `['created_at', 'session_id', 'title']`，搜不到 `api_key`，也搜不到 `SECRET`。

**② 服务端内存里的真实对象（脚本直接打印出来的）：**
```
内部对象类型：SessionRecord
内部对象字段：['created_at', 'session_id', 'title', 'upstream_api_key']
内部对象的密钥：sk-SECRET-do-not-leak-1234567890
```

**这就是关键证据。** 不是「忘了设密钥」，而是 `upstream_api_key` 明明在内存对象里、
明明有值，只是**没有被写进响应**。

### 为什么这比「手写 del」好

| 做法 | 问题 |
| --- | --- |
| `data.pop("api_key")` | 每个接口都要记得写；漏一个就是事故 |
| 定义一个过滤函数 | 同上，而且散落各处 |
| **声明 `response_model`** | 形状由契约决定，**实现层想漏都漏不出去** |

安全属性从「人记得做对」变成了「结构上做不到错」。这是今天最值钱的一课。

### 反向的坑：声明了但没返回，会炸

`response_model` 是**双向**的。脚本第四部分现场搭了个最小 app 验证：

```python
class Pair(BaseModel):
    a: int
    b: int

@app.get("/only-a", response_model=Pair)
async def only_a():
    return {"a": 1}       # 少了 b
```

结果不是「静默补 null」，而是直接抛：

```
ResponseValidationError
{'type': 'missing', 'loc': ('response', 'b'), 'msg': 'Field required', 'input': {'a': 1}}
```

注意 `loc` 是 `('response', 'b')` —— 框架明确告诉你**响应里缺了 b**。
所以今后遇到「我明明定义了字段，响应里却没有」，原因只剩一个：函数根本没返回它。

> 另外一个容易误解的点：**多余的字段会被静默丢弃，不会报错**（上面 `/chat/sessions` 就是）。
> 丢字段不报错、缺字段才报错 —— 这两条不对称，记住。

---

## 五、同一概念两个模型：内部 vs 对外

今天的 `chat.py` 里有两对模型，这是真实项目的标准做法：

| 模型 | 用途 | 含敏感字段 |
| --- | --- | --- |
| `SessionRecord` | 服务端内部存储/传参 | ✅ 有 `upstream_api_key` |
| `SessionOut` | 对外响应 | ❌ 没有 |
| `ChatRequest` | 收进来的请求体 | —— |
| `ChatResponse` | 发出去的响应 | —— |

命名习惯上，`...Out` / `...Response` / `...Public` 表示对外。看到这类后缀，
就该默认它「只包含能公开的字段」。

`SessionOut` 上还挂了一个配置：

```python
model_config = ConfigDict(from_attributes=True)
```

它让模型能接受**任意带同名属性的对象**，不只是 dict。
Day 8 接上 SQLAlchemy 后，ORM 实例可以直接 `return` 出来，不用先转 dict。

---

## 六、Header 与 Cookie

```python
async def whoami(
    x_client_id: str = Header(...),
    user_agent: str | None = Header(None),
    session_token: str | None = Cookie(None),
): ...
```

**(1) 参数名的下划线会自动转成横线。**
`x_client_id` 匹配请求头 `x-client-id`（且不区分大小写）。想用别的名字就 `alias="X-Client-Id"`。
Cookie 不做这个转换，参数名就是 cookie 名。

**(2) Header 里的值全是字符串，但类型注解照样有效。**
你写 `retry_count: int = Header(0)`，FastAPI 会帮你转成 int，转不了就 422。
所以放心用类型注解 —— 和 body 走的是同一套校验机制。

实测报错里的 `loc` 是 `["header", "x-client-id"]`，位置信息同样精确。

**(3) 这个接口就是 Day 15 的伏笔。**
`X-Client-Id` 换成 `X-API-Key`，`Header(...)` 换成依赖注入里的校验函数，
就是完整的 API Key 鉴权。今天先把「怎么读头」这一步走通。

---

## 七、422 报错速查表（今天实测收集）

| `type` | 触发场景 | 出现位置示例 |
| --- | --- | --- |
| `missing` | 必填项没传 | `["body"]`、`["header","x-client-id"]` |
| `int_parsing` | 字符串转 int 失败 | `["path","n"]` |
| `string_too_short` | 字符串短于 `min_length` | `["path","session_id"]`、`["body","messages",0,"content"]` |
| `too_short` | 列表短于 `min_length` | `["body","messages"]` |
| `literal_error` | 值不在 `Literal` 里 | `["body","messages",0,"role"]` |
| `less_than_equal` | 超过 `le` 上限 | `["body","temperature"]` |

读 `loc` 的技巧：**从后往前读**。最后一项是出错的字段名，往前依次是它的父级容器，
`0` 这类数字是数组下标。所以 `["body","messages",0,"role"]` 读作：
「请求体 → messages 数组 → 第 0 条 → 它的 role 字段」。

---

## 八、三个必须亲手做的实验

服务你自己起着（我确认过 `--reload` 生效，我的改动已经自动加载了）。
打开 <http://127.0.0.1:8000/docs>，找到 `chat` 这一组：

### 实验 1 · 在文档里体验请求体

点开 `POST /chat` → **Try it out**，会把 `ChatRequest` 的完整 JSON Schema 直接展开给你，
连 `temperature` 的 0~2 范围和字段说明都在。改改数值直接执行，看响应。

### 实验 2 · 亲手让它 422

把 `role` 改成 `"banana"` 执行，读报错里的 `loc` 和 `msg`。
再把 `temperature` 改成 `5`，对比两次报错的 `type` 有什么不同。

### 实验 3 · 亲眼确认密钥没出去

执行 `POST /chat/sessions`，在响应里反复找 `SECRET` —— 找不到。
然后打开 `app/routers/chat.py`，确认那行密钥**确实写在代码里**。

这一步做完，`response_model` 就不再是一句「据说」了。

---

## 九、验收清单

- [ ] 能说出「为什么 `payload: ChatRequest` 自动就是请求体」（判定链第 2 条）
- [ ] 能区分 `Field(...)` / `Field("默认值")` / `Field(None) + | None` 三种写法
- [ ] 能在 422 里读懂 `loc: ["body","messages",0,"role"]` 的层级
- [ ] 能解释 `response_model` 是运行时过滤器，而不是文档声明
- [ ] 知道「多余字段静默丢弃、缺字段抛 ResponseValidationError」这个不对称
- [ ] 知道 Header 参数名的下划线会自动转横线
- [ ] `python scripts/check_day02.py` 全绿

---

## 十、今天的 5 个知识点（面试会问的形态）

1. **参数来源靠判定链决定，`BaseModel` 类型直接命中请求体**，无需显式标记。
2. **校验是声明式的**：约束写在 `Field` 里，违反时函数根本不执行。
3. **`response_model` 是运行时出参过滤器**，是「敏感字段不外泄」的结构性保障。
4. **内部模型与对外模型分离**（`Record` / `Out`），是契约设计的基本功。
5. **422（框架层，进函数前）vs 400/404（业务层，函数内）** 的边界要清楚。
   今天新增一条：**响应校验失败是 500，因为它发生在函数执行之后。**

---

## 十一、埋下的伏笔

| 伏笔 | 什么时候填 |
| --- | --- |
| `ChatResponse` 里的 `finish_reason` 有 `tool_calls` 选项 | Day 4 工具调用会真的用到它 |
| `_SESSIONS` 内存字典 | Day 8 换成数据库 |
| `SessionOut` 的 `from_attributes=True` | Day 8 直传 ORM 实例 |
| `/chat` 只返回假回复 | Day 7 接真模型、Day 11 改成 SSE 流式 |
| `Field` 的约束已经开始有点啰嗦 | Day 3 用 `field_validator` / `model_validator` 处理跨字段规则 |
| `X-Client-Id` 只是个摆设 | Day 15 变成真正的 API Key 鉴权 |

---

**下一步（Day 3）**：Pydantic v2 深入 —— 自定义校验器、跨字段约束、
以及**泛型响应包装 `ApiResponse[T]`**。核心问题是：
**当校验规则没法用 `Field` 表达时（比如「temperature 为 0 时 top_p 必须为 1」），该怎么写？**
