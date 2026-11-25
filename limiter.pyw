"""
League Limiter - caps how many League of Legends games you play per day.

* When the League client opens and you haven't picked a limit for today,
  it asks how many games you want to play.
* A small always-on-top counter shows how many games you have left while
  the client is open (hidden while you're in a match).
* A game counts when it actually starts (unique game ID from the client's
  local API), so reconnects and champ-select dodges don't count.
* When you're out of games, the client is closed - but NEVER during champ
  select or a match, so you never get a dodge or leaver penalty.

Standard library only. Run with pythonw.exe so no console window appears.
Right-click the counter to lower today's limit.
"""

import base64
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import socket
import ssl
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO = "--demo" in sys.argv
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), "LeagueLimiter")
if DEMO:
    DATA_DIR = os.path.join(DATA_DIR, "demo")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "state.json")
UI_FILE = os.path.join(DATA_DIR, "ui.json")
LOG_FILE = os.path.join(DATA_DIR, "limiter.log")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "reset_hour": 4,               # the "day" starts at 4 AM
    "default_games": 1,            # used if you close the prompt without choosing
    "max_games_choice": 10,
    "allow_raising_limit": False,  # once set, today's limit can only go down
    "count_custom_games": False,
    "count_practice_tool": False,
    "close_delay_seconds": 15,     # time to look at post-game stats before closing
    "league_dir": r"C:\Riot Games\League of Legends",
}

CLIENT_EXES = ("leagueclient.exe", "leagueclientux.exe", "leagueclientuxrender.exe")
GAME_EXE = "league of legends.exe"
# Phases where closing the client would cost you (dodge / leaver penalty).
PROTECTED_PHASES = {"ChampSelect", "GameStart", "InProgress", "Reconnect", "WaitingForStats"}
# Phases where you're trying to start another game - close right away when out.
QUEUE_PHASES = {"Lobby", "Matchmaking", "ReadyCheck"}
COUNT_PHASES = {"GameStart", "InProgress", "Reconnect"}


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


# --------------------------------------------------------------------------
# Windows process helpers (ctypes, no psutil needed)
# --------------------------------------------------------------------------
k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
k32.CloseHandle.argtypes = [wt.HANDLE]
INVALID_HANDLE = ctypes.c_void_p(-1).value


def list_procs():
    """[(pid, lowercase exe name)] for every running process."""
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == INVALID_HANDLE:
        return []
    out = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out.append((entry.th32ProcessID, entry.szExeFile.lower()))
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def exe_path(pid):
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        k32.CloseHandle(h)
    return None


def kill_pid(pid):
    h = k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if not h:
        return False
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)


# --------------------------------------------------------------------------
# League client local API (LCU)
# --------------------------------------------------------------------------
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE  # the client uses a self-signed cert on 127.0.0.1


def find_lcu_creds(procs, cfg):
    dirs = []
    for pid, name in procs:
        if name in ("leagueclient.exe", "leagueclientux.exe"):
            p = exe_path(pid)
            if p:
                dirs.append(os.path.dirname(p))
    dirs.append(cfg["league_dir"])
    for d in dirs:
        try:
            with open(os.path.join(d, "lockfile"), encoding="utf-8") as f:
                parts = f.read().strip().split(":")
            return parts[2], parts[3]  # port, password
        except (OSError, IndexError):
            continue
    return None


def lcu_get(creds, path):
    port, password = creds
    req = urllib.request.Request(f"https://127.0.0.1:{port}{path}")
    token = base64.b64encode(f"riot:{password}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=1.5) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:  # no gameflow session = idle in client
            return {"phase": "None"}
        return None
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Daily state
# --------------------------------------------------------------------------
def day_key(cfg):
    now = datetime.datetime.now() - datetime.timedelta(hours=cfg["reset_hour"])
    return now.date().isoformat()


class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.data = load_json(STATE_FILE, {})
        self._roll()

    def _roll(self):
        today = day_key(self.cfg)
        if self.data.get("day") != today:
            self.data = {"day": today, "limit": None, "games": []}
            self._save()

    def _save(self):
        save_json(STATE_FILE, self.data)

    def snapshot(self):
        with self.lock:
            self._roll()
            return dict(self.data, games=list(self.data["games"]))

    def set_limit(self, n):
        with self.lock:
            self._roll()
            self.data["limit"] = int(n)
            self._save()
            log(f"limit set to {n}")

    def add_game(self, game_id, desc):
        with self.lock:
            self._roll()
            if game_id in self.data["games"]:
                return False
            if self.data["limit"] is None:
                self.data["limit"] = self.cfg["default_games"]
            self.data["games"].append(game_id)
            self._save()
            log(f"counted game {game_id} ({desc}); {len(self.data['games'])}/{self.data['limit']}")
            return True


def counts_toward_limit(session, cfg):
    gd = session.get("gameData") or {}
    queue = gd.get("queue") or {}
    mode = (queue.get("gameMode") or "").upper()
    if mode == "PRACTICETOOL" and not cfg["count_practice_tool"]:
        return False
    if gd.get("isCustomGame") and mode != "PRACTICETOOL" and not cfg["count_custom_games"]:
        return False
    return True


# --------------------------------------------------------------------------
# Background watcher
# --------------------------------------------------------------------------
class Watcher(threading.Thread):
    def __init__(self, cfg, state):
        super().__init__(daemon=True)
        self.cfg, self.state = cfg, state
        self.status = {"client": False, "game": False, "phase": "None", "client_pids": []}

    def poll(self):
        if DEMO:
            procs = [(0, "leagueclientux.exe")]
            if os.path.exists(os.path.join(DATA_DIR, "demo_game")):
                procs.append((1, GAME_EXE))
            session = load_json(os.path.join(DATA_DIR, "demo_session.json"), {"phase": "None"})
        else:
            procs = list_procs()
            session = None
        client_pids = [pid for pid, n in procs if n in CLIENT_EXES]
        game = any(n == GAME_EXE for _, n in procs)
        if client_pids and not DEMO:
            creds = find_lcu_creds(procs, self.cfg)
            if creds:
                session = lcu_get(creds, "/lol-gameflow/v1/session")
        phase = (session or {}).get("phase") or ("Unknown" if client_pids else "None")

        if session and phase in COUNT_PHASES:
            gd = session.get("gameData") or {}
            gid = gd.get("gameId")
            if gid and counts_toward_limit(session, self.cfg):
                q = gd.get("queue") or {}
                self.state.add_game(gid, q.get("description") or q.get("gameMode") or "?")

        self.status = {"client": bool(client_pids), "game": game, "phase": phase,
                       "client_pids": client_pids}

    def run(self):
        while True:
            try:
                self.poll()
            except Exception as e:  # never die
                log(f"poll error: {e!r}")
            time.sleep(2)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
BG = "#10141c"
FG = "#e8e6e3"
GOLD = "#c8aa6e"
GREEN = "#4cc38a"
AMBER = "#e6a23c"
RED = "#e5484d"
FONT = ("Segoe UI", 10, "bold")


class App:
    def __init__(self):
        self.cfg = load_config()
        self.state = State(self.cfg)
        self.watcher = Watcher(self.cfg, self.state)
        self.root = tk.Tk()
        self.root.withdraw()
        self.dialog = None
        self.close_deadline = None
        self._build_overlay()
        self.watcher.start()
        self.root.after(500, self.tick)
        log("started" + (" (demo)" if DEMO else ""))

    # ---- overlay counter -------------------------------------------------
    def _build_overlay(self):
        ov = self.overlay = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.92)
        ov.configure(bg=GOLD)
        inner = tk.Frame(ov, bg=BG, padx=10, pady=4)
        inner.pack(padx=1, pady=1)
        self.icon_lbl = tk.Label(inner, text="\u2694", bg=BG, fg=GOLD, font=("Segoe UI Symbol", 11))
        self.icon_lbl.pack(side="left", padx=(0, 6))
        self.count_lbl = tk.Label(inner, text="", bg=BG, fg=FG, font=FONT)
        self.count_lbl.pack(side="left")
        self.sub_lbl = tk.Label(inner, text="", bg=BG, fg="#8a8f98", font=("Segoe UI", 9))
        self.sub_lbl.pack(side="left", padx=(6, 0))

        ui = load_json(UI_FILE, {})
        x = ui.get("x", ov.winfo_screenwidth() - 320)
        y = ui.get("y", 12)
        ov.geometry(f"+{x}+{y}")
        ov.withdraw()
        self.overlay_visible = False

        for w in (ov, inner, self.icon_lbl, self.count_lbl, self.sub_lbl):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Button-3>", self._menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Change today's limit\u2026", command=self.open_dialog)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.overlay.winfo_x(), e.y_root - self.overlay.winfo_y()

    def _drag_move(self, e):
        self.overlay.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _drag_end(self, _e):
        try:
            save_json(UI_FILE, {"x": self.overlay.winfo_x(), "y": self.overlay.winfo_y()})
        except OSError:
            pass

    def _menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def show_overlay(self, show):
        if show and not self.overlay_visible:
            self.overlay.deiconify()
            self.overlay.attributes("-topmost", True)
        elif not show and self.overlay_visible:
            self.overlay.withdraw()
        self.overlay_visible = show

    # ---- limit dialog ----------------------------------------------------
    def open_dialog(self):
        if self.dialog is not None:
            self.dialog.lift()
            return
        snap = self.state.snapshot()
        played = len(snap["games"])
        current = snap["limit"]
        lo = max(1, played)
        if current is None or self.cfg["allow_raising_limit"]:
            hi = self.cfg["max_games_choice"]
        else:
            hi = max(lo, current)
        start = current if current is not None else self.cfg["default_games"]
        start = min(max(start, lo), hi)

        d = self.dialog = tk.Toplevel(self.root)
        d.title("League Limiter")
        d.configure(bg=BG)
        d.resizable(False, False)
        d.attributes("-topmost", True)
        pad = {"padx": 18}
        first = current is None
        tk.Label(d, text="How many games today?" if first else "Change today's limit",
                 bg=BG, fg=GOLD, font=("Segoe UI", 13, "bold")).pack(pady=(16, 4), **pad)
        reset = f"{self.cfg['reset_hour']}:00 AM"
        note = (f"Locked until {reset} once set - you can only lower it."
                if not self.cfg["allow_raising_limit"] else f"Resets at {reset}.")
        if played:
            note = f"Played so far: {played}. " + note
        tk.Label(d, text=note, bg=BG, fg="#8a8f98", font=("Segoe UI", 9),
                 wraplength=260, justify="center").pack(pady=(0, 10), **pad)

        var = tk.IntVar(value=start)
        row = tk.Frame(d, bg=BG)
        row.pack(pady=4)

        def step(delta):
            var.set(min(max(var.get() + delta, lo), hi))
            num.config(text=str(var.get()))

        btn = {"bg": "#1e2430", "fg": FG, "activebackground": "#2a3242", "activeforeground": FG,
               "relief": "flat", "font": ("Segoe UI", 14, "bold"), "width": 3, "bd": 0}
        tk.Button(row, text="\u2212", command=lambda: step(-1), **btn).pack(side="left")
        num = tk.Label(row, text=str(start), bg=BG, fg=FG, font=("Segoe UI", 22, "bold"), width=3)
        num.pack(side="left", padx=8)
        tk.Button(row, text="+", command=lambda: step(1), **btn).pack(side="left")

        def confirm():
            self.state.set_limit(var.get())
            close()

        def close():
            if self.state.snapshot()["limit"] is None:
                self.state.set_limit(self.cfg["default_games"])
            d.destroy()
            self.dialog = None

        tk.Button(d, text="Set limit", command=confirm, bg=GOLD, fg=BG, activebackground="#d8bc84",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=4, bd=0
                  ).pack(pady=(12, 16))
        d.protocol("WM_DELETE_WINDOW", close)
        d.bind("<Return>", lambda _e: confirm())
        d.bind("<Up>", lambda _e: step(1))
        d.bind("<Down>", lambda _e: step(-1))
        d.update_idletasks()
        w, h = d.winfo_width(), d.winfo_height()
        d.geometry(f"+{(d.winfo_screenwidth() - w) // 2}+{(d.winfo_screenheight() - h) // 3}")
        d.focus_force()

    # ---- enforcement -----------------------------------------------------
    def close_client(self, pids):
        # Last-second safety check with a fresh process list (status can be ~2s old).
        procs = [(0, self._demo_game())] if DEMO else list_procs()
        if any(n == GAME_EXE for _, n in procs):
            log("skipped closing client: a game is running")
            return
        log(f"closing client (pids {pids})")
        if DEMO:
            return
        for pid in pids:
            kill_pid(pid)

    @staticmethod
    def _demo_game():
        return GAME_EXE if os.path.exists(os.path.join(DATA_DIR, "demo_game")) else ""

    def tick(self):
        try:
            self._tick()
        except Exception as e:
            log(f"tick error: {e!r}")
        self.root.after(500, self.tick)

    def _tick(self):
        st = self.watcher.status
        snap = self.state.snapshot()
        limit, played = snap["limit"], len(snap["games"])

        if not st["client"]:
            self.close_deadline = None
            self.show_overlay(False)
            return

        if limit is None and self.dialog is None:
            self.open_dialog()

        # hide the counter during a match (fullscreen game)
        self.show_overlay(not st["game"])

        if limit is None:
            self.count_lbl.config(text="Set today's limit", fg=FG)
            self.sub_lbl.config(text="")
            return

        left = max(0, limit - played)
        phase = st["phase"]
        color = GREEN if left > 1 else AMBER if left == 1 else RED
        self.count_lbl.config(text=f"{left} game{'s' if left != 1 else ''} left", fg=color)
        self.sub_lbl.config(text=f"{played}/{limit} played")

        # Never close while a match is running - checked both by the client's
        # reported phase AND by the game process itself, so it holds even if
        # the client API can't be reached.
        if left > 0 or phase in PROTECTED_PHASES or st["game"]:
            self.close_deadline = None
            return

        now = time.monotonic()
        if phase in QUEUE_PHASES:
            # Trying to queue with no games left: close almost immediately.
            if self.close_deadline is None or self.close_deadline - now > 3:
                self.close_deadline = now + 3
        elif self.close_deadline is None:
            self.close_deadline = now + self.cfg["close_delay_seconds"]

        remaining = int(self.close_deadline - now + 0.999)
        self.sub_lbl.config(text=f"done for today \u2013 closing in {max(0, remaining)}s")
        if now >= self.close_deadline:
            self.close_client(st["client_pids"])
            self.close_deadline = None

    def run(self):
        self.root.mainloop()


def single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47811 if not DEMO else 47812))
    except OSError:
        return None
    return s


if __name__ == "__main__":
    _lock = single_instance()
    if _lock is None:
        sys.exit(0)
    App().run()
