class GameError(Exception):
    pass


def move_pos(direction, pos_yx):
    if direction == 'UP':
        pos_yx[0] -= 1
    elif direction == 'DOWN':
        pos_yx[0] += 1
    elif direction == 'RIGHT':
        pos_yx[1] += 1
    elif direction == 'LEFT':
        pos_yx[1] -= 1


class Task:

    def __init__(self, thing, name, args=(), kwargs={}):
        self.name = name
        self.thing = thing
        self.args = args
        self.kwargs = kwargs
        self.todo = 1

    def check(self):
        if self.name == 'move':
            if len(self.args) > 0:
                direction = self.args[0]
            else:
                direction = self.kwargs['direction']
            test_pos = self.thing.position[:]
            move_pos(direction, test_pos)
            if test_pos[0] < 0 or test_pos[1] < 0 or \
               test_pos[0] >= self.thing.world.map_size[0] or \
               test_pos[1] >= self.thing.world.map_size[1]:
                raise GameError('would move outside map bounds')
            pos_i = test_pos[0] * self.thing.world.map_size[1] + test_pos[1]
            map_tile = self.thing.world.map_[pos_i]
            if map_tile != '.':
                raise GameError('would move into illegal terrain')


class Thing:

    def __init__(self, world, type_, position):
        self.world = world
        self.type_ = type_
        self.position = position
        self.task = Task(self, 'wait')

    def task_wait(self):
        pass

    def task_move(self, direction):
        move_pos(direction, self.position)

    def decide_task(self):
        if self.position[1] > 1:
            self.set_task('move', 'LEFT')
        elif self.position[1] < 3:
            self.set_task('move', 'RIGHT')
        else:
            self.set_task('wait')

    def set_task(self, task, *args, **kwargs):
        self.task = Task(self, task, args, kwargs)
        self.task.check()

    def proceed(self, is_AI=True):
        """Further the thing in its tasks.

        Decrements .task.todo; if it thus falls to <= 0, enacts method whose
        name is 'task_' + self.task.name and sets .task = None. If is_AI, calls
        .decide_task to decide a self.task.
        """
        self.task.todo -= 1
        if self.task.todo <= 0:
            task = getattr(self, 'task_' + self.task.name)
            task(*self.task.args, **self.task.kwargs)
            self.task = None
        if is_AI and self.task is None:
            self.decide_task()


class World:

    def __init__(self):
        self.turn = 0
        self.map_size = (5, 5)
        self.map_ = 'xxxxx' +\
                    'x...x' +\
                    'x.X.x' +\
                    'x...x' +\
                    'xxxxx'
        self.things = [
            Thing(self, 'human', [3, 3]),
            Thing(self, 'monster', [1, 1])
        ]
        self.player_i = 0
        self.player = self.things[self.player_i]
