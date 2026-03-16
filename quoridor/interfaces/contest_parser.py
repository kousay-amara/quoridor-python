"""Contest input parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class ContestError(ValueError):
    """Raised when contest input is invalid."""


_BLOCK_COMMENT_RE = re.compile(r"\{.*?\}", re.DOTALL)
_CELL_TOKEN_PATTERN = re.compile(r"^X?[_1-4]$")


@dataclass(frozen=True)
class ContestPosition:
    size: int
    current_player: int
    positions: dict[int, int]
    remaining_walls: dict[int, int]
    vertical_walls: list[tuple[int, int]]
    horizontal_walls: list[tuple[int, int]]


def _strip_block_comments(text: str) -> str:
    return _BLOCK_COMMENT_RE.sub("", text)


def _strip_inline_comment(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def _tokenize(line: str) -> list[str]:
    return [tok for tok in line.strip().split() if tok]


def _parse_cell_token(token: str, *, line_no: int, col_no: int) -> tuple[bool, str]:
    if not _CELL_TOKEN_PATTERN.match(token):
        raise ContestError(
            f"invalid cell token at line {line_no}, column {col_no}: {token}"
        )
    if token.startswith("X"):
        return True, token[1]
    return False, token[0]


def _parse_cell_row(
    *,
    line_no: int,
    line: str,
    row: int,
    size: int,
    positions: dict[int, int],
    vertical_walls: list[tuple[int, int]],
) -> None:
    tokens = _tokenize(line)
    if len(tokens) != size:
        raise ContestError(
            f"invalid cell row length at line {line_no}: "
            f"expected {size} tokens, got {len(tokens)}"
        )
    for col, tok in enumerate(tokens):
        has_vwall, cell = _parse_cell_token(tok, line_no=line_no, col_no=col + 1)
        if has_vwall and col > 0:
            left = row * size + (col - 1)
            right = row * size + col
            vertical_walls.append((left, right))
        if cell.isdigit():
            player_id = int(cell)
            if player_id in positions:
                raise ContestError(
                    f"duplicate player id at line {line_no}, column {col + 1}: {player_id}"
                )
            positions[player_id] = row * size + col


def _parse_separator_row(
    *,
    line_no: int,
    line: str,
    row: int,
    size: int,
    horizontal_walls: list[tuple[int, int]],
) -> None:
    tokens = _tokenize(line)
    if len(tokens) != size:
        raise ContestError(
            f"invalid separator row length at line {line_no}: "
            f"expected {size} tokens, got {len(tokens)}"
        )
    for col, tok in enumerate(tokens):
        if tok == "X":
            top = row * size + col
            bottom = (row + 1) * size + col
            horizontal_walls.append((top, bottom))
        elif tok != ".":
            raise ContestError(
                f"invalid separator token at line {line_no}, column {col + 1}: {tok}"
            )


def _parse_board_lines(
    lines: list[tuple[int, str]],
) -> tuple[int, dict[int, int], list[tuple[int, int]], list[tuple[int, int]]]:
    if not lines:
        raise ContestError("missing board data")

    first_tokens = _tokenize(lines[0][1])
    if not first_tokens:
        raise ContestError("missing board data")
    size = len(first_tokens)
    if size < 3 or size > 15 or size % 2 == 0:
        raise ContestError(f"invalid board size: {size}")

    expected_lines = size * 2 - 1
    if len(lines) < expected_lines:
        raise ContestError(
            f"incomplete board data: expected {expected_lines} lines, got {len(lines)}"
        )

    positions: dict[int, int] = {}
    vertical_walls: list[tuple[int, int]] = []
    horizontal_walls: list[tuple[int, int]] = []

    cursor = 0
    for row in range(size):
        cell_line_no, cell_line = lines[cursor]
        cursor += 1
        _parse_cell_row(
            line_no=cell_line_no,
            line=cell_line,
            row=row,
            size=size,
            positions=positions,
            vertical_walls=vertical_walls,
        )

        if row < size - 1:
            sep_line_no, sep_line = lines[cursor]
            cursor += 1
            _parse_separator_row(
                line_no=sep_line_no,
                line=sep_line,
                row=row,
                size=size,
                horizontal_walls=horizontal_walls,
            )

    return size, positions, vertical_walls, horizontal_walls


def _parse_walls_line(
    line: str,
    *,
    player_ids: list[int],
    line_no: int,
) -> dict[int, int]:
    if not line.lower().startswith("walls:"):
        raise ContestError(f"invalid walls line at line {line_no}")

    tokens = _tokenize(line.split(":", 1)[1])
    if len(tokens) != len(player_ids):
        raise ContestError(
            f"invalid walls count at line {line_no}: "
            f"expected {len(player_ids)} values, got {len(tokens)}"
        )

    try:
        return {pid: int(token) for pid, token in zip(player_ids, tokens, strict=True)}
    except ValueError as exc:
        raise ContestError(f"invalid walls value at line {line_no}") from exc


def parse_contest_file(path: str | Path) -> ContestPosition:
    raw = Path(path).read_text(encoding="utf-8")
    text = _strip_block_comments(raw)

    lines: list[tuple[int, str]] = []
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_inline_comment(raw_line).strip()
        if line:
            lines.append((idx, line))

    try:
        game_idx = next(
            i for i, (_, line) in enumerate(lines) if line.lower() == "[game]"
        )
    except StopIteration as exc:
        raise ContestError("missing [game] section") from exc

    cursor = game_idx + 1
    if cursor >= len(lines):
        raise ContestError("missing current player")
    try:
        current_player = int(lines[cursor][1].split()[0])
    except ValueError as exc:
        raise ContestError(
            f"invalid current player at line {lines[cursor][0]}"
        ) from exc
    cursor += 1

    board_lines: list[tuple[int, str]] = []
    while cursor < len(lines):
        _line_no, line = lines[cursor]
        if line.startswith("[") and line.endswith("]"):
            break
        if line.lower().startswith("walls:"):
            break
        board_lines.append(lines[cursor])
        cursor += 1

    size, positions, vertical_walls, horizontal_walls = _parse_board_lines(board_lines)
    if current_player not in positions:
        raise ContestError(f"current player {current_player} not on board")

    remaining_walls: dict[int, int] = {}
    if cursor < len(lines) and lines[cursor][1].lower().startswith("walls:"):
        remaining_walls = _parse_walls_line(
            lines[cursor][1],
            player_ids=sorted(positions),
            line_no=lines[cursor][0],
        )

    return ContestPosition(
        size=size,
        current_player=current_player,
        positions=positions,
        remaining_walls=remaining_walls,
        vertical_walls=vertical_walls,
        horizontal_walls=horizontal_walls,
    )
