from quoridor.application.contest import run_contest


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
