"""Modelo de dados da lista de tarefas."""
import time
from datetime import datetime

PRIORITIES = ("low", "medium", "high")
PRIORITY_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


def pad(n):
    return str(n).zfill(2)


def local_key(dt):
    return f"{dt.year}-{pad(dt.month)}-{pad(dt.day)}"


def today_key():
    return local_key(datetime.now())


def now_time():
    now = datetime.now()
    return f"{pad(now.hour)}:{pad(now.minute)}"


def format_date(key):
    if not key:
        return ""
    try:
        y, m, d = key.split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return key


def parse_date_br(s):
    """Converte DD/MM/AAAA (ou DD/MM/AA) em YYYY-MM-DD. Retorna '' se inválido."""
    s = (s or "").strip()
    if not s:
        return ""
    parts = s.split("/")
    if len(parts) != 3:
        return ""
    d, m, y = parts
    if len(y) == 2:
        y = "20" + y
    if not (d.isdigit() and m.isdigit() and y.isdigit()):
        return ""
    dd, mm, yy = d.zfill(2), m.zfill(2), y
    if not (1 <= int(dd) <= 31 and 1 <= int(mm) <= 12 and 1900 <= int(yy) <= 2100):
        return ""
    return f"{yy}-{mm}-{dd}"


def new_id():
    return int(time.time() * 1000)


def make_todo(text, due_date, due_time, priority, category):
    return {
        "id": new_id(),
        "text": text,
        "completed": False,
        "dueDate": due_date or today_key(),
        "dueTime": due_time,
        "priority": priority if priority in PRIORITIES else "medium",
        "category": category.strip() if category and category.strip() else "General",
        "reminderFired": False,
    }


def normalize_todo(task, index):
    if not isinstance(task, dict) or not isinstance(task.get("text"), str) or not task["text"].strip():
        raise ValueError("Tarefa inválida")
    return {
        "id": int(task.get("id") or new_id() + index),
        "text": task["text"].strip(),
        "completed": bool(task.get("completed")),
        "dueDate": task.get("dueDate") if isinstance(task.get("dueDate"), str) else "",
        "dueTime": task.get("dueTime") if isinstance(task.get("dueTime"), str) else "",
        "priority": task.get("priority") if task.get("priority") in PRIORITIES else "medium",
        "category": task.get("category").strip() if isinstance(task.get("category"), str) and task.get("category").strip() else "General",
        "reminderFired": bool(task.get("reminderFired")),
    }


def normalize_todos(list_):
    if not isinstance(list_, list):
        raise ValueError("Formato inválido")
    return [normalize_todo(t, i) for i, t in enumerate(list_)]


def is_overdue(todo):
    return (not todo["completed"]) and bool(todo["dueDate"]) and todo["dueDate"] < today_key()


def sort_key(todo):
    pr = {"high": 0, "medium": 1, "low": 2}
    return (
        int(is_overdue(todo)),
        int(todo["completed"]),
        todo.get("dueDate") or "9999",
        pr.get(todo.get("priority"), 1),
    )
