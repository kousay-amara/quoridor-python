from src.quoridor.application.game_session import GameSession
from src.quoridor.core.game_state import GameState


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

    session.undo(requester_id=1)
    try:
        session.redo(requester_id=2)
        assert False, "PermissionError expected"
    except PermissionError:
        pass
