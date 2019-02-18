from plomrogue.tasks import Task_WAIT, Task_MOVE
from plomrogue.errors import GameError, ArgError
from plomrogue.commands import (cmd_GEN_WORLD, cmd_GET_GAMESTATE, cmd_MAP,
                                cmd_MAP, cmd_THING_TYPE, cmd_THING_POS,
                                cmd_TERRAIN_LINE, cmd_PLAYER_ID, cmd_TURN,
                                cmd_SWITCH_PLAYER, cmd_SAVE)
from plomrogue.mapping import MapHex
from plomrogue.parser import Parser
from plomrogue.io import GameIO
from plomrogue.misc import quote, stringify_yx



class ThingBase:

    def __init__(self, world, id_, type_='?', position=[0,0]):
        self.world = world
        self.id_ = id_
        self.type_ = type_
        self.position = position



class Thing(ThingBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_task('WAIT')
        self._last_task_result = None
        self._stencil = None

    def move_towards_target(self, target):
        dijkstra_map = type(self.world.map_)(self.world.map_.size)
        n_max = 256
        dijkstra_map.terrain = [n_max for i in range(dijkstra_map.size_i)]
        dijkstra_map[target] = 0
        shrunk = True
        visible_map = self.get_visible_map()
        while shrunk:
            shrunk = False
            for pos in dijkstra_map:
                if visible_map[pos] != '.':
                    continue
                neighbors = dijkstra_map.get_neighbors(tuple(pos))
                for direction in neighbors:
                    yx = neighbors[direction]
                    if yx is not None and dijkstra_map[yx] < dijkstra_map[pos] - 1:
                        dijkstra_map[pos] = dijkstra_map[yx] + 1
                        shrunk = True
        #with open('log', 'a') as f:
        #    f.write('---------------------------------\n')
        #    for y, line in dijkstra_map.lines():
        #        for val in line:
        #            if val < 10:
        #                f.write(str(val))
        #            elif val == 256:
        #                f.write('x')
        #            else:
        #                f.write('~')
        #        f.write('\n')
        neighbors = dijkstra_map.get_neighbors(tuple(self.position))
        n = n_max
        #print('DEBUG', self.position, neighbors)
        #dirs = dijkstra_map.get_directions()
        #print('DEBUG dirs', dirs)
        #print('DEBUG neighbors', neighbors)
        #debug_scores = []
        #for pos in neighbors:
        #    if pos is None:
        #        debug_scores += [9000]
        #    else:
        #        debug_scores += [dijkstra_map[pos]]
        #print('DEBUG debug_scores', debug_scores)
        target_direction = None
        for direction in neighbors:
            yx = neighbors[direction]
            if yx is not None:
                n_new = dijkstra_map[yx]
                if n_new < n:
                    n = n_new
                    target_direction = direction
        #print('DEBUG result', direction)
        if target_direction:
            self.set_task('MOVE', (target_direction,))

    def decide_task(self):
        # TODO: Check if monster can follow player too well (even when they should lose them)
        visible_things = self.get_visible_things()
        target = None
        for t in visible_things:
            if t.type_ == 'human':
                target = t.position
                break
        if target is not None:
            try:
                self.move_towards_target(target)
                return
            except GameError:
                pass
        self.set_task('WAIT')

    def set_task(self, task_name, args=()):
        task_class = self.world.game.tasks[task_name]
        self.task = task_class(self, args)
        self.task.check()  # will throw GameError if necessary

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
            self._last_task_result = e
            if is_AI:
                try:
                    self.decide_task()
                except GameError:
                    self.set_task('WAIT')
            return
        self.task.todo -= 1
        if self.task.todo <= 0:
            self._last_task_result = self.task.do()
            self.task = None
        if is_AI and self.task is None:
            try:
                self.decide_task()
            except GameError:
                self.set_task('WAIT')

    def get_stencil(self):
        if self._stencil is not None:
            return self._stencil
        self._stencil = self.world.map_.get_fov_map(self.position)
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



class WorldBase:

    def __init__(self, game):
        self.turn = 0
        self.things = []
        self.game = game

    def get_thing(self, id_, create_unfound=True):
        for thing in self.things:
            if id_ == thing.id_:
                return thing
        if create_unfound:
            t = self.game.thing_type(self, id_)
            self.things += [t]
            return t
        return None



class World(WorldBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_id = 0

    def new_map(self, yx):
        self.map_ = self.game.map_type(yx)

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

    def make_new(self, yx, seed):
        import random
        random.seed(seed)
        self.turn = 0
        self.new_map(yx)
        for pos in self.map_:
            if 0 in pos or (yx[0] - 1) == pos[0] or (yx[1] - 1) == pos[1]:
                self.map_[pos] = '#'
                continue
            self.map_[pos] = random.choice(('.', '.', '.', '.', 'x'))
        player = self.game.thing_type(self, 0)
        player.type_ = 'human'
        player.position = [random.randint(0, yx[0] -1),
                           random.randint(0, yx[1] - 1)]
        npc = self.game.thing_type(self, 1)
        npc.type_ = 'monster'
        npc.position = [random.randint(0, yx[0] -1),
                        random.randint(0, yx[1] -1)]
        self.things = [player, npc]
        return 'success'



class Game:

    def __init__(self, game_file_name):
        self.io = GameIO(game_file_name, self)
        self.map_type = MapHex
        self.tasks = {'WAIT': Task_WAIT, 'MOVE': Task_MOVE}
        self.commands = {'GEN_WORLD': cmd_GEN_WORLD,
                         'GET_GAMESTATE': cmd_GET_GAMESTATE,
                         'MAP': cmd_MAP,
                         'THING_TYPE': cmd_THING_TYPE,
                         'THING_POS': cmd_THING_POS,
                         'TERRAIN_LINE': cmd_TERRAIN_LINE,
                         'PLAYER_ID': cmd_PLAYER_ID,
                         'TURN': cmd_TURN,
                         'SWITCH_PLAYER': cmd_SWITCH_PLAYER,
                         'SAVE': cmd_SAVE}
        self.world_type = World
        self.world = self.world_type(self)
        self.thing_type = Thing

    def get_string_options(self, string_option_type):
        if string_option_type == 'direction':
            return self.world.map_.get_directions()
        return None

    def send_gamestate(self, connection_id=None):
        """Send out game state data relevant to clients."""

        self.io.send('TURN ' + str(self.world.turn))
        self.io.send('MAP ' + stringify_yx(self.world.map_.size))
        visible_map = self.world.get_player().get_visible_map()
        for y, line in visible_map.lines():
            self.io.send('VISIBLE_MAP_LINE %5s %s' % (y, quote(line)))
        visible_things = self.world.get_player().get_visible_things()
        for thing in visible_things:
            self.io.send('THING_TYPE %s %s' % (thing.id_, thing.type_))
            self.io.send('THING_POS %s %s' % (thing.id_,
                                              stringify_yx(thing.position)))
        player = self.world.get_player()
        self.io.send('PLAYER_POS %s' % (stringify_yx(player.position)))
        self.io.send('GAME_STATE_COMPLETE')

    def proceed(self):
        """Send turn finish signal, run game world, send new world data.

        First sends 'TURN_FINISHED' message, then runs game world
        until new player input is needed, then sends game state.
        """
        self.io.send('TURN_FINISHED ' + str(self.world.turn))
        self.world.proceed_to_next_player_turn()
        msg = str(self.world.get_player()._last_task_result)
        self.io.send('LAST_PLAYER_TASK_RESULT ' + quote(msg))
        self.send_gamestate()

    def get_command(self, command_name):

        def partial_with_attrs(f, *args, **kwargs):
            from functools import partial
            p = partial(f, *args, **kwargs)
            p.__dict__.update(f.__dict__)
            return p

        def cmd_TASK_colon(task_name, game, *args):
            game.world.get_player().set_task(task_name, args)
            game.proceed()

        def cmd_SET_TASK_colon(task_name, game, thing_id, todo, *args):
            t = game.world.get_thing(thing_id, False)
            if t is None:
                raise ArgError('No such Thing.')
            task_class = game.tasks[task_name]
            t.task = task_class(t, args)
            t.task.todo = todo

        def task_prefixed(command_name, task_prefix, task_command,
                          argtypes_prefix=None):
            if command_name[:len(task_prefix)] == task_prefix:
                task_name = command_name[len(task_prefix):]
                if task_name in self.tasks:
                    f = partial_with_attrs(task_command, task_name, self)
                    task = self.tasks[task_name]
                    if argtypes_prefix:
                        f.argtypes = argtypes_prefix + ' ' + task.argtypes
                    else:
                        f.argtypes = task.argtypes
                    return f
            return None

        command = task_prefixed(command_name, 'TASK:', cmd_TASK_colon)
        if command:
            return command
        command = task_prefixed(command_name, 'SET_TASK:', cmd_SET_TASK_colon,
                                'int:nonneg int:nonneg ')
        if command:
            return command
        if command_name in self.commands:
            f = partial_with_attrs(self.commands[command_name], self)
            return f
        return None
