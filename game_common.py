from parser import ArgError


class Map:

    def __init__(self, size=(0, 0), terrain=''):
        self.size = size
        self.terrain = terrain

    def set_line(self, y, line):
        height_map = self.size[0]
        width_map = self.size[1]
        if y >= height_map:
            raise ArgError('too large row number %s' % y)
        width_line = len(line)
        if width_line > width_map:
            raise ArgError('too large map line width %s' % width_line)
        self.terrain = self.terrain[:y * width_map] + line +\
                       self.terrain[(y + 1) * width_map:]

    def set_size(self, yx):
        y, x = yx
        self.size = (y, x)
        self.terrain = ''
        for y in range(self.size[0]):
            self.terrain += '?' * self.size[1]

    def get_position_index(self, yx):
        return yx[0] * self.size[1] + yx[1]


class World:

    def __init__(self):
        self.turn = 0
        self.map_ = Map()
        self.things = []
        self.Thing = Thing  # child classes may use an extended Thing class here

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


class CommonCommandsMixin:

    def cmd_MAP_SIZE(self, yx):
        """Set self.map_size to yx, redraw self.terrain_map as '?' cells."""
        self.world.map_.set_size(yx)
    cmd_MAP_SIZE.argtypes = 'yx_tuple:nonneg'

    def cmd_THING_TYPE(self, i, type_):
        t = self.world.get_thing(i)
        t.type_ = type_
    cmd_THING_TYPE.argtypes = 'int:nonneg string'

    def cmd_THING_POS(self, i, yx):
        t = self.world.get_thing(i)
        t.position = list(yx)
    cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'
