from __future__ import annotations

from pathlib import Path

import pytest

from quoridor.application.ai_logic import evaluate_state
from quoridor.application.blitz import Blitz
from quoridor.application.game_application_service import GameApplicationService
from quoridor.application.game_session import GameSession
from quoridor.application.minimax_engine import resolve_auto_minimax_depth
from quoridor.core.game_state import GameState


def _make_session() -> GameSession:
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    return GameSession(state=state, player_types={1: "human", 2: "human"})


def test_service_save_and_load_roundtrip(tmp_path: Path):
    session = _make_session()
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])
    blitz.consume_time(1, 5.0)
    service = GameApplicationService(session=session, blitz=blitz)

    save_path = tmp_path / "session.txt"
    service.save(str(save_path))

    loaded_session, loaded_blitz = service.load(
        str(save_path),
        fallback_player_types={1: "human", 2: "human"},
        fallback_walls_per_player={1: 20, 2: 20},
    )

    assert loaded_session.state.player_positions == {1: 4, 2: 76}
    assert loaded_blitz.is_enabled() is True
    assert loaded_blitz.remaining_time(1) < loaded_blitz.remaining_time(2)


def test_service_move_and_undo_redo_groups():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    won, player_id = service.play_pawn_move_token("e1-e2")
    assert won is False
    assert player_id == 1

    won, player_id = service.play_pawn_move_token("e9-e8")
    assert won is False
    assert player_id == 2

    groups, total = service.undo_groups(requester_id=1, count=1)
    assert groups == 1
    assert total == 1

    groups, total = service.redo_groups(requester_id=1, count=1)
    assert groups == 1
    assert total == 1


def test_service_hint_minimax_returns_move_tuple():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    move = service.hint(ai_mode="minimax", ai_time=2, ai_minimax_depth=1)

    assert isinstance(move, tuple)
    assert len(move) >= 2


def test_service_hint_modes_and_errors():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    mcts_called = {"ok": False}
    iterative_called = {"ok": False}
    minimax_called = {"ok": False}

    def fake_mcts(state, *, time_limit):
        assert state is service.session.state
        assert time_limit == 2
        mcts_called["ok"] = True
        return ("move_pawn", 0, 1)

    def fake_iterative(
        state,
        *,
        ai_player_id,
        eval_fn,
        time_limit_sec,
        max_depth,
    ):
        assert state is service.session.state
        assert ai_player_id == 1
        assert callable(eval_fn)
        assert time_limit_sec == 3
        assert max_depth == 4
        iterative_called["ok"] = True
        return ("move_pawn", 0, 1)

    def fake_minimax(state, *, ai_player_id, depth, eval_fn):
        assert state is service.session.state
        assert ai_player_id == 1
        assert depth == 2
        assert callable(eval_fn)
        minimax_called["ok"] = True
        return ("move_pawn", 0, 1)

    assert (
        service.hint(
            ai_mode="mcts",
            ai_time=2,
            ai_minimax_depth=None,
            mcts_fn=fake_mcts,
        )
        == ("move_pawn", 0, 1)
    )
    assert mcts_called["ok"] is True

    assert (
        service.hint(
            ai_mode="iterative",
            ai_time=3,
            ai_minimax_depth=4,
            ai_minimax_scoring=1,
            iterative_fn=fake_iterative,
        )
        == ("move_pawn", 0, 1)
    )
    assert iterative_called["ok"] is True

    assert (
        service.hint(
            ai_mode="minimax",
            ai_time=1,
            ai_minimax_depth=2,
            ai_minimax_scoring=1,
            minimax_fn=fake_minimax,
        )
        == ("move_pawn", 0, 1)
    )
    assert minimax_called["ok"] is True

    with pytest.raises(ValueError, match="no legal moves available"):
        service.hint(
            ai_mode="mcts",
            ai_time=1,
            ai_minimax_depth=None,
            mcts_fn=lambda *_args, **_kwargs: None,
        )

    with pytest.raises(ValueError, match="unsupported AI mode"):
        service.hint(ai_mode="unknown", ai_time=1, ai_minimax_depth=None)


def test_service_hint_passes_selected_minimax_scoring():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    observed = {"score": None}

    def fake_minimax(state, *, ai_player_id, depth, eval_fn):
        assert state is service.session.state
        assert ai_player_id == 1
        assert depth == 2
        observed["score"] = eval_fn(state, ai_player_id)
        return ("move_pawn", 0, 1)

    service.hint(
        ai_mode="minimax",
        ai_time=1,
        ai_minimax_depth=2,
        ai_minimax_scoring=2,
        minimax_fn=fake_minimax,
    )

    assert observed["score"] == evaluate_state(
        session.state, 1, scoring_type=2
    )


def test_service_hint_uses_automatic_depth_for_minimax():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)
    called = {"depth": None}

    def fake_minimax(state, *, ai_player_id, depth, eval_fn):
        assert state is service.session.state
        assert ai_player_id == 1
        assert callable(eval_fn)
        called["depth"] = depth
        return ("move_pawn", 0, 1)

    service.hint(
        ai_mode="minimax",
        ai_time=5,
        ai_minimax_depth=None,
        minimax_fn=fake_minimax,
    )

    assert called["depth"] == resolve_auto_minimax_depth(5)


def test_service_hint_rejects_terminal_state():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 76, 2: 67},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "human", 2: "human"})
    service = GameApplicationService(session=session, blitz=None)

    with pytest.raises(ValueError, match="Game is over. No hint available."):
        service.hint(ai_mode="minimax", ai_time=1, ai_minimax_depth=1)


def test_service_undo_redo_count_validation_and_empty_history():
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    with pytest.raises(ValueError, match="N must be > 0"):
        service.undo_groups(requester_id=1, count=0)
    with pytest.raises(ValueError, match="N must be > 0"):
        service.redo_groups(requester_id=1, count=0)

    assert service.undo_groups(requester_id=1, count=1) == (0, 0)
    assert service.redo_groups(requester_id=1, count=1) == (0, 0)


def test_service_place_wall_token_validation_branches(monkeypatch):
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    with pytest.raises(ValueError, match="Invalid format"):
        service.place_wall_token("e2", wall_token_min_length=3)

    with pytest.raises(ValueError, match="Invalid wall orientation"):
        service.place_wall_token("e2x", wall_token_min_length=3)

    monkeypatch.setattr(
        "quoridor.application.game_application_service.validate_wall",
        lambda *_args, **_kwargs: (False, "wall blocked"),
    )
    with pytest.raises(ValueError, match="wall blocked"):
        service.place_wall_token("e2h", wall_token_min_length=3)


def test_service_play_pawn_token_validation_branches(monkeypatch):
    session = _make_session()
    service = GameApplicationService(session=session, blitz=None)

    with pytest.raises(ValueError, match="Invalid format"):
        service.play_pawn_move_token("e1e2")

    monkeypatch.setattr(
        "quoridor.application.game_application_service.validate_pawn_move",
        lambda *_args, **_kwargs: (False, "illegal"),
    )
    with pytest.raises(ValueError, match="illegal"):
        service.play_pawn_move_token("e1-e2")
