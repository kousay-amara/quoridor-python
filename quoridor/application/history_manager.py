"""History manager for undo/redo operations."""

from __future__ import annotations

from collections.abc import Callable

from ..core.move_record import BlitzSnapshot, GameSnapshot, MoveRecord, PlayerType


class HistoryManager:
    """Manage move history with an undo/redo cursor."""

    def __init__(self) -> None:
        self.records: list[MoveRecord] = []
        self.cursor: int = -1

    def record_move(self, record: MoveRecord) -> None:
        """Record a new move and drop future history when branching."""
        if self.cursor < len(self.records) - 1:
            self.records = self.records[: self.cursor + 1]
        self.records.append(record)
        self.cursor = len(self.records) - 1

    def can_undo(self) -> bool:
        return self.cursor >= 0

    def can_redo(self) -> bool:
        return self.cursor + 1 < len(self.records)

    def undo_until_human_boundary(
        self,
        apply_snapshot: Callable[[GameSnapshot], None],
        requester_type: PlayerType = "human",
        apply_blitz_snapshot: Callable[[BlitzSnapshot | None], None] | None = None,
    ) -> list[MoveRecord]:
        """Undo moves until the previous human boundary is reached."""
        self._ensure_human_requester(requester_type)
        if not self.can_undo():
            return []

        undone: list[MoveRecord] = []
        seen_human = False

        while self.can_undo():
            record = self.records[self.cursor]
            apply_snapshot(record.before_state)
            if apply_blitz_snapshot is not None:
                apply_blitz_snapshot(record.before_blitz)
            undone.append(record)
            self.cursor -= 1

            if record.player_type == "human":
                seen_human = True

            if (
                seen_human
                and self.can_undo()
                and self.records[self.cursor].player_type == "human"
            ):
                break

        return undone

    def redo_until_human_boundary(
        self,
        apply_snapshot: Callable[[GameSnapshot], None],
        requester_type: PlayerType = "human",
        apply_blitz_snapshot: Callable[[BlitzSnapshot | None], None] | None = None,
    ) -> list[MoveRecord]:
        """Redo moves until the next human boundary is reached."""
        self._ensure_human_requester(requester_type)
        if not self.can_redo():
            return []

        redone: list[MoveRecord] = []
        human_redone = False

        while self.can_redo():
            next_record = self.records[self.cursor + 1]
            if human_redone and next_record.player_type == "human":
                break

            apply_snapshot(next_record.after_state)
            if apply_blitz_snapshot is not None:
                apply_blitz_snapshot(next_record.after_blitz)
            self.cursor += 1
            redone.append(next_record)

            if next_record.player_type == "human":
                human_redone = True

        return redone

    @staticmethod
    def _ensure_human_requester(requester_type: PlayerType) -> None:
        if requester_type != "human":
            raise PermissionError(
                "undo/redo is allowed for human players only"
            )
