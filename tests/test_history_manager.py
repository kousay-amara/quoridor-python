from quoridor.application.history_manager import HistoryManager
from quoridor.core.move_record import MoveRecord, PlayerType


def _snap(turn: int) -> dict:
    return {
        "board_size": 9,
        "current_player": turn,
        "player_positions": {},
        "remaining_walls": {},
        "vertical_walls": [],
        "horizontal_walls": [],
    }


def _record(
    player_id: int,
    player_type: PlayerType,
    before_turn: int,
    after_turn: int,
) -> MoveRecord:
    return MoveRecord(
        player_id=player_id,
        player_type=player_type,
        action="move_pawn",
        before_state=_snap(before_turn),
        after_state=_snap(after_turn),
    )


def test_record_move_updates_cursor_and_truncates_future():
    history = HistoryManager()
    r1 = _record(1, "human", 0, 1)
    r2 = _record(2, "ai", 1, 2)
    r3 = _record(1, "human", 2, 3)

    history.record_move(r1)
    history.record_move(r2)
    history.cursor = 0
    history.record_move(r3)

    assert history.cursor == 1
    assert history.records == [r1, r3]


def test_undo_until_human_boundary():
    history = HistoryManager()
    for rec in [
        _record(1, "human", 0, 1),
        _record(2, "ai", 1, 2),
        _record(3, "ai", 2, 3),
        _record(4, "human", 3, 4),
    ]:
        history.record_move(rec)

    restored_turns: list[int] = []
    undone = history.undo_until_human_boundary(
        lambda s: restored_turns.append(s["current_player"])
    )

    assert [r.player_type for r in undone] == ["human", "ai", "ai"]
    assert history.cursor == 0
    assert restored_turns == [3, 2, 1]


def test_redo_until_human_boundary():
    history = HistoryManager()
    for rec in [
        _record(1, "human", 0, 1),
        _record(2, "ai", 1, 2),
        _record(3, "ai", 2, 3),
        _record(4, "human", 3, 4),
    ]:
        history.record_move(rec)

    history.cursor = -1
    restored_turns: list[int] = []
    redone = history.redo_until_human_boundary(
        lambda s: restored_turns.append(s["current_player"])
    )

    assert [r.player_type for r in redone] == ["human", "ai", "ai"]
    assert history.cursor == 2
    assert restored_turns == [1, 2, 3]


def test_undo_redo_forbidden_for_ai():
    history = HistoryManager()
    history.record_move(_record(1, "human", 0, 1))

    try:
        history.undo_until_human_boundary(lambda _s: None, requester_type="ai")
        assert False, "PermissionError expected"
    except PermissionError:
        pass

    history.cursor = -1
    try:
        history.redo_until_human_boundary(lambda _s: None, requester_type="ai")
        assert False, "PermissionError expected"
    except PermissionError:
        pass
