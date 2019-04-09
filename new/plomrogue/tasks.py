from plomrogue.errors import GameError
from plomrogue.misc import quote



class Task:
    argtypes = ''

    def __init__(self, thing, args=()):
        self.thing = thing
        self.args = args
        self.todo = 3

    def check(self):
        pass

    def get_args_string(self):
        stringed_args = []
        for arg in self.args:
            if type(arg) == str:
                stringed_args += [quote(arg)]
            else:
                raise GameError('stringifying arg type not implemented')
        return ' '.join(stringed_args)



class Task_WAIT(Task):

    def do(self):
        return 'success'



class Task_MOVE(Task):
    argtypes = 'string:direction'

    def check(self):
        test_pos = self.thing.world.map_.move(self.thing.position, self.args[0])
        if test_pos is None:
            raise GameError('would move outside map bounds')
        if self.thing.world.map_[test_pos] != '.':
            raise GameError('%s would move into illegal terrain' % self.thing.id_)
        for t in self.thing.world.things:
            if t.blocking and t.position == test_pos:
                raise GameError('%s would move into other thing' % self.thing.id_)

    def do(self):
        self.thing.position = self.thing.world.map_.move(self.thing.position,
                                                         self.args[0])
        for id_ in self.thing.inventory:
            t = self.thing.world.get_thing(id_)
            t.position = self.thing.position



class Task_PICKUP(Task):
    argtypes = 'int:nonneg'

    def check(self):
        to_pick_up = self.thing.world.get_thing(self.args[0],
                                                create_unfound=False)
        if to_pick_up is None or \
           to_pick_up.id_ not in self.thing.get_pickable_items():
            raise GameError('thing of ID %s not in reach to pick up'
                            % self.args[0])

    def do(self):
        to_pick_up = self.thing.world.get_thing(self.args[0])
        self.thing.inventory += [self.args[0]]
        to_pick_up.in_inventory = True
        to_pick_up.position = self.thing.position



class Task_DROP(Task):
    argtypes = 'int:nonneg'

    def check(self):
        to_drop = self.thing.world.get_thing(self.args[0], create_unfound=False)
        if to_drop is None:
            raise GameError('no thing of ID %s to drop' % self.args[0])
        if to_drop.id_ not in self.thing.inventory:
            raise GameError('no thing of ID %s to drop in inventory'
                            % self.args[0])

    def do(self):
        to_drop = self.thing.world.get_thing(self.args[0])
        del self.thing.inventory[self.thing.inventory.index(to_drop.id_)]
        to_drop.in_inventory = False
