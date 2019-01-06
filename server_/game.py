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
            player = self.get_player()
            player_i = self.things.index(player)
            for thing in self.things[player_i+1:]:
                thing.proceed()
            self.turn += 1
            for thing in self.things[:player_i]:
                thing.proceed()
            player.proceed(is_AI=False)
            if player.task is None:
                break

    def get_player(self):
        return self.get_thing(self.player_id)


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

        Before doing anything, checks that task is still possible, and aborts
        it otherwise (for AI things, decides a new task).
        """
        try:
            self.task.check()
        except GameError:
            self.task = None
            if is_AI:
                self.decide_task()
            return
        self.task.todo -= 1
        if self.task.todo <= 0:
            task = getattr(self, 'task_' + self.task.name)
            task(*self.task.args, **self.task.kwargs)
            self.task = None
        if is_AI and self.task is None:
            self.decide_task()


class Commander():

    def cmd_MOVE(self, direction):
        """Set player task to 'move' with direction arg, finish player turn."""
        if direction not in {'UP', 'DOWN', 'RIGHT', 'LEFT'}:
            raise parser.ArgError('Move argument must be one of: '
                                  'UP, DOWN, RIGHT, LEFT')
        self.world.get_player().set_task('move', direction=direction)
        self.proceed()
    cmd_MOVE.argtypes = 'string'

    def cmd_WAIT(self):
        """Set player task to 'wait', finish player turn."""
        self.world.get_player().set_task('wait')
        self.proceed()

    def cmd_GET_TURN(self, connection_id):
        """Send world.turn to caller."""
        self.send_to(connection_id, str(self.world.turn))

    def cmd_ECHO(self, msg, connection_id):
        """Send msg to caller."""
        self.send_to(connection_id, msg)
    cmd_ECHO.argtypes = 'string'

    def cmd_ALL(self, msg, connection_id):
        """Send msg to all clients."""
        self.send_all(msg)
    cmd_ALL.argtypes = 'string'
