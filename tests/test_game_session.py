from quoridor.application.blitz import Blitz
from quoridor.application.game_session import GameSession
from quoridor.application.game_session_builder import GameSessionBuilder
from quoridor.core.game_state import GameState


def _session() -> GameSession:
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 0, 2: 80},
        remaining_walls={1: 10, 2: 10},
    )
    return GameSession(state=state, player_types={1: "human", 2: "ai"})


def test_game_session_records_moves_and_undo_redo_chain():
    session = _session()

    session.play_pawn_move(1, 1)
    session.play_pawn_move(2, 79)

    assert session.state.player_positions == {1: 1, 2: 79}
    assert session.state.current_player == 1
    assert session.history.cursor == 1

    undone = session.undo(requester_id=1)
    assert [r.player_type for r in undone] == ["ai", "human"]
    assert session.state.player_positions == {1: 0, 2: 80}
    assert session.state.current_player == 1
    assert session.history.cursor == -1

    redone = session.redo(requester_id=1)
    assert [r.player_type for r in redone] == ["human", "ai"]
    assert session.state.player_positions == {1: 1, 2: 79}
    assert session.state.current_player == 1
    assert session.history.cursor == 1


def test_game_session_cuts_future_after_new_move_post_undo():
    session = _session()

    session.play_pawn_move(1, 1)
    session.play_pawn_move(2, 79)
    session.undo(requester_id=1)

    session.play_pawn_move(1, 9)

    assert session.history.can_redo() is False
    assert len(session.history.records) == 1
    assert session.state.player_positions == {1: 9, 2: 80}


def test_game_session_undo_redo_forbidden_for_ai_requester():
    session = _session()
    session.play_pawn_move(1, 1)

    try:
        session.undo(requester_id=2)
        assert False, "PermissionError expected"
    except PermissionError:
        pass


def test_game_session_builder_requires_state_and_player_types():
    builder = GameSessionBuilder()
    try:
        builder.build()
        assert False, "ValueError expected"
    except ValueError:
        pass

    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 0, 2: 80},
        remaining_walls={1: 10, 2: 10},
    )
    try:
        builder.with_state(state).build()
        assert False, "ValueError expected"
    except ValueError:
        pass

    session = builder.with_player_types({1: "human", 2: "ai"}).with_state(state).build()
    assert isinstance(session, GameSession)
    assert session.player_types == {1: "human", 2: "ai"}

    session.undo(requester_id=1)
    try:
        session.redo(requester_id=2)
        assert False, "PermissionError expected"
    except PermissionError:
        pass


def test_play_ai_turn_rejects_minimax_without_depth():
    state = GameState(
        board_size=9,
        current_player=2,
        player_positions={1: 0, 2: 80},
        remaining_walls={1: 10, 2: 10},
    )
    session = GameSession(state=state, player_types={1: "human", 2: "ai"})

    try:
        session.play_ai_turn(mode="minimax", depth=None, time_limit_sec=1.0)
        assert False, "ValueError expected"
    except ValueError as exc:
        assert "requires a fixed depth" in str(exc)


def test_play_ai_turn_uses_mcts_when_mode_is_mcts(monkeypatch):
    state = GameState(
        board_size=9,
        current_player=2,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 10, 2: 10},
    )
    session = GameSession(state=state, player_types={1: "human", 2: "ai"})

    captured = {}

    def fake_mcts_search(root_state, time_limit=5.0, exploration_weight=1.41):
        del root_state, exploration_weight
        captured["time_limit"] = time_limit
        return ("pawn", 67)

    monkeypatch.setattr(
        "quoridor.application.game_session.mcts_search",
        fake_mcts_search,
    )

    record = session.play_ai_turn(mode="mcts", time_limit_sec=1.5)

    assert captured["time_limit"] == 1.5
    assert record.action == "move_pawn"


def test_timeout_undo_restores_blitz_snapshot_and_keeps_redo_branch():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "human", 2: "human"})
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])
    session.attach_blitz(blitz)

    before_timeout = blitz.snapshot()
    assert blitz.consume_time(1, 61.0) is True
    assert blitz.remaining_time(1) == 0.0

    record, winner = session.timeout_player(
        1,
        before_blitz_snapshot=before_timeout,
    )
    assert record.action == "timeout_loss"
    assert winner == 2
    assert session.history.can_redo() is False

    session.undo(requester_id=2)

    assert session.state.is_player_active(1)
    assert blitz.remaining_time(1) == before_timeout["remaining_times"][1]
    assert session.history.can_redo() is True
