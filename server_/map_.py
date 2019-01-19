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

    @property
    def geometry(self):
        return self.__class__.__name__[3:]

    def lines(self):
        width = self.size[1]
        for y in range(self.size[0]):
            yield (y, self.terrain[y * width:(y + 1) * width])

    def get_fov_map(self, yx):
        # TODO: Currently only have MapFovHex. Provide MapFovSquare.
        fov_map_class = map_manager.get_map_class('Fov' + self.geometry)
        return fov_map_class(self, yx)

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

    # The following is used nowhere, so not implemented.
    #def are_neighbors(self, pos_1, pos_2):
    #    if pos_1[0] == pos_2[0] and abs(pos_1[1] - pos_2[1]) <= 1:
    #        return True
    #    elif abs(pos_1[0] - pos_2[0]) == 1:
    #        if pos_1[0] % 2 == 0:
    #            if pos_2[1] in (pos_1[1], pos_1[1] - 1):
    #                return True
    #        elif pos_2[1] in (pos_1[1], pos_1[1] + 1):
    #            return True
    #    return False

    def move_UPLEFT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] - 1, start_pos[1] - 1]
        else:
            return [start_pos[0] - 1, start_pos[1]]

    def move_UPRIGHT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] - 1, start_pos[1]]
        else:
            return [start_pos[0] - 1, start_pos[1] + 1]

    def move_DOWNLEFT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] + 1, start_pos[1] - 1]
        else:
            return [start_pos[0] + 1, start_pos[1]]

    def move_DOWNRIGHT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] + 1, start_pos[1]]
        else:
            return [start_pos[0] + 1, start_pos[1] + 1]


class MapFovHex(MapHex):

    def __init__(self, source_map, yx):
        self.source_map = source_map
        self.size = self.source_map.size
        self.terrain = '?' * self.size_i
        self[yx] = '.'
        self.shadow_angles = []
        self.circle_out(yx, self.shadow_process_hex)

    def shadow_process_hex(self, yx, distance_to_center, dir_i, hex_i):
        # TODO: If no shadow_angles yet and self[yx] == '.', skip all.
        CIRCLE = 360  # Since we'll float anyways, number is actually arbitrary.

        def correct_angle(angle):
            if angle < 0:
                angle += CIRCLE
            return angle

        def under_shadow_angle(new_angle):
            for old_angle in self.shadow_angles:
                if old_angle[0] >= new_angle[0] and \
                    new_angle[1] >= old_angle[1]:
                    #print('DEBUG shadowed by:', old_angle)
                    return True
            return False

        def merge_angle(new_angle):
            for old_angle in self.shadow_angles:
                if new_angle[0] > old_angle[0] and \
                    new_angle[1] <= old_angle[0]:
                    #print('DEBUG merging to', old_angle)
                    old_angle[0] = new_angle[0]
                    #print('DEBUG merged angle:', old_angle)
                    return True
                if new_angle[1] < old_angle[1] and \
                    new_angle[0] >= old_angle[1]:
                    #print('DEBUG merging to', old_angle)
                    old_angle[1] = new_angle[1]
                    #print('DEBUG merged angle:', old_angle)
                    return True
            return False

        def eval_angle(angle):
            new_angle = [left_angle, right_angle]
            #print('DEBUG ANGLE', angle, '(', step_size, distance_to_center, number_steps, ')')
            if under_shadow_angle(angle):
                return
            self[yx] = '.'
            if self.source_map[yx] != '.':
                #print('DEBUG throws shadow', angle)
                unmerged = True
                while merge_angle(angle):
                    unmerged = False
                if unmerged:
                    self.shadow_angles += [angle]

        #print('DEBUG', yx)
        step_size = (CIRCLE/6)/distance_to_center
        number_steps = dir_i * distance_to_center + hex_i
        left_angle = correct_angle(-(step_size/2) - step_size*number_steps)
        right_angle = correct_angle(left_angle - step_size)
        # TODO: derive left_angle from prev right_angle where possible
        if right_angle > left_angle:
            eval_angle([left_angle, 0])
            eval_angle([CIRCLE, right_angle])
        else:
            eval_angle([left_angle, right_angle])

    def circle_out(self, yx, f):

        def move(pos, direction):
            """Move position pos into direction. Return whether still in map."""
            mover = getattr(self, 'move_' + direction)
            pos[:] = mover(pos)
            if pos[0] < 0 or pos[1] < 0 or \
               pos[0] >= self.size[0] or pos[1] >= self.size[1]:
                return False
            return True

        # TODO: Start circling only in earliest obstacle distance.
        directions = ('DOWNLEFT', 'LEFT', 'UPLEFT', 'UPRIGHT', 'RIGHT', 'DOWNRIGHT')
        circle_in_map = True
        distance = 1
        first_direction = 'RIGHT'
        yx = yx[:]
        #print('DEBUG CIRCLE_OUT', yx)
        while circle_in_map:
            circle_in_map = False
            move(yx, 'RIGHT')
            for dir_i in range(len(directions)):
                for hex_i in range(distance):
                    direction = directions[dir_i]
                    if move(yx, direction):
                        f(yx, distance, dir_i, hex_i)
                        circle_in_map = True
            distance += 1


class MapSquare(Map):

    # The following is used nowhere, so not implemented.
    #def are_neighbors(self, pos_1, pos_2):
    #    return abs(pos_1[0] - pos_2[0]) <= 1 and abs(pos_1[1] - pos_2[1] <= 1)

    def move_UP(self, start_pos):
        return [start_pos[0] - 1, start_pos[1]]

    def move_DOWN(self, start_pos):
        return [start_pos[0] + 1, start_pos[1]]


map_manager = game_common.MapManager(globals())
