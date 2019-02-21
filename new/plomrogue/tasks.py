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
        if self.thing.world.map_[test_pos] != '.':
            raise GameError('%s would move into illegal terrain' % self.thing.id_)
        for t in self.thing.world.things:
            if t.blocking and t.position == test_pos:
                raise GameError('%s would move into other thing' % self.thing.id_)

    def do(self):
        self.thing.position = self.thing.world.map_.move(self.thing.position,
                                                         self.args[0])
