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


test = Graph()
print(test.adj)