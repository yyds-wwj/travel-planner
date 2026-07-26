# 旅游攻略多智能体系统 (Travel Planner)

基于 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 项目 s15-s17 多智能体模式构建的旅游攻略生成系统。

## 架构

```
用户需求
  │
  ▼
┌──────────────────────────────┐
│  Lead Agent (旅游攻略协调员)    │
│  - 需求分析 & 任务拆分          │
│  - 团队管理 & 冲突协调          │
│  - 整合输出最终攻略             │
└──────┬──────┬──────┬─────────┘
       │      │      │
       ▼      ▼      ▼
  ┌────────┐┌──────┐┌──────────┐
  │景点美术 ││交通  ││住宿      │
  │专家    ││专家  ││专家      │  ← 并行工作
  └────┬───┘└──┬───┘└────┬─────┘
       │       │        │
       └───────┴────────┘
               │
               ▼
       ┌──────────────┐
       │ 时间规划专家   │  ← 等上面完成后启动
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │ Lead 整合输出 │
       └──────────────┘
```

## 目录结构

```
travel-planner/
├── server.py                 # Web 服务端（FastAPI + WebSocket）
├── main.py                   # CLI 主入口（命令行版）
├── harness/                  # Harness 层（从 s01-s17 提炼的通用机制）
│   ├── agent_loop.py         # 核心 Agent 循环
│   ├── message_bus.py        # 文件收件箱消息总线
│   ├── task_board.py         # 任务看板 CRUD
│   ├── team_protocols.py     # 团队协议（shutdown/审批）
│   ├── tools.py              # 工具定义与处理函数
│   └── permission.py         # 三段式权限门控
├── agents/                   # Agent 定义（System Prompt + 工具配置）
│   ├── lead.py               # Lead 协调员
│   ├── attraction_art.py     # 景点美术专家
│   ├── transport.py          # 交通专家
│   ├── accommodation.py      # 住宿专家
│   └── schedule.py           # 时间规划专家
├── static/                   # 前端 UI（单页应用）
│   ├── index.html            # 主页面
│   ├── css/style.css         # 样式
│   └── js/app.js             # WebSocket 实时通信 + UI 渲染
├── outputs/                  # 生成的攻略输出
├── data/                     # 静态数据（景点/酒店库）
├── .env.example              # 环境配置模板
└── requirements.txt          # Python 依赖
```

## 与 learn-claude-code 各章节的对应

| 机制 | 对应章节 | 在本系统中的体现 |
|------|---------|----------------|
| Agent Loop | s01 | `harness/agent_loop.py` — while + tool_use 循环 |
| 多工具 Dispatch | s02 | `harness/tools.py` — TOOL_HANDLERS 字典 |
| 权限门控 | s03-s04 | `harness/permission.py` — 三段审批 |
| 团队通信 | s15 | `harness/message_bus.py` — 文件收件箱 |
| 团队协议 | s16 | `harness/team_protocols.py` — 请求-响应 |
| 自主认领 | s17 | Expert idle 轮询 + 任务板认领 |

## 快速开始

```bash
cd travel-planner

# 安装依赖
pip install -r requirements.txt

# 环境配置（项目根目录已有 .env）
# 确认 ANTHROPIC_API_KEY 和 MODEL_ID 正确

# 方式1: Web 界面启动（推荐）
python server.py
# 浏览器访问 http://localhost:8765

# 方式2: 命令行启动
python main.py
```

## Web 界面功能

| 面板 | 功能 |
|------|------|
| **Agent 团队** (左侧) | 实时显示 1 Lead + 4 专家状态：待机/工作中/完成，最新操作日志 |
| **对话** (Tab) | Agent 实时输出：Lead 的思考、工具调用、专家启动通知 |
| **任务看板** (Tab) | 任务拆分与进度追踪，含负责人和依赖关系 |
| **Agent 通信** (Tab) | 实时显示 Agent 间的消息传递（result/info_request） |
| **最终攻略** (Tab) | 渲染生成的 Markdown 攻略文档 |

## 使用示例

Web 界面中提供了快速体验按钮：杭州3日游、成都4日游、大理5日游、西安3日游。

也可以自定义输入：`我想去杭州玩3天，预算3000元，喜欢自然风光和艺术展览，从上海出发`

## MVP 阶段说明

**MVP (Minimum Viable Product)** 即"最小可行产品"——用最少的代码实现最核心的功能，验证想法是否可行，然后根据反馈逐步迭代。

### 本系统的 MVP 包含

- [x] 1 Lead + 4 专家的多智能体协作
- [x] 文件收件箱消息通信
- [x] 任务看板 + 自主认领
- [x] 结构化数据输出（JSON → Markdown）
- [x] 权限门控
- [x] Web 前端 UI（实时 Agent 状态 + WebSocket 通信）
- [x] CLI 命令行界面

### V2 计划

- [ ] 接入高德/百度地图 API 获取真实地理数据
- [ ] 接入酒店/车票 API 获取实时价格
- [ ] 互联网搜索增强（Agent 自主搜索景点信息）
- [ ] 用户偏好记忆（基于 s09 记忆系统）

### V3 计划

- [ ] Web 前端展示攻略（复用项目 web/ 目录）
- [ ] 多轮对话优化方案
- [ ] 可视化行程地图
- [ ] 导出 PDF/分享功能
