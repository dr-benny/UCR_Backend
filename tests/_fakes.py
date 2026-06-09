"""Shared test doubles.

InMemoryRedis is a minimal async substitute for redis.asyncio that covers
the string, sorted-set, and pub/sub operations the app uses, so unit tests
can run the real code paths without a live Redis.
"""
from __future__ import annotations

import asyncio
import fnmatch


class _FakePubSub:
    def __init__(self, redis: "InMemoryRedis") -> None:
        self._redis = redis
        self._channels: set[str] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def subscribe(self, channel: str) -> None:
        self._channels.add(channel)
        self._redis._subscribers.setdefault(channel, []).append(self._queue)

    async def unsubscribe(self, channel: str) -> None:
        self._channels.discard(channel)
        subs = self._redis._subscribers.get(channel, [])
        if self._queue in subs:
            subs.remove(self._queue)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float | None = None):
        try:
            if timeout is None:
                data = await self._queue.get()
            else:
                data = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return {"type": "message", "data": data}

    async def aclose(self) -> None:
        for ch in list(self._channels):
            await self.unsubscribe(ch)


class InMemoryRedis:
    """Minimal async Redis substitute for unit tests."""

    def __init__(self) -> None:
        self._store: dict = {}
        self._ss: dict = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # ── strings ──────────────────────────────────────────────
    async def set(self, key, value, ex=None, **_):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, *keys):
        for k in keys:
            self._store.pop(k, None)

    async def incr(self, key):
        val = int(self._store.get(key, 0)) + 1
        self._store[key] = val
        return val

    async def expire(self, *_):
        pass

    # ── sorted sets ──────────────────────────────────────────
    async def zadd(self, name, mapping):
        ss = self._ss.setdefault(name, {})
        ss.update(mapping)

    async def zrem(self, name, *members):
        for m in members:
            self._ss.get(name, {}).pop(m, None)

    async def zcard(self, name):
        return len(self._ss.get(name, {}))

    async def zscore(self, name, member):
        return self._ss.get(name, {}).get(member)

    async def zrevrange(self, name, start, stop, withscores=False):
        items = sorted(self._ss.get(name, {}).items(), key=lambda x: -x[1])
        sliced = items[start:] if stop == -1 else items[start:stop + 1]
        if withscores:
            return [(k.encode(), v) for k, v in sliced]
        return [k.encode() for k, _ in sliced]

    async def zremrangebyscore(self, *_):
        pass

    # ── scan / keys ──────────────────────────────────────────
    async def keys(self, *_):
        return list(self._store.keys())

    async def scan_iter(self, match=None, count=None):
        for k in list(self._store.keys()):
            if match is None or fnmatch.fnmatch(k, match):
                yield k

    # ── pub/sub ──────────────────────────────────────────────
    async def publish(self, channel, data):
        for q in self._subscribers.get(channel, []):
            q.put_nowait(data)

    def pubsub(self):
        return _FakePubSub(self)

    # ── misc ─────────────────────────────────────────────────
    async def ping(self):
        return True

    async def aclose(self):
        pass
