from quoridor.application.blitz import Blitz


def test_disabled_blitz_has_no_timer():
    blitz = Blitz(time_limit_minutes=0)

    assert blitz.is_enabled() is False
    assert blitz.input_timeout_for(1) is None


def test_blitz_for_players_initializes_same_time_for_everyone():
    blitz = Blitz(time_limit_minutes=1, player_ids=[3, 1, 2])

    assert blitz.is_enabled() is True
    assert blitz.remaining_times() == {1: 60.0, 2: 60.0, 3: 60.0}
    assert blitz.input_timeout_for(2) == 60.0


def test_consume_time_reduces_remaining_time():
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])

    timed_out = blitz.consume_time(1, 12.5)

    assert timed_out is False
    assert blitz.remaining_time(1) == 47.5
    assert blitz.remaining_time(2) == 60.0


def test_consume_time_and_expire_player_stop_at_zero():
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])

    assert blitz.consume_time(1, 61.0) is True
    assert blitz.remaining_time(1) == 0.0

    blitz.expire_player(2)

    assert blitz.remaining_time(2) == 0.0


def test_paused_blitz_does_not_consume_time():
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])

    assert blitz.toggle_pause() is True
    assert blitz.input_timeout_for(1) is None
    assert blitz.consume_time(1, 20.0) is False
    assert blitz.remaining_time(1) == 60.0
    assert blitz.toggle_pause() is False
    assert blitz.input_timeout_for(1) == 60.0
