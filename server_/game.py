import sys
sys.path.append('../')
import game_common


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


class World(game_common.World):

    def __init__(self):
        super().__init__()
        self.Thing = Thing  # use local Thing class instead of game_common's
        self.player_id = 0

    def proceed_to_next_player_turn(self):
        """Run game world turns until player can decide their next step.

        Iterates through all non-player things, on each step
        furthering them in their tasks (and letting them decide new
        ones if they finish). The iteration order is: first all things
        that come after the player in the world things list, then
        (after incrementing the world turn) all that come before the
        player; then the player's .proceed() is run, and if it does
        not finish his task, the loop starts at the beginning. Once
        the player's task is finished, the loop breaks.
        """
        while True:
            for thing in self.things[self.player_id+1:]:
                thing.proceed()
            self.turn += 1
            for thing in self.things[:self.player_id]:
                thing.proceed()
            player = self.get_thing(self.player_id)
            player.proceed(is_AI=False)
            if player.task is None:
                break


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
            map_tile = self.thing.world.terrain_map[pos_i]
            if map_tile != '.':
                raise GameError('would move into illegal terrain')


class Thing(game_common.Thing):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def set_task(self, task_name, *args, **kwargs):
        self.task = Task(self, task_name, args, kwargs)
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
