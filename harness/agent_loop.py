"""
Agent Loop — 核心引擎。

每个 Agent（Lead 或专家）都运行这个循环：
while stop_reason == "tool_use":
    response = LLM(messages, tools)
    执行工具
    追加结果到 messages

设计原则：
- Agent = Model + Harness（本文件定义 Harness）
- 工具通过 TOOL_HANDLERS dispatch 机制分发（s02 模式）
- 权限检查在每个工具执行前触发（s03 模式）
"""

import json
import traceback
import anthropic
from pathlib import Path
from typing import Callable

from harness.permission import check_permission

# 工作区根目录
WORKSPACE = Path(__file__).parent.parent.resolve()
OUTPUTS_DIR = WORKSPACE / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def run_agent_loop(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    initial_message: str,
    tool_definitions: list[dict],
    tool_handlers: dict[str, Callable],
    agent_name: str = "agent",
    max_turns: int = 30,
    on_pre_tool: Callable | None = None,   # Hook: 工具执行前
    on_post_tool: Callable | None = None,  # Hook: 工具执行后
    on_stop: Callable | None = None,       # Hook: 停止时
) -> list[dict]:
    """运行 Agent 主循环。

    Args:
        client: Anthropic 客户端
        model: 模型 ID
        system_prompt: 系统提示词
        initial_message: 初始用户消息
        tool_definitions: 工具定义列表
        tool_handlers: 工具名 → 处理函数的映射
        agent_name: Agent 名称（用于日志和权限）
        max_turns: 最大 LLM 调用轮数
        on_pre_tool: 工具执行前的回调 (tool_name, params) -> None
        on_post_tool: 工具执行后的回调 (tool_name, params, result) -> None
        on_stop: Agent 停止时的回调 (reason, messages) -> None

    Returns:
        完整的消息历史
    """
    messages = [{"role": "user", "content": initial_message}]
    turn_count = 0

    while turn_count < max_turns:
        turn_count += 1
        print(f"\n  [{agent_name}] turn {turn_count}/{max_turns} ...")

        try:
            response = client.messages.create(
                model=model,
                max_tokens=8000,
                system=system_prompt,
                messages=messages,
                tools=tool_definitions,
            )
        except anthropic.AuthenticationError:
            print(f"  [{agent_name}] Auth error — check ANTHROPIC_API_KEY")
            break
        except anthropic.APIConnectionError:
            print(f"  [{agent_name}] Connection error — retrying...")
            continue
        except anthropic.APIStatusError as e:
            print(f"  [{agent_name}] API error ({e.status_code}): {e.message}")
            continue

        # 处理响应
        assistant_block = {"role": "assistant", "content": []}
        tool_results = []

        for block in response.content:
            if block.type == "text":
                assistant_block["content"].append({
                    "type": "text",
                    "text": block.text,
                })
                print(f"  [{agent_name}] TEXT: {block.text[:200]}...")

            elif block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                print(f"  [{agent_name}] TOOL: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:150]})")

                assistant_block["content"].append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input,
                })

                # 权限检查
                allowed, reason = check_permission(tool_name, tool_input, str(WORKSPACE))
                if not allowed:
                    result_text = f"Permission denied: {reason}"
                    print(f"  [{agent_name}] DENIED: {reason}")
                else:
                    # Hook: 工具执行前
                    if on_pre_tool:
                        on_pre_tool(tool_name, tool_input)

                    # 执行工具
                    handler = tool_handlers.get(tool_name)
                    if handler:
                        try:
                            result_text = handler(tool_input)
                        except Exception as e:
                            result_text = f"Tool error: {e}\n{traceback.format_exc()}"
                    else:
                        result_text = f"Unknown tool: {tool_name}"

                    # Hook: 工具执行后
                    if on_post_tool:
                        on_post_tool(tool_name, tool_input, result_text)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_text,
                })

        # 追加 assistant 消息
        messages.append(assistant_block)

        # 追加 tool_result 消息
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        # 检查停止条件
        if response.stop_reason != "tool_use":
            if on_stop:
                on_stop(response.stop_reason, messages)
            break

    return messages
