# fatsapi

> FastAPI 学习仓库 · 目标：把 `week1/agent_demo` 的 Agent 能力包装成**可部署、可并发、可流式返回**的后端服务。
> 周期：约 1 个月（22 个学习日 + 机动）

---

## 为什么学这个

Agent 方向的实习 JD 里反复出现 FastAPI，考的不是「会不会写 CRUD」，而是这四件事：

1. **异步** —— 大模型调用是长耗时 IO，不能把服务卡死
2. **流式** —— token 要边生成边推给前端（SSE）
3. **契约** —— 对外的接口参数必须用 Pydantic 严格校验
4. **工程化** —— 鉴权、限流、日志、部署，不能是裸奔的 demo

所以本仓库的重点是 **Week 3 的流式与异步**，前两周铺路，第 4 周做出作品。

---

## 学习计划

完整计划见 **[docs/learning-plan.md](docs/learning-plan.md)**（含每日安排、验收标准、20 道面试高频题）。

| 周次 | 主题 | 核心产出 |
| --- | --- | --- |
| Week 1 | 接口与数据契约 | 分层清晰的 CRUD 骨架 |
| Week 2 | 异步与数据层 | 并发 LLM 调用优化 + 会话落库 |
| Week 3 | 面向 LLM 的服务能力 ★ | SSE 流式接口 + 鉴权限流 |
| Week 4 | 工程化与综合项目 | agent_demo 包装成可部署 API 服务 |

---

## 进度

### Week 1 · 接口与数据契约
- [x] Day 1 — 第一个接口与路由组织 · [笔记](docs/day01.md)
- [ ] Day 2 — 请求三件套 + Pydantic 模型
- [ ] Day 3 — Pydantic v2 深入
- [ ] Day 4 — 依赖注入 `Depends`
- [ ] Day 5 — 异常、中间件、CORS

### Week 2 · 异步与数据层
- [ ] Day 6 — async/await 原理
- [ ] Day 7 — 异步 IO：并发调用 LLM
- [ ] Day 8 — 数据库建模与迁移（Alembic）
- [ ] Day 9 — 异步数据访问与 Repository
- [ ] Day 10 — 会话持久化

### Week 3 · 面向 LLM 的服务能力
- [ ] Day 11 — 流式响应 SSE
- [ ] Day 12 — SSE 进阶：心跳、断连、错误事件
- [ ] Day 13 — WebSocket 与选型
- [ ] Day 14 — 后台任务与长任务
- [ ] Day 15 — 认证、鉴权、限流

### Week 4 · 工程化与综合项目
- [ ] Day 16 — 测试
- [ ] Day 17 — 配置、日志、可观测性
- [ ] Day 18 — 容器化与部署
- [ ] Day 19-21 — 综合项目：Agent 服务化
- [ ] Day 22 — 打磨与复盘

---

## 环境

```bash
# 用独立的 Anaconda Prompt 执行（不要在 WorkBuddy 终端里装包）
conda create -n fastapi python=3.11 -y
conda activate fastapi
pip install "fastapi[standard]" uvicorn[standard] pydantic-settings
```

当前环境实测版本：Python 3.11.16 · FastAPI 0.141.1 · Pydantic 2.13.5 · uvicorn 0.53.0

## 运行

```bash
# 开发服务（--reload 会在文件变化时自动重启进程）
uvicorn app.main:app --reload --port 8000

# 接口文档
#   http://127.0.0.1:8000/docs    Swagger UI（带 Try it out）
#   http://127.0.0.1:8000/redoc   只读文档

# 一键验证当天接口
python scripts/check_day01.py

# 跑测试（Day 16 起）
python -m pytest
```

> ⚠️ 提交格式沿用 `dayN: 做了什么`；`.env` 永不入库，只留 `.env.example`。

## 当前结构

```
fastapi/
├── app/
│   ├── main.py              # 装配层：建 app、挂路由
│   └── routers/
│       ├── health.py        # GET /health, /health/ready
│       └── playground.py    # 路径参数 / 查询参数练习
├── scripts/
│   └── check_day01.py       # Day 1 接口验证
└── docs/
    ├── learning-plan.md     # 完整 4 周计划
    └── day01.md             # Day 1 讲解
```

