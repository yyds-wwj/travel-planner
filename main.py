"""
旅游攻略多智能体系统 — 主入口

架构: 1 Lead + 4 专家 Agent（基于 s15-s17 的团队模式）

用法:
    python main.py

启动后输入你的旅游需求，系统会自动协调专家团队生成攻略。
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

import anthropic

from harness.message_bus import MessageBus
from harness.task_board import TaskBoard
from harness.team_protocols import ProtocolManager
from harness.agent_loop import run_agent_loop, WORKSPACE, OUTPUTS_DIR
from harness.tools import (
    READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
    SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL,
    CREATE_TASK_TOOL, LIST_TASKS_TOOL,
    SPAWN_TEAMMATE_TOOL, REQUEST_SHUTDOWN_TOOL,
    IP_LOCATION_TOOL,
    AMAP_TOOLS,
    make_handlers,
)

# Agent 定义
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
# 模型选型：Lead 用大模型，Expert 用小模型
LEAD_MODEL = os.getenv("LEAD_MODEL", "") or os.getenv("MODEL_ID", "claude-sonnet-4-6")
EXPERT_MODEL = os.getenv("EXPERT_MODEL", "") or os.getenv("MODEL_ID", "claude-sonnet-4-6")

client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)
BUS = MessageBus(WORKSPACE / ".mailboxes")
BOARD = TaskBoard(WORKSPACE / ".tasks")
PROTOCOL = ProtocolManager(BUS)

# 活跃的队友线程追踪
active_teammates: dict[str, threading.Thread] = {}
teammate_results: dict[str, str] = {}


# ============================================================
# 专家 Agent 线程
# ============================================================

EXPERT_REGISTRY = {
    "attraction_expert": {
        "system_prompt": ATTRACTION_SYSTEM_PROMPT,
        "role": "景点与美术推荐专家",
        "tools": [READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
                  SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL] + AMAP_TOOLS,
    },
    "transport_expert": {
        "system_prompt": TRANSPORT_SYSTEM_PROMPT,
        "role": "交通出行专家",
        "tools": [READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
                  SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL] + AMAP_TOOLS,
    },
    "accommodation_expert": {
        "system_prompt": ACCOMMODATION_SYSTEM_PROMPT,
        "role": "住宿推荐专家",
        "tools": [READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
                  SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL] + AMAP_TOOLS,
    },
    "schedule_expert": {
        "system_prompt": SCHEDULE_SYSTEM_PROMPT,
        "role": "时间规划专家",
        "tools": [READ_FILE_TOOL, WRITE_FILE_TOOL, BASH_TOOL,
                  SEND_MESSAGE_TOOL, CHECK_INBOX_TOOL] + AMAP_TOOLS,
    },
}


def spawn_teammate_fn(name: str, role: str, prompt: str) -> str:
    """Lead 调用 spawn_teammate 工具时触发。

    启动一个专家 Agent 线程，跑在自己的 agent loop 中。
    """
    if name in active_teammates:
        return f"Teammate '{name}' already running."

    expert_config = EXPERT_REGISTRY.get(name)
    if expert_config is None:
        return f"Unknown expert type: {name}. Available: {list(EXPERT_REGISTRY.keys())}"

    def run_expert():
        print(f"\n{'='*60}")
        print(f"  [{name}] 启动 — {role}")
        print(f"  [{name}] 任务: {prompt[:200]}...")
        print(f"{'='*60}")

        handlers = make_handlers(BUS, BOARD, name)

        messages = run_agent_loop(
            client=client,
            model=EXPERT_MODEL,  # Expert 用小模型
            system_prompt=expert_config["system_prompt"],
            initial_message=prompt,
            tool_definitions=expert_config["tools"],
            tool_handlers=handlers,
            agent_name=name,
            max_turns=20,
        )

        # 完成后总结
        summary_parts = []
        for m in messages:
            if m["role"] == "assistant":
                for block in m.get("content", []):
                    if block.get("type") == "text":
                        summary_parts.append(block["text"])
        summary = " ".join(summary_parts[-3:])[:500]  # 最后3段文本

        BUS.send(name, "lead", f"[{name}] 工作完成。\n{summary}", "result")
        teammate_results[name] = summary
        print(f"\n  [{name}] 完成，已发送结果给 Lead")

    thread = threading.Thread(target=run_expert, daemon=True, name=name)
    active_teammates[name] = thread
    thread.start()
    return f"Teammate '{name}' ({role}) started. Task: {prompt[:150]}"


# ============================================================
# Lead Agent 工具定义
# ============================================================

LEAD_TOOL_DEFINITIONS = [
    READ_FILE_TOOL,
    WRITE_FILE_TOOL,
    BASH_TOOL,
    SEND_MESSAGE_TOOL,
    CHECK_INBOX_TOOL,
    CREATE_TASK_TOOL,
    LIST_TASKS_TOOL,
    SPAWN_TEAMMATE_TOOL,
    REQUEST_SHUTDOWN_TOOL,
]


# ============================================================
# 收件箱轮询（注入 Lead 的对话上下文）
# ============================================================

def consume_lead_inbox(messages: list[dict]):
    """从收件箱读取消息，解析协议响应，注入到 messages"""
    msgs = BUS.read_inbox("lead")
    if not msgs:
        return

    for msg in msgs:
        # 处理协议响应
        req_id = msg.metadata.get("request_id", "")
        if req_id and msg.msg_type.endswith("_response"):
            PROTOCOL.receive_response(
                msg.msg_type, req_id,
                msg.metadata.get("approved", False),
                msg.content,
            )

    # 将收件箱内容注入对话历史
    inbox_lines = []
    for msg in msgs:
        prefix = {"result": "[完成]", "plan_request": "[待审批]",
                  "message": "[消息]", "info_request": "[请求信息]"}.get(
            msg.msg_type, f"[{msg.msg_type}]")
        inbox_lines.append(f"{prefix} From {msg.msg_from}: {msg.content[:300]}")

    if inbox_lines:
        inbox_text = "\n".join(inbox_lines)
        messages.append({
            "role": "user",
            "content": f"[收件箱 — 专家消息]\n{inbox_text}\n\n请根据以上消息决定下一步行动。"
        })


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("  旅游攻略多智能体系统")
    print("  Travel Planner — Multi-Agent System")
    print("=" * 60)
    print(f"  Lead 模型 (大): {LEAD_MODEL}")
    print(f"  Expert 模型 (小): {EXPERT_MODEL}")
    print(f"  API: {BASE_URL}")
    print(f"  输出目录: {OUTPUTS_DIR}")
    print("=" * 60)
    print()
    print("提示：输入你的旅游需求，我将协调专家团队为你制定详细攻略。")
    print("示例：我想去杭州玩3天，预算3000元，喜欢自然风光和艺术展览。")
    print()

    user_input = input("请输入你的旅游需求: ").strip()
    if not user_input:
        print("未输入需求，退出。")
        return

    initial_message = f"""用户需求：{user_input}

当前日期：{datetime.now().strftime('%Y年%m月%d日 %A')}。规划行程时必须以此日期为基准，所有日期必须是真实日期。

你是旅游攻略协调员。**重要：直接开始工作，不要向用户提问。**

用户需求中缺失的信息按以下默认值处理：
- 出发城市：调用 ip_location 工具自动检测；如果检测失败，默认"北京"
- 预算：默认3000元（舒适型）
- 偏好：默认经典必去景点+美食体验
- 出行日期：从当前日期开始（当前日期已给出）

现在按以下流程执行：
1. 先调用 ip_location 检测出发城市
2. 使用 create_task 创建5个任务（task_01到task_05）
3. 使用 spawn_teammate 启动 attraction_expert, transport_expert, accommodation_expert（三个可同时启动）
4. 等待前三个完成后启动 schedule_expert
5. 收集结果，整合为最终攻略写入 outputs/travel_plan.md

专家启动参数：
- attraction_expert: role="景点与美术推荐专家", prompt="推荐{目的地}必去景点和博物馆，写outputs/attractions.json"
- transport_expert: role="交通出行专家", prompt="规划往返交通和市内出行，写outputs/transport.json"
- accommodation_expert: role="住宿推荐专家", prompt="推荐每日住宿方案，写outputs/accommodations.json"
- schedule_expert: role="时间规划专家", prompt="根据景点和住宿数据设计每日行程，写outputs/schedule.json"

开始！"""

    print(f"\n  [Lead] 开始处理需求: {user_input[:100]}...")
    print(f"  [Lead] 工作区: {WORKSPACE}")
    print()

    # Lead 的工具处理器
    lead_handlers = make_handlers(BUS, BOARD, "lead", spawn_fn=spawn_teammate_fn)

    # ============================================================
    # Lead Agent 主循环（手动实现以支持收件箱注入）
    # ============================================================
    messages = [{"role": "user", "content": initial_message}]
    turn_count = 0
    max_turns = 50

    while turn_count < max_turns:
        turn_count += 1
        print(f"\n  [Lead] --- Turn {turn_count}/{max_turns} ---")

        # Lead 用大模型
        try:
            response = client.messages.create(
                model=LEAD_MODEL,
                max_tokens=8000,
                system=LEAD_SYSTEM_PROMPT,
                messages=messages,
                tools=LEAD_TOOL_DEFINITIONS,
            )
        except anthropic.AuthenticationError:
            print("  [Lead] Auth error — check ANTHROPIC_API_KEY")
            break
        except anthropic.APIConnectionError:
            print("  [Lead] Connection error — retrying...")
            time.sleep(2)
            continue
        except anthropic.APIStatusError as e:
            print(f"  [Lead] API error ({e.status_code}): {e.message}")
            if e.status_code >= 500:
                time.sleep(2)
                continue
            break

        # 处理响应
        assistant_block = {"role": "assistant", "content": []}
        tool_results = []
        has_tool_use = False

        for block in response.content:
            if block.type == "text":
                text = block.text
                assistant_block["content"].append({"type": "text", "text": text})
                print(f"  [Lead] 💬 {text[:300]}")

            elif block.type == "tool_use":
                has_tool_use = True
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                assistant_block["content"].append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input,
                })

                print(f"  [Lead] 🔧 {tool_name}: {json.dumps(tool_input, ensure_ascii=False)[:200]}")

                handler = lead_handlers.get(tool_name)
                if handler:
                    try:
                        result_text = handler(tool_input)
                    except Exception as e:
                        result_text = f"Tool error: {e}"
                else:
                    result_text = f"Unknown tool: {tool_name}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_text,
                })
                print(f"  [Lead]    → {result_text[:200]}")

        messages.append(assistant_block)

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        # 收件箱注入（工具执行后、下一轮 LLM 调用前）
        consume_lead_inbox(messages)

        # 停止条件
        if response.stop_reason == "end_turn":
            # Lead 可能认为任务完成了，检查收件箱
            consume_lead_inbox(messages)
            # 如果没有任何活跃队友，且用户确认，则结束
            if not active_teammates or all(not t.is_alive() for t in active_teammates.values()):
                print("\n  [Lead] 任务似乎已完成。")
                confirm = input("  是否结束? (y/n，或继续对话): ").strip().lower()
                if confirm == "y":
                    break
                else:
                    messages.append({"role": "user", "content": confirm or "请继续。"})
            else:
                print(f"  [Lead] 等待队友完成... (活跃: {[n for n,t in active_teammates.items() if t.is_alive()]})")
                time.sleep(2)
                consume_lead_inbox(messages)

    # ============================================================
    # 结束
    # ============================================================
    print("\n" + "=" * 60)
    print("  旅游攻略生成完成！")
    print(f"  输出目录: {OUTPUTS_DIR}")
    print("=" * 60)

    # 列出生成的文件
    for f in sorted(OUTPUTS_DIR.glob("*")):
        if f.is_file():
            print(f"  - {f.name} ({f.stat().st_size} bytes)")

    print()


if __name__ == "__main__":
    main()
