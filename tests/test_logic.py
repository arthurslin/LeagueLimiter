"""Unit tests for League Limiter's counting and state logic (no League or UI needed)."""
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Keep test data out of the real %LOCALAPPDATA%\LeagueLimiter.
_TMP = tempfile.mkdtemp(prefix="leaguelimiter-test-")
os.environ["LOCALAPPDATA"] = _TMP
if "--demo" not in sys.argv:
    sys.argv.append("--demo")

_spec = importlib.util.spec_from_file_location("limiter", os.path.join(ROOT, "limiter.pyw"))
lim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lim)


def session(game_id, mode="CLASSIC", custom=False, phase="InProgress"):
    return {"phase": phase, "gameData": {"gameId": game_id, "isCustomGame": custom,
                                         "queue": {"gameMode": mode, "description": "test"}}}


class ConfigTests(unittest.TestCase):
    def test_shipped_config_matches_defaults(self):
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            shipped = json.load(f)
        self.assertEqual(set(shipped), set(lim.DEFAULT_CONFIG))
        self.assertEqual(shipped, lim.DEFAULT_CONFIG)

    def test_data_dir_is_isolated(self):
        self.assertTrue(lim.DATA_DIR.startswith(_TMP))


class DayKeyTests(unittest.TestCase):
    def test_reset_hour_shifts_day(self):
        cfg = dict(lim.DEFAULT_CONFIG, reset_hour=4)
        real = lim.datetime.datetime

        class Fake(real):
            now_value = None

            @classmethod
            def now(cls, tz=None):
                return cls.now_value

        lim.datetime.datetime = Fake
        try:
            Fake.now_value = real(2026, 11, 26, 3, 59)
            self.assertEqual(lim.day_key(cfg), "2026-11-25")
            Fake.now_value = real(2026, 11, 26, 4, 0)
            self.assertEqual(lim.day_key(cfg), "2026-11-26")
        finally:
            lim.datetime.datetime = real


class CountingRuleTests(unittest.TestCase):
    cfg = dict(lim.DEFAULT_CONFIG)

    def test_normal_game_counts(self):
        self.assertTrue(lim.counts_toward_limit(session(1), self.cfg))

    def test_practice_tool_ignored_by_default(self):
        self.assertFalse(lim.counts_toward_limit(session(1, "PRACTICETOOL", custom=True), self.cfg))
        cfg = dict(self.cfg, count_practice_tool=True)
        self.assertTrue(lim.counts_toward_limit(session(1, "PRACTICETOOL", custom=True), cfg))

    def test_custom_game_ignored_by_default(self):
        self.assertFalse(lim.counts_toward_limit(session(1, custom=True), self.cfg))
        cfg = dict(self.cfg, count_custom_games=True)
        self.assertTrue(lim.counts_toward_limit(session(1, custom=True), cfg))

    def test_protected_phases_cover_whole_match(self):
        for phase in ("ChampSelect", "GameStart", "InProgress", "Reconnect", "WaitingForStats"):
            self.assertIn(phase, lim.PROTECTED_PHASES)
        self.assertFalse(lim.PROTECTED_PHASES & lim.QUEUE_PHASES)


class StateTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(lim.STATE_FILE):
            os.remove(lim.STATE_FILE)
        self.cfg = dict(lim.DEFAULT_CONFIG)

    def test_reconnect_does_not_double_count(self):
        st = lim.State(self.cfg)
        st.set_limit(2)
        self.assertTrue(st.add_game(111, "x"))
        self.assertFalse(st.add_game(111, "x"))
        self.assertEqual(st.snapshot()["games"], [111])

    def test_survives_restart(self):
        st = lim.State(self.cfg)
        st.set_limit(2)
        st.add_game(1, "x")
        st.add_game(2, "x")
        again = lim.State(self.cfg).snapshot()
        self.assertEqual(again["limit"], 2)
        self.assertEqual(again["games"], [1, 2])

    def test_new_day_resets(self):
        lim.save_json(lim.STATE_FILE, {"day": "2000-01-01", "limit": 1, "games": [5]})
        snap = lim.State(self.cfg).snapshot()
        self.assertIsNone(snap["limit"])
        self.assertEqual(snap["games"], [])

    def test_game_without_limit_uses_default(self):
        st = lim.State(self.cfg)
        st.add_game(9, "x")
        self.assertEqual(st.snapshot()["limit"], self.cfg["default_games"])


class ProcessHelperTests(unittest.TestCase):
    def test_lists_own_process(self):
        names = [n for _, n in lim.list_procs()]
        self.assertTrue(any(n.startswith("python") for n in names))

    def test_exe_path_of_self(self):
        self.assertTrue(lim.exe_path(os.getpid()).lower().endswith(".exe"))


if __name__ == "__main__":
    unittest.main()
