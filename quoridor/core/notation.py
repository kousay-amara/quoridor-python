"""
Quoridor notation conversion utilities.

This module acts as a bridge between standard algebraic notation
(e.g., 'e4', 'e4h') and the integer indices used by the game graph.
The coordinate system uses (0,0) for the top-left cell (a1).
"""


def get_node_from_notation(notation: str, size: int = 9) -> int:
    """
    Translates a cell notation (e.g., 'e4') into a node index.

    Args:
        notation: A string of 2 or more characters (e.g., 'a1' to 'i9').
        size: The size of the board.

    Returns:
        The corresponding node index (row * size + col).
    """
    text = notation.strip().lower()
    if len(text) < 2:
        raise ValueError(f"invalid cell notation: {notation}")

    col = ord(text[0]) - ord("a")
    row = int(text[1:]) - 1
    if col < 0 or col >= size or row < 0 or row >= size:
        raise ValueError(f"cell out of bounds: {notation}")
    return row * size + col


def get_notation_from_node(node: int, size: int = 9) -> str:
    """
    Translates a node index into algebraic notation (e.g., 40 -> 'e5').

    Args:
        node: The integer index of the node.
        size: The size of the board.

    Returns:
        A string representing the cell (e.g., 'e5').
    """
    row, col = divmod(node, size)
    col_char = chr(ord("a") + col)
    return f"{col_char}{row + 1}"


def get_edges_for_wall(notation: str, size: int = 9) -> list[tuple[int, int]]:
    """
    Translates a wall notation (e.g., 'e4h') into graph edges to be removed.

    An 'h' (horizontal) wall at 'e4' blocks vertical passages below
    'e4' and 'f4'. A 'v' (vertical) wall at 'e4' blocks horizontal
    passages to the right of 'e4' and 'e5'.

    Args:
        notation: 3-character string (e.g., 'e4h', 'a1v').
        size: The size of the board.

    Returns:
        A list of two tuples, each representing an edge (node1, node2).
    """
    text = notation.strip().lower()
    if len(text) < 3:
        raise ValueError(f"invalid wall notation: {notation}")

    orientation = text[-1]
    if orientation not in {"h", "v"}:
        raise ValueError(f"invalid wall orientation in notation: {notation}")

    base_notation = text[:-1]
    col = ord(base_notation[0]) - ord("a")
    row = int(base_notation[1:]) - 1

    # Wall anchors must be inside intersections:
    # on 9x9 board: cols a..h and rows 1..8.
    if row < 0 or row >= size - 1 or col < 0 or col >= size - 1:
        raise ValueError(
            f"wall anchor out of bounds: {notation} "
            f"(valid columns a-{chr(ord('a') + size - 2)}, rows 1-{size - 1})"
        )

    node = row * size + col
    edges = []
    if orientation == "h":
        edges.append((node, node + size))
        edges.append((node + 1, node + 1 + size))

    elif orientation == "v":
        edges.append((node, node + 1))
        edges.append((node + size, node + size + 1))

    return edges


def get_edges_for_wall_at(
    row: int, col: int, orientation: str, size: int
) -> list[tuple[int, int]]:
    node = row * size + col
    edges = []
    if orientation == "h":
        edges.append((node, node + size))
        edges.append((node + 1, node + 1 + size))

    elif orientation == "v":
        edges.append((node, node + 1))
        edges.append((node + size, node + size + 1))
    return edges
