"""
旅游攻略多智能体系统 — Web 服务端

FastAPI + WebSocket，连接前端 UI 与 Agent 系统。

用法:
    python server.py
    # 访问 http://localhost:8765
"""

import os
import sys
import json
import time
import queue
import threading
import asyncio
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 导入 harness 层
sys.path.insert(0, str(Path(__file__).parent))
from harness.message_bus import MessageBus
from harness.task_board import TaskBoard, Task
from harness.team_protocols import ProtocolManager
from harness.tools import (
    READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
    SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL,
    CREATE_TASK_TOOL, LIST_TASKS_TOOL,
    SPAWN_TEAMMATE_TOOL, REQUEST_SHUTDOWN_TOOL,
    IP_LOCATION_TOOL,
    AMAP_TOOLS,
    make_handlers,
)
from harness import storage as store
from agents.lead import LEAD_SYSTEM_PROMPT
from agents.attraction_art import ATTRACTION_SYSTEM_PROMPT
from agents.schedule import SCHEDULE_SYSTEM_PROMPT
from agents.accommodation import ACCOMMODATION_SYSTEM_PROMPT
from agents.transport import TRANSPORT_SYSTEM_PROMPT

# ============================================================
# 初始化
# ============================================================
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
# 模型选型：Lead 用大模型（推理强），Expert 用小模型（速度快、成本低）
LEAD_MODEL = os.getenv("LEAD_MODEL", "") or os.getenv("MODEL_ID", "claude-sonnet-4-6")
EXPERT_MODEL = os.getenv("EXPERT_MODEL", "") or os.getenv("MODEL_ID", "claude-sonnet-4-6")

ROOT = Path(__file__).parent
WORKSPACE = ROOT
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)

# ============================================================
# 全局事件队列（Agent → WebSocket 实时推送）
# ============================================================
event_queues: list[queue.Queue] = []  # 所有已连接的 WebSocket 客户端


def emit(event_type: str, data: dict | str):
    """向所有 WebSocket 客户端推送事件"""
    event = {
        "type": event_type,
        "data": data,
        "ts": time.time(),
    }
    for q in event_queues[:]:
        try:
            q.put_nowait(event)
        except Exception:
            pass


# ============================================================
# Agent 系统封装
# ============================================================
# 基础工具集（所有 Agent 共享）
BASE_TOOLS = [READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL, SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL]
# 专家工具集（基础 + 高德地图）
EXPERT_BASE_TOOLS = BASE_TOOLS + AMAP_TOOLS

EXPERT_REGISTRY = {
    "attraction_expert": {
        "rp": ATTRACTION_SYSTEM_PROMPT,
        "role": "景点与美术推荐专家",
        "tools": EXPERT_BASE_TOOLS,
        "icon": "🏯",
    },
    "transport_expert": {
        "rp": TRANSPORT_SYSTEM_PROMPT,
        "role": "交通出行专家",
        "tools": EXPERT_BASE_TOOLS,
        "icon": "🚄",
    },
    "accommodation_expert": {
        "rp": ACCOMMODATION_SYSTEM_PROMPT,
        "role": "住宿推荐专家",
        "tools": EXPERT_BASE_TOOLS,
        "icon": "🏨",
    },
    "schedule_expert": {
        "rp": SCHEDULE_SYSTEM_PROMPT,
        "role": "时间规划专家",
        "tools": EXPERT_BASE_TOOLS,
        "icon": "📅",
    },
}

LEAD_TOOL_DEFINITIONS = [
    READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
    SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL,
    CREATE_TASK_TOOL, LIST_TASKS_TOOL,
    SPAWN_TEAMMATE_TOOL, REQUEST_SHUTDOWN_TOOL,
    IP_LOCATION_TOOL,
]

active_teammates: dict[str, threading.Thread] = {}
running = False  # 全局运行标志


class AgentRunner:
    """封装整个多 Agent 协调流程"""

    def __init__(self):
        self.bus = MessageBus(WORKSPACE / ".mailboxes")
        self.board = TaskBoard(WORKSPACE / ".tasks")
        self.protocol = ProtocolManager(self.bus)
        self.session_id = ""

    def _emit(self, event_type: str, data: dict | str):
        """发送 WebSocket 事件 + 写入 SQLite"""
        emit(event_type, data)
        # session_id 为空时跳过 DB 写入
        if not self.session_id:
            return
        # 按事件类型写入对应表
        if event_type == "lead_text":
            store.save_chat_message(self.session_id, "lead", data.get("text", str(data)))
        elif event_type == "lead_tool":
            store.save_chat_message(self.session_id, "tool", f"{data.get('tool','')}: {data.get('input','')}")
        elif event_type == "status":
            store.save_chat_message(self.session_id, "system", str(data))
        elif event_type == "expert_started":
            d = data if isinstance(data, dict) else {}
            store.save_agent_log(self.session_id, d.get("name",""), "started", d.get("role",""), d.get("icon",""))
        elif event_type == "expert_text":
            d = data if isinstance(data, dict) else {}
            store.save_agent_log(self.session_id, d.get("name",""), "text", d.get("text","")[:200])
        elif event_type == "expert_tool":
            d = data if isinstance(data, dict) else {}
            store.save_agent_log(self.session_id, d.get("name",""), "tool",
                                f"{d.get('tool','')}: {d.get('input','')[:100]}")
        elif event_type == "expert_completed":
            d = data if isinstance(data, dict) else {}
            store.save_agent_log(self.session_id, d.get("name",""), "completed", d.get("summary","")[:200])
        elif event_type == "agent_message":
            d = data if isinstance(data, dict) else {}
            store.save_chat_message(self.session_id, "system",
                                    f"[{d.get('from','')}→{d.get('to','')}] {d.get('content','')[:200]}")
        elif event_type == "plan_ready":
            store.save_plan(self.session_id, str(data))
        elif event_type == "task_board":
            store.save_task_snapshot(self.session_id, str(data))
        elif event_type == "done":
            store.update_session(self.session_id, "completed")

    def spawn_teammate(self, name: str, role: str, prompt: str) -> str:
        if not running:
            return "System stopped."
        cfg = EXPERT_REGISTRY.get(name)
        if not cfg:
            return f"Unknown expert: {name}"

        def run():
            self._emit("expert_started", {"name": name, "role": role, "icon": cfg["icon"]})
            handlers = make_handlers(self.bus, self.board, name)

            messages = [{"role": "user", "content": prompt}]

            for turn in range(20):
                if not running:
                    break

                # 检查收件箱
                inbox = self.bus.read_inbox(name)
                should_stop = False
                for m in inbox:
                    if m.msg_type == "shutdown_request":
                        self.bus.send(name, m.msg_from, f"{name} shutting down.",
                                     "shutdown_response",
                                     {"request_id": m.metadata.get("request_id", ""), "approved": True})
                        should_stop = True
                    self._emit("agent_message", {"from": m.msg_from, "to": name,
                          "content": m.content[:200], "type": m.msg_type})
                if should_stop:
                    break
                if inbox:
                    inbox_text = "\n".join(f"From {m.msg_from} [{m.msg_type}]: {m.content[:500]}" for m in inbox)
                    messages.append({"role": "user", "content": f"[Inbox]\n{inbox_text}"})

                # Expert 用小模型
                try:
                    response = client.messages.create(
                        model=EXPERT_MODEL, max_tokens=8000,
                        system=cfg["rp"], messages=messages,
                        tools=cfg["tools"],
                    )
                except Exception as e:
                    self._emit("error", f"[{name}] API error: {e}")
                    break

                assistant_block = {"role": "assistant", "content": []}
                tool_results = []

                for block in response.content:
                    if block.type == "text":
                        self._emit("expert_text", {"name": name, "text": block.text})
                        assistant_block["content"].append({"type": "text", "text": block.text})

                    elif block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id
                        self._emit("expert_tool", {"name": name, "tool": tool_name,
                              "input": json.dumps(tool_input, ensure_ascii=False)[:200]})

                        assistant_block["content"].append({
                            "type": "tool_use", "id": tool_id,
                            "name": tool_name, "input": tool_input,
                        })

                        handler = handlers.get(tool_name)
                        if handler:
                            try:
                                result_text = handler(tool_input)
                            except Exception as e:
                                result_text = f"Error: {e}"
                        else:
                            result_text = f"Unknown: {tool_name}"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result_text,
                        })

                messages.append(assistant_block)
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

                if response.stop_reason != "tool_use":
                    break

            # 完成
            summary = ""
            for m in messages:
                if m["role"] == "assistant":
                    for b in m.get("content", []):
                        if b.get("type") == "text":
                            summary += b["text"] + " "
            summary = summary[-500:]
            self.bus.send(name, "lead", summary, "result")
            self._emit("expert_completed", {"name": name, "summary": summary[:300]})

        t = threading.Thread(target=run, daemon=True, name=name)
        active_teammates[name] = t
        t.start()
        return f"Teammate '{name}' started."

    def run_lead(self, user_input: str, client_ip: str = ""):
        """运行 Lead Agent（在后台线程中）"""
        global running
        running = True

        # 创建数据库会话（必须在任何 _emit 写DB之前）
        self.session_id = store.create_session(user_input)

        self._emit("status", "开始分析需求...")
        self._emit("lead_text", {"text": f"收到需求: {user_input}"})

        # 清理之前的任务
        for f in (WORKSPACE / ".tasks").glob("*.json"):
            f.unlink(missing_ok=True)
        for f in (WORKSPACE / ".mailboxes").glob("*.jsonl"):
            f.unlink(missing_ok=True)

        # 如果用户没给出发城市，提示 Lead 用 IP 定位自动获取
        ip_hint = ""
        if client_ip and client_ip not in ("127.0.0.1", "localhost", "::1"):
            ip_hint = f"\n注意：用户客户端 IP 是 {client_ip}，如果用户没写出发城市，请调用 ip_location(ip=\"{client_ip}\") 自动获取。"
        else:
            ip_hint = "\n注意：如果用户没写出发城市，请调用 ip_location() 尝试自动获取，或直接询问用户。"

        initial_message = f"""用户需求：{user_input}
{ip_hint}

当前日期：{datetime.now().strftime('%Y年%m月%d日 %A')}。规划行程时必须以此日期为基准，使用真实日期。

你是旅游攻略协调员。**重要：直接开始工作，不要向用户提问。**

用户需求中缺失的信息按以下默认值：
- 出发城市：调用 ip_location 工具自动检测；失败默认"北京"
- 预算：默认3000元
- 偏好：默认经典景点+美食
- 日期：默认一周后出发

现在执行：
1. 调用 ip_location 检测出发城市
2. 用 create_task 创建5个任务：task_01(景点) task_02(交通) task_03(住宿) task_04(行程,依赖01/03) task_05(整合,依赖01-04)
3. 用 spawn_teammate 同时启动 attraction_expert, transport_expert, accommodation_expert
4. 前三个完成后启动 schedule_expert
5. 整合为 outputs/travel_plan.md

开始！"""

        lead_handlers = make_handlers(self.bus, self.board, "lead",
                                       spawn_fn=self.spawn_teammate)

        messages = [{"role": "user", "content": initial_message}]

        for turn in range(60):
            if not running:
                break

            # Lead 用大模型
            try:
                response = client.messages.create(
                    model=LEAD_MODEL, max_tokens=8000,
                    system=LEAD_SYSTEM_PROMPT, messages=messages,
                    tools=LEAD_TOOL_DEFINITIONS,
                )
            except Exception as e:
                self._emit("error", f"[Lead] API error: {e}")
                break

            assistant_block = {"role": "assistant", "content": []}
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    self._emit("lead_text", {"text": block.text})
                    assistant_block["content"].append({"type": "text", "text": block.text})

                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id
                    self._emit("lead_tool", {"tool": tool_name,
                         "input": json.dumps(tool_input, ensure_ascii=False)[:300]})

                    assistant_block["content"].append({
                        "type": "tool_use", "id": tool_id,
                        "name": tool_name, "input": tool_input,
                    })

                    handler = lead_handlers.get(tool_name)
                    if handler:
                        try:
                            result_text = handler(tool_input)
                        except Exception as e:
                            result_text = f"Error: {e}"
                    else:
                        result_text = f"Unknown: {tool_name}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_text,
                    })

            messages.append(assistant_block)
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # 收件箱注入
            inbox = self.bus.read_inbox("lead")
            if inbox:
                inbox_lines = []
                for m in inbox:
                    req_id = m.metadata.get("request_id", "")
                    if req_id and m.msg_type.endswith("_response"):
                        self.protocol.receive_response(m.msg_type, req_id,
                                                        m.metadata.get("approved", False), m.content)
                    prefix = {"result": "[完成]", "plan_request": "[待审批]",
                              "message": "[消息]"}.get(m.msg_type, f"[{m.msg_type}]")
                    inbox_lines.append(f"{prefix} From {m.msg_from}: {m.content[:300]}")
                    self._emit("agent_message", {"from": m.msg_from, "to": "lead",
                          "content": m.content[:200], "type": m.msg_type})
                if inbox_lines:
                    messages.append({"role": "user", "content": "[收件箱]\n" + "\n".join(inbox_lines)})

            # 更新任务看板
            self._emit("task_board", self.board.summary())

            # 检查完成条件
            if response.stop_reason != "tool_use":
                alive = [n for n, t in active_teammates.items() if t.is_alive()]
                if not alive:
                    self._emit("status", "所有专家已完成，正在整合最终攻略...")
                    # 再给 Lead 一次机会整合
                    messages.append({"role": "user",
                        "content": "所有专家已完成工作。请读取他们的输出文件，整合生成最终攻略写入 outputs/travel_plan.md"})
                    continue
                else:
                    time.sleep(2)

        # 结束
        running = False

        # 检查是否生成了最终攻略
        plan_file = OUTPUTS_DIR / "travel_plan.md"
        if plan_file.exists():
            plan_content = plan_file.read_text(encoding="utf-8")
            self._emit("plan_ready", plan_content)
        else:
            # 收集所有输出
            all_outputs = []
            for f in sorted(OUTPUTS_DIR.glob("*.json")):
                all_outputs.append(f"\n### {f.name}\n```json\n{f.read_text(encoding='utf-8')[:2000]}\n```")
            for f in sorted(OUTPUTS_DIR.glob("*.md")):
                all_outputs.append(f"\n### {f.name}\n{f.read_text(encoding='utf-8')[:3000]}")
            self._emit("plan_ready", "\n".join(all_outputs) or "攻略生成中，请查看输出目录。")

        self._emit("done", "任务完成")


# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(title="旅游攻略多智能体系统", version="1.0.0")

# 静态文件
static_dir = ROOT / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/api/outputs")
async def list_outputs():
    """列出已生成的攻略文件"""
    files = []
    if OUTPUTS_DIR.exists():
        for f in sorted(OUTPUTS_DIR.glob("*")):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "content": f.read_text(encoding="utf-8")[:50000],
                })
    return {"files": files}


@app.get("/api/sessions")
async def list_sessions_api():
    """列出历史会话"""
    sessions = store.list_sessions(limit=30)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session_api(session_id: str):
    """加载一个完整会话"""
    data = store.load_full_session(session_id)
    if not data:
        return {"error": "Session not found"}
    return data


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket — Agent 实时状态推送"""
    await ws.accept()
    q: queue.Queue = queue.Queue()
    event_queues.append(q)

    global running
    try:
        while True:
            # 接收前端消息
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                msg = json.loads(data)

                if msg.get("action") == "start":
                    user_input = msg.get("input", "")
                    if user_input and not running:
                        # 获取客户端 IP（用于 IP 定位出发城市）
                        client_ip = ws.client.host if ws.client else ""
                        # 在后台线程中启动 Agent 系统
                        runner = AgentRunner()
                        t = threading.Thread(target=runner.run_lead, args=(user_input, client_ip), daemon=True)
                        t.start()
                        await ws.send_text(json.dumps({"type": "started", "data": "Agent system started"}, ensure_ascii=False))

                elif msg.get("action") == "stop":
                    running = False
                    await ws.send_text(json.dumps({"type": "stopped", "data": "Stopping..."}, ensure_ascii=False))

            except asyncio.TimeoutError:
                pass

            # 推送事件给前端
            try:
                while True:
                    event = q.get_nowait()
                    await ws.send_text(json.dumps(event, ensure_ascii=False))
            except queue.Empty:
                pass

            await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass
    finally:
        event_queues.remove(q)


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  旅游攻略多智能体系统 — Web Server")
    print(f"  访问: http://localhost:8765")
    print(f"  Lead 模型 (大): {LEAD_MODEL}")
    print(f"  Expert 模型 (小): {EXPERT_MODEL}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
