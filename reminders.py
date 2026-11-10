"""Lembretes verificados pelo relógio da interface."""
from threading import Thread

from models import local_key
from notifications import notify_os, play_alarm
from storage import save_todos


class ReminderScheduler:
    def __init__(self, todos):
        self.todos = todos
        self.last_minute = None

    def invalidate(self):
        self.last_minute = None

    def check(self, now, show_reminder):
        minute = now.replace(second=0, microsecond=0)
        if minute == self.last_minute:
            return
        date = local_key(now)
        time = now.strftime("%H:%M")
        due = [
            task for task in self.todos
            if not task["completed"] and not task["reminderFired"]
            and task["dueDate"] == date and task["dueTime"] == time
        ]
        if due:
            for task in due:
                task["reminderFired"] = True
            try:
                save_todos(self.todos)
            except OSError:
                for task in due:
                    task["reminderFired"] = False
                raise
        self.last_minute = minute
        if due:
            Thread(target=self._notify, args=(due, time), daemon=True).start()
            play_alarm()
            for task in due:
                show_reminder(task)

    @staticmethod
    def _notify(tasks, time):
        for task in tasks:
            notify_os("🔔 Task reminder", f"{task['text']} · Due at {time}")
