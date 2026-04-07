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


def test_play_ai_turn_uses_automatic_depth_for_minimax(monkeypatch):
    from quoridor.application import game_session as game_session_mod

    state = GameState(
        board_size=9,
        current_player=2,
        player_positions={1: 0, 2: 80},
        remaining_walls={1: 10, 2: 10},
    )
    session = GameSession(state=state, player_types={1: "human", 2: "ai"})
    captured = {}

    monkeypatch.setattr(
        game_session_mod,
        "resolve_auto_minimax_depth",
        lambda time_limit_sec: 2 if time_limit_sec == 1.0 else 99,
    )

    def fake_find_best_move_minimax(state, *, ai_player_id, depth, eval_fn):
        del state, eval_fn
        captured["ai_player_id"] = ai_player_id
        captured["depth"] = depth
        return ("pawn", 71)

    monkeypatch.setattr(
        game_session_mod,
        "find_best_move_minimax",
        fake_find_best_move_minimax,
    )

    record = session.play_ai_turn(
        mode="minimax",
        depth=None,
        time_limit_sec=1.0,
    )

    assert captured == {"ai_player_id": 2, "depth": 2}
    assert record.action == "move_pawn"
    assert session.state.player_positions[2] == 71


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


def test_game_session_compute_scores_returns_deterministic_values():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "human", 2: "human"})

    scores = session.compute_scores()

    # Both players are at symmetric starting positions (distance 8 to target).
    assert scores == {1: 73, 2: 73}
    assert session.game_outcome().status == "ongoing"


def test_game_session_declares_draw_when_turn_limit_reached():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
    )
    session = GameSession(
        state=state,
        player_types={1: "human", 2: "human"},
        draw_turn_limit=2,
    )

    session.play_pawn_move(1, 13)
    assert session.game_outcome().status == "ongoing"
    session.play_pawn_move(2, 67)

    outcome = session.game_outcome()
    assert outcome.status == "draw"
    assert outcome.winner_id is None


def test_game_session_winner_detection_unchanged_with_outcome_api():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 67, 2: 21},
        remaining_walls={1: 20, 2: 20},
    )
    session = GameSession(state=state, player_types={1: "human", 2: "human"})

    session.play_pawn_move(1, 76)
    outcome = session.game_outcome()

    assert outcome.status == "winner"
    assert outcome.winner_id == 1
    assert outcome.scores[1] > outcome.scores[2]
