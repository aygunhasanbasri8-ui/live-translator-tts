import pytest

from live_translator.providers import Cooldown, Provider, ServiceUnavailable, call_first_available


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_cooldown_doubles_until_cap_and_resets_on_success():
    clock = FakeClock()
    cooldown = Cooldown(base_sec=4, max_sec=10, clock=clock)

    assert [cooldown.failed() for _ in range(3)] == [4, 8, 10]
    assert cooldown.active()
    clock.now += 10
    assert not cooldown.active()

    cooldown.succeeded()
    assert cooldown.failed() == 4


def test_rate_limited_provider_is_skipped_until_cooldown_ends():
    clock = FakeClock()
    calls = []

    def google(text):
        calls.append("google")
        raise ConnectionError("429")

    def backup(text):
        calls.append("backup")
        return text.upper()

    providers = [Provider("Google", google, cooldown=Cooldown(clock=clock)),
                 Provider("Yedek", backup, finals_only=True, cooldown=Cooldown(clock=clock))]

    def transient(exc):
        return isinstance(exc, ConnectionError)

    assert call_first_available(providers, ("a",), True, transient) == "A"
    assert call_first_available(providers, ("b",), True, transient) == "B"
    assert calls == ["google", "backup", "backup"]

    # kısmi sonuç kotalı yedeğe gitmez
    with pytest.raises(ServiceUnavailable):
        call_first_available(providers, ("c",), False, transient)

    clock.now += 5
    call_first_available(providers, ("d",), True, transient)
    assert calls[-2:] == ["google", "backup"]
