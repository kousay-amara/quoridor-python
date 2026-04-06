from __future__ import annotations

from types import SimpleNamespace

from quoridor.interfaces.shell import bootstrap as bootstrap_mod
from quoridor.interfaces.shell import events as events_mod
from quoridor.interfaces.shell import input as input_mod
from quoridor.interfaces.shell import play_strategy as strategy_mod


def test_event_bus_and_emit_event_paths():
    events: list[tuple[str, dict]] = []
    bus = events_mod.EventBus()
    unsub_a = bus.subscribe("game.winner", lambda e: events.append((e.name, e.payload)))
    bus.subscribe("*", lambda e: events.append((f"*:{e.name}", e.payload)))

    bus.emit("game.winner", player_id=1)
    unsub_a()
    bus.emit("game.winner", player_id=2)
    unsub_a()  # second unsubscribe should be a no-op

    assert ("game.winner", {"player_id": 1}) in events
    assert ("*:game.winner", {"player_id": 1}) in events
    assert ("*:game.winner", {"player_id": 2}) in events

    capture: list[tuple[str, dict]] = []
    events_mod.emit_event(
        SimpleNamespace(emit=lambda name, **payload: capture.append((name, payload))),
        "x",
        value=1,
    )
    events_mod.emit_event(None, "x", value=2)
    events_mod.emit_event(SimpleNamespace(), "x", value=3)
    assert capture == [("x", {"value": 1})]


def test_shell_input_helpers_without_real_readline(monkeypatch):
    completer = input_mod.build_completer(["help", "history", "hint"])
    assert completer("hi", 0) == "history"
    assert completer("h", 2) == "hint"
    assert completer("h", 3) is None

    fake = SimpleNamespace(
        _items=["one", "find-me", "another find-me"],
        get_current_history_length=lambda: 3,
        get_history_item=lambda idx: ["one", "find-me", "another find-me"][idx - 1],
        removed=[],
        remove_history_item=lambda idx: fake.removed.append(idx),
        set_history_length=lambda _size: None,
        set_completer_delims=lambda _delims: None,
        set_completer=lambda _comp: None,
        parse_and_bind=lambda _binding: None,
    )
    monkeypatch.setattr(input_mod, "readline", fake)

    assert input_mod.has_readline() is True
    assert input_mod.get_last_history_match("find") == "another find-me"
    input_mod.maybe_remove_last_history_item()
    assert fake.removed == [2]
    input_mod.setup_readline(completer=completer, history_size=200)

    monkeypatch.setattr(input_mod, "readline", None)
    assert input_mod.has_readline() is False
    assert input_mod.get_last_history_match("x") is None
    input_mod.maybe_remove_last_history_item()
    input_mod.setup_readline(completer=completer, history_size=10)


def test_play_strategy_resolution_and_execution():
    local = strategy_mod.LocalPlayCommandStrategy(
        local_handler=lambda _state, text: (text == "move", False)
    )
    network = strategy_mod.NetworkPlayCommandStrategy(
        network_handler=lambda _state, text: text == "quit"
    )

    s_local = SimpleNamespace(network_client=None, has_unsaved_changes=False)
    chosen = strategy_mod.resolve_play_command_strategy(
        s_local,
        local_strategy=local,
        network_strategy=network,
    )
    assert chosen.execute(s_local, "move") == (True, False)

    s_net = SimpleNamespace(network_client=object(), has_unsaved_changes=True)
    chosen = strategy_mod.resolve_play_command_strategy(
        s_net,
        local_strategy=local,
        network_strategy=network,
    )
    assert chosen.execute(s_net, "quit") == (True, True)


def test_bootstrap_initialize_state_for_load_and_new_paths(capsys):
    class FakeBlitz:
        def __init__(self, *, enabled=False, time_limit_minutes=30):
            self._enabled = enabled
            self.time_limit_minutes = time_limit_minutes
            self.restored = None

        def restore_snapshot(self, snap):
            self.restored = snap
            self._enabled = bool(snap.get("enabled", False))
            self.time_limit_minutes = snap.get(
                "time_limit_minutes",
                self.time_limit_minutes,
            )

        def is_enabled(self):
            return self._enabled

    class FakeSession:
        def __init__(self, players=2):
            self.state = SimpleNamespace(
                player_positions={i: i for i in range(1, players + 1)},
                board_size=9,
            )
            self._attached = None

        def attach_blitz(self, blitz):
            self._attached = blitz

    config_load = SimpleNamespace(
        time_limit=15,
        blitz_enabled=False,
        ai_minimax_depth=None,
        ai_mode="iterative",
        ai_time=4,
        ai_mcts_selection="UCT",
        verbose=False,
        debug=False,
        walls_per_player=20,
    )

    state, should_break = bootstrap_mod.initialize_shell_state(
        config=config_load,
        save_file="/tmp/s.txt",
        shell_state_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        create_new_session=lambda _cfg: FakeSession(),
        fallback_player_types=lambda _cfg: {1: "human", 2: "human"},
        fallback_remaining_walls=lambda _cfg: {1: 20, 2: 20},
        load_session_from_file=lambda *_a, **_k: FakeSession(),
        load_blitz_snapshot_from_file=lambda _path: {
            "enabled": True,
            "time_limit_minutes": 9,
        },
        blitz_factory=lambda **kwargs: FakeBlitz(
            enabled=False,
            time_limit_minutes=kwargs["time_limit_minutes"],
        ),
        format_minutes=lambda m: f"{m:g}",
        print_state=lambda _session: None,
        print_blitz_times=lambda _blitz: None,
        session_ai_players=lambda _session: [1],
        auto_play_fn=lambda *_a, **_k: True,
        ai_mode_minimax="minimax",
        unbalanced_players_count=3,
        translate=lambda s: s,
    )
    assert state is None
    assert should_break is True
    out = capsys.readouterr().out
    assert "Loading game from /tmp/s.txt" in out
    assert "Game loaded with blitz timer state." in out

    config_new = SimpleNamespace(
        time_limit=30,
        blitz_enabled=True,
        ai_minimax_depth=2,
        ai_mode="minimax",
        ai_time=5,
        ai_mcts_selection="PUCT",
        verbose=True,
        debug=False,
        walls_per_player=8,
    )

    state, should_break = bootstrap_mod.initialize_shell_state(
        config=config_new,
        save_file=None,
        shell_state_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        create_new_session=lambda _cfg: FakeSession(players=3),
        fallback_player_types=lambda _cfg: {1: "human", 2: "human", 3: "human"},
        fallback_remaining_walls=lambda _cfg: {1: 20, 2: 20, 3: 20},
        load_session_from_file=lambda *_a, **_k: None,
        load_blitz_snapshot_from_file=lambda _path: None,
        blitz_factory=lambda **kwargs: FakeBlitz(
            enabled=("player_ids" in kwargs),
            time_limit_minutes=kwargs["time_limit_minutes"],
        ),
        format_minutes=lambda m: f"{m:g}",
        print_state=lambda _session: None,
        print_blitz_times=lambda _blitz: None,
        session_ai_players=lambda _session: [2],
        auto_play_fn=lambda *_a, **_k: False,
        ai_mode_minimax="minimax",
        unbalanced_players_count=3,
        translate=lambda s: s,
    )
    assert should_break is False
    assert state is not None
    assert state.players == 3
    assert state.ai_players == [2]
    assert state.ai_mcts_selection == "PUCT"
    out = capsys.readouterr().out
    assert "New game started (blitz: 30 min/player)." in out
    assert "warning: 3-player mode can be unbalanced." in out
