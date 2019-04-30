from plomrogue.errors import ArgError
import collections



class YX(collections.namedtuple('YX', ('y', 'x'))):

    def __add__(self, other):
        return YX(self.y + other.y, self.x + other.x)

    def __sub__(self, other):
        return YX(self.y - other.y, self.x - other.x)

    def __str__(self):
        return 'Y:%s,X:%s' % (self.y, self.x)



class Map:

    def __init__(self, size=YX(0, 0), init_char = '?'):
        self.size = size
        self.terrain = init_char*self.size_i

    def __getitem__(self, yx):
        return self.terrain[self.get_position_index(yx)]

    def __setitem__(self, yx, c):
        pos_i = self.get_position_index(yx)
        if type(c) == str:
            self.terrain = self.terrain[:pos_i] + c + self.terrain[pos_i + 1:]
        else:
            self.terrain[pos_i] = c

    def __iter__(self):
        """Iterate over YX position coordinates."""
        for y in range(self.size.y):
            for x in range(self.size.x):
                yield YX(y, x)

    @property
    def size_i(self):
        return self.size.y * self.size.x

    def set_line(self, y, line):
        height_map = self.size.y
        width_map = self.size.x
        if y >= height_map:
            raise ArgError('too large row number %s' % y)
        width_line = len(line)
        if width_line > width_map:
            raise ArgError('too large map line width %s' % width_line)
        self.terrain = self.terrain[:y * width_map] + line +\
                       self.terrain[(y + 1) * width_map:]

    def get_position_index(self, yx):
        return yx.y * self.size.x + yx.x

    def lines(self):
        width = self.size.x
        for y in range(self.size.y):
            yield (y, self.terrain[y * width:(y + 1) * width])



class MapGeometry():

    def get_directions(self):
        directions = []
        for name in dir(self):
            if name[:5] == 'move_':
                directions += [name[5:]]
        return directions

    def get_neighbors(self, pos, map_size):
        neighbors = {}
        if not hasattr(self, 'neighbors_to'):
            self.neighbors_to = {}
        if not map_size in self.neighbors_to:
            self.neighbors_to[map_size] = {}
        if pos in self.neighbors_to[map_size]:
            return self.neighbors_to[map_size][pos]
        for direction in self.get_directions():
            neighbors[direction] = self.move(pos, direction, map_size)
        self.neighbors_to[map_size][pos] = neighbors
        return neighbors

    def undouble_coordinate(self, maps_size, coordinate):
        y = maps_size.y * coordinate[0].y + coordinate[1].y
        x = maps_size.x * coordinate[0].x + coordinate[1].x
        return YX(y, x)

    def get_view_offset(self, maps_size, center, radius):
        yx_to_origin = self.undouble_coordinate(maps_size, center)
        return yx_to_origin - YX(radius, radius)

    def pos_in_view(self, pos, offset, maps_size):
        return self.undouble_coordinate(maps_size, pos) - offset

    def get_view(self, maps_size, get_map, radius, view_offset):
        m = Map(size=YX(radius*2+1, radius*2+1)
        for pos in m:
            seen_pos = self.correct_double_coordinate(maps_size, (0,0),
                                                      pos + view_offset)
            seen_map = get_map(seen_pos[0], False)
            if seen_map is None:
                seen_map = Map(size=maps_size)
            m[pos] = seen_map[seen_pos[1]]
        return m

    def get_correcting_map_size(self, size, offset):
        return size

    def correct_double_coordinate(self, map_size, big_yx, little_yx):

        def adapt_axis(axis):
            maps_crossed = little_yx[axis] // map_size[axis]
            new_big = big_yx[axis] + maps_crossed
            new_little = little_yx[axis] % map_size[axis]
            return new_big, new_little

        new_big_y, new_little_y = adapt_axis(0)
        new_big_x, new_little_x = adapt_axis(1)
        return YX(new_big_y, new_big_x), YX(new_little_y, new_little_x)

    def move(self, start_pos, direction, map_size):
        mover = getattr(self, 'move_' + direction)
        big_yx, little_yx = start_pos
        uncorrected_target = mover(little_yx)
        return self.correct_double_coordinate(map_size, big_yx,
                                              uncorrected_target)



class MapGeometryWithLeftRightMoves(MapGeometry):

    def move_LEFT(self, start_pos):
        return YX(start_pos.y, start_pos.x - 1)

    def move_RIGHT(self, start_pos):
        return YX(start_pos.y, start_pos.x + 1)



class MapGeometrySquare(MapGeometryWithLeftRightMoves):

    def move_UP(self, start_pos):
        return YX(start_pos.y - 1, start_pos.x)

    def move_DOWN(self, start_pos):
        return YX(start_pos.y + 1, start_pos.x)



class MapGeometryHex(MapGeometryWithLeftRightMoves):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fov_map_type = FovMapHex

    def move_UPLEFT(self, start_pos):
        if start_pos.y % 2 == 1:
            return YX(start_pos.y - 1, start_pos.x - 1)
        else:
            return YX(start_pos.y - 1, start_pos.x)

    def move_UPRIGHT(self, start_pos):
        if start_pos.y % 2 == 1:
            return YX(start_pos.y - 1, start_pos.x)
        else:
            return YX(start_pos.y - 1, start_pos.x + 1)

    def move_DOWNLEFT(self, start_pos):
        if start_pos.y % 2 == 1:
             return YX(start_pos.y + 1, start_pos.x - 1)
        else:
               return YX(start_pos.y + 1, start_pos.x)

    def move_DOWNRIGHT(self, start_pos):
        if start_pos.y % 2 == 1:
            return YX(start_pos.y + 1, start_pos.x)
        else:
            return YX(start_pos.y + 1, start_pos.x + 1)


class FovMap(Map):

    def __init__(self, source_map, center):
        self.source_map = source_map
        self.size = self.source_map.size
        self.fov_radius = (self.size.y / 2) - 0.5
        self.terrain = '?' * self.size_i
        self[center] = '.'
        self.shadow_cones = []
        self.circle_out(center, self.shadow_process_hex)

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
            import math
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
        step_size = (CIRCLE/len(self.circle_out_directions)) / distance_to_center
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

    def basic_circle_out_move(self, pos, direction):
        """Move position pos into direction. Return whether still in map."""
        mover = getattr(self.geometry, 'move_' + direction)
        pos = mover(pos)
        if pos.y < 0 or pos.x < 0 or \
            pos.y >= self.size.y or pos.x >= self.size.x:
            return pos, False
        return pos, True

    def circle_out(self, yx, f):
        # Optimization potential: Precalculate movement positions. (How to check
        # circle_in_map then?)
        # Optimization potential: Precalculate what hexes are shaded by what hex
        # and skip evaluation of already shaded hexes. (This only works if hex
        # shading implies they completely lie in existing shades; otherwise we
        # would lose shade growth through hexes at shade borders.)

        # TODO: Start circling only in earliest obstacle distance.
        # TODO: get rid of circle_in_map logic
        circle_in_map = True
        distance = 1
        yx = YX(yx.y, yx.x)
        #print('DEBUG CIRCLE_OUT', yx)
        while circle_in_map:
            if distance > self.fov_radius:
                break
            circle_in_map = False
            yx, _ = self.basic_circle_out_move(yx, 'RIGHT')
            for dir_i in range(len(self.circle_out_directions)):
                for dir_progress in range(distance):
                    direction = self.circle_out_directions[dir_i]
                    yx, test = self.circle_out_move(yx, direction)
                    if test:
                        f(yx, distance, dir_i, dir_progress)
                        circle_in_map = True
            distance += 1



class FovMapHex(FovMap):
    circle_out_directions = ('DOWNLEFT', 'LEFT', 'UPLEFT',
                             'UPRIGHT', 'RIGHT', 'DOWNRIGHT')

    def __init__(self, *args, **kwargs):
        self.geometry = MapGeometryHex()
        super().__init__(*args, **kwargs)

    def circle_out_move(self, yx, direction):
        return self.basic_circle_out_move(yx, direction)



class FovMapSquare(FovMap):
    circle_out_directions = (('DOWN', 'LEFT'), ('LEFT', 'UP'),
                             ('UP', 'RIGHT'), ('RIGHT', 'DOWN'))

    def __init__(self, *args, **kwargs):
        self.geometry = MapGeometrySquare()
        super().__init__(*args, **kwargs)

    def circle_out_move(self, yx, direction):
        self.basic_circle_out_move(yx, direction[0])
        return self.basic_circle_out_move(yx, direction[1])

