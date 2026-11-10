"""Interface CustomTkinter da Lista de Tarefas."""
import calendar
import ctypes
from ctypes import wintypes
import json
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from models import (
    PRIORITY_LABELS,
    format_date,
    is_overdue,
    make_todo,
    normalize_todos,
    parse_date_br,
    sort_key,
    today_key,
)
from notifications import stop_alarm
from storage import (
    build_backup_payload,
    has_backup_changes,
    last_backup_text,
    parse_backup,
    record_backup,
    save_todos,
)

FILTERS = {"all": "Pending", "today": "Today", "upcoming": "Upcoming", "completed": "Completed"}
EMPTY_MSG = {
    "all": "No pending tasks",
    "today": "No tasks due today",
    "upcoming": "No upcoming tasks",
    "completed": "No completed tasks",
}


C = {
    "bg": "#091221",
    "panel": "#101F35",
    "field": "#182E4E",
    "hover": "#23446F",
    "line": "#2A4870",
    "ink": "#F1F7FF",
    "muted": "#B9CAE1",
    "dim": "#93ACC9",
    "accent": "#0585E6",
    "accent_hover": "#35A2F5",
    "dark": "#050B15",
    "royal": "#0236A5",
    "calendar_task": "#FE0369",
    "calendar_task_hover": "#FF4B95",
    "high": "#FF7176",
    "medium": "#FFD45F",
    "low": "#68E3A1",
    "clock": "#79DBFF",
    "done": "#142E4B",
    "late": "#321832",
}
PRIORITY_COLOR = {"high": C["high"], "medium": C["medium"], "low": C["low"]}
PRIORITY_KEYS = {label: key for key, label in PRIORITY_LABELS.items()}
MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
FONT = "Segoe UI"


class TodoApp:
    def __init__(self, root, todos, scheduler):
        self.root = root
        self.todos = todos
        self.editing = None
        self.scheduler = scheduler
        self.filter = "all"
        self.view = datetime.now()
        self.selected = today_key()

        root.title("Task List")
        root.configure(fg_color=C["bg"])
        area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
            width = min(1240, area.right - area.left - 24)
            height = min(860, area.bottom - area.top - 48)
            root.geometry(f"{width}x{height}+{area.left + 8}+{area.top + 8}")
        else:
            root.geometry("1120x660")
        root.minsize(800, 420)
        self._build()
        self._timer = None
        self._clock_date = None
        root.bind("<Map>", self._on_visibility, add="+")
        root.bind("<Unmap>", self._on_visibility, add="+")
        self._tick()
        self.render()
        self.render_calendar()
        self.render_backup_status()

    def _label(self, parent, text, size=13, *, color=None, bold=False, **options):
        return ctk.CTkLabel(parent, text=text, text_color=color or C["ink"],
                            font=(FONT, size, "bold" if bold else "normal"), **options)

    def _button(self, parent, text, command, *, accent=False, width=0, height=32, **options):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                             corner_radius=9, font=(FONT, 13, "bold"),
                             fg_color=C["accent"] if accent else C["field"],
                             text_color=C["dark"] if accent else C["ink"],
                             hover_color=C["accent_hover"] if accent else C["hover"], **options)

    def _card(self, parent, **options):
        return ctk.CTkFrame(parent, fg_color=C["panel"], corner_radius=18,
                            border_width=1, border_color=C["line"], **options)

    def _scroll_panel(self, parent):
        # O canvas limita o conteúdo à altura disponível, inclusive em janelas pequenas.
        shell = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        canvas = tk.Canvas(shell, bg=C["bg"], highlightthickness=0, width=1, height=1)
        scrollbar = ttk.Scrollbar(shell, command=canvas.yview, style="Tasks.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(3, 0))
        canvas.pack(side="left", fill="both", expand=True)
        content = ctk.CTkFrame(canvas, corner_radius=0, fg_color=C["bg"])
        window = canvas.create_window(0, 0, window=content, anchor="nw")
        def sync_scroll_region(event):
            width, height = canvas.winfo_width(), canvas.winfo_height()
            if event.widget is canvas:
                canvas.itemconfigure(window, width=width)
            content_height = content.winfo_height()
            # Uma região menor que a janela permite deslocamento para coordenadas negativas.
            canvas.configure(scrollregion=(0, 0, width, max(height, content_height)))
            if content_height <= height:
                canvas.yview_moveto(0)

        tk.Misc.bind(content, "<Configure>", sync_scroll_region, add="+")
        canvas.bind("<Configure>", sync_scroll_region)
        self.scroll_panels[shell] = canvas
        return shell, canvas, content

    def _scroll_at_pointer(self, event):
        if not event.delta:
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            canvas = self.scroll_panels.get(widget)
            if canvas is not None:
                top, bottom = canvas.yview()
                if (event.delta > 0 and top > 0) or (event.delta < 0 and bottom < 1):
                    canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
                return "break"
            widget = widget.master

    def _build(self):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)
        body.grid_columnconfigure(0, weight=3, minsize=400)
        body.grid_columnconfigure(1, weight=1, minsize=352)
        body.grid_rowconfigure(0, weight=1)
        self.scroll_panels = {}
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Tasks.Vertical.TScrollbar", background=C["hover"], troughcolor=C["bg"],
                        bordercolor=C["bg"], lightcolor=C["hover"], darkcolor=C["hover"],
                        arrowcolor=C["muted"], arrowsize=12)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_form(left)
        self._build_filters(left)
        task_panel, self.task_canvas, self.list_frame = self._scroll_panel(left)
        task_panel.pack(fill="both", expand=True)
        self.task_canvas.bind("<Configure>", self._wrap_tasks, add="+")

        sidebar, self.sidebar_canvas, right = self._scroll_panel(body)
        sidebar.grid(row=0, column=1, sticky="nsew")
        self._build_today_card(right)
        self._build_calendar(right)
        self._build_stats(right)
        self._build_backup(right)
        self.root.bind("<MouseWheel>", self._scroll_at_pointer, add="+")

    def _build_form(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        self._label(inner, "TASK LIST", 11, color=C["accent"], bold=True).pack(anchor="w")
        self.form_title = self._label(inner, "New task", 26, bold=True)
        self.form_title.pack(anchor="w", pady=(0, 8))
        self.text_var = tk.StringVar()
        self.text_entry = self._entry(inner, self.text_var)
        self.text_entry.pack(fill="x", pady=(0, 8))

        fields = ctk.CTkFrame(inner, fg_color="transparent")
        fields.pack(fill="x")
        self.date_var = tk.StringVar(value=format_date(today_key()))
        self.time_var = tk.StringVar()
        self.prio_var = tk.StringVar(value=PRIORITY_LABELS["medium"])
        self.cat_var = tk.StringVar()
        for col, (label, var) in enumerate((
            ("Date (DD/MM/YYYY)", self.date_var),
            ("Time (HH:MM)", self.time_var),
            ("Priority", self.prio_var),
            ("Category", self.cat_var),
        )):
            fields.grid_columnconfigure(col, weight=1, uniform="form")
            cell = ctk.CTkFrame(fields, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew", padx=(0, 6) if col < 3 else 0)
            self._label(cell, label, 12, color=C["muted"], bold=True).pack(anchor="w")
            if var is self.prio_var:
                field = ctk.CTkOptionMenu(cell, variable=var, values=list(PRIORITY_LABELS.values()),
                                          fg_color=C["field"], button_color=C["hover"],
                                          button_hover_color=C["line"], text_color=C["ink"],
                                          dropdown_fg_color=C["panel"], dropdown_text_color=C["ink"],
                                          dropdown_hover_color=C["hover"], width=1, height=33)
            else:
                field = self._entry(cell, var)
            field.pack(fill="x")
            if var is self.time_var:
                self.time_entry = field
                field.bind("<KeyRelease>", self._format_time)

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        self.submit_button = self._button(actions, "+  Add task", self.add_todo, accent=True, height=38)
        self.submit_button.pack(side="left", fill="x", expand=True)
        self.cancel_edit_button = self._button(actions, "Cancel", self._reset_form, width=92, height=38)

    def _entry(self, parent, var):
        return ctk.CTkEntry(parent, textvariable=var, width=1, height=33,
                            fg_color=C["field"], border_color=C["line"], border_width=1,
                            text_color=C["ink"], corner_radius=8)

    def _format_time(self, event=None):
        digits = "".join(ch for ch in self.time_var.get() if ch.isdigit())[:4]
        if len(digits) > 2:
            digits = digits[:2] + ":" + digits[2:]
        self.time_var.set(digits)
        self.time_entry.icursor(tk.END)

    def _build_filters(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(0, 5), padx=(2, 16))
        self._label(head, "Tasks", 21, bold=True).pack(side="left")
        self.task_count = self._label(head, "", 12, color=C["muted"])
        self.task_count.pack(side="right")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8), padx=(0, 16))
        self.filter_btns = {}
        for col, (key, label) in enumerate(FILTERS.items()):
            row.grid_columnconfigure(col, weight=1, uniform="filters")
            button = self._button(row, label, lambda k=key: self.set_filter(k), accent=key == self.filter)
            button.grid(row=0, column=col, sticky="ew", padx=(0, 5) if col < 3 else 0)
            self.filter_btns[key] = button

    def _build_today_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["royal"], corner_radius=18)
        card.pack(fill="x", pady=(0, 9))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=11)
        inner.grid_columnconfigure(0, weight=1)
        self.today_weekday_lbl = self._label(inner, "", 20, color=C["ink"], bold=True)
        self.today_weekday_lbl.grid(row=0, column=0, sticky="w")
        self.today_date_lbl = self._label(inner, "", 17, color=C["ink"], bold=True)
        self.today_date_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))
        clock = ctk.CTkFrame(inner, fg_color=C["dark"], corner_radius=10)
        clock.grid(row=0, column=1, sticky="e", padx=(6, 0))
        self.today_time_lbl = ctk.CTkLabel(clock, text="", text_color=C["clock"],
                                           font=("Consolas", 27, "bold"), height=36)
        self.today_time_lbl.pack(padx=9, pady=2)
        jump = self._button(inner, "Go to today", self._jump_to_today, height=26, width=88)
        jump.grid(row=1, column=1, sticky="e", padx=(6, 0), pady=(4, 0))

    def _build_calendar(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 9))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=11, pady=(10, 3))
        self._button(head, "‹", self.prev_month, width=32).pack(side="left")
        self._button(head, "›", self.next_month, width=32).pack(side="right")
        self.month_lbl = self._label(head, "", 18, bold=True)
        self.month_lbl.pack(expand=True)
        self.cal_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.cal_frame.pack(fill="x", padx=10, pady=(0, 5))
        for col, name in enumerate(("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")):
            self.cal_frame.grid_columnconfigure(col, weight=1, uniform="days")
            self._label(self.cal_frame, name, 11, color=C["muted"], bold=True).grid(row=0, column=col)
        self.calendar_buttons = []
        for index in range(42):
            row, col = divmod(index, 7)
            button = self._button(self.cal_frame, "", None, height=37)
            button.grid(row=row + 1, column=col, sticky="ew", padx=2, pady=2)
            self.calendar_buttons.append(button)
        legend = ctk.CTkFrame(card, fg_color="transparent")
        legend.pack(anchor="w", padx=13, pady=(0, 5))
        ctk.CTkFrame(legend, width=13, height=13, fg_color=C["calendar_task"],
                     corner_radius=3).pack(side="left", padx=(0, 6))
        self._label(legend, "Day with pending tasks", 11,
                    color=C["muted"]).pack(side="left")

    def _build_stats(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 9))
        self._label(card, "Progress", 16, bold=True).pack(anchor="w", padx=13, pady=(6, 0))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=9, pady=(0, 8))
        self.stat_labels = {}
        for col, (key, label, color) in enumerate((
            ("total", "Total", C["ink"]), ("pending", "Pending", C["medium"]),
            ("completed", "Completed", C["low"]), ("overdue", "Overdue", C["high"]),
        )):
            row.grid_columnconfigure(col, weight=1, uniform="stats")
            tile = ctk.CTkFrame(row, fg_color=C["field"], corner_radius=9)
            tile.grid(row=0, column=col, sticky="ew", padx=2)
            val = self._label(tile, "0", 20, color=color, bold=True)
            val.pack(pady=(3, 0))
            self._label(tile, label, 11, color=C["muted"], height=18).pack(pady=(0, 4))
            self.stat_labels[key] = val

    def _build_backup(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 2))
        self._label(card, "Local backup", 16, bold=True).pack(anchor="w", padx=13, pady=(6, 0))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(2, 0))
        self._button(row, "↓  Export", self.export_backup).pack(side="left", expand=True, fill="x", padx=(0, 3))
        self._button(row, "↑  Import", self.import_backup).pack(side="right", expand=True, fill="x", padx=(3, 0))
        self.backup_lbl = self._label(card, "", 11, color=C["muted"], wraplength=255, justify="left")
        self.backup_lbl.pack(anchor="w", padx=13, pady=(1, 5))

    # ---------- dados ----------
    def _save(self):
        save_todos(self.todos)
        self.render_backup_status()
        self.scheduler.invalidate()
        self._tick()

    def add_todo(self):
        text = self.text_var.get().strip()
        if not text:
            messagebox.showwarning("Task required", "Enter a task description.")
            return
        due_date = parse_date_br(self.date_var.get()) or today_key()
        values = make_todo(text, due_date, self.time_var.get(),
                           PRIORITY_KEYS.get(self.prio_var.get(), self.prio_var.get()),
                           self.cat_var.get())
        if self.editing is None:
            self.todos.append(values)
        else:
            task = self.editing
            if (task["dueDate"], task["dueTime"]) != (values["dueDate"], values["dueTime"]):
                task["reminderFired"] = False
            for field in ("text", "dueDate", "dueTime", "priority", "category"):
                task[field] = values[field]
        self._save()
        self._reset_form()
        self.render()

    def edit_todo(self, task):
        self.editing = task
        self.form_title.configure(text="Edit task")
        self.submit_button.configure(text="Save changes")
        self.cancel_edit_button.pack(side="right", padx=(8, 0))
        self.text_var.set(task["text"])
        self.date_var.set(format_date(task["dueDate"]))
        self.time_var.set(task["dueTime"])
        self.prio_var.set(PRIORITY_LABELS[task["priority"]])
        self.cat_var.set(task["category"])
        self.text_entry.focus_set()

    def _reset_form(self):
        if self.editing is not None:
            self.prio_var.set(PRIORITY_LABELS["medium"])
        self.editing = None
        self.form_title.configure(text="New task")
        self.submit_button.configure(text="+  Add task")
        self.cancel_edit_button.pack_forget()
        self.text_var.set("")
        self.cat_var.set("")
        self.date_var.set(format_date(today_key()))
        self.time_var.set("")
        self.selected = today_key()
        self.render_calendar()

    def toggle_todo(self, todo):
        todo["completed"] = not todo["completed"]
        self._save()
        # adia o re-render para o clique do checkbox concluir sem destruir o widget
        self.root.after(0, self.render)
        self.root.after(0, self.render_calendar)

    def delete_todo(self, todo):
        if self.editing is todo:
            self._reset_form()
        self.todos[:] = [t for t in self.todos if t["id"] != todo["id"]]
        self._save()
        self.render()
        self.render_calendar()

    def set_filter(self, key):
        self.filter = key
        for k, b in self.filter_btns.items():
            active = k == key
            b.configure(fg_color=C["accent"] if active else C["field"],
                        text_color=C["dark"] if active else C["ink"],
                        hover_color=C["accent_hover"] if active else C["hover"])
        self.render()
        self.task_canvas.yview_moveto(0)

    # ---------- render ----------
    def _visible(self):
        lst = [t for t in self.todos if not t["completed"]]
        if self.filter == "today":
            lst = [t for t in lst if t["dueDate"] == today_key()]
        elif self.filter == "upcoming":
            lst = [t for t in lst if t["dueDate"] > today_key()]
        elif self.filter == "completed":
            lst = [t for t in self.todos if t["completed"]]
        return sorted(lst, key=sort_key)

    def _wrap_tasks(self, event=None):
        width = max(80, self.task_canvas.winfo_width() - 190)
        for title, details in self.task_labels:
            title.configure(wraplength=width)
            details.configure(wraplength=max(60, width - 82))

    def render(self):
        self.task_labels = []
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        tasks = self._visible()
        count = len(tasks)
        self.task_count.configure(text=f"{count} task" if count == 1 else f"{count} tasks")
        if not tasks:
            card = self._card(self.list_frame)
            card.pack(fill="x")
            self._label(card, EMPTY_MSG[self.filter], 15, color=C["muted"], bold=True).pack(pady=22)
        for task in tasks:
            self._render_todo(task)
        self._wrap_tasks()
        self.render_stats()

    def _render_todo(self, task):
        done = task["completed"]
        overdue = is_overdue(task)
        bg = C["done"] if done else C["late"] if overdue else C["panel"]
        priority = PRIORITY_COLOR[task["priority"]]
        row = ctk.CTkFrame(self.list_frame, fg_color=bg, corner_radius=13,
                           border_width=1, border_color=C["line"])
        row.pack(fill="x", pady=(0, 6))
        row.grid_columnconfigure(1, weight=1)
        checkbox = ctk.CTkCheckBox(row, text="", width=22, checkbox_width=21, checkbox_height=21,
                                   variable=tk.BooleanVar(value=done), fg_color=C["accent"],
                                   hover_color=C["accent_hover"], checkmark_color=C["dark"],
                                   border_color=C["dim"], command=lambda: self.toggle_todo(task))
        checkbox.grid(row=0, column=0, rowspan=2, padx=(11, 9))
        title = self._label(row, task["text"], 15, color=C["muted"] if done else C["ink"],
                            bold=True, anchor="w", justify="left")
        if done:
            title.configure(font=ctk.CTkFont(family=FONT, size=15, overstrike=True))
        title.grid(row=0, column=1, sticky="ew", pady=(6, 0))
        title.bind("<Button-1>", lambda event: self.toggle_todo(task))
        meta = [task["category"] or "General"]
        if task["dueDate"]:
            due = format_date(task["dueDate"])
            if task["dueTime"]:
                due += f" at {task['dueTime']}"
            meta.insert(0, due)
        if overdue:
            meta.insert(0, "Overdue")
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=1, column=1, sticky="ew", pady=(1, 8))
        badge = self._label(info, PRIORITY_LABELS[task["priority"]].upper(), 11,
                            color=C["dark"], bold=True, fg_color=priority,
                            corner_radius=6, width=68, height=23)
        badge.pack(side="left", padx=(0, 8))
        details = self._label(info, "  ·  ".join(meta), 11, color=C["muted"], height=18,
                              anchor="w", justify="left")
        details.pack(side="left", fill="x", expand=True)
        self._button(row, "Edit", lambda: self.edit_todo(task), width=58).grid(row=0, column=2, rowspan=2, padx=(8, 4))
        self._button(row, "Delete", lambda: self.delete_todo(task), width=59).grid(row=0, column=3, rowspan=2, padx=(0, 9))

        self.task_labels.append((title, details))

    def render_stats(self):
        total = len(self.todos)
        completed = sum(1 for task in self.todos if task["completed"])
        overdue = sum(1 for task in self.todos if is_overdue(task))
        for key, count in (("total", total), ("completed", completed),
                           ("pending", total - completed), ("overdue", overdue)):
            self.stat_labels[key].configure(text=str(count))

    def render_calendar(self):
        self.month_lbl.configure(text=f"{MONTHS[self.view.month - 1]} {self.view.year}")
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.view.year, self.view.month)
        dates = [day for week in weeks for day in week]
        task_dates = {task["dueDate"] for task in self.todos if not task["completed"]}
        today = today_key()
        for index, button in enumerate(self.calendar_buttons):
            if index >= len(dates):
                button.grid_remove()
                continue
            day = dates[index]
            key = day.isoformat()
            selected = key == self.selected
            active_month = day.month == self.view.month
            fg = C["ink"] if active_month else C["dim"]
            if active_month and index % 7 in (0, 6):
                fg = C["high"]
            has_tasks = key in task_dates
            if has_tasks:
                bg, fg, hover = C["calendar_task"], C["dark"], C["calendar_task_hover"]
            elif selected:
                bg, fg, hover = C["accent"], C["dark"], C["accent_hover"]
            else:
                bg = C["done"] if key == today else C["field"]
                hover = C["hover"]
            button.configure(text=str(day.day), fg_color=bg, text_color=fg,
                             hover_color=hover, border_width=3 if selected and has_tasks else 0,
                             border_color=C["dark"],
                             command=lambda date=key: self.select_date(date))
            button.grid()

    def select_date(self, key):
        self.selected = key
        self.date_var.set(format_date(key))
        self.render_calendar()

    def prev_month(self):
        self.view = self.view.replace(day=1)
        self.view = self.view.replace(month=self.view.month - 1) if self.view.month > 1 else self.view.replace(year=self.view.year - 1, month=12)
        self.render_calendar()

    def next_month(self):
        self.view = self.view.replace(day=1)
        self.view = self.view.replace(month=self.view.month + 1) if self.view.month < 12 else self.view.replace(year=self.view.year + 1, month=1)
        self.render_calendar()

    # ---------- backup ----------
    def render_backup_status(self):
        text = last_backup_text()
        if has_backup_changes(self.todos):
            text += " · unsaved to backup"
        self.backup_lbl.configure(text=text)

    def export_backup(self):
        path = filedialog.asksaveasfilename(
            title="Export backup", defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=f"task-backup-{today_key()}.json")
        if not path:
            return
        payload = build_backup_payload(self.todos)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        record_backup(self.todos)
        self.render_backup_status()
        messagebox.showinfo("Backup saved", f"Exported {len(self.todos)} task(s).")

    def import_backup(self):
        path = filedialog.askopenfilename(title="Import backup", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data, _ = parse_backup(f.read())
            imported = normalize_todos(data)
        except Exception:
            messagebox.showerror("Invalid file", "Could not import this JSON file.")
            return
        if not messagebox.askyesno("Import backup", f"Replace your current tasks with {len(imported)} task(s) from this backup?"):
            return
        if self.editing is not None:
            self._reset_form()
        self.todos[:] = imported
        self._save()
        self.render()
        self.render_calendar()
        messagebox.showinfo("Backup restored", f"Restored {len(imported)} task(s).")

    # ---------- relógio e eventos ----------
    def _on_visibility(self, event):
        if event.widget is self.root:
            self._tick()

    def _tick(self):
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None
        now = datetime.now()
        visible = self.root.winfo_viewable()
        if visible:
            if self._clock_date != now.date():
                self._clock_date = now.date()
                weekday = WEEKDAYS[now.weekday()]
                date_text = f"{MONTHS[now.month - 1]} {now.day}, {now.year}"
                self.today_weekday_lbl.configure(text=weekday)
                self.today_date_lbl.configure(text=date_text)
            time_text = now.strftime("%H:%M:%S")
            self.today_time_lbl.configure(text=time_text)

        interval = 1000 if visible else 60000
        delay = interval - (now.second * 1000 + now.microsecond // 1000) % interval
        self._timer = self.root.after(delay, self._tick)
        self.scheduler.check(now, self.show_reminder)

    def _jump_to_today(self):
        self.view = datetime.now().replace(day=1)
        self.selected = today_key()
        self.date_var.set(format_date(self.selected))
        self.render_calendar()

    def show_reminder(self, task):
        win = ctk.CTkToplevel(self.root, fg_color=C["bg"])
        win.title("Task reminder")
        win.resizable(False, False)
        x = max(0, self.root.winfo_screenwidth() - 440)
        win.geometry(f"400x220+{x}+60")
        win.attributes("-topmost", True)

        def close():
            stop_alarm()
            win.destroy()

        card = self._card(win)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        self._label(card, "REMINDER", 11, color=C["accent"], bold=True).pack(anchor="w", padx=14, pady=(10, 0))
        self._button(card, "Close", close, accent=True, width=100).pack(side="bottom", anchor="e", padx=14, pady=10)
        body = task["text"] + (f" · {task['dueTime']}" if task["dueTime"] else "")
        self._label(card, body, 17, bold=True, wraplength=315, justify="left").pack(anchor="w", padx=14)
        win.protocol("WM_DELETE_WINDOW", close)
        win.lift()
        win.focus_force()
