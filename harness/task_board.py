"""
任务看板 — 文件持久化的任务图。

每个任务一个 .tasks/task_{id}.json 文件。
支持状态流转: pending → in_progress → completed | failed
支持依赖关系: blockedBy（前置任务必须先完成）
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


TASK_STATUSES = ("pending", "in_progress", "completed", "failed")


@dataclass
class Task:
    id: str
    subject: str
    description: str = ""
    status: str = "pending"
    owner: str = ""
    blocked_by: list[str] = field(default_factory=list)
    output: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in TASK_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")

    def can_start(self, task_board: "TaskBoard") -> bool:
        """检查所有前置任务是否已完成"""
        for dep_id in self.blocked_by:
            dep = task_board.load_task(dep_id)
            if dep is None or dep.status != "completed":
                return False
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            id=d["id"],
            subject=d["subject"],
            description=d.get("description", ""),
            status=d.get("status", "pending"),
            owner=d.get("owner", ""),
            blocked_by=d.get("blocked_by", []),
            output=d.get("output", ""),
            metadata=d.get("metadata", {}),
        )


class TaskBoard:
    """文件持久化的任务看板"""

    def __init__(self, tasks_dir: str = ".tasks"):
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def create_task(self, task: Task) -> Task:
        """创建新任务"""
        path = self._task_path(task.id)
        if path.exists():
            raise ValueError(f"Task {task.id} already exists")
        path.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return task

    def load_task(self, task_id: str) -> Task | None:
        """加载单个任务"""
        path = self._task_path(task_id)
        if not path.exists():
            return None
        return Task.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_task(self, task: Task):
        """保存任务"""
        self._task_path(task.id).write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")

    def list_tasks(self) -> list[Task]:
        """列出所有任务"""
        tasks = []
        for f in sorted(self.tasks_dir.glob("*.json")):
            try:
                tasks.append(Task.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return tasks

    def get_unclaimed(self) -> list[Task]:
        """获取所有可认领的任务（pending + 无 owner + 依赖已满足）"""
        unclaimed = []
        for task in self.list_tasks():
            if task.status == "pending" and not task.owner and task.can_start(self):
                unclaimed.append(task)
        return unclaimed

    def claim_task(self, task_id: str, owner: str) -> str:
        """认领任务"""
        task = self.load_task(task_id)
        if task is None:
            return f"Error: Task {task_id} not found"
        if task.status != "pending":
            return f"Error: Task {task_id} is {task.status}, cannot claim"
        if task.owner:
            return f"Error: Task {task_id} already owned by {task.owner}"
        if not task.can_start(self):
            blocked = [b for b in task.blocked_by
                      if self.load_task(b) and self.load_task(b).status != "completed"]
            return f"Error: Task {task_id} blocked by: {blocked}"
        task.owner = owner
        task.status = "in_progress"
        self.save_task(task)
        return f"Claimed {task.id}: {task.subject}"

    def complete_task(self, task_id: str, output: str = "") -> str:
        """完成任务"""
        task = self.load_task(task_id)
        if task is None:
            return f"Error: Task {task_id} not found"
        task.status = "completed"
        task.output = output
        self.save_task(task)
        return f"Completed {task.id}: {task.subject}"

    def fail_task(self, task_id: str, reason: str = "") -> str:
        """任务失败"""
        task = self.load_task(task_id)
        if task is None:
            return f"Error: Task {task_id} not found"
        task.status = "failed"
        task.output = reason
        self.save_task(task)
        return f"Failed {task_id}: {reason}"

    def summary(self) -> str:
        """返回任务看板摘要"""
        tasks = self.list_tasks()
        if not tasks:
            return "No tasks on board."
        lines = ["## 任务看板"]
        for t in tasks:
            icon = {"pending": "○", "in_progress": "●", "completed": "✓", "failed": "✗"}[t.status]
            owner = f" ({t.owner})" if t.owner else ""
            deps = f" [依赖: {', '.join(t.blocked_by)}]" if t.blocked_by else ""
            lines.append(f"  {icon} {t.id}: {t.subject}{owner}{deps}")
        return "\n".join(lines)
