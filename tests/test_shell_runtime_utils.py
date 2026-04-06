from __future__ import annotations

from types import SimpleNamespace

from quoridor.interfaces.shell import runtime as runtime_mod


class _FakeBlitz:
    def __init__(
        self,
        *,
        enabled: bool = False,
        paused: bool = False,
        timeout: float | None = None,
        consume_timeout: bool = False,
        remaining: float = 5.0,
    ) -> None:
        self._enabled = enabled
        self.paused = paused
        self._timeout = timeout
        self._consume_timeout = consume_timeout
        self._remaining = remaining
        self.expired: list[int] = []

    def is_enabled(self) -> bool:
        return self._enabled

    def remaining_time(self, _pid: int) -> float:
        return self._remaining

    def snapshot(self):
        return {"enabled": self._enabled}

    def input_timeout_for(self, _pid: int):
        return self._timeout

    def expire_player(self, pid: int) -> None:
        self.expired.append(pid)

    def consume_time(self, _pid: int, _elapsed: float) -> bool:
        return self._consume_timeout


def test_alarm_helpers_and_effective_ai_time_limit(monkeypatch):
    assert runtime_mod.start_blitz_alarm(None) == (False, None)
    assert runtime_mod.start_blitz_alarm(0) == (False, None)

    monkeypatch.setattr(runtime_mod.signal, "getsignal", lambda _sig: "prev")
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(
        runtime_mod.signal,
        "signal",
        lambda sig, handler: events.append(("signal", (sig, handler))),
    )
    monkeypatch.setattr(
        runtime_mod.signal,
        "setitimer",
        lambda timer, sec: events.append(("itimer", (timer, sec))),
    )
    started, previous = runtime_mod.start_blitz_alarm(0.2)
    assert started is True
    assert previous == "prev"

    runtime_mod.stop_blitz_alarm(True, previous)
    assert any(kind == "itimer" for kind, _ in events)

    monkeypatch.setattr(
        runtime_mod.signal,
        "getsignal",
        lambda _sig: (_ for _ in ()).throw(AttributeError),
    )
    assert runtime_mod.start_blitz_alarm(1) == (False, None)

    blitz_off = _FakeBlitz(enabled=False)
    blitz_on = _FakeBlitz(enabled=True, remaining=2.5)
    assert (
        runtime_mod.effective_ai_time_limit(
            7,
            blitz=blitz_off,
            player_id=1,
        )
        == 7.0
    )
    assert (
        runtime_mod.effective_ai_time_limit(
            7,
            blitz=blitz_on,
            player_id=1,
        )
        == 2.5
    )


def test_pause_blocks_and_handle_timeout_emits_and_reports(capsys):
    printed: list[str] = []
    assert (
        runtime_mod.pause_blocks_gameplay(
            _FakeBlitz(paused=True), print_fn=printed.append
        )
        is True
    )
    assert printed == ["Game is paused."]

    session = SimpleNamespace(
        timeout_player=lambda loser_id, before_blitz_snapshot=None: (
            None,
            2 if loser_id == 1 else None,
        ),
        game_outcome=lambda: SimpleNamespace(status="winner", winner_id=2),
    )
    events: list[tuple[str, dict]] = []
    event_bus = SimpleNamespace(
        emit=lambda name, **payload: events.append((name, payload))
    )
    stop = runtime_mod.handle_timeout(
        session,
        1,
        print_state=lambda _s: print("STATE"),
        event_bus=event_bus,
    )
    out = capsys.readouterr().out
    assert stop is True
    assert "Player 1 ran out of time and loses." in out
    assert "Player 2 wins!" in out
    assert ("game.timeout", {"loser_id": 1, "winner_id": 2}) in events


def test_auto_play_ai_until_human_or_end_winner_and_timeout_paths(capsys):
    state = SimpleNamespace(current_player=1)
    session = SimpleNamespace(
        state=state,
        player_types={1: "ai", 2: "human"},
        compute_ai_move=lambda **_kwargs: ("pawn", 13),
        apply_ai_move=lambda _move, player_id: setattr(state, "current_player", 2),
        game_outcome=lambda: SimpleNamespace(status="winner", winner_id=1),
    )
    events: list[str] = []
    should_break = runtime_mod.auto_play_ai_until_human_or_end(
        session,
        ai_mode="minimax",
        ai_time=3,
        ai_minimax_depth=2,
        blitz=_FakeBlitz(enabled=False),
        print_state=lambda _s: print("STATE"),
        timeout_handler=lambda *_a, **_k: False,
        event_bus=SimpleNamespace(emit=lambda name, **_payload: events.append(name)),
    )
    out = capsys.readouterr().out
    assert should_break is True
    assert "AI player 1 played." in out
    assert "Player 1 wins!" in out
    assert "game.winner" in events

    state_t = SimpleNamespace(current_player=1)
    session_t = SimpleNamespace(
        state=state_t,
        player_types={1: "ai"},
        compute_ai_move=lambda **_kwargs: ("pawn", 13),
        apply_ai_move=lambda *_a, **_k: None,
        game_outcome=lambda: SimpleNamespace(status="ongoing", winner_id=None),
    )
    timed_out = runtime_mod.auto_play_ai_until_human_or_end(
        session_t,
        ai_mode="minimax",
        ai_time=3,
        ai_minimax_depth=2,
        blitz=_FakeBlitz(enabled=True, consume_timeout=True),
        print_state=lambda _s: None,
        timeout_handler=lambda *_a, **_k: True,
    )
    assert timed_out is True


def test_run_auto_play_interrupt_handling_and_input_paths(monkeypatch, capsys):
    called = {"count": 0}

    def ok_auto_play(*_args, **_kwargs):
        called["count"] += 1
        return True

    result = runtime_mod.run_auto_play_with_interrupt_handling(
        SimpleNamespace(),
        "minimax",
        1,
        1,
        blitz=_FakeBlitz(),
        auto_play_fn=ok_auto_play,
    )
    assert result == (True, False)
    assert called["count"] == 1

    events: list[str] = []

    def interrupting(*_args, **_kwargs):
        raise KeyboardInterrupt

    result = runtime_mod.run_auto_play_with_interrupt_handling(
        SimpleNamespace(),
        "minimax",
        1,
        1,
        blitz=_FakeBlitz(),
        auto_play_fn=interrupting,
        event_bus=SimpleNamespace(emit=lambda name, **_payload: events.append(name)),
    )
    assert result == (False, True)
    assert "shell.interrupted" in events

    state = SimpleNamespace(
        session=SimpleNamespace(state=SimpleNamespace(current_player=1)),
        blitz=_FakeBlitz(enabled=True, timeout=0.0),
        has_unsaved_changes=False,
    )
    line, should_break = runtime_mod.read_shell_input(
        state,
        ">> ",
        timeout_handler=lambda *_a, **_k: False,
        input_fn=lambda _prompt: "ignored",
    )
    assert (line, should_break) == ("", False)
    assert state.has_unsaved_changes is True

    state2 = SimpleNamespace(
        session=SimpleNamespace(state=SimpleNamespace(current_player=1)),
        blitz=_FakeBlitz(enabled=False, timeout=None, consume_timeout=False),
        has_unsaved_changes=False,
    )
    line, should_break = runtime_mod.read_shell_input(
        state2,
        ">> ",
        timeout_handler=lambda *_a, **_k: False,
        input_fn=lambda _prompt: " help  ",
    )
    assert (line, should_break) == ("help", False)

    state3 = SimpleNamespace(
        session=SimpleNamespace(state=SimpleNamespace(current_player=1)),
        blitz=_FakeBlitz(enabled=False, timeout=None),
        has_unsaved_changes=False,
    )
    line, should_break = runtime_mod.read_shell_input(
        state3,
        ">> ",
        timeout_handler=lambda *_a, **_k: False,
        input_fn=lambda _prompt: (_ for _ in ()).throw(EOFError),
    )
    assert (line, should_break) == (None, True)

    state4 = SimpleNamespace(
        session=SimpleNamespace(state=SimpleNamespace(current_player=1)),
        blitz=_FakeBlitz(enabled=True, timeout=None),
        has_unsaved_changes=False,
    )
    line, should_break = runtime_mod.read_shell_input(
        state4,
        ">> ",
        timeout_handler=lambda *_a, **_k: False,
        input_fn=lambda _prompt: (_ for _ in ()).throw(runtime_mod.BlitzInputTimeout),
    )
    assert (line, should_break) == ("", False)
    assert state4.blitz.expired == [1]

    out = capsys.readouterr().out
    assert "\n" in out
