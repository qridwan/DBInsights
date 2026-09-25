from experiments.load.harness import poll_until_stable


class FakeClock:
    """Advances only when told to; `sleep` moves it forward by the given amount."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def reader(values: list[int]):
    calls = iter(values + [values[-1]] * 100)
    return lambda: next(calls)


def test_waits_for_the_initial_delay_before_the_first_read():
    clock = FakeClock()
    poll_until_stable(
        reader([5, 5, 5]),
        stable_reads=3,
        initial_delay=1.0,
        interval=0.5,
        timeout=10,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert clock.sleeps[0] == 1.0


def test_does_not_stop_at_the_first_read_even_if_repeated_once():
    # Two zero-reads in a row must not be mistaken for "nothing coming".
    calls = reader([0, 0, 4, 4, 4])
    value = poll_until_stable(
        calls,
        stable_reads=3,
        initial_delay=0,
        interval=0.1,
        timeout=10,
        sleep=lambda _: None,
        now=FakeClock().now,
    )
    assert value == 4


def test_a_genuinely_empty_run_still_settles_at_zero():
    value = poll_until_stable(
        reader([0, 0, 0]),
        stable_reads=3,
        initial_delay=0,
        interval=0.1,
        timeout=10,
        sleep=lambda _: None,
        now=FakeClock().now,
    )
    assert value == 0


def test_restarts_the_streak_on_every_change():
    calls = reader([1, 2, 3, 3, 3])
    value = poll_until_stable(
        calls,
        stable_reads=3,
        initial_delay=0,
        interval=0.1,
        timeout=10,
        sleep=lambda _: None,
        now=FakeClock().now,
    )
    assert value == 3


def test_gives_up_at_the_timeout_and_returns_the_last_value_read():
    clock = FakeClock()
    alternating = ([7, 8][i % 2] for i in range(1000))  # never stabilizes
    value = poll_until_stable(
        lambda: next(alternating),
        stable_reads=3,
        initial_delay=0,
        interval=1.0,
        timeout=3.5,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert value in (7, 8)
    assert clock.t >= 3.5


def test_stops_polling_as_soon_as_it_stabilizes_rather_than_using_the_full_timeout():
    clock = FakeClock()
    poll_until_stable(
        reader([9, 9, 9]),
        stable_reads=3,
        initial_delay=1.0,
        interval=0.5,
        timeout=100,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert clock.t == 2.0  # 1.0 initial + 2 * 0.5 interval for the two confirming reads
