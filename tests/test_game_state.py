from src.quoridor.core.game_state import GameState


def test_to_snapshot_returns_copied_data():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 10, 2: 10},
        vertical_walls=[(0, 1)],
        horizontal_walls=[(9, 18)],
    )

    snap = state.to_snapshot()
    state.player_positions[1] = 5
    state.remaining_walls[1] = 9
    state.vertical_walls.append((1, 2))

    assert snap["player_positions"] == {1: 4, 2: 76}
    assert snap["remaining_walls"] == {1: 10, 2: 10}
    assert snap["vertical_walls"] == [(0, 1)]


def test_restore_restores_state_and_graph():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 10, 2: 10},
        vertical_walls=[(0, 1)],
        horizontal_walls=[],
    )
    snapshot = state.to_snapshot()

    state.current_player = 2
    state.player_positions = {1: 13, 2: 67}
    state.remaining_walls = {1: 9, 2: 10}
    state.vertical_walls = []
    state.horizontal_walls = [(9, 18)]
    state._rebuild_graph()

    state.restore(snapshot)

    assert state.current_player == 1
    assert state.player_positions == {1: 4, 2: 76}
    assert state.remaining_walls == {1: 10, 2: 10}
    assert state.vertical_walls == [(0, 1)]
    assert state.horizontal_walls == []
    assert 1 not in state.graph.adj[0]


def test_from_snapshot_creates_equivalent_state():
    snapshot = {
        "board_size": 9,
        "current_player": 1,
        "player_positions": {1: 4, 2: 76},
        "remaining_walls": {1: 10, 2: 10},
        "vertical_walls": [(0, 1)],
        "horizontal_walls": [],
    }
    state = GameState.from_snapshot(snapshot)

    assert state.to_snapshot() == snapshot
    assert 1 not in state.graph.adj[0]
