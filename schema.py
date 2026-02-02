import asyncio
from dataclasses import dataclass, field
from typing import Set


@dataclass
class SessionState:
    _files_read: Set[str] = field(default_factory=set, init=False, repr=False)
    _files_written: Set[str] = field(default_factory=set, init=False, repr=False)
    _commands_run: list[dict] = field(default_factory=list, init=False, repr=False)
    _searches_performed: list[dict] = field(
        default_factory=list, init=False, repr=False
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def add_file_read(self, path: str):
        async with self._lock:
            self._files_read.add(path)

    async def add_file_written(self, path: str):
        async with self._lock:
            self._files_written.add(path)

    async def add_command_run(self, command: dict):
        async with self._lock:
            self._commands_run.append(command)

    async def add_search_performed(self, search: dict):
        async with self._lock:
            self._searches_performed.append(search)

    @property
    def files_read(self) -> frozenset[str]:
        return frozenset(self._files_read)

    @property
    def files_written(self) -> frozenset[str]:
        return frozenset(self._files_written)

    @property
    def commands_run(self) -> tuple[dict, ...]:
        return tuple(self._commands_run)

    @property
    def searches_performed(self) -> tuple[dict, ...]:
        return tuple(self._searches_performed)

    def summary(self) -> str:
        return f"""
=== SESSION SUMMARY ===
Files read: {len(self._files_read)}
Files written: {len(self._files_written)}
Commands run: {len(self._commands_run)}
Searches performed: {len(self._searches_performed)}

Files read: {", ".join(sorted(self._files_read)) if self._files_read else "None"}
Files written: {", ".join(sorted(self._files_written)) if self._files_written else "None"}
""".strip()
