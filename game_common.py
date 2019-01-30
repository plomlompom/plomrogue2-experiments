from parser import ArgError


class MapManager:

    def __init__(self, map_classes):
        """Collects tuple of basic Map[Geometry] classes."""
        self.map_classes = map_classes

    def get_map_geometries(self):
        geometries = []
        for map_class in self.map_classes:
            geometries += [map_class.__name__[3:]]
        return geometries

    def get_map_class(self, geometry):
        for map_class in self.map_classes:
            if map_class.__name__[3:] == geometry:
                return map_class


class Map:

    def __init__(self, size=(0, 0)):
        self.size = size
        self.terrain = '?'*self.size_i

    @property
    def size_i(self):
        return self.size[0] * self.size[1]

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

    def get_position_index(self, yx):
        return yx[0] * self.size[1] + yx[1]


class World:

    def __init__(self):
        self.Thing = Thing  # child classes may use an extended Thing class here
        self.turn = 0
        self.things = []

    def get_thing(self, id_, create_unfound=True):
        for thing in self.things:
            if id_ == thing.id_:
                return thing
        if create_unfound:
            t = self.Thing(self, id_)
            self.things += [t]
            return t
        return None

    def new_map(self, geometry, yx):
        map_type = self.game.map_manager.get_map_class(geometry)
        self.map_ = map_type(yx)


class Thing:

    def __init__(self, world, id_):
        self.world = world
        self.id_ = id_
        self.type_ = '?'
        self.position = [0,0]


class CommonCommandsMixin:

    def cmd_MAP(self, geometry, yx):
        """Create new map of grid geometry, size yx and only '?' cells."""
        self.world.new_map(geometry, yx)
    cmd_MAP.argtypes = 'string:geometry yx_tuple:pos'

    def cmd_THING_TYPE(self, i, type_):
        t = self.world.get_thing(i)
        t.type_ = type_
    cmd_THING_TYPE.argtypes = 'int:nonneg string'

    def cmd_THING_POS(self, i, yx):
        t = self.world.get_thing(i)
        t.position = list(yx)
    cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'
