import pytest
from src.quoridor.graph import Graph

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
    assert g.has_path(node=76, target_row=0) == True

def test_has_path_blocked():
    """Vérifie que l'algorithme détecte quand un joueur est complètement enfermé."""
    g = Graph(size=9)
    # On enferme la case 0 en coupant ses deux seuls accès (vers 1 et 9)
    g.remove_edge(0, 1)
    g.remove_edge(0, 9)
    # La case 0 ne peut plus atteindre la ligne 8 (ou n'importe quelle autre ligne)
    assert g.has_path(node=0, target_row=8) == False