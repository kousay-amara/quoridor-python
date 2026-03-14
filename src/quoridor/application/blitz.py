"""Blitz timer state and operations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class Blitz:
    """Manage per-player blitz timers independently from the CLI shell."""

    time_limit_minutes: int
    paused: bool = False
    _remaining_times: dict[int, float] | None = field(default=None, repr=False)

    @classmethod
    def disabled(cls, *, time_limit_minutes: int = 0) -> "Blitz":
        return cls(time_limit_minutes=time_limit_minutes)

    @classmethod
    def for_players(
        cls, player_ids: Iterable[int], *, time_limit_minutes: int
    ) -> "Blitz":
        seconds = float(time_limit_minutes * 60)
        remaining_times = {
            player_id: seconds for player_id in sorted(set(player_ids))
        }
        return cls(
            time_limit_minutes=time_limit_minutes,
            paused=False,
            _remaining_times=remaining_times,
        )

    def is_enabled(self) -> bool:
        return self._remaining_times is not None

    def remaining_time(self, player_id: int) -> float:
        remaining_times = self._require_remaining_times()
        if player_id not in remaining_times:
            raise ValueError(f"unknown blitz player: {player_id}")
        return remaining_times[player_id]

    def remaining_times(self) -> dict[int, float]:
        remaining_times = self._require_remaining_times()
        return {
            player_id: remaining_times[player_id]
            for player_id in sorted(remaining_times)
        }

    def input_timeout_for(self, player_id: int) -> float | None:
        if not self.is_enabled() or self.paused:
            return None
        return self.remaining_time(player_id)

    def consume_time(self, player_id: int, elapsed: float) -> bool:
        if not self.is_enabled() or self.paused:
            return False

        remaining_times = self._require_remaining_times()
        if player_id not in remaining_times:
            raise ValueError(f"unknown blitz player: {player_id}")

        remaining_times[player_id] = max(0.0, remaining_times[player_id] - elapsed)
        return remaining_times[player_id] <= 0

    def expire_player(self, player_id: int) -> None:
        remaining_times = self._require_remaining_times()
        if player_id not in remaining_times:
            raise ValueError(f"unknown blitz player: {player_id}")
        remaining_times[player_id] = 0.0

    def toggle_pause(self) -> bool:
        if not self.is_enabled():
            raise ValueError("blitz mode is not enabled")
        self.paused = not self.paused
        return self.paused

    def _require_remaining_times(self) -> dict[int, float]:
        if self._remaining_times is None:
            raise ValueError("blitz mode is not enabled")
        return self._remaining_times
