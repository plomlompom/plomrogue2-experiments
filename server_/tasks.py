from server_.game_error import GameError



class TaskManager:

    def __init__(self, task_classes):
        self.task_classes = task_classes

    def get_task_class(self, task_name):
        for task_class in self.task_classes:
            if task_class.__name__ == 'Task_' + task_name:
                return task_class
        return None


class Task:
    argtypes = ''

    def __init__(self, thing, args=()):
        self.thing = thing
        self.args = args
        self.todo = 3

    @property
    def name(self):
        prefix = 'Task_'
        class_name = self.__class__.__name__
        return class_name[len(prefix):]

    def check(self):
        pass

    def get_args_string(self):
        stringed_args = []
        for arg in self.args:
            if type(arg) == str:
                stringed_args += [server_.io.quote(arg)]
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
            if t.position == test_pos:
                raise GameError('%s would move into other thing' % self.thing.id_)

    def do(self):
        self.thing.position = self.thing.world.map_.move(self.thing.position,
                                                         self.args[0])



task_manager = TaskManager((Task_WAIT, Task_MOVE))
