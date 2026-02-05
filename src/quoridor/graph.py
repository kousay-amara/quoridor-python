"""
Graphe du plateau Quoridor : cases en nœuds, déplacements possibles en arêtes.

Les murs sont représentés par l'absence d'arête entre deux cases adjacentes.
"""

from collections import deque


class Graph:
    """
    Plateau de jeu modélisé en graphe (grille 4-connexe).

    Attributes:
        size: Côté du plateau (grille size x size).
        nodes: Nombre de cases (size * size).
        adj: Dictionnaire qui relie chaque nœud (int) à la liste de ses voisins
            accessibles (sans mur entre eux).
    """

    def __init__(self, size=9):
        """
        Initialise le plateau sous forme de graphe.

        Args:
            size: Côté du plateau (défaut 9, grille 9x9).
        """
        self.size = size
        self.nodes = size * size
        self.adj = {}
        for i in range(self.nodes):
            self.adj[i] = self.get_initial_neighbors(i)

    def get_initial_neighbors(self, node):
        """
        Calcule les voisins d'une case sans aucun mur (grille 4-connexe).

        Args:
            node: Index du nœud (0..nodes-1).

        Returns:
            Liste des nœuds voisins (haut, bas, gauche, droite selon les bords).
        """
        neighbors = []
        row, col = divmod(node, self.size)

        if row > 0 : neighbors.append(node - self.size)
        if row < self.size - 1 : neighbors.append(node + self.size)
        if col > 0 : neighbors.append(node - 1)
        if col < self.size - 1 : neighbors.append(node + 1)

        return neighbors
    
    def remove_edge(self, node1, node2):
        """
        Supprime le lien entre deux cases (pose d'un mur entre elles).

        Args:
            node1: Première case.
            node2: Deuxième case (doit être voisine de node1).
        """
        if node2 in self.adj[node1] :
            self.adj[node1].remove(node2)
        
        if node1 in self.adj[node2] :
            self.adj[node2].remove(node1)


    def has_path(self, node, target_row = None, target_col = None):
        """
        BFS pour trouver un chemin valide depuis un nœud vers une ligne ou colonne de victoire.

        On part du nœud de départ et on cherche à atteindre la ligne target_row
        et/ou la colonne target_col (selon le mode 2 ou 4 joueurs). À chaque nœud
        visité, on vérifie si la ligne ou colonne de victoire est atteinte.

        Args:
            node: Nœud de départ.
            target_row: Ligne à atteindre (None pour ignorer).
            target_col: Colonne à atteindre (None pour ignorer).

        Returns:
            True si un chemin existe vers la cible, False sinon.
        """
        visited = {node}
        queue = deque([node])

        while queue :
            curr = queue.popleft()
            curr_row, curr_col = divmod(curr, self.size)
            if target_row is not None and curr_row == target_row :
                return True
            if target_col is not None and curr_col == target_col :
                return True

            for neighbor in self.adj[curr]:
                if neighbor not in visited :
                    visited.add(neighbor)
                    queue.append(neighbor)
    
        return False

    def is_walk_legal(self, from_node: int, to_node: int) -> bool:
        """
        Vérifie si un déplacement du pion est légal (pas de mur entre les deux cases).

        Args:
            from_node: Case de départ (index 0..nodes-1).
            to_node: Case d'arrivée.

        Returns:
            True si to_node est voisine de from_node dans le graphe actuel (déplacement autorisé).
        """
        if from_node < 0 or from_node >= self.nodes or to_node < 0 or to_node >= self.nodes:
            return False
        return to_node in self.adj[from_node]

    def is_wall_legal(
        self,
        player_positions: list[int],
        wall_edges: list[tuple[int, int]],
        player_targets: list[tuple[int | None, int | None]] | None = None,
    ) -> bool:
        """
        Vérifie si la pose d'un mur est légale (aucun joueur ne doit être bloqué).

        Simule la suppression des arêtes du mur, vérifie que chaque joueur peut
        encore atteindre sa ligne/colonne de victoire (BFS), puis restaure le graphe.
        Ne modifie pas le graphe en cas de succès : l'appelant doit appeler
        remove_edge pour chaque arête du mur s'il souhaite l'appliquer.

        Args:
            player_positions: Liste des cases actuelles des joueurs [pos0, pos1, ...].
            wall_edges: Liste des arêtes à bloquer par le mur, ex. [(node1, node2)].
            player_targets: Pour chaque joueur, (target_row, target_col) avec l'un à None.
                Si None : 2 joueurs -> (ligne 8, ligne 0), 4 joueurs -> (ligne 8, ligne 0, col 8, col 0).

        Returns:
            True si la pose du mur est légale (tous les joueurs gardent un chemin).

        Algorithm:
            1. Déterminer les cibles par défaut si besoin (2 joueurs : lignes 8 et 0 ;
               4 joueurs : lignes 8 et 0, colonnes 8 et 0).
            2. Vérifier que chaque arête du mur existe (liaison réelle entre deux cases).
            3. Sauvegarder le plateau (copie des listes d'adjacence).
            4. Supprimer temporairement les arêtes du mur.
            5. Pour chaque joueur, vérifier qu'il existe un chemin vers sa cible (BFS).
            6. Restaurer le plateau dans tous les cas (finally).
        """
        wall_edges = list(wall_edges)
        if not wall_edges:
            return True

        n = len(player_positions)
        if player_targets is None:
            if n == 2:
                player_targets = [(self.size - 1, None), (0, None)]
            elif n == 4:
                player_targets = [
                    (self.size - 1, None),
                    (0, None),
                    (None, self.size - 1),
                    (None, 0),
                ]
            else:
                player_targets = [(self.size - 1, None)] * n

        for (n1, n2) in wall_edges:
            if n1 not in self.adj or n2 not in self.adj.get(n1, []):
                return False

        backup = {i: list(neighbors) for i, neighbors in self.adj.items()}

        for (n1, n2) in wall_edges:
            self.remove_edge(n1, n2)

        try:
            for i, pos in enumerate(player_positions):
                if i >= len(player_targets):
                    break
                target_row, target_col = player_targets[i]
                if not self.has_path(pos, target_row=target_row, target_col=target_col):
                    return False
            return True
        finally:
            self.adj = backup