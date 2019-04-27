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
            elif type(arg) == int:
                stringed_args += [str(arg)]
            else:
                raise GameError('stringifying arg type not implemented')
        return ' '.join(stringed_args)



class Task_WAIT(Task):

    def do(self):
        return 'success'



class Task_MOVE(Task):
    argtypes = 'string:direction'

    def check(self):
        test_pos = ((0,0),
                    self.thing.world.maps[(0,0)].
                    move(self.thing.position[1], self.args[0]))
        if test_pos == ((0,0), None):
            raise GameError('would move outside map bounds')
        if self.thing.world.maps[test_pos[0]][test_pos[1]] != '.':
            raise GameError('%s would move into illegal terrain' % self.thing.id_)
        for t in self.thing.world.things_at_pos(test_pos):
            if t.blocking:
                raise GameError('%s would move into other thing' % self.thing.id_)

    def do(self):
        self.thing.position = (0,0), self.thing.world.maps[(0,0)].\
                                     move(self.thing.position[1], self.args[0])



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



class TaskOnInventoryItem(Task):
    argtypes = 'int:nonneg'

    def _basic_inventory_item_check(self):
        item = self.thing.world.get_thing(self.args[0], create_unfound=False)
        if item is None:
            raise GameError('no thing of ID %s' % self.args[0])
        if item.id_ not in self.thing.inventory:
            raise GameError('no thing of ID %s in inventory' % self.args[0])
        return item

    def _eliminate_from_inventory(self):
        item = self.thing.world.get_thing(self.args[0])
        del self.thing.inventory[self.thing.inventory.index(item.id_)]
        item.in_inventory = False
        return item



class Task_DROP(TaskOnInventoryItem):
    argtypes = 'int:nonneg'

    def check(self):
        self._basic_inventory_item_check()

    def do(self):
        self._eliminate_from_inventory()



class Task_EAT(TaskOnInventoryItem):
    argtypes = 'int:nonneg'

    def check(self):
        to_eat = self._basic_inventory_item_check()
        if to_eat.type_ != 'food':
            raise GameError('thing of ID %s s not food' % self.args[0])

    def do(self):
        to_eat = self._eliminate_from_inventory()
        del self.thing.world.things[self.thing.world.things.index(to_eat)]
        self.thing.health += 50
