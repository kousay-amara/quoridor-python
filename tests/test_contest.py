import pytest

from quoridor.application.contest import run_contest
from quoridor.interfaces.contest_parser import ContestError, parse_contest_file


def test_contest_respects_horizontal_wall(tmp_path):
    content = """[game]
1
_ _ _
. X .
_ 1 _
. . .
_ _ 2
"""
    game_file = tmp_path / "contest.txt"
    game_file.write_text(content, encoding="utf-8")

    move = run_contest(game_file)

    assert move == "b2-b3"


def test_contest_respects_vertical_wall(tmp_path):
    content = """[game]
1
_ _ _
. . .
_ 1 X_
. . .
_ _ 2
"""
    game_file = tmp_path / "contest.txt"
    game_file.write_text(content, encoding="utf-8")

    move = run_contest(game_file)

    assert move == "b2-b3"


def test_contest_uses_search_not_lexicographic_first_pawn_move(tmp_path):
    content = """[game]
1
1 _ _ _ _
. . . . .
_ _ _ _ _
. . . . .
2 _ _ _ _
. . . . .
_ _ _ _ _
. . . . .
_ _ _ _ _
walls: 0 0
"""
    game_file = tmp_path / "contest.txt"
    game_file.write_text(content, encoding="utf-8")

    move = run_contest(game_file)

    # Lexicographically first legal pawn move is a1-a2, but search picks a1-b1.
    assert move == "a1-b1"


def test_parse_contest_reports_line_for_missing_current_player(tmp_path):
    game_file = tmp_path / "contest.txt"
    game_file.write_text("[game]\n", encoding="utf-8")

    with pytest.raises(ContestError, match=r"missing current player at line 2"):
        parse_contest_file(game_file)


def test_parse_contest_reports_line_for_missing_board_data(tmp_path):
    game_file = tmp_path / "contest.txt"
    game_file.write_text("[game]\n1\n", encoding="utf-8")

    with pytest.raises(ContestError, match=r"missing board data at line 3"):
        parse_contest_file(game_file)


def test_parse_contest_reports_line_for_invalid_board_size(tmp_path):
    game_file = tmp_path / "contest.txt"
    game_file.write_text("[game]\n1\n_ _\n", encoding="utf-8")

    with pytest.raises(ContestError, match=r"invalid board size at line 3: 2"):
        parse_contest_file(game_file)


def test_parse_contest_reports_line_for_incomplete_board_data(tmp_path):
    game_file = tmp_path / "contest.txt"
    game_file.write_text("[game]\n1\n_ _ _\n. . .\n", encoding="utf-8")

    with pytest.raises(
        ContestError,
        match=r"incomplete board data at line 3: expected 5 lines, got 2",
    ):
        parse_contest_file(game_file)


def test_parse_contest_reports_declared_line_for_missing_current_player_on_board(
    tmp_path,
):
    game_file = tmp_path / "contest.txt"
    game_file.write_text(
        "[game]\n1\n_ _ _\n. . .\n_ _ _\n. . .\n_ _ 2\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ContestError,
        match=r"current player 1 not on board \(declared at line 2\)",
    ):
        parse_contest_file(game_file)
