"""Ponto de entrada do executável de Lista de Tarefas."""
import ctypes

import customtkinter as ctk

from notifications import stop_alarm
from reminders import ReminderScheduler
from storage import load_todos
from ui import TodoApp


def main():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    mutex = kernel.CreateMutexW(None, False, "Local\\ListaDeTarefas")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    already_running = ctypes.get_last_error() == 183
    try:
        if already_running:
            return
        todos = load_todos()
        ctk.set_appearance_mode("dark")
        root = ctk.CTk()
        TodoApp(root, todos, ReminderScheduler(todos))
        root.mainloop()
    finally:
        if not already_running:
            stop_alarm()
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
