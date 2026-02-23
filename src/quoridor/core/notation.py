"""
Quoridor notation conversion utilities.

This module acts as a bridge between standard algebraic notation (e.g., 'e4', 'e4h')
and the integer indices used by the game graph.
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
    col = ord(notation[0].lower()) - ord('a')
    row = int(notation[1:]) - 1
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
    col_char = chr(ord('a') + col)
    return f"{col_char}{row + 1}"


def get_edges_for_wall(notation: str, size: int = 9) -> list[tuple[int, int]]:
    """
    Translates a wall notation (e.g., 'e4h') into graph edges to be removed.
    
    An 'h' (horizontal) wall at 'e4' blocks vertical passages below 'e4' and 'f4'.
    A 'v' (vertical) wall at 'e4' blocks horizontal passages to the right of 'e4' and 'e5'.
    
    Args:
        notation: 3-character string (e.g., 'e4h', 'a1v').
        size: The size of the board.
        
    Returns:
        A list of two tuples, each representing an edge (node1, node2).
    """
    base_notation = notation[:2]
    orientation = notation[2].lower()

    node = get_node_from_notation(base_notation, size)
    edges = []
    if orientation == 'h':
        # Mur horizontal : bloque entre (row, col) et (row+1, col) ET entre (row, col+1) et (row+1, col+1)
        edges.append((node, node + size))
        edges.append((node + 1, node + 1 + size))
    elif orientation == 'v':
        # Mur vertical : bloque entre (row, col) et (row, col+1) ET entre (row+1, col) et (row+1, col+1)
        edges.append((node, node + 1))
        edges.append((node + size, node + size + 1))
    
    return edges