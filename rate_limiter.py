import asyncio
import time
from collections import deque

from logging_config import logger


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    async def acquire(self):
        now = time.time()
        while self.calls and self.calls[0] < now - self.period:
            self.calls.popleft()

        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                logger.warning(
                    "Rate limit hit",
                    max_calls=self.max_calls,
                    period=self.period,
                    sleep_time=sleep_time,
                )
                await asyncio.sleep(sleep_time)
                now = time.time()
                while self.calls and self.calls[0] < now - self.period:
                    self.calls.popleft()

        self.calls.append(now)
