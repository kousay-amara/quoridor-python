from collections import deque

def has_path(graph, node, target_row = None, target_col = None):
        """
        BFS to find a valid path from a node to a winning row or column.

        Starts from the given node and searches for target_row and/or target_col
        (2 or 4 player mode). At each visited node, checks if the winning row
        or column is reached.

        Args:
            node: Starting node.
            target_row: Row to reach (None to ignore).
            target_col: Column to reach (None to ignore).

        Returns:
            True if a path to the target exists, False otherwise.
        """
        visited = {node}
        queue = deque([node])

        while queue :
            curr = queue.popleft()
            curr_row, curr_col = divmod(curr, graph.size)
            if target_row is not None and curr_row == target_row :
                return True
            if target_col is not None and curr_col == target_col :
                return True

            for neighbor in graph.adj[curr]:
                if neighbor not in visited :
                    visited.add(neighbor)
                    queue.append(neighbor)
    
        return False