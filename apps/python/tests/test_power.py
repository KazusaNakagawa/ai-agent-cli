from unittest.mock import patch

from src.power import is_system_awake

# Real `pmset -g log` lines, captured 2026-07-31 while diagnosing the sleep-severed
# sector sweep. Column widths and the tab before the detail are reproduced as-is.
_DARK_WAKE = (
    "2026-07-31 05:54:18 +0900 DarkWake            \tDarkWake from Deep Idle [CDNP] : "
    "due to smc.sysState.Wake(0x70070000) wifibt SMC.OutboxNotEmpty/ Using BATT (Charge:61%)"
)
_SLEEP = (
    "2026-07-31 05:57:18 +0900 Sleep               \tEntering Sleep state due to "
    "'Maintenance Sleep':TCPKeepAlive=active Using Batt (Charge:61%) 247 secs"
)
_FULL_WAKE = (
    "2026-07-31 06:01:25 +0900 Wake                \tWake from Deep Idle [CDNVA] : "
    "due to smc.sysState.Wake(0x70070000) lid SMC.OutboxNotEmpty RTP.multi-touch"
)
_ASSERTION_NOISE = (
    "2026-07-31 06:03:54 +0900 Assertions          \tPID 589(WindowServer) Created "
    "PreventSystemSleep \"com.apple.WindowServer.PUIDS\""
)


def _with_log(text: str):
    return patch("src.power._pmset_log", return_value=text)


class TestIsSystemAwake:
    def test_full_wake_is_awake(self):
        with _with_log("\n".join([_SLEEP, _FULL_WAKE])):
            assert is_system_awake() is True

    def test_dark_wake_is_not_awake(self):
        with _with_log("\n".join([_FULL_WAKE, _SLEEP, _DARK_WAKE])):
            assert is_system_awake() is False

    def test_trailing_assertion_lines_do_not_mask_the_last_wake(self):
        """Assertions are logged constantly; only Sleep/Wake/DarkWake decide the state."""
        with _with_log("\n".join([_DARK_WAKE, _ASSERTION_NOISE])):
            assert is_system_awake() is False

    def test_sleep_as_last_event_is_not_awake(self):
        with _with_log("\n".join([_FULL_WAKE, _SLEEP])):
            assert is_system_awake() is False

    def test_unavailable_pmset_falls_back_to_awake(self):
        """Fail open: on a machine without pmset (CI, Linux) the guard must not
        block a recovery run that would otherwise succeed."""
        with patch("src.power._pmset_log", side_effect=FileNotFoundError):
            assert is_system_awake() is True

    def test_log_without_any_power_event_falls_back_to_awake(self):
        with _with_log(_ASSERTION_NOISE):
            assert is_system_awake() is True
