"""
SQLite 持久化存储 — 会话、对话、日志、攻略

表结构:
  sessions      — 每次规划会话
  chat_messages — Lead 对话记录
  agent_logs    — 所有 Agent 的活动日志
  plans         — 最终攻略内容
  task_snapshots — 任务看板快照
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "travel_planner.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    """获取数据库连接，自动初始化表"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    """确保所有表存在（在 get_db 中自动调用）"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_input TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            msg_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            icon TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            plan_content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS task_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            task_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_logs_session ON agent_logs(session_id);
    """)
    conn.commit()


# 模块加载时初始化
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# Session CRUD
# ============================================================

def create_session(user_input: str) -> str:
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (id, user_input, status, created_at, updated_at) VALUES (?, ?, 'running', ?, ?)",
        (session_id, user_input, now, now))
    conn.commit()
    conn.close()
    return session_id


def update_session(session_id: str, status: str):
    conn = get_db()
    conn.execute(
        "UPDATE sessions SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), session_id))
    conn.commit()
    conn.close()


def list_sessions(limit: int = 20) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# Chat Messages
# ============================================================

def save_chat_message(session_id: str, msg_type: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_messages (session_id, msg_type, content, created_at) VALUES (?,?,?,?)",
        (session_id, msg_type, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_chat_messages(session_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Agent Logs
# ============================================================

def save_agent_log(session_id: str, agent_name: str, event_type: str,
                   content: str, icon: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO agent_logs (session_id, agent_name, event_type, content, icon, created_at) VALUES (?,?,?,?,?,?)",
        (session_id, agent_name, event_type, content, icon, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_agent_logs(session_id: str, agent_name: str = "") -> list[dict]:
    conn = get_db()
    if agent_name:
        rows = conn.execute(
            "SELECT * FROM agent_logs WHERE session_id=? AND agent_name=? ORDER BY id ASC",
            (session_id, agent_name)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_logs WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Plans
# ============================================================

def save_plan(session_id: str, plan_content: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO plans (session_id, plan_content, created_at) VALUES (?,?,?)",
        (session_id, plan_content, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_plan(session_id: str) -> str | None:
    conn = get_db()
    row = conn.execute(
        "SELECT plan_content FROM plans WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    return row["plan_content"] if row else None


# ============================================================
# Task Snapshots
# ============================================================

def save_task_snapshot(session_id: str, task_data: str):
    conn = get_db()
    # 每个 session 只保留最新一条
    conn.execute(
        "DELETE FROM task_snapshots WHERE session_id=?", (session_id,))
    conn.execute(
        "INSERT INTO task_snapshots (session_id, task_data, created_at) VALUES (?,?,?)",
        (session_id, task_data, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_task_snapshot(session_id: str) -> str | None:
    conn = get_db()
    row = conn.execute(
        "SELECT task_data FROM task_snapshots WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return row["task_data"] if row else None


# ============================================================
# 完整会话加载
# ============================================================

def load_full_session(session_id: str) -> dict | None:
    """加载一个会话的所有数据"""
    session = get_session(session_id)
    if not session:
        return None
    return {
        "session": session,
        "chat_messages": get_chat_messages(session_id),
        "agent_logs": get_agent_logs(session_id),
        "plan": get_plan(session_id),
        "task_board": get_task_snapshot(session_id),
    }
