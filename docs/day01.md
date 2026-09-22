# Day 1 · 第一个接口与路由组织

> 产出：`app/main.py`、`app/routers/health.py`、`app/routers/playground.py`
> 验收：`/docs` 能看到全部接口；改代码后自动重载；传非法参数返回 422 而不是 500

---

## 一、先建立心智模型：一个请求进来，谁在处理

这一步比写代码重要。**uvicorn 和 FastAPI 是两个不同的东西**，很多人一开始就混在一起：

```
浏览器 / curl
      │  HTTP 请求（TCP 上的字节流）
      ▼
┌─────────────────────────────────┐
│  uvicorn —— ASGI 服务器          │  监听端口、解析 HTTP、驱动事件循环
│  它不认识你的路由，只认 ASGI 协议  │
└─────────────────────────────────┘
      │  ASGI 调用：scope / receive / send
      ▼
┌─────────────────────────────────┐
│  FastAPI app 对象                │  路由匹配 → 参数校验 → 依赖注入 → 调函数
│  它不认识 TCP，只管处理请求对象    │
└─────────────────────────────────┘
      │  普通 Python 函数调用
      ▼
   你的业务函数
```

所以启动命令 `uvicorn app.main:app` 要拆成两半读：

| 部分 | 含义 |
| --- | --- |
| `uvicorn` | 用哪个服务器 |
| `app.main:app` | 「模块路径 : 变量名」—— import `app.main`，取出里面的 `app` 对象 |

**这条命令的本质是：让 uvicorn 去 import 你的应用对象。**
理解了这点，后面 `--reload`、`--workers`、gunicorn 的配置就都是同一个道理。

---

## 二、目录结构

```
fastapi/
├── app/
│   ├── __init__.py          # 包说明 + 分层约定（写在 docstring 里当备忘录）
│   ├── main.py              # ★ 装配层：建 app、挂路由
│   └── routers/
│       ├── __init__.py
│       ├── health.py        # ★ 健康检查
│       └── playground.py    # ★ 参数练习
├── scripts/
│   └── check_day01.py       # 一键验证脚本
└── requirements.txt
```

Day 1 只有三层里的两层（装配 + 编排）。`schemas/`、`services/`、`repositories/`、`core/` 会随着 Day 2–17 逐步长出来 —— **不要提前建空目录**，按需生长。

---

## 三、逐文件讲解

### 1. `app/main.py` —— 装配层，只做三件事

```python
app = FastAPI(title=..., description=..., version="0.1.0")

app.include_router(health.router)
app.include_router(playground.router)

@app.get("/")
async def root(): ...
```

**这个文件里一行业务逻辑都不该有。** 理由很实在：它是整个应用唯一的入口，
将来路由多了、中间件多了、异常处理器多了，能不能一眼看出「什么挂在什么位置」，
取决于它够不够干净。

`FastAPI(...)` 那三个参数不是装饰品 —— 它们直接渲染进 `/docs` 的页头和
`/openapi.json`。面试官打开你的 `/docs`，第一眼看到的就是 `title` 和 `description`。

`@app.get("/")` 这种直接挂在 app 上的写法，只适合根路径、探针这类**零散接口**。
有主题的接口一律走 `APIRouter`，见下。

### 2. `app/routers/health.py` —— 你的第一个 APIRouter

```python
router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

三件事值得说：

**(1) `APIRouter` 就是「路由表的局部变量」。**
它和 `app` 一样能挂路由，只是不会立刻生效，要等 `include_router` 才接入主应用。
好处是你可以在文件里把前缀、标签、依赖一次性声明好，`main.py` 那边只写一行。

**(2) 路径写 `""` 而不是 `"/"`。**

| 写法 | 实际路径 | 访问 `/health` 的结果 |
| --- | --- | --- |
| `@router.get("")` | `/health` | 直接 200 ✅ |
| `@router.get("/")` | `/health/` | 307 跳转到 `/health/`，多一次往返 ⚠️ |

Starlette 默认开着 `redirect_slashes`，所以写 `"/"` 不会报错，只是白跑一趟。
**能少一次往返就少一次** —— 这不是强迫症，高频接口下它是实打实的开销。

**(3) 为什么健康检查要单开一个文件。**
它和业务无关，是给运维用的。生产环境里 K8s 探针只会打这一个路径，
独立出来便于给它单独配限流豁免、单独决定要不要鉴权。

顺带记住两个接口的分工（Day 18 部署会真的用到）：

| 接口 | 语义 | 数据库挂了应该返回 |
| --- | --- | --- |
| `/health`（liveness） | 进程还活着吗？挂了就**重启** | 200（进程没死） |
| `/health/ready`（readiness） | 能收流量吗？ | 503（别把请求发给它） |

### 3. `app/routers/playground.py` —— 参数是怎么进函数的

这是今天唯一需要背下来的规则：

> **参数名出现在路径的 `{}` 里 → 路径参数；没出现 → 查询参数。**
> 有没有默认值、是什么类型，都**不影响**这个判定。

拿 `squares` 举例：

```python
@router.get("/squares/{n}")
async def squares(n: int, offset: int = 0): ...
```

- `n` 在 `{}` 里 → 路径参数
- `offset` 不在 → 查询参数，因为给了默认值所以可以省略

然后看 `list_messages` 的四种签名，正好覆盖全部组合：

```python
async def list_messages(
    session_id: str,          # 无默认值 → 必填
    role: str | None = None,  # 默认 None → 可选，可不传
    skip: int = 0,            # 默认 0    → 可选
    limit: int = 10,          # 默认 10   → 可选
): ...
```

**类型注解做三件事，全是自动的：**

| 注解 | 转换 | 校验 | 文档 |
| --- | --- | --- | --- |
| `n: int` | `"3"` → `3` | 转不了就 422 | 标成 integer |
| `offset: int = 0` | 同上，但可省略 | 同上 | 标成可选 |
| `role: str \| None = None` | 不转换 | 允许不传 | 标成 optional |

最后那句返回类型注解 `-> dict` 也不是写给自己看的，FastAPI 拿它生成响应 schema。

---

## 四、三个必须亲手做的实验

光看不算学会，这三个做完 Day 1 才算落地。

### 实验 1 · 打开自动文档

```bash
uvicorn app.main:app --reload --port 8000
```

浏览器打开 <http://127.0.0.1:8000/docs>，你应该看到：

- 三组标签：`meta` / `health` / `playground`
- 每个接口右边有 **Try it out** 按钮，可以直接在页面上发请求
- `/playground/squares/{n}` 的 `n` 被标成 `integer`，`offset` 被标成可省略

**试试点 Try it out 传个 `abc`**，页面会直接显示 422 的响应体。整个接口的调试闭环不用写一行客户端代码。

同时看看 <http://127.0.0.1:8000/redoc> —— 同一个 OpenAPI 数据的另一种渲染，适合当文档页给人看。

### 实验 2 · 看热重载

服务保持运行，把 `app/routers/playground.py` 里 `hello` 的返回值改一下：

```python
return {"message": f"你好，{name}", "changed": True}
```

保存，**不要重启服务**。终端里会出现：

```
WARNING:  WatchFiles detected changes in 'app\routers\playground.py'. Reloading...
INFO:     Application startup complete.
```

再刷新 `/docs` 或重发请求，新字段就在了。

> `--reload` 的原理是监视文件变化 → 整个进程重启。
> 记住是**重启**，不是热更新：任何模块级状态都会丢。所以它只适合开发，
> 生产用 `--workers`（Day 18 会讲）。

### 实验 3 · 看 422 到底长什么样

```bash
curl http://127.0.0.1:8000/playground/squares/abc
```

拿到的是：

```json
{"detail":[{"type":"int_parsing","loc":["path","n"],
  "msg":"Input should be a valid integer, unable to parse string as an integer",
  "input":"abc"}]}
```

三个字段必须读懂：

| 字段 | 作用 |
| --- | --- |
| `loc` | 出错的位置，`["path","n"]` 表示路径里的 `n`；`["query","session_id"]` 表示查询参数 |
| `type` | 机器可读的错误类型，客户端可以据此做 i18n |
| `msg` | 给人看的说明 |

**关键结论：这是在进入你的函数之前拦下来的。**
你的 `squares()` 一次都没被执行，所以你永远不可能拿到一个非法值 ——
不需要在每个函数开头写 `if not isinstance(n, int)`。这就是「声明式」的收益。

（422 是 FastAPI 对「语义错误」的定义：格式对、内容不合法。400 留给业务层自己抛，Day 5 会讲。）

---

## 五、实测结果

用 `scripts/check_day01.py` 跑的真实输出（TestClient 走 ASGI 直调，
不占端口，但走的是和真实请求完全一样的完整流程）：

```
✅ 200  GET /                                    {"message":"服务已启动","docs":"/docs"}
✅ 200  GET /health                              {"status":"ok"}
✅ 200  GET /health/ready                        {"status":"ok","checks":{"database":"not_configured"}}
✅ 200  GET /playground/hello/砚                  {"message":"你好，砚"}
✅ 200  GET /playground/squares/3?offset=10      {"n":3,"offset":10,"squares":[11,14,19]}
✅ 200  GET /playground/messages?session_id=s1&limit=2
                                                 {"session_id":"s1","total":20,"skip":0,"limit":2,...}

⚠️  422  GET /playground/squares/abc             {"detail":[{"type":"int_parsing","loc":["path","n"],...}]}
⚠️  422  GET /playground/messages                {"detail":[{"type":"missing","loc":["query","session_id"],...}]}
✅ 307  GET /playground/hello/砚/                 （redirect_slashes 跳转）
✅ 200  GET /playground/hello/砚/                 （客户端跟随重定向后）
```

真实 uvicorn 服务也确认过：`/` `/health` `/docs` `/openapi.json` 全部 200。

**自己跑一遍：**

```bash
python scripts/check_day01.py
```

> 脚本开头有一小段 `sys.path` 修正。原因和你之前在 `agent_demo/test/` 踩的坑是同一个：
> 直接执行 `python scripts/xxx.py` 时，Python 会把**脚本所在目录**放进 `sys.path[0]`，
> 而不会放当前工作目录，于是 `import app` 找不到包。
> 显式把项目根目录插到最前面就解决了。**这不是 hack，是这类脚本的标准做法。**

---

## 六、常见报错速查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `Error loading ASGI app. Could not import module "app.main"` | 启动目录不对 | 必须在**项目根目录**（有 `app/` 的那层）执行 |
| `[Errno 10048] address already in use` | 8000 端口被占 | `--port 8001`，或杀进程：`netstat -ano \| findstr :8000` |
| 改了代码没反应 | 启动时忘了 `--reload` | 加上它；已运行的需重启 |
| `/docs` 打开是空白 | 多半是浏览器缓存或 CDN 被墙 | Swagger UI 的 JS 走 CDN，改用 `/redoc` 试试 |
| 返回 307 而不是 200 | 路径尾斜杠不一致 | 见上文「写 `""` 不写 `"/"`」 |
| `ModuleNotFoundError: No module named 'app'` | 运行位置或 `sys.path` | 见上文脚本那段说明 |

---

## 七、验收清单

- [ ] `uvicorn app.main:app --reload --port 8000` 能起来
- [ ] `/docs` 里能看到 `meta` / `health` / `playground` 三组、共 6 个接口
- [ ] 改一行代码保存，终端出现 `WatchFiles detected changes`，刷新后生效
- [ ] `/playground/squares/abc` 返回 **422**（不是 500），你的函数没被执行
- [ ] `/playground/messages` 不带参数返回 422，报错点名 `session_id`
- [ ] `python scripts/check_day01.py` 全绿
- [ ] 能用自己的话解释：uvicorn 和 FastAPI 各自负责什么

---

## 八、今天的 5 个知识点（面试会问的形态）

1. **uvicorn ≠ FastAPI**。前者是 ASGI 服务器，后者是应用框架，通过 ASGI 协议解耦。
   → 所以你可以把 FastAPI 换成 Starlette/Django，服务器不动；也可以换服务器，应用不动。

2. **`APIRouter` 与 `app` 的关系**：前者是局部路由表，`include_router` 才真正接入。

3. **参数归属只看「是否出现在路径模板里」**，与默认值、类型无关。

4. **类型注解是声明式的全部**：转换、校验、文档三件事都从它推导出来。
   → 这正是为什么 `response_model`、Pydantic 模型在 FastAPI 里是核心 —— Day 2 展开。

5. **422 发生在函数执行之前**，框架层拦截；500 才是「你的代码炸了」。
   分清这两者，是排查问题的第一直觉。

---

## 九、今天埋下的伏笔

| 伏笔 | 什么时候填 |
| --- | --- |
| `playground.py` 里的假数据 | Day 9 换成真实数据库查询 |
| `/health/ready` 里写死的 `not_configured` | Day 8 接上数据库后做真实探测 |
| 所有路由都用 `async def` 但其实没必要 | Day 6 讲清 `def` 和 `async def` 的差别与代价 |
| `str \| None`、返回类型注解这些「文档化」用法 | Day 2 用 Pydantic 模型系统化 |
| `scripts/check_day01.py` 这种手写验证 | Day 16 升级成 pytest，并 mock 掉外部依赖 |

---

**下一步（Day 2）**：请求体（`POST` + JSON）、Pydantic 模型、`response_model` 的作用 ——
以及那个必须搞明白的问题：**为什么 `response_model` 能挡住敏感字段进响应。**
