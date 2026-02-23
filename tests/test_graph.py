import pytest
from src.utils.graph import Graph
from src.quoridor.rules.pawn_rules import is_walk_legal
from src.quoridor.rules.pathfinding import has_path
from src.quoridor.rules.wall_rules import is_wall_legal

def test_initialization():
    """Vérifie que le graphe a la bonne taille et les bonnes connexions au départ."""
    g = Graph(size=9)
    assert g.nodes == 81
    # La case 0 (coin) doit avoir exactement 2 voisins (droite et bas)
    assert len(g.adj[0]) == 2
    # La case 40 (centre) doit avoir 4 voisins
    assert len(g.adj[40]) == 4

def test_remove_edge():
    """Vérifie que la suppression d'une arête fonctionne (pose d'un mur)."""
    g = Graph(size=9)
    # On supprime le lien entre la case 0 et la case 1
    g.remove_edge(0, 1)
    assert 1 not in g.adj[0]
    assert 0 not in g.adj[1]

def test_has_path_success():
    """Vérifie qu'un chemin est trouvé quand il n'y a pas d'obstacle majeur."""
    g = Graph(size=9)
    # Un joueur en (8,4) soit l'index 76 doit pouvoir atteindre la ligne 0
    assert has_path(g, node=76, target_row=0) is True

def test_has_path_blocked():
    """Vérifie que l'algorithme détecte quand un joueur est complètement enfermé."""
    g = Graph(size=9)
    # On enferme la case 0 en coupant ses deux seuls accès (vers 1 et 9)
    g.remove_edge(0, 1)
    g.remove_edge(0, 9)
    # La case 0 ne peut plus atteindre la ligne 8 (ou n'importe quelle autre ligne)
    assert has_path(g, node=0, target_row=8) is False


def test_is_walk_legal_neighbor():
    """Déplacement vers une case voisine sans mur est légal."""
    g = Graph(size=9)
    assert is_walk_legal(g, 40, 31) is True   # centre vers haut
    assert is_walk_legal(g, 40, 49) is True   # centre vers bas
    assert is_walk_legal(g, 40, 39) is True   # centre vers gauche
    assert is_walk_legal(g, 40, 41) is True   # centre vers droite


def test_is_walk_legal_not_neighbor():
    """Déplacement vers une case non voisine est illégal."""
    g = Graph(size=9)
    assert is_walk_legal(g, 0, 2) is False
    assert is_walk_legal(g, 0, 18) is False
    assert is_walk_legal(g, 40, 0) is False


def test_is_walk_legal_after_wall():
    """Après pose d'un mur entre deux cases, le déplacement entre elles est illégal."""
    g = Graph(size=9)
    assert is_walk_legal(g, 0, 1) is True
    g.remove_edge(0, 1)
    assert is_walk_legal(g, 0, 1) is False


def test_is_walk_legal_bounds():
    """Cases hors plateau : déplacement illégal."""
    g = Graph(size=9)
    assert is_walk_legal(g, 0, -1) is False
    assert is_walk_legal(g, 0, 81) is False
    assert is_walk_legal(g, -1, 0) is False


def test_is_wall_legal_ok():
    """Pose d'un mur qui ne bloque aucun joueur : légal."""
    g = Graph(size=9)
    # Joueur 0 en 0 vise ligne 8, joueur 1 en 80 vise ligne 0. Mur au centre (40-41) ne les bloque pas.
    assert is_wall_legal(
        g,
        player_positions=[0, 80],
        wall_edges=[(40, 41)],
    ) is True
    # Le graphe est inchangé après le test (simulation + restauration)
    assert 41 in g.adj[40]
    assert 40 in g.adj[41]


def test_is_wall_legal_blocked():
    """Pose d'un mur qui enferme un joueur : illégal."""
    g = Graph(size=9)
    # Joueur 0 en case 0 doit atteindre ligne 8. Si on coupe (0,1) et (0,9), il est bloqué.
    assert is_wall_legal(
        g,
        player_positions=[0],
        wall_edges=[(0, 1), (0, 9)],
        player_targets=[(8, None)],
    ) is False
    # Graphe restauré
    assert 1 in g.adj[0]
    assert 9 in g.adj[0]


def test_is_wall_legal_empty_edges():
    """Aucune arête à bloquer : toujours légal."""
    g = Graph(size=9)
    assert is_wall_legal(g, player_positions=[0, 80], wall_edges=[]) is True


def test_is_wall_legal_invalid_edge():
    """Mur sur une arête inexistante (cases non voisines) : illégal."""
    g = Graph(size=9)
    assert is_wall_legal(
        g,
        player_positions=[0, 80],
        wall_edges=[(0, 2)],  # 0 et 2 ne sont pas voisines
    ) is False
