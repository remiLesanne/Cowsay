import asyncio

import httpx

from compliance_agent import LlmPacer


class FakeClock:
    """Time only moves when a caller sleeps, so waits are exact and instant."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def _pacer(clock, requests=100, tokens=1000):
    return LlmPacer(requests, tokens, utilization=1.0, clock=clock, sleep=clock.sleep)


def test_calls_within_quota_do_not_wait():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock)
        for _ in range(4):
            await pacer.reserve(250)
        assert clock.slept == []

    asyncio.run(scenario())


def test_token_budget_full_waits_until_the_oldest_call_leaves_the_window():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock, tokens=1000)
        await pacer.reserve(600)
        clock.now += 10
        await pacer.reserve(300)
        await pacer.reserve(300)  # 1200 > 1000: must wait for the first call to expire
        assert sum(clock.slept) == 50  # 60 s window - 10 s already elapsed

    asyncio.run(scenario())


def test_request_budget_full_waits_too():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock, requests=2, tokens=10**9)
        await pacer.reserve(1)
        await pacer.reserve(1)
        await pacer.reserve(1)
        assert sum(clock.slept) == 60

    asyncio.run(scenario())


def test_settling_with_real_usage_frees_the_overestimate():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock, tokens=1000)
        call = await pacer.reserve(900)  # estimate
        pacer.settle(call, 200)  # real usage
        await pacer.reserve(700)
        assert clock.slept == []

    asyncio.run(scenario())


def test_an_oversized_call_is_still_admitted_on_an_empty_window():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock, tokens=100)
        await pacer.reserve(5000)
        assert clock.slept == []

    asyncio.run(scenario())


def test_limits_follow_the_provider_headers():
    pacer = LlmPacer()
    pacer.update_limits(httpx.Headers({
        "x-ratelimit-limit-req-minute": "500",
        "x-ratelimit-limit-tokens-minute": "2000000",
    }))
    assert (pacer.requests_per_minute, pacer.tokens_per_minute) == (500, 2_000_000)
    pacer.update_limits(httpx.Headers({"x-ratelimit-limit-req-minute": "garbage"}))
    assert pacer.requests_per_minute == 500


def test_waiting_calls_are_served_in_arrival_order():
    async def scenario():
        clock = FakeClock()
        pacer = _pacer(clock, requests=1, tokens=10**9)
        await pacer.reserve(1)
        order = []

        async def call(name):
            await pacer.reserve(1)
            order.append(name)

        await asyncio.gather(call("first"), call("second"), call("third"))
        assert order == ["first", "second", "third"]

    asyncio.run(scenario())
