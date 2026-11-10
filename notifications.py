"""Notificações do sistema operacional: toast nativo, som e popup de alarme."""
import threading
import winsound

try:
    from winotify import Notification, audio
    _HAS_WINOTIFY = True
except Exception:
    _HAS_WINOTIFY = False

_APP_ID = "Task List"
_sound_lock = threading.Lock()
_sound_playing = False


def _toast(title, body):
    if not _HAS_WINOTIFY:
        return False
    try:
        toast = Notification(app_id=_APP_ID, title=title, msg=body, duration="long")
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return True
    except Exception:
        return False


def notify_os(title, body):
    """Dispara toast nativo do Windows. Retorna True se funcionou."""
    return _toast(title, body)


def play_alarm():
    """Toca som estilo despertador em loop (winsound)."""
    global _sound_playing
    with _sound_lock:
        if _sound_playing:
            return
        _sound_playing = True
    try:
        winsound.PlaySound(
            winsound.SND_ALIAS + winsound.SND_ASYNC + winsound.SND_LOOP,
            winsound.SND_ALIAS,
        )
    except Exception:
        try:
            winsound.Beep(880, 400)
        except Exception:
            pass


def stop_alarm():
    global _sound_playing
    with _sound_lock:
        _sound_playing = False
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
