from collections import deque

class Graph:
    def __init__(self, size=9):
        """
        Initialise le plateau sous forme de graphe.
        Taille 9x9 par défault
        """

        self.size = size
        self.nodes = size * size
        self.adj = {} #Dictionnaire qui relie un int (noeud) à tous ses voisins
        for i in range(self.nodes):
            self.adj[i] = self.get_initial_neighbors(i)

        #self.adj = {i: self.get_initial_neighbors(i) for i in range(self.nodes)}

    def get_initial_neighbors(self, node):
        """Calcule les voisins d'une case sans aucun mur"""

        neighbors = []
        row, col = divmod(node, self.size)

        if row > 0 : neighbors.append(node - self.size)
        if row < self.size - 1 : neighbors.append(node + self.size)
        if col > 0 : neighbors.append(node - 1)
        if col < self.size - 1 : neighbors.append(node + 1)

        return neighbors
    
    def remove_edge(self, node1, node2):
        """Supprime le lien entre 2 cases"""

        if node2 in self.adj[node1] :
            self.adj[node1].remove(node2)
        
        if node1 in self.adj[node2] :
            self.adj[node1].remove(node2)


    def has_path(self, node, target_row = None, target_col = None):
        """
        BFS pour trouver un chemin valide si il existe.
        On part d'un noeud de départ et on essais d'arriver à la ligne ou colonne de victoire (2 ou 4 joueurs)
        """

        visited = {node}
        queue = deque([node])

        while queue :
            curr = queue.popleft()

            #Vérification de victoire 
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
    
    def is_wall_legal(self, player_position, wall_edges):
        """Vérifie si la pose d'un mur est légal (Ne bloque aucun joueur)"""

        # 1 : Sauvegarde temporaire du plateau (arêtes)
        # 2 : Suppression des arêtes
        # 3 : Simulation (BFS)
        # 4 : Si illégal alors restauration du plateau
        # 5 : Si légal application du nouveau plateau



test = Graph()
print(test.adj)