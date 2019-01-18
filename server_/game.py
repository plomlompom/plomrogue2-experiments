import sys
sys.path.append('../')
import game_common
import server_.map_


class GameError(Exception):
    pass


class World(game_common.World):

    def __init__(self, game):
        super().__init__()
        self.game = game
        self.player_id = 0
        # use extended local classes
        self.Thing = Thing

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
        self.todo = 3

    def check(self):
        if self.name == 'move':
            if len(self.args) > 0:
                direction = self.args[0]
            else:
                direction = self.kwargs['direction']
            test_pos = self.thing.world.map_.move(self.thing.position, direction)
            if self.thing.world.map_[test_pos] != '.':
                raise GameError('would move into illegal terrain')
            for t in self.thing.world.things:
                if t.position == test_pos:
                    raise GameError('would move into other thing')


class Thing(game_common.Thing):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = Task(self, 'wait')
        self.last_task_result = None
        self._stencil = None

    def task_wait(self):
        return 'success'

    def task_move(self, direction):
        self.position = self.world.map_.move(self.position, direction)
        return 'success'

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

        Decrements .task.todo; if it thus falls to <= 0, enacts method
        whose name is 'task_' + self.task.name and sets .task =
        None. If is_AI, calls .decide_task to decide a self.task.

        Before doing anything, ensures an empty map visibility stencil
        and checks that task is still possible, and aborts it
        otherwise (for AI things, decides a new task).

        """
        self._stencil = None
        try:
            self.task.check()
        except GameError as e:
            self.task = None
            self.last_task_result = e
            if is_AI:
                self.decide_task()
            return
        self.task.todo -= 1
        if self.task.todo <= 0:
            task = getattr(self, 'task_' + self.task.name)
            self.last_task_result = task(*self.task.args, **self.task.kwargs)
            self.task = None
        if is_AI and self.task is None:
            self.decide_task()

    def get_stencil(self):
        if self._stencil is not None:
            return self._stencil
        m = self.world.map_.new_from_shape('?')
        for pos in m:
            if pos == self.position or m.are_neighbors(pos, self.position):
                m[pos] = '.'
        self._stencil = m
        return self._stencil

    def get_visible_map(self):
        stencil = self.get_stencil()
        m = self.world.map_.new_from_shape(' ')
        for pos in m:
            if stencil[pos] == '.':
                m[pos] = self.world.map_[pos]
        return m

    def get_visible_things(self):
        stencil = self.get_stencil()
        visible_things = []
        for thing in self.world.things:
            if stencil[thing.position] == '.':
                visible_things += [thing]
        return visible_things


def fib(n):
    """Calculate n-th Fibonacci number. Very inefficiently."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


class Game(game_common.CommonCommandsMixin):

    def __init__(self, game_file_name):
        import server_.io
        self.map_manager = server_.map_.map_manager
        self.world = World(self)
        self.io = server_.io.GameIO(game_file_name, self)
        # self.pool and self.pool_result are currently only needed by the FIB
        # command and the demo of a parallelized game loop in cmd_inc_p.
        from multiprocessing import Pool
        self.pool = Pool()
        self.pool_result = None

    def send_gamestate(self, connection_id=None):
        """Send out game state data relevant to clients."""

        def stringify_yx(tuple_):
            """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
            return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])

        self.io.send('NEW_TURN ' + str(self.world.turn))
        self.io.send('MAP ' + self.world.map_.geometry +\
                     ' ' + stringify_yx(self.world.map_.size))
        visible_map = self.world.get_player().get_visible_map()
        for y, line in visible_map.lines():
            self.io.send('VISIBLE_MAP_LINE %5s %s' % (y, self.io.quote(line)))
        visible_things = self.world.get_player().get_visible_things()
        for thing in visible_things:
            self.io.send('THING_TYPE %s %s' % (thing.id_, thing.type_))
            self.io.send('THING_POS %s %s' % (thing.id_,
                                              stringify_yx(thing.position)))

    def proceed(self):
        """Send turn finish signal, run game world, send new world data.

        First sends 'TURN_FINISHED' message, then runs game world
        until new player input is needed, then sends game state.
        """
        self.io.send('TURN_FINISHED ' + str(self.world.turn))
        self.world.proceed_to_next_player_turn()
        msg = str(self.world.get_player().last_task_result)
        self.io.send('LAST_PLAYER_TASK_RESULT ' + self.io.quote(msg))
        self.send_gamestate()

    def cmd_FIB(self, numbers, connection_id):
        """Reply with n-th Fibonacci numbers, n taken from tokens[1:].

        Numbers are calculated in parallel as far as possible, using fib().
        A 'CALCULATING …' message is sent to caller before the result.
        """
        self.io.send('CALCULATING …', connection_id)
        results = self.pool.map(fib, numbers)
        reply = ' '.join([str(r) for r in results])
        self.io.send(reply, connection_id)
    cmd_FIB.argtypes = 'seq:int:nonneg'

    def cmd_INC_P(self, connection_id):
        """Increment world.turn, send game turn data to everyone.

        To simulate game processing waiting times, a one second delay between
        TURN_FINISHED and NEW_TURN occurs; after NEW_TURN, some expensive
        calculations are started as pool processes that need to be finished
        until a further INC finishes the turn.

        This is just a demo structure for how the game loop could work when
        parallelized. One might imagine a two-step game turn, with a non-action
        step determining actor tasks (the AI determinations would take the
        place of the fib calculations here), and an action step wherein these
        tasks are performed (where now sleep(1) is).
        """
        from time import sleep
        if self.pool_result is not None:
            self.pool_result.wait()
        self.io.send('TURN_FINISHED ' + str(self.world.turn))
        sleep(1)
        self.world.turn += 1
        self.send_gamestate()
        self.pool_result = self.pool.map_async(fib, (35, 35))

    def cmd_MOVE(self, direction):
        """Set player task to 'move' with direction arg, finish player turn."""
        import parser
        legal_directions = self.world.map_.get_directions()
        if direction not in legal_directions:
            raise parser.ArgError('Move argument must be one of: ' +
                                  ', '.join(legal_directions))
        self.world.get_player().set_task('move', direction=direction)
        self.proceed()
    cmd_MOVE.argtypes = 'string'

    def cmd_WAIT(self):
        """Set player task to 'wait', finish player turn."""
        self.world.get_player().set_task('wait')
        self.proceed()

    def cmd_GET_GAMESTATE(self, connection_id):
        """Send game state jto caller."""
        self.send_gamestate(connection_id)

    def cmd_ECHO(self, msg, connection_id):
        """Send msg to caller."""
        self.io.send(msg, connection_id)
    cmd_ECHO.argtypes = 'string'

    def cmd_ALL(self, msg, connection_id):
        """Send msg to all clients."""
        self.io.send(msg)
    cmd_ALL.argtypes = 'string'

    def cmd_TERRAIN_LINE(self, y, terrain_line):
        self.world.map_.set_line(y, terrain_line)
    cmd_TERRAIN_LINE.argtypes = 'int:nonneg string'
