# FastAPI 学习计划 · 面向 Agent 应用开发

> 目标：把 `week1/agent_demo` 的能力，包装成一个**可部署、可并发、可流式返回**的后端服务。
> 周期：约 1 个月（22 个学习日 + 机动）
> 制定时间：2026-09-22

---

## 零、先想清楚：为什么 Agent 岗位要考 FastAPI

如果只是「Web 后端框架」，那 Agent 岗没必要单独提它。招聘 JD 里出现 FastAPI，真正的潜台词是这四件事：

| JD 潜台词 | 对应的 FastAPI 考点 | 本计划位置 |
| --- | --- | --- |
| 大模型调用是**长耗时 IO**，不能把服务卡死 | `async/await`、并发、阻塞代码隔离 | Week 2 |
| Agent 输出 token 是**流式的**，要边生成边推给前端 | SSE / `StreamingResponse` | Week 3 · Day 11-12 |
| 接口要接**第三方调用**，参数必须严格契约化 | Pydantic 校验 + `response_model` | Week 1 |
| 服务要有**鉴权、限流、可观测**，不是裸奔 demo | Depends 体系、中间件、日志、部署 | Week 1 / 3 / 4 |

**所以学习的重心不是「会写 CRUD」，而是「会写一个扛得住并发、能把 LLM 流式吐出去的 API」。**
本计划 Week 3 是整个月的核心，前两周是为它铺路，第 4 周是把它变成作品。

---

## 一、环境与工程约定

### 1.1 环境准备（在你的 Anaconda Prompt 里执行，不要在 WorkBuddy 终端里装包）

```bash
# 新建独立环境，避免污染 sx / yang
conda create -n fastapi python=3.11 -y
conda activate fastapi

# 核心依赖
pip install "fastapi[standard]" uvicorn[standard] pydantic-settings

# 后续按天补：httpx sqlalchemy alembic aiosqlite asyncpg
#           python-jose[cryptography] passlib[bcrypt] slowapi pytest pytest-asyncio
```

> ⚠️ 本机 Clash 系统代理会间歇性重置 pip 连接。若下载失败，用清华源：
> `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`

### 1.2 运行约定（沿用你已有习惯）

| 事项 | 约定 |
| --- | --- |
| 启动开发服务 | `uvicorn app.main:app --reload --port 8000` |
| 接口文档 | 启动后访问 `http://127.0.0.1:8000/docs` |
| 跑测试 | 项目根目录 `python -m pytest`（**不要**用 `python tests/xxx.py`，会破坏 `sys.path`） |
| 提交格式 | `dayN: 做了什么`（与 agent_demo 一致） |
| 分支 | `main` |

### 1.3 目录分层约定（从第一天就定好，别等重构）

```
纯逻辑（无 IO）  → app/services/      可单测，不依赖框架
数据访问        → app/repositories/   只做读写
协议契约        → app/schemas/        Pydantic，只描述数据形状
路由编排        → app/routers/        只做「收请求 → 调 service → 返响应」
横切关注点      → app/core/           配置、日志、安全、异常
装配            → app/main.py         挂路由、中间件、异常处理器
```

**这个分层和 `agent_demo` 的 `app/llm_client.py`（IO 层）/ `app/prompting.py`（纯逻辑）/ `run_*.py`（编排层）是同一个思想**，只是换了个皮。你已经建立过一遍直觉了。

---

## 二、四周总览

| 周次 | 主题 | 核心产出 | 一句话目标 |
| --- | --- | --- | --- |
| **Week 1** | 接口与数据契约 | 一套分层清晰的 CRUD 骨架 | 能定义「前端/客户端怎么调我」 |
| **Week 2** | 异步与数据层 | 并发 LLM 调用 demo + 会话落库 | 明白 async 解决了什么、阻塞代码有多致命 |
| **Week 3** | 面向 LLM 的服务能力 ★ | SSE 流式接口 + 鉴权限流 | 能写出 Agent 产品真正需要的接口形态 |
| **Week 4** | 工程化与综合项目 | 把 agent_demo 包装成可部署服务 | 从「跑得起来」到「敢给别人用」 |

---

## 三、详细日程

### Week 1 · 接口与数据契约（Day 1–5）

#### Day 1 — 第一个接口与路由组织

- 最小应用 `app.main:app`，跑通 `--reload` 热重载
- 路径参数、查询参数、`/docs` 自动文档怎么用
- **用 `APIRouter` 拆路由**，不要把所有接口堆在 `main.py`
- 产出：`app/main.py`、`app/routers/health.py`（`GET /health`）
- ✅ 验收：`/docs` 能看到接口，改代码后自动重载

#### Day 2 — 请求三件套 + Pydantic 模型

- `Path` / `Query` / `Body` / `Header` / `Cookie` 五类参数的声明方式
- `BaseModel` + `Field`：默认值、`Optional`、别名
- **`response_model` 的真正作用**：过滤敏感字段（如 `api_key` 不进响应）+ 生成文档
- 产出：`app/schemas/chat.py` + `POST /chat` 骨架
- ✅ 验收：故意传错类型，读懂 422 响应的结构（`loc` / `msg` / `type`）

> 💡 这一步和你在 Day 3 写的 `parse_json_response` 是同一件事的两面：
> 那边是你**解析**模型输出的 JSON，这边是框架**校验**客户端传来的 JSON。

#### Day 3 — Pydantic v2 深入 ★

- `field_validator` / `model_validator`：自定义校验逻辑
- 约束：`min_length` / `ge` / `le` / `pattern` / `max_length`
- `model_config`：`from_attributes`（从 ORM 对象构造）、`extra="forbid"`
- 嵌套模型、模型列表、**泛型响应包装** `ApiResponse[T]`
- 产出：`app/schemas/common.py`（统一响应格式）
- ✅ 验收：能写出一个模型，拒绝「messages 为空」且自动修正「role 非法」的请求

> 🎯 **这个技能直接迁移到 LLM 的 structured output**。想让模型稳定吐 JSON，
> 最靠谱的做法就是给它一个 Pydantic schema 当约束 —— Day 3 学完你就拥有它了。

#### Day 4 — 依赖注入 Depends ★★

这是 FastAPI 的**灵魂**，也是面试第一高频考点。

- 函数依赖、类依赖、**子依赖**（依赖的依赖）
- `yield` 依赖：请求前建立、请求后清理（数据库 session 的标准写法）
- **依赖缓存机制**：同一个请求内，同一个依赖默认只执行一次（重要，必须搞懂）
- 全局依赖 / 路由级依赖 / 接口级依赖
- 实战用途：DB session、当前用户、配置对象、API Key 校验、request_id 注入
- 产出：`app/deps.py`
- ✅ 验收：能用 `Depends` 实现「取当前登录用户」，且业务代码里不出现任何鉴权逻辑

> 🎯 面试大概率会问：「FastAPI 的依赖注入和 Spring 的有什么不同？」
> 答案要点：FastAPI 是基于**函数签名 + 类型注解**的轻量 DI，没有容器、没有反射魔法，
> 靠 `Depends` 显式声明，可测试性体现在 `app.dependency_overrides`（Day 16 会用到）。

#### Day 5 — 异常、中间件、CORS

- `HTTPException` + `@app.exception_handler` 自定义异常处理器
- **统一错误响应格式**（让客户端不用猜错误长什么样）
- 自定义业务异常 → 全局映射成 HTTP 响应
- 中间件：请求日志、耗时统计、`X-Request-ID` 贯穿
- CORS：前端联调必踩，`allow_origins` 不能配 `["*"]` 还要带凭证
- 产出：`app/core/errors.py`、`app/core/middleware.py`
- ✅ 验收：任何异常都能返回统一结构的 JSON，且日志里能按 request_id 串起一次请求

---

### Week 2 · 异步与数据层（Day 6–10）

#### Day 6 — async/await 原理（今天不写接口，只写脚本）

- 事件循环、协程、`await` 到底在等什么
- **对比实验**：串行 vs `asyncio.gather` 并发（本机 sleep 模拟 IO）
- ⚠️ **本机最致命的坑**：在 `async def` 路由里调用同步阻塞函数
  （`time.sleep`、`requests.get`、同步数据库驱动）会**卡死整个服务**，不只是这个请求
- 解法：`run_in_threadpool` / `asyncio.to_thread`，或换成异步库
- 产出：`scripts/async_demo.py`，打印串行/并发耗时对比
- ✅ 验收：能说清「为什么同步函数放进 async 路由是灾难」

> 🎯 这个 demo 很小，但面试时非常有说服力：
> 「我把 3 次 LLM 调用从串行 4.5s 改成并发 1.6s」—— 这是实打实的优化能力证明。

#### Day 7 — 异步 IO 实战：并发调用 LLM

- `httpx.AsyncClient` 替代 `requests`
- 并发调 3 个模型/3 个 prompt，观察耗时塌缩
- 超时控制：`asyncio.wait_for`、httpx 的 `timeout=`
- **限流**：`asyncio.Semaphore` 控制最大并发（防止把 API 打爆 / 触发 429）
- 异常隔离：`gather(return_exceptions=True)` —— 一个失败不能拖垮全部
- 产出：`app/services/llm.py`（异步版，替代 `llm_client.py` 的同步实现）
- ✅ 验收：并发 3 路调用，单路失败不影响其余两路，总耗时 ≈ 最慢的一路

> 💡 你的 `agent_demo` 里 `chat()` 用 `except Exception` 吞掉异常返回中文文案 ——
> 在服务端这是**有毒**的：调用方拿到 200 + 一句「服务不可用」，没法重试、没法告警。
> 服务端必须让错误以异常形式冒出来，由 Day 5 的异常处理器统一转成合适的 HTTP 状态码。

#### Day 8 — 数据库建模与迁移

- SQLAlchemy 2.0 声明式 ORM：`Mapped` / `mapped_column` 新写法
- SQLite 起步（`aiosqlite`），生产换 PostgreSQL（`asyncpg`）
- Session 生命周期：**和 Day 4 的 `yield` 依赖结合**，这是标准范式
- Alembic 迁移：`alembic init` / `revision --autogenerate` / `upgrade head`
- 产出：`app/db.py`、`app/models/*.py`、`alembic/`
- ✅ 验收：能通过迁移命令创建表，而不是靠 `create_all()`

> ⚠️ 坑点：SQLite 的 `create_all` 很好用，但一旦上生产就会失控。
> 从 Day 8 就强制自己走 Alembic，面试问「你怎么管表结构变更」时有东西可答。

#### Day 9 — 异步数据访问与 Repository

- `AsyncSession` 的全部操作都是 `await` 的（`await session.execute(...)`）
- 分页（`limit`/`offset` 与游标分页的取舍）、排序、条件过滤
- Repository 模式：把 SQL 收进 `repositories/`，业务层不碰 ORM 细节
- N+1 查询问题与 `selectinload` 预加载
- 产出：`app/repositories/base.py`、`app/repositories/message.py`
- ✅ 验收：接口层完全不出现 SQLAlchemy 的 import

#### Day 10 — 会话持久化：把 agent_demo 的记忆落库

- 一对多关系：`Session` → `Message`
- 把 `agent_demo/app/memory.py` 的 `ConversationMemory` 从内存搬到数据库
- **顺手修掉两个遗留问题**：
  1. 用真实 token 预算做摘要压缩，替掉 `max_messages=10` 的硬截断
  2. 把写入记忆推迟到请求成功之后（避免失败时 user 消息成孤儿、破坏奇偶性）
- 产出：`app/repositories/conversation.py`、`app/services/conversation.py`
- ✅ 验收：进程重启后，历史会话还能读回来；中断的请求不污染历史

> 🎯 这一步把你 `Day5_记忆机制代码审查.md` 里挂着的问题真正解决掉。
> 面试讲「我做过会话记忆」和讲「我做过带 token 预算压缩、失败不留脏数据的会话记忆」，是两个段位。

---

### Week 3 · 面向 LLM 的服务能力（Day 11–15）★ 本月核心

#### Day 11 — 流式响应 SSE ★★★

**这是 Agent 应用最核心的接口形态，也是本计划最重要的一天。**

- `text/event-stream` 协议格式：`data: xxx\n\n`（两个换行才是事件结束）
- `StreamingResponse`（同步/异步生成器）与 `EventSourceResponse`（sse-starlette）的取舍
- **对接你的流式 LLM**：把 `agent_demo` 的 chunk 生成器接进响应流
- 客户端怎么消费：浏览器 `EventSource` / Python `httpx.stream()`
- ⚠️ 坑点：SSE 下 `response_model` 失效、异常发生在响应头已发出之后无法改状态码
- 产出：`app/routers/chat.py` 的 `POST /chat/stream`
- ✅ 验收：`curl -N` 能看到 token 逐字吐出来

```bash
# 验证命令（关键：-N 关闭缓冲，否则你会以为它没流式）
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"用三句话介绍 FastAPI"}'
```

#### Day 12 — SSE 进阶：生产级别才需要考虑的事

- **心跳保活**：长时间无数据时发注释行 `: keepalive\n\n`，防 Nginx/网关超时断连
- **客户端断开检测**：`await request.is_disconnected()` → 及时取消上游 LLM 调用（**省钱**）
- 流中出错怎么告诉前端：定义错误事件 `event: error\ndata: {...}`，而不是直接断流
- 事件类型化：`event: token` / `event: tool_call` / `event: done`
  → 前端可以据此渲染「正在调用工具…」的 UI
- 产出：`app/services/streaming.py`（统一的 SSE 事件封装）
- ✅ 验收：用户关掉页面时，服务端日志显示上游请求被取消

> 🎯 这一天的内容几乎没人写进简历，但只要你做过，面试官一问「流式怎么处理异常、怎么处理断连」，
> 你能答上来，立刻和别人拉开差距。

#### Day 13 — WebSocket 与选型

- `@app.websocket` 双向通信：接收、发送、关闭码
- 适用场景：需要客户端**中途插话/打断**的对话、多端同步
- **SSE vs WebSocket 选型对比**（写进笔记，面试常问）：

| 维度 | SSE | WebSocket |
| --- | --- | --- |
| 方向 | 单向（服务端→客户端） | 双向 |
| 协议 | 普通 HTTP | 需升级握手 |
| 断线重连 | 浏览器 `EventSource` 自带 | 需自己实现 |
| 代理/CDN 友好度 | 好 | 一般 |
| 适合场景 | LLM 流式输出 | 交互式对话、协同编辑 |

- 产出：`app/routers/ws.py` + 一页选型笔记
- ✅ 验收：能用三种方式（普通 POST / SSE / WS）实现同一个对话，并说清各自代价

#### Day 14 — 后台任务与长任务

- `BackgroundTasks`：请求返回后执行（发通知、写审计日志），**不适合长耗时**
- 长任务正确姿势：**提交 → 立刻返回 `task_id` → 客户端轮询状态**
  - `POST /tasks` → `202 Accepted` + `{"task_id": "..."}`
  - `GET /tasks/{task_id}` → `{"status": "running|done|failed", "result": ...}`
- 任务状态表设计（复用 Day 8 的模型体系）
- 何时该上 Celery + Redis：多机部署、需要重试/定时、任务量级上来之后 —— **现阶段明确不上，够用就好**
- 产出：`app/routers/tasks.py`
- ✅ 验收：提交一个 30 秒任务，接口立刻返回，轮询能看到状态流转

#### Day 15 — 认证、鉴权、限流

- **API Key 方案**（Agent 服务最常见）：`Header` 取 key → 依赖注入校验 → 绑定用户
- OAuth2 Password Flow + JWT：`python-jose` 签验、过期时间、`Depends` 解出 `current_user`
- 密码哈希 `passlib[bcrypt]`（**注意**：绝不明文、绝不自己写加密）
- **限流**：`slowapi` 按 IP / 按用户配额，返回 429 + `Retry-After`
- 文件上传下载：`UploadFile`、流式保存大文件、大小与类型白名单（**别信 `content_type`**）
- 产出：`app/core/security.py`、`app/deps.py` 的 `get_current_user` / `rate_limit`
- ✅ 验收：无 key 访问返回 401，超配额返回 429，越权访问返回 403

---

### Week 4 · 工程化与综合项目（Day 16–22）

#### Day 16 — 测试

- `TestClient`（同步）快速测接口
- 异步测试：`httpx.AsyncClient(transport=ASGITransport(app=app))`
- **`app.dependency_overrides`**：把 LLM 依赖换成假的 → **测试不烧 token、不依赖网络**
- 数据库测试：每个测试用独立事务并回滚，或内存 SQLite
- SSE 接口怎么测（读流、断言事件序列）
- 产出：`tests/conftest.py`、`tests/test_chat.py`、`tests/test_stream.py`
- ✅ 验收：`python -m pytest` 全绿，且测试期间**零真实 API 调用**

#### Day 17 — 配置、日志、可观测性

- `pydantic-settings`：`.env` 读取、类型转换、`SecretStr`、多环境（dev/prod）
- **`.env` 必须进 `.gitignore`**，仓库只留 `.env.example`
- 结构化日志（JSON 格式）+ `request_id` 贯穿全链路 + 耗时统计
- 健康检查：`/health`（存活）与 `/ready`（就绪，含 DB 连通性）分开
- 产出：`app/core/config.py`、`app/core/logging.py`
- ✅ 验收：一条日志能定位「哪个请求、调了哪个模型、耗时多少、花多少 token」

> 🎯 这一步直接对应 Agent 项目里的 `trace.py`：**每个请求都能回放**。
> 服务端可观测性和 Agent 可观测性是同一个能力，你已经练过一遍了。

#### Day 18 — 容器化与部署

- `Dockerfile`：多阶段构建、精简镜像、**非 root 用户运行**
- `docker-compose.yml`：app + postgres + redis 一键起
- 进程模型：`uvicorn --workers N` vs `gunicorn -k uvicorn.workers.UvicornWorker`
  （`--reload` 千万不能上生产）
- Nginx 反代 **SSE 专属坑**：`proxy_buffering off; proxy_read_timeout` 调大，
  否则你的流式会变成「憋 60 秒一次性吐出来」
- 产出：`Dockerfile`、`docker-compose.yml`、`deploy/nginx.conf`
- ✅ 验收：`docker compose up` 能起来，且通过 Nginx 访问时**流式仍然逐字输出**

#### Day 19–21 — 综合项目：把 agent_demo 包装成生产级 API 服务 ★

**这是本月的交付作品，也是简历上能写的那一行。**

把 `week1/agent_demo` 的 `tools.py` / `agent.py` / `memory.py` 作为内核搬进来，套上服务外壳：

```
POST   /api/v1/chat              普通对话（一次性返回）
POST   /api/v1/chat/stream       ★ SSE 流式对话（支持 tool_call 事件）
POST   /api/v1/sessions          创建会话
GET    /api/v1/sessions          会话列表（分页）
GET    /api/v1/sessions/{id}     会话详情 + 历史消息
DELETE /api/v1/sessions/{id}     删除会话
GET    /api/v1/tasks/{task_id}   长任务状态（Day 14）
GET    /health  /ready           健康检查
```

要求清单：

- [ ] 三层分层清晰：routers / services / repositories 各司其职
- [ ] 请求与响应全部有 Pydantic 契约，OpenAPI 文档完整
- [ ] LLM 调用全异步 + 信号量限流 + 超时 + 失败重试
- [ ] SSE 支持心跳、错误事件、客户端断连取消上游
- [ ] 会话与消息落库，token 预算超限自动摘要压缩
- [ ] API Key 鉴权 + 按用户限流
- [ ] 统一错误格式 + 结构化日志 + request_id 贯穿
- [ ] `python -m pytest` 全覆盖，且 mock 掉 LLM
- [ ] `docker compose up` 一键起
- [ ] README 写清架构图、接口表、部署步骤

> 💡 复用技巧：`agent_demo` 的 `tools.py` / `prompting.py` 是**纯逻辑无 IO**，
> 可以直接 import 或复制过来，不用改一行。这正是当初分层的回报。

#### Day 22 — 打磨与复盘

- 压测：`hey` 或 `locust`，观察并发下的延迟曲线与错误率
- 用 `pytest-cov` 看覆盖率，补关键路径
- 把 `docs/` 下的思考整理成项目 README（**面试官只看 README 和 git log**）
- 对照下面的「面试速查表」自测，答不上来的回炉
- ✅ 验收：能对着 README，在 5 分钟内把整个项目讲明白

---

## 四、面试高频问题速查表（自查用）

学到 Day 22，应该能**不看资料**答出下面这些：

**框架与协议**
1. FastAPI 为什么快？（Starlette + Pydantic v2，异步 + Rust 内核校验）
2. `response_model` 有什么用？不做会发生什么？
3. 422 和 400 的区别？（框架校验失败 vs 业务校验失败）
4. 同步路由和异步路由，FastAPI 分别怎么处理？（同步走线程池，异步走事件循环）

**异步（高频）**
5. `async def` 里调用 `requests.get` 会怎样？怎么修？
6. `asyncio.gather` 和 `asyncio.TaskGroup` 的差异？
7. 怎么限制并发数？（`Semaphore`）
8. 怎么给一个协程加超时？（`wait_for` / `timeout`）

**依赖注入（高频）**
9. `Depends` 的请求内缓存是怎么工作的？怎么关掉？（`use_cache=False`）
10. `yield` 依赖的清理代码，在抛异常时还会执行吗？
11. 测试时怎么替换依赖？（`dependency_overrides`）

**流式（Agent 岗必问）**
12. SSE 和 WebSocket 你怎么选？
13. SSE 报文格式？为什么是**两个**换行？
14. 流到一半报错了怎么办？（此时响应头已发出，改不了状态码）
15. 前端关掉页面，怎么避免继续烧 token？
16. Nginx 下 SSE 为什么变成一次性返回？怎么配？

**数据与工程**
17. Session 生命周期怎么和请求绑定？为什么不能全局共享一个 session？
18. 什么情况下用 Alembic，什么情况下 `create_all` 够用？
19. 怎么管理配置和密钥？（`pydantic-settings` + `.env` + `SecretStr`）
20. 生产环境用 uvicorn 还是 gunicorn？worker 数怎么定？

---

## 五、里程碑验收

| 里程碑 | 时间 | 验收标准 |
| --- | --- | --- |
| M1 能定义接口 | Day 5 末 | 一套分层 CRUD，`/docs` 完整，异常返回统一格式 |
| M2 懂异步 | Day 7 末 | 能说出阻塞代码的后果，并完成并发 LLM 调用优化 |
| M3 会流式 ★ | Day 12 末 | `curl -N` 看到逐字输出，断连能取消上游，异常有事件 |
| M4 敢上线 | Day 18 末 | `docker compose up` 起来，Nginx 后 SSE 依然流式 |
| M5 有作品 | Day 22 末 | agent_demo 变成有鉴权/限流/测试/文档的 API 服务 |
| M6 能面试 | Day 22 末 | 上面 20 个问题能当场答出 16 个以上 |

---

## 六、目标目录结构（Day 22 完成时）

```
fastapi/
├── app/
│   ├── main.py                 # 装配：路由 + 中间件 + 异常处理器
│   ├── deps.py                 # 依赖注入集合（见 Day 4）
│   ├── core/
│   │   ├── config.py           # pydantic-settings
│   │   ├── logging.py          # 结构化日志 + request_id
│   │   ├── errors.py           # 业务异常 + 全局处理器
│   │   ├── middleware.py       # 日志/耗时/request_id
│   │   └── security.py         # API Key / JWT / 限流
│   ├── schemas/                # Pydantic 契约层
│   ├── models/                 # SQLAlchemy ORM
│   ├── repositories/           # 数据访问
│   ├── services/               # 业务逻辑（含 llm.py、streaming.py、conversation.py）
│   └── routers/                # health / chat / sessions / tasks / ws
├── agent/                      # ← 从 week1/agent_demo 搬来的内核
│   ├── tools.py
│   ├── agent.py
│   └── prompting.py
├── alembic/                    # 数据库迁移
├── scripts/                    # async_demo.py 等验证脚本
├── tests/                      # conftest + 接口 + 流式测试
├── docs/
│   └── learning-plan.md        # ← 本文件
├── deploy/nginx.conf
├── Dockerfile
├── docker-compose.yml
├── .env.example                # 真 .env 永不入库
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 七、参考资源

| 类型 | 资源 | 用法 |
| --- | --- | --- |
| 官方 | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/zh/) | **主教材**，有中文版，按 Tutorial 顺序刷 |
| 官方 | [Pydantic v2 文档](https://docs.pydantic.dev/latest/) | Day 3 重点查阅 |
| 官方 | [SQLAlchemy 2.0 ORM](https://docs.sqlalchemy.org/en/20/orm/) | Day 8-9 |
| 进阶 | [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | 官方项目模板，Day 17-18 对照它的工程化组织 |
| 范式 | [python-weekly 上的 FastAPI 生产实践文章](https://github.com/tiangolo) | 挑生产实践类的读，别只读入门 |
| 工具 | `hey` / `locust` | Day 22 压测 |

> 📌 学习原则：**官方文档优先**。FastAPI 文档质量极高，中文版完整，
> 遇到第三方教程与官方不一致时，以官方为准（版本迭代快，博客常过期）。

---

## 八、给这个月的三句提醒

1. **别把时间花在 CRUD 上。** 会写 CRUD 的人一大把，能写出稳定 SSE 流式接口 + 正确隔离阻塞调用的人不多。
2. **每个 Day 都要有可运行的产物。** 看完文档不写代码，一周就忘光。`scripts/` 下的验证脚本比笔记有用十倍。
3. **第 4 周的作品比前 3 周的知识点重要。** 面试官不会问你「FastAPI 有多少个装饰器」，他会问「你用它做过什么」。
