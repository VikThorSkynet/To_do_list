"""Persistência em JSON em %APPDATA% e backup exportar/importar."""
import json
import os
from datetime import datetime

from models import normalize_todos, today_key

APP_NAME = "TodoList"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
TODOS_FILE = os.path.join(DATA_DIR, "todos.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
BACKUP_KEY = os.path.join(DATA_DIR, "last_backup.txt")
BACKUP_SNAPSHOT = os.path.join(DATA_DIR, "last_backup_snapshot.json")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_todos():
    _ensure_dir()
    if not os.path.exists(TODOS_FILE):
        return []
    try:
        with open(TODOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_todos(data)
    except (ValueError, json.JSONDecodeError, OSError):
        return []


def save_todos(todos):
    _ensure_dir()
    with open(TODOS_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def load_settings():
    _ensure_dir()
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, json.JSONDecodeError, OSError):
        return {}


def save_settings(settings):
    _ensure_dir()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def has_backup_changes(todos):
    if not todos:
        return False
    try:
        with open(BACKUP_SNAPSHOT, "r", encoding="utf-8") as f:
            return f.read() != json.dumps(todos, ensure_ascii=False)
    except OSError:
        return True


def last_backup_text():
    try:
        with open(BACKUP_KEY, "r", encoding="utf-8") as f:
            value = f.read().strip()
        if not value:
            return "No backup exported"
        dt = datetime.fromisoformat(value)
        return "Last backup: " + dt.strftime("%d/%m/%Y %H:%M")
    except (OSError, ValueError):
        return "No backup exported"


def record_backup(todos):
    _ensure_dir()
    exported_at = datetime.now().isoformat()
    with open(BACKUP_KEY, "w", encoding="utf-8") as f:
        f.write(exported_at)
    with open(BACKUP_SNAPSHOT, "w", encoding="utf-8") as f:
        f.write(json.dumps(todos, ensure_ascii=False))
    return exported_at


def build_backup_payload(todos):
    return {
        "application": "Lista de Tarefas",
        "version": 1,
        "exportedAt": datetime.now().isoformat(),
        "todos": todos,
    }


def parse_backup(text):
    data = json.loads(text)
    if isinstance(data, list):
        return data, datetime.now().isoformat()
    if isinstance(data, dict) and "todos" in data:
        return data["todos"], data.get("exportedAt") or datetime.now().isoformat()
    raise ValueError("Formato inválido")
