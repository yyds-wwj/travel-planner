"""
MessageBus — 文件收件箱，多 Agent 异步通信。

每个 Agent 有一个 .jsonl 邮箱文件。
发消息 = 往对方文件 append 一行 JSON。
读消息 = 消费式读取（读完删除）。
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Message:
    """团队通信消息"""
    msg_from: str
    msg_to: str
    content: str
    msg_type: str = "message"          # message | result | shutdown_request | shutdown_response | plan_request | plan_response
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "from": self.msg_from,
            "to": self.msg_to,
            "content": self.content,
            "type": self.msg_type,
            "metadata": self.metadata,
            "ts": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            msg_from=d.get("from", ""),
            msg_to=d.get("to", ""),
            content=d.get("content", ""),
            msg_type=d.get("type", "message"),
            metadata=d.get("metadata", {}),
            timestamp=d.get("ts", 0.0),
        )


class MessageBus:
    """文件收件箱消息总线"""

    def __init__(self, mailbox_dir: str = ".mailboxes"):
        self.mailbox_dir = Path(mailbox_dir)
        self.mailbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, from_agent: str, to_agent: str,
             content: str, msg_type: str = "message",
             metadata: dict | None = None) -> Message:
        """发送消息到目标 Agent 的收件箱"""
        msg = Message(
            msg_from=from_agent,
            msg_to=to_agent,
            content=content,
            msg_type=msg_type,
            metadata=metadata or {},
        )
        inbox = self.mailbox_dir / f"{to_agent}.jsonl"
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
        return msg

    def read_inbox(self, agent: str) -> list[Message]:
        """消费式读取收件箱：读完后删除文件"""
        inbox = self.mailbox_dir / f"{agent}.jsonl"
        if not inbox.exists():
            return []
        try:
            text = inbox.read_text(encoding="utf-8").strip()
            if not text:
                inbox.unlink(missing_ok=True)
                return []
            messages = [Message.from_dict(json.loads(line))
                       for line in text.split("\n") if line.strip()]
        except Exception:
            messages = []
        inbox.unlink(missing_ok=True)
        return messages

    def check_inbox(self, agent: str) -> list[Message]:
        """非消费式检查收件箱（不删除）"""
        inbox = self.mailbox_dir / f"{agent}.jsonl"
        if not inbox.exists():
            return []
        try:
            text = inbox.read_text(encoding="utf-8").strip()
            if not text:
                return []
            return [Message.from_dict(json.loads(line))
                    for line in text.split("\n") if line.strip()]
        except Exception:
            return []
