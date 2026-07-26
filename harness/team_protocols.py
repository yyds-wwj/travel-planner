"""
团队协议 — 结构化 Agent 间通信。

协议类型:
- shutdown:   Lead → 专家，请求体面关机
- plan_approval: 专家 → Lead，提交方案待审批
- info_request:  专家 → Lead，请求补充信息
"""

import time
import uuid
from dataclasses import dataclass, field
from harness.message_bus import MessageBus


VALID_PROTOCOLS = {"shutdown", "plan_approval", "info_request"}


@dataclass
class ProtocolState:
    """协议请求的状态追踪"""
    request_id: str
    protocol_type: str          # shutdown | plan_approval | info_request
    sender: str                 # 发起方
    target: str                 # 接收方
    status: str = "pending"     # pending | approved | rejected
    payload: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


class ProtocolManager:
    """协议请求管理器"""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.pending: dict[str, ProtocolState] = {}

    def new_request_id(self) -> str:
        return f"req_{uuid.uuid4().hex[:8]}"

    def send_request(self, sender: str, target: str,
                     protocol_type: str, payload: str = "") -> ProtocolState:
        """发送协议请求"""
        if protocol_type not in VALID_PROTOCOLS:
            raise ValueError(f"Unknown protocol: {protocol_type}")
        req_id = self.new_request_id()
        state = ProtocolState(
            request_id=req_id,
            protocol_type=protocol_type,
            sender=sender,
            target=target,
            payload=payload,
        )
        self.pending[req_id] = state

        # 通过 MessageBus 发送协议消息
        msg_type = f"{protocol_type}_request"
        self.bus.send(sender, target, payload, msg_type,
                      metadata={"request_id": req_id, "protocol": protocol_type})
        return state

    def receive_response(self, msg_type: str, request_id: str,
                         approved: bool, payload: str = "") -> str:
        """处理协议响应"""
        state = self.pending.get(request_id)
        if not state:
            return f"No pending request found for {request_id}"
        if state.status != "pending":
            return f"Request {request_id} already resolved: {state.status}"

        expected_response = f"{state.protocol_type}_response"
        if msg_type != expected_response:
            return f"Type mismatch: expected {expected_response}, got {msg_type}"

        state.status = "approved" if approved else "rejected"
        state.payload = payload
        return f"Protocol {request_id} → {state.status}"

    def handle_inbox(self, agent_name: str, messages: list) -> tuple[list, bool]:
        """处理收件箱消息，分离协议消息和普通消息。

        Returns: (普通消息列表, 是否收到 shutdown 请求)
        """
        normal = []
        should_shutdown = False

        for msg in messages:
            msg_type = msg.msg_type

            if msg_type == "shutdown_request":
                req_id = msg.metadata.get("request_id", "")
                # 自动回复 shutdown_response
                self.bus.send(agent_name, msg.msg_from,
                             f"{agent_name} shutting down.",
                             "shutdown_response",
                             {"request_id": req_id, "approved": True})
                should_shutdown = True
                normal.append(msg)

            elif msg_type == "plan_approval_response":
                req_id = msg.metadata.get("request_id", "")
                approved = msg.metadata.get("approved", False)
                if req_id:
                    self.receive_response(msg_type, req_id, approved, msg.content)
                normal.append(msg)

            elif msg_type == "shutdown_response":
                req_id = msg.metadata.get("request_id", "")
                approved = msg.metadata.get("approved", False)
                if req_id:
                    self.receive_response(msg_type, req_id, approved, msg.content)
                normal.append(msg)

            else:
                normal.append(msg)

        return normal, should_shutdown
