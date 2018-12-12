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

    def get_thing(self, i):
        for thing in self.things:
            if i == thing.id_:
                return thing
        t = self.Thing(self, i)
        self.things += [t]
        return t


class Thing:

    def __init__(self, world, id_):
        self.world = world
        self.id_ = id_
        self.type_ = '?'
        self.position = [0,0]
