class Player:
    def __init__(self, player_id, pos, target_row = None, target_col = None, wall_count = 10):
        self.player_id = player_id
        self.pos = pos
        self.target_row = target_row
        self.target_col = target_col
        self.wall_count = wall_count

    def move(self, new_pos):
        self.pos = new_pos

    def use_wall(self):
        if self.wall_count > 0:
            self.wall_count -= 1


