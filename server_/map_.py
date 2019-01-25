import sys
sys.path.append('../')
import game_common
import server_.game
import math


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
        self.shadow_cones = []
        self.circle_out(yx, self.shadow_process_hex)

    def shadow_process_hex(self, yx, distance_to_center, dir_i, dir_progress):
        # Possible optimization: If no shadow_cones yet and self[yx] == '.',
        # skip all.
        CIRCLE = 360  # Since we'll float anyways, number is actually arbitrary.

        def correct_arm(arm):
            if arm < 0:
                arm += CIRCLE
            return arm

        def in_shadow_cone(new_cone):
            for old_cone in self.shadow_cones:
                if old_cone[0] >= new_cone[0] and \
                    new_cone[1] >= old_cone[1]:
                    #print('DEBUG shadowed by:', old_cone)
                    return True
                # We might want to also shade hexes whose middle arm is inside a
                # shadow cone for a darker FOV. Note that we then could not for
                # optimization purposes rely anymore on the assumption that a
                # shaded hex cannot add growth to existing shadow cones.
            return False

        def merge_cone(new_cone):
            for old_cone in self.shadow_cones:
                if new_cone[0] > old_cone[0] and \
                    (new_cone[1] < old_cone[0] or
                     math.isclose(new_cone[1], old_cone[0])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[0] = new_cone[0]
                    #print('DEBUG merged cone:', old_cone)
                    return True
                if new_cone[1] < old_cone[1] and \
                    (new_cone[0] > old_cone[1] or
                     math.isclose(new_cone[0], old_cone[1])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[1] = new_cone[1]
                    #print('DEBUG merged cone:', old_cone)
                    return True
            return False

        def eval_cone(cone):
            #print('DEBUG CONE', cone, '(', step_size, distance_to_center, number_steps, ')')
            if in_shadow_cone(cone):
                return
            self[yx] = '.'
            if self.source_map[yx] != '.':
                #print('DEBUG throws shadow', cone)
                unmerged = True
                while merge_cone(cone):
                    unmerged = False
                if unmerged:
                    self.shadow_cones += [cone]

        #print('DEBUG', yx)
        step_size = (CIRCLE/6) / distance_to_center
        number_steps = dir_i * distance_to_center + dir_progress
        left_arm = correct_arm(-(step_size/2) - step_size*number_steps)
        right_arm = correct_arm(left_arm - step_size)
        # Optimization potential: left cone could be derived from previous
        # right cone. Better even: Precalculate all cones.
        if right_arm > left_arm:
            eval_cone([left_arm, 0])
            eval_cone([CIRCLE, right_arm])
        else:
            eval_cone([left_arm, right_arm])

    def circle_out(self, yx, f):
        # Optimization potential: Precalculate movement positions. (How to check
        # circle_in_map then?)
        # Optimization potential: Precalculate what hexes are shaded by what hex
        # and skip evaluation of already shaded hexes. (This only works if hex
        # shading implies they completely lie in existing shades; otherwise we
        # would lose shade growth through hexes at shade borders.)

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
        yx = yx[:]
        #print('DEBUG CIRCLE_OUT', yx)
        while circle_in_map:
            circle_in_map = False
            move(yx, 'RIGHT')
            for dir_i in range(len(directions)):
                for dir_progress in range(distance):
                    direction = directions[dir_i]
                    if move(yx, direction):
                        f(yx, distance, dir_i, dir_progress)
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


class MapFovSquare(MapSquare):
    """Just a marginally and unsatisfyingly adapted variant of MapFovHex."""

    def __init__(self, source_map, yx):
        self.source_map = source_map
        self.size = self.source_map.size
        self.terrain = '?' * self.size_i
        self[yx] = '.'
        self.shadow_cones = []
        self.circle_out(yx, self.shadow_process_hex)

    def shadow_process_hex(self, yx, distance_to_center, dir_i, dir_progress):
        CIRCLE = 360  # Since we'll float anyways, number is actually arbitrary.

        def correct_arm(arm):
            if arm < 0:
                arm += CIRCLE
            return arm

        def in_shadow_cone(new_cone):
            for old_cone in self.shadow_cones:
                if old_cone[0] >= new_cone[0] and \
                    new_cone[1] >= old_cone[1]:
                    #print('DEBUG shadowed by:', old_cone)
                    return True
            return False

        def merge_cone(new_cone):
            for old_cone in self.shadow_cones:
                if new_cone[0] > old_cone[0] and \
                    (new_cone[1] < old_cone[0] or
                     math.isclose(new_cone[1], old_cone[0])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[0] = new_cone[0]
                    #print('DEBUG merged cone:', old_cone)
                    return True
                if new_cone[1] < old_cone[1] and \
                    (new_cone[0] > old_cone[1] or
                     math.isclose(new_cone[0], old_cone[1])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[1] = new_cone[1]
                    #print('DEBUG merged cone:', old_cone)
                    return True
            return False

        def eval_cone(cone):
            new_cone = [left_arm, right_arm]
            #print('DEBUG CONE', cone, '(', step_size, distance_to_center, number_steps, ')')
            if in_shadow_cone(cone):
                return
            self[yx] = '.'
            if self.source_map[yx] != '.':
                #print('DEBUG throws shadow', cone)
                unmerged = True
                while merge_cone(cone):
                    unmerged = False
                if unmerged:
                    self.shadow_cones += [cone]

        #print('DEBUG', yx)
        step_size = (CIRCLE/4) / distance_to_center
        number_steps = dir_i * distance_to_center + dir_progress
        left_arm = correct_arm(-(step_size/2) - step_size*number_steps)
        right_arm = correct_arm(left_arm - step_size)
        if right_arm > left_arm:
            eval_cone([left_arm, 0])
            eval_cone([CIRCLE, right_arm])
        else:
            eval_cone([left_arm, right_arm])

    def circle_out(self, yx, f):

        def move(pos, direction):
            """Move position pos into direction. Return whether still in map."""
            mover = getattr(self, 'move_' + direction)
            pos[:] = mover(pos)
            if pos[0] < 0 or pos[1] < 0 or \
               pos[0] >= self.size[0] or pos[1] >= self.size[1]:
                return False
            return True

        directions = (('DOWN', 'LEFT'), ('LEFT', 'UP'),
                      ('UP', 'RIGHT'), ('RIGHT', 'DOWN'))
        circle_in_map = True
        distance = 1
        yx = yx[:]
        #print('DEBUG CIRCLE_OUT', yx)
        while circle_in_map:
            circle_in_map = False
            move(yx, 'RIGHT')
            for dir_i in range(len(directions)):
                for dir_progress in range(distance):
                    direction = directions[dir_i]
                    move(yx, direction[0])
                    if move(yx, direction[1]):
                        f(yx, distance, dir_i, dir_progress)
                        circle_in_map = True
            distance += 1


map_manager = game_common.MapManager(globals())
