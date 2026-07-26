"""
权限门控 — 三段式审批管道。

1. 硬拒绝列表（危险命令）
2. 规则匹配（写工作区之外、破坏性操作）
3. 用户审批
"""

import shlex
from pathlib import Path


# 硬拒绝列表 — 永远不允许执行的命令模式
HARD_DENY = [
    "rm -rf /",
    "sudo rm",
    "mkfs.",
    "dd if=",
    ":(){ :|:& };:",   # fork bomb
    "> /dev/sda",
]


def check_permission(tool_name: str, params: dict, workspace: str) -> tuple[bool, str]:
    """检查操作权限。

    Returns: (allowed, reason)
    """
    workspace_path = Path(workspace).resolve()

    # Gate 1: 硬拒绝
    if tool_name == "bash":
        command = params.get("command", "")
        for denied in HARD_DENY:
            if denied in command:
                return False, f"Hard deny: command matches '{denied}'"

    # Gate 2: 规则检查
    if tool_name in ("write_file", "edit_file"):
        file_path = Path(params.get("file_path", "")).resolve()
        try:
            file_path.relative_to(workspace_path)
        except ValueError:
            return False, f"Write outside workspace: {file_path}"

    # Gate 3: 用户审批（高风险操作需确认）
    if tool_name == "bash":
        command = params.get("command", "")
        dangerous_keywords = ["rm ", "delete", "drop", "truncate", "shutdown", "reboot"]
        for kw in dangerous_keywords:
            if kw in command.lower():
                # 需要用户确认
                return _ask_user(command)

    return True, ""


def _ask_user(command: str) -> tuple[bool, str]:
    """用户审批（命令行交互）"""
    print(f"\n  [Permission] 高风险命令: {command}")
    answer = input("  允许执行? (y/n): ").strip().lower()
    if answer == "y":
        return True, "User approved"
    return False, "User denied"
