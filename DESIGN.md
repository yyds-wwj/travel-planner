# 旅游攻略多智能体系统 — 技术设计文档

## 一、架构总览

```
浏览器 (Web UI)
  │ WebSocket
  ▼
FastAPI 服务端 (server.py)
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  Lead Agent (旅游攻略协调员)                           │
│  模型: deepseek-v4-pro[1m] (大模型)                   │
│  工具: 任务管理 + IP定位 + 静态地图 + 天气             │
│  职责: 需求分析 → 任务拆分 → 启动专家 → 冲突协调 → 整合  │
└──────┬──────────┬──────────┬──────────┬─────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
  ┌─────────┐┌──────┐┌────────┐┌──────────┐
  │景点美术 ││交通  ││住宿    ││时间规划  │
  │专家     ││专家  ││专家    ││专家      │
  │🏯 flash ││🚄 flash││🏨 flash││📅 flash  │
  └────┬────┘└──┬───┘└───┬────┘└────┬─────┘
       │        │       │          │
       └────────┴───────┴──────────┘
                    │
         MessageBus (.mailboxes/*.jsonl)
         团队协议 (shutdown/审批/请求信息)
```

**核心设计原则：**
- **Harness 哲学**: 模型即 Agent，代码即 Harness（缰绳）
- **大小模型分离**: Lead 用大模型保证推理质量，Expert×4 用小模型降本提速
- **异步协作**: 文件收件箱 + 线程并行

---

## 二、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| **LLM** | DeepSeek v4 Pro / Flash（Anthropic 兼容 API） | 大小模型分离 |
| **后端** | Python 3 + FastAPI + uvicorn | WebSocket 实时推送 |
| **前端** | 原生 HTML/CSS/JS（单页应用） | 零构建依赖，WebSocket 双向通信 |
| **存储** | SQLite (WAL 模式) | 5 表：sessions/chat_messages/agent_logs/plans/task_snapshots |
| **地图** | 高德 Web 服务 API | 13 个端点 |
| **通信** | MessageBus (JSONL 文件收件箱) | 基于 learn-claude-code s15 模式 |

---

## 三、Harness 层（6 个模块）

| 模块 | 来源 | 行数 | 功能 |
|------|------|------|------|
| `agent_loop.py` | s01 | ~80 | `while stop_reason=="tool_use"` 核心循环 |
| `message_bus.py` | s15 | ~70 | JSONL 文件收件箱，消费式读取 |
| `task_board.py` | s12 | ~90 | 文件持久化任务看板，支持依赖(dependsOn) |
| `team_protocols.py` | s16 | ~100 | 结构化请求-响应协议（shutdown/plan_approval/info_request）|
| `tools.py` | s02-s17 | ~300 | 22 个工具定义 + dispatch 处理器 |
| `permission.py` | s03 | ~40 | 三段权限门控（硬拒绝/规则检查/用户审批）|
| `storage.py` | — | ~160 | SQLite CRUD |
| `amap_client.py` | — | ~300 | 高德 API 封装（13 个端点 + 格式化函数）|

---

## 四、Agent 团队

### Lead Agent — 协调员

| 项 | 值 |
|----|-----|
| 模型 | `LEAD_MODEL` (deepseek-v4-pro[1m]) |
| 工具数 | 10（read/write/bash + 通信 + 任务管理 + IP定位 + 静态地图 + 天气）|
| 职责 | 需求分析、任务拆分、团队启动、冲突协调、攻略整合输出 |

### Expert Agent ×4

| Agent | 模型 | 工具 | 输出 |
|-------|------|------|------|
| attraction_expert 🏯 | `EXPERT_MODEL` (flash) | 8（基础 + search_attractions/search_around/geocode/route/weather）| `outputs/attractions.json` |
| transport_expert 🚄 | `EXPERT_MODEL` (flash) | 8（基础 + route/amap_distance/geocode/input_tips）| `outputs/transport.json` |
| accommodation_expert 🏨 | `EXPERT_MODEL` (flash) | 8（基础 + search_hotels/search_around/geocode/route）| `outputs/accommodations.json` |
| schedule_expert 📅 | `EXPERT_MODEL` (flash) | 9（基础 + route/amap_distance/weather/regeocode/search_around）| `outputs/schedule.json` |

---

## 五、高德 API 集成（13 个端点）

| # | API | 工具名 | 功能 |
|---|-----|--------|------|
| 1 | POI 关键字搜索 | `search_attractions` | 搜城市景点/博物馆（坐标+评分+价格）|
| 2 | POI 周边搜索 | `search_around` | 搜坐标周边地铁站/餐厅 |
| 3 | 酒店搜索 | `search_hotels` | 按城市或坐标搜酒店/民宿 |
| 4 | 地理编码 | `geocode` | 地址 → 经纬度 |
| 5 | 逆地理编码 | `regeocode` | 经纬度 → 地址+周边POI |
| 6 | 距离计算 | `amap_distance` | 多点驾车/步行距离+时间 |
| 7-9 | 路径规划 | `route(type)` | 驾车/公交地铁/步行路线 |
| 10 | 天气查询 | `weather` | 未来4天预报（自动城市名→adcode）|
| 11 | IP定位 | `ip_location` | IP→城市 |
| 12 | 输入提示 | `input_tips` | 模糊地址自动补全 |
| 13 | 静态地图 | `generate_map` | 生成景点标注地图URL |

---

## 六、前后端通信

### WebSocket 事件流

```
前端 ──{action:"start", input:"..."}──▶ 服务端
       ◀── {"type":"started"} ── 确认
       ◀── {"type":"lead_text"} ── Lead 思考
       ◀── {"type":"lead_tool"} ── Lead 调工具
       ◀── {"type":"expert_started"} ── 专家启动
       ◀── {"type":"expert_text/tool"} ── 专家工作
       ◀── {"type":"task_board"} ── 任务更新
       ◀── {"type":"agent_message"} ── Agent 间通信
       ◀── {"type":"expert_completed"} ── 专家完成
       ◀── {"type":"plan_ready"} ── 攻略生成
```

### REST API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/sessions` | GET | 历史会话列表 |
| `/api/sessions/{id}` | GET | 加载完整会话 |
| `/api/outputs` | GET | 生成的文件列表 |

---

## 七、数据持久化

```
travel_planner.db (SQLite, WAL 模式)

sessions         — id, user_input, status, created_at, updated_at
chat_messages    — session_id, msg_type, content, created_at
agent_logs       — session_id, agent_name, event_type, content, icon
plans            — session_id, plan_content (最终攻略全文)
task_snapshots   — session_id, task_data (看板最新快照)
```

**写入时机**: 实时写入（每产生一条消息/日志即写入 DB），刷新页面后从历史面板恢复。

---

## 八、前端 UI

| 区域 | 功能 |
|------|------|
| 左侧面板 | Agent 团队实时状态 + 历史记录列表 |
| 对话 Tab | Lead 思考/工具调用/系统通知实时流 |
| 任务 Tab | 任务看板（进度+负责人+依赖关系）|
| 通信 Tab | Agent 间消息流向记录 |
| 攻略 Tab | 最终攻略 Markdown 渲染 |
| 顶部状态栏 | 连接状态指示（绿=已连接/蓝=运行中/紫=完成）|
| Toast 通知 | 右上角弹出（Agent 启动/完成/错误）|
| 快速体验 | 4 个预置目的地点击即用 |
| 自动重连 | WebSocket 断开自动重连（3秒间隔）|

---

## 九、大小模型选型

```
LEAD_MODEL=deepseek-v4-pro[1m]    # 大模型：强推理
EXPERT_MODEL=deepseek-v4-flash    # 小模型：快+省
MODEL_ID=deepseek-v4-pro[1m]      # fallback
```

**收益**: Expert 从 pro 换 flash，每次规划省 ~55-60% token 费用，专家响应快 2-3 倍。

---

## 十、工作流程

```
1. 用户输入 "北京三日游"
2. Lead 分析需求（缺失信息用默认值填充）
3. Lead 调用 ip_location 检测出发城市
4. Lead 创建 5 个任务（task_01 ~ task_05）到看板
5. Lead 同时启动 attraction/transport/accommodation 三个专家
6. 三个专家并行工作：
   - 景点专家: search_attractions → 写 attractions.json
   - 交通专家: route + geocode → 写 transport.json
   - 住宿专家: search_hotels → 写 accommodations.json
7. 三个完成后，Lead 启动 schedule_expert
8. 时间规划专家: 读前三份数据 + route计算交通时间 → 写 schedule.json
9. Lead 读所有输出，整合为 travel_plan.md
10. 保存到 SQLite，前端展示最终攻略
```

---

## 十一、下一步方向

### 阶段一：Agent 能力深化（学习 s06-s20）

| # | 方向 | 对应章节 | 说明 |
|---|------|---------|------|
| 1 | **子 Agent 模式** | s06 | 允许 Expert 在需要时 spawn 更细粒度的子 Agent（如景点专家 spawn "博物馆子Agent"） |
| 2 | **Hook 系统** | s04 | 在工具执行前后插入钩子（如 PreToolUse 自动日志、PostToolUse 自动保存） |
| 3 | **上下文压缩** | s08 | 长对话自动压缩，避免 token 溢出（当前 Expert 最多 20 轮后可能丢失上下文） |
| 4 | **记忆系统** | s09 | 学习用户偏好（"喜欢自然风光" → 下次自动推荐）、历史攻略复用 |
| 5 | **错误恢复** | s11 | API 调用失败自动重试、专家崩溃自动重启 |
| 6 | **技能加载** | s07 | 按需注入知识（如用户说"想去雪山"，加载滑雪/高反相关技能提示词）|
| 7 | **MCP 协议** | s19 | 通过 MCP 接入第三方工具（如携程/12306 的真实预订能力） |

### 阶段二：产品化增强

| # | 方向 | 说明 |
|---|------|------|
| 8 | **流式输出** | 当前 LLM 调用是同步等待全量返回，改为 SSE 流式，前端逐字渲染 |
| 9 | **PDF 导出** | 攻略一键导出为排版精美的 PDF |
| 10 | **多人协作** | 多人同时编辑同一份攻略，实时同步 |
| 11 | **自定义 Agent** | 用户可自定义新增专家（如"美食专家"、"购物专家"） |
| 12 | **行程分享** | 生成分享链接，朋友可查看/评论 |
| 13 | **TTS 播报** | 每日行程语音播报，出发前听一遍 |

### 阶段三：数据增强

| # | 方向 | 说明 |
|---|------|------|
| 14 | **真实车票/酒店预订** | 接入 12306/携程 API，攻略生成后一键跳转预订 |
| 15 | **实时客流数据** | 接入景区实时人流量 API，避开高峰期 |
| 16 | **UGC 内容** | 抓取小红书/马蜂窝的游记和点评，作为 Agent 知识 |
| 17 | **价格日历** | 酒店/机票价格趋势，推荐最佳预订时间 |

### 阶段四：大模型深度应用

| # | 方向 | 说明 |
|---|------|------|
| 18 | **多轮对话优化** | 用户可在生成后继续对话修改（"第二天太赶了，调整一下"） |
| 19 | **ReAct 模式** | Agent 思考-行动-观察循环，更强的自主决策 |
| 20 | **反思机制** | 攻略生成后自动自我审查（"这个行程有没有不合理的地方？"） |
| 21 | **多模态** | 用户上传景点照片，Agent 识别并纳入行程 |
| 22 | **A/B 方案** | 同时生成 2 套方案让用户选择 |

---

## 十二、文件清单

```
travel-planner/
├── server.py              # FastAPI + WebSocket 服务端 (540行)
├── main.py                # CLI 命令行入口 (290行)
├── harness/
│   ├── agent_loop.py      # 核心 Agent 循环
│   ├── message_bus.py     # 文件收件箱
│   ├── task_board.py      # 任务看板
│   ├── team_protocols.py  # 团队协议
│   ├── tools.py           # 22 工具定义+处理 (560行)
│   ├── permission.py      # 权限门控
│   ├── amap_client.py     # 高德 13 API (380行)
│   └── storage.py         # SQLite 持久化 (180行)
├── agents/
│   ├── lead.py            # 协调员 System Prompt
│   ├── attraction_art.py  # 景点专家 Prompt
│   ├── transport.py       # 交通专家 Prompt
│   ├── accommodation.py   # 住宿专家 Prompt
│   └── schedule.py        # 时间规划 Prompt
├── static/
│   ├── index.html         # Web UI 主页面
│   ├── css/style.css      # 样式 (340行)
│   └── js/app.js          # 前端逻辑 (200行)
├── .env                   # 环境配置
├── requirements.txt
└── DESIGN.md              # 本文档
```
