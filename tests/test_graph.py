import pytest
from quoridor.utils.graph import Graph
from quoridor.utils.graph import bfs_has_path
from quoridor.core.board import QuoridorBoard
from quoridor.rules.pawn_rules import is_walk_legal
from quoridor.rules.pawn_rules import get_all_legal_pawn_moves
from quoridor.rules.wall_rules import is_wall_legal
from quoridor.core.notation import get_edges_for_wall
from quoridor.core.notation import get_notation_from_node

# --- Définition des lambdas de victoire pour les tests ---
TARGET_L8 = lambda n: (n // 9) == 8
TARGET_L0 = lambda n: (n // 9) == 0


def test_initialization():
    """Vérifie que le plateau initialise correctement son graphe interne."""
    board = QuoridorBoard(size=9)
    # Le graphe doit avoir 81 nœuds (0 à 80)
    assert len(board.graph.adj) == 81
    # La case 0 (coin) doit avoir exactement 2 voisins (1 et 9)
    assert len(board.graph.adj[0]) == 2
    # La case 40 (centre) doit avoir 4 voisins
    assert len(board.graph.adj[40]) == 4


def test_remove_edge_on_graph():
    """Vérifie que la suppression d'une arête sur le graphe générique fonctionne."""
    g = Graph()
    g.add_edge(0, 1)
    assert 1 in g.adj[0]
    g.remove_edge(0, 1)
    assert 1 not in g.adj[0]
    assert 0 not in g.adj.get(1, [])


def test_bfs_has_path_success():
    """Vérifie que bfs_has_path trouve un chemin avec une lambda."""
    board = QuoridorBoard(size=9)
    # Un joueur en 76 (ligne 8) doit pouvoir atteindre la ligne 0
    assert bfs_has_path(board.graph, 76, TARGET_L0) is True


def test_bfs_has_path_blocked():
    """Vérifie que l'algorithme détecte quand un joueur est enfermé."""
    board = QuoridorBoard(size=9)
    # On enferme la case 0
    board.graph.remove_edge(0, 1)
    board.graph.remove_edge(0, 9)
    # La case 0 ne peut plus atteindre la ligne 8
    assert bfs_has_path(board.graph, 0, TARGET_L8) is False


def test_is_walk_legal():
    """Vérifie la légalité d'un déplacement de pion simple."""
    board = QuoridorBoard(size=9)
    # Déplacement normal
    assert is_walk_legal(board.graph, 40, 31) is True
    # Après mur
    board.graph.remove_edge(40, 31)
    assert is_walk_legal(board.graph, 40, 31) is False


def test_is_wall_legal_ok():
    """Pose d'un mur qui ne bloque personne : légal."""
    board = QuoridorBoard(size=9)
    # Joueur 1 en 0 vise ligne 8, Joueur 2 en 80 vise ligne 0
    positions = [0, 80]
    targets = [TARGET_L8, TARGET_L0]
    mur = [(40, 41), (49, 50)]  # Un mur vertical au milieu

    assert is_wall_legal(board.graph, positions, mur, targets) is True
    # Vérification que le graphe a été restauré
    assert 41 in board.graph.adj[40]


def test_is_wall_legal_blocked():
    """Pose d'un mur qui enferme un joueur : illégal."""
    board = QuoridorBoard(size=9)
    positions = [0]
    targets = [TARGET_L8]
    # On tente de couper les deux seules sorties de la case 0
    mur_interdit = [(0, 1), (0, 9)]

    assert is_wall_legal(board.graph, positions, mur_interdit, targets) is False
    # Vérification que le graphe a été restauré malgré l'échec
    assert 1 in board.graph.adj[0]
    assert 9 in board.graph.adj[0]


def test_is_wall_legal_invalid_edge():
    """Mur sur une arête inexistante : illégal."""
    board = QuoridorBoard(size=9)
    # 0 et 2 ne sont pas voisins, l'arête n'existe pas
    assert is_wall_legal(board.graph, [0], [(0, 2)], [TARGET_L8]) is False


def test_get_all_legal_pawn_moves_simple():
    board = QuoridorBoard(size=9)
    # Au centre (40), sans adversaire, on doit avoir 4 mouvements
    moves = get_all_legal_pawn_moves(board.graph, 40, [40])
    assert len(moves) == 4
    assert 31 in moves
    assert 49 in moves
    assert 39 in moves
    assert 41 in moves


def test_custom_board_size_uses_correct_adjacency_and_moves():
    board = QuoridorBoard(size=5)

    assert len(board.graph.adj) == 25
    assert sorted(board.graph.adj[7]) == [2, 6, 8, 12]
    assert sorted(board.graph.adj[12]) == [7, 11, 13, 17]

    moves = sorted(get_all_legal_pawn_moves(board.graph, 7, [7, 13]))
    assert moves == [2, 6, 8, 12]
    assert 16 not in moves


def test_is_walk_legal_invalid_nodes():
    """Couvre la ligne 9 : nœuds inexistants."""
    board = QuoridorBoard(size=9)
    # Test avec un index hors limites
    assert is_walk_legal(board.graph, 40, 999) is False
    assert is_walk_legal(board.graph, -1, 40) is False


def test_pawn_jump_straight():
    """Couvre les lignes 26-30 : Saut par-dessus un adversaire."""
    board = QuoridorBoard(size=9)
    player_pos = 40
    opponent_pos = 31  # Juste au-dessus

    # On demande les coups possibles avec un adversaire en 31
    moves = get_all_legal_pawn_moves(
        board.graph, player_pos, [player_pos, opponent_pos]
    )

    # On doit pouvoir sauter en 22 (31 + (31-40))
    assert 22 in moves
    # La case de l'adversaire (31) ne doit PAS être dans les coups
    assert 31 not in moves


def test_pawn_jump_diagonal():
    """Couvre les lignes 33-39 : Saut diagonal quand le saut direct est bloqué."""
    board = QuoridorBoard(size=9)
    player_pos = 4  # Bord haut du plateau
    opponent_pos = 13  # En dessous du joueur

    # Le saut direct vers 22 est possible par défaut,
    # mais si on met un mur entre 13 et 22, le saut devient diagonal.
    board.graph.remove_edge(13, 22)

    moves = get_all_legal_pawn_moves(
        board.graph, player_pos, [player_pos, opponent_pos]
    )

    # Le saut vers 22 est impossible, on doit trouver les voisins de 13 : 12 et 14
    assert 22 not in moves
    assert 12 in moves
    assert 14 in moves


def test_pawn_jump_blocked_by_two_opponents():
    """Couvre la ligne 32 (le 'pass') : Deux adversaires à la suite."""
    board = QuoridorBoard(size=9)
    # Joueur en 40, adversaires en 31 et 22
    moves = get_all_legal_pawn_moves(board.graph, 40, [40, 31, 22])

    # On ne peut pas sauter en 22 car occupé, et le code fait 'pass'
    # pour cette direction si aucune diagonale n'est possible (si murs présents par ex)
    assert 22 not in moves


def test_get_edges_for_wall():
    # Sur un plateau 9x9, 'a1h' devrait bloquer (0,9) et (1,10)
    edges = get_edges_for_wall("a1h", size=9)
    assert (0, 9) in edges
    assert (1, 10) in edges

    # 'a1v' devrait bloquer (0,1) et (9,10)
    edges = get_edges_for_wall("a1v", size=9)
    assert (0, 1) in edges
    assert (9, 10) in edges


def test_get_notation_from_node():
    """
    Tests the conversion from node index to algebraic notation.
    Size 9 board: 0 is 'a1', 80 is 'i9'.
    """
    size = 9

    # Test corners
    assert get_notation_from_node(0, size) == "a1"
    assert get_notation_from_node(8, size) == "i1"
    assert get_notation_from_node(72, size) == "a9"
    assert get_notation_from_node(80, size) == "i9"

    # Test center (e5)
    assert get_notation_from_node(40, size) == "e5"

    # Test random positions
    assert get_notation_from_node(20, size) == "c3"
    assert get_notation_from_node(61, size) == "h7"
