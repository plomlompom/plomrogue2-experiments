from parser import ArgError


class World:

    def __init__(self):
        self.turn = 0
        self.map_size = (0, 0)
        self.terrain_map = ''
        self.things = []
        self.Thing = Thing  # child classes may use an extended Thing class here

    def set_map_size(self, yx):
        y, x = yx
        self.map_size = (y, x)
        self.terrain_map = ''
        for y in range(self.map_size[0]):
            self.terrain_map += '?' * self.map_size[1]

    def set_map_line(self, y, line):
        width_map = self.map_size[1]
        if y >= self.map_size[0]:
            raise ArgError('too large row number %s' % y)
        width_line = len(line)
        if width_line > width_map:
            raise ArgError('too large map line width %s' % width_line)
        self.terrain_map = self.terrain_map[:y * width_map] + line + \
                           self.terrain_map[(y + 1) * width_map:]

    def get_thing(self, id_):
        for thing in self.things:
            if id_ == thing.id_:
                return thing
        t = self.Thing(self, id_)
        self.things += [t]
        return t


class Thing:

    def __init__(self, world, id_):
        self.world = world
        self.id_ = id_
        self.type_ = '?'
        self.position = [0,0]


class Commander:

    def cmd_MAP_SIZE(self, yx):
        """Set self.map_size to yx, redraw self.terrain_map as '?' cells."""
        self.world.set_map_size(yx)
    cmd_MAP_SIZE.argtypes = 'yx_tuple:nonneg'

    def cmd_TERRAIN_LINE(self, y, terrain_line):
        self.world.set_map_line(y, terrain_line)
    cmd_TERRAIN_LINE.argtypes = 'int:nonneg string'

    def cmd_THING_TYPE(self, i, type_):
        t = self.world.get_thing(i)
        t.type_ = type_
    cmd_THING_TYPE.argtypes = 'int:nonneg string'

    def cmd_THING_POS(self, i, yx):
        t = self.world.get_thing(i)
        t.position = list(yx)
    cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'
