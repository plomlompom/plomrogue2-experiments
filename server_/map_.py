import sys
sys.path.append('../')
import game_common
import server_.game


class Map(game_common.Map):

    def __getitem__(self, yx):
        return self.terrain[self.get_position_index(yx)]

    def __setitem__(self, yx, c):
        pos_i = self.get_position_index(yx)
        self.terrain = self.terrain[:pos_i] + c + self.terrain[pos_i + 1:]

    def __iter__(self):
        """Iterate over YX position coordinates."""
        for y in range(self.size[0]):
            for x in range(self.size[1]):
                yield [y, x]

    def lines(self):
        width = self.size[1]
        for y in range(self.size[0]):
            yield (y, self.terrain[y * width:(y + 1) * width])

    # The following is used nowhere, so not implemented.
    #def items(self):
    #    for y in range(self.size[0]):
    #        for x in range(self.size[1]):
    #            yield ([y, x], self.terrain[self.get_position_index([y, x])])

    def get_directions(self):
        directions = []
        for name in dir(self):
            if name[:5] == 'move_':
                directions += [name[5:]]
        return directions

    def new_from_shape(self, init_char):
        import copy
        new_map = copy.deepcopy(self)
        for pos in new_map:
            new_map[pos] = init_char
        return new_map

    def move(self, start_pos, direction):
        mover = getattr(self, 'move_' + direction)
        new_pos = mover(start_pos)
        if new_pos[0] < 0 or new_pos[1] < 0 or \
                new_pos[0] >= self.size[0] or new_pos[1] >= self.size[1]:
            raise server_.game.GameError('would move outside map bounds')
        return new_pos

    def move_LEFT(self, start_pos):
        return [start_pos[0], start_pos[1] - 1]

    def move_RIGHT(self, start_pos):
        return [start_pos[0], start_pos[1] + 1]


class MapHex(Map):

    def are_neighbors(self, pos_1, pos_2):
        if pos_1[0] == pos_2[0] and abs(pos_1[1] - pos_2[1]) <= 1:
            return True
        elif abs(pos_1[0] - pos_2[0]) == 1:
            if pos_1[0] % 2 == 0:
                if pos_2[1] in (pos_1[1], pos_1[1] - 1):
                    return True
            elif pos_2[1] in (pos_1[1], pos_1[1] + 1):
                return True
        return False

    def move_UPLEFT(self, start_pos):
        if start_pos[0] % 2 == 0:
            return [start_pos[0] - 1, start_pos[1] - 1]
        else:
            return [start_pos[0] - 1, start_pos[1]]

    def move_UPRIGHT(self, start_pos):
        if start_pos[0] % 2 == 0:
            return [start_pos[0] - 1, start_pos[1]]
        else:
            return [start_pos[0] - 1, start_pos[1] + 1]

    def move_DOWNLEFT(self, start_pos):
        if start_pos[0] % 2 == 0:
            return [start_pos[0] + 1, start_pos[1] - 1]
        else:
            return [start_pos[0] + 1, start_pos[1]]

    def move_DOWNRIGHT(self, start_pos):
        if start_pos[0] % 2 == 0:
            return [start_pos[0] + 1, start_pos[1]]
        else:
            return [start_pos[0] + 1, start_pos[1] + 1]


class MapSquare(Map):

    def are_neighbors(self, pos_1, pos_2):
        return abs(pos_1[0] - pos_2[0]) <= 1 and abs(pos_1[1] - pos_2[1] <= 1)

    def move_UP(self, start_pos):
        return [start_pos[0] - 1, start_pos[1]]

    def move_DOWN(self, start_pos):
        return [start_pos[0] + 1, start_pos[1]]


def get_map_class(geometry):
    return globals()['Map' + geometry]
