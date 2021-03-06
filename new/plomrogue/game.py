from plomrogue.tasks import (Task_WAIT, Task_MOVE, Task_PICKUP,
                             Task_DROP, Task_EAT)
from plomrogue.errors import ArgError, GameError
from plomrogue.commands import (cmd_GEN_WORLD, cmd_GET_GAMESTATE,
                                cmd_MAP, cmd_MAP, cmd_THING_TYPE,
                                cmd_THING_POS, cmd_THING_INVENTORY,
                                cmd_THING_HEALTH, cmd_SEED,
                                cmd_GET_PICKABLE_ITEMS, cmd_MAP_SIZE,
                                cmd_TERRAIN_LINE, cmd_PLAYER_ID,
                                cmd_TURN, cmd_SWITCH_PLAYER, cmd_SAVE)
from plomrogue.mapping import MapGeometryHex, Map, YX
from plomrogue.parser import Parser
from plomrogue.io import GameIO
from plomrogue.misc import quote
from plomrogue.things import Thing, ThingMonster, ThingHuman, ThingFood
import random



class PRNGod(random.Random):

    def seed(self, seed):
        self.prngod_seed = seed

    def getstate(self):
        return self.prngod_seed

    def setstate(seed):
        self.seed(seed)

    def random(self):
        self.prngod_seed = ((self.prngod_seed * 1103515245) + 12345) % 2**32
        return (self.prngod_seed >> 16) / (2**16 - 1)



class GameBase:

    def __init__(self):
        self.turn = 0
        self.things = []

    def get_thing(self, id_, create_unfound=True):
        for thing in self.things:
            if id_ == thing.id_:
                return thing
        if create_unfound:
            t = self.thing_type(self, id_)
            self.things += [t]
            return t
        return None

    def things_at_pos(self, pos):
        things = []
        for t in self.things:
            if t.position == pos:
                things += [t]
        return things



class Game(GameBase):

    def __init__(self, game_file_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.io = GameIO(game_file_name, self)
        self.map_size = None
        self.map_geometry = MapGeometryHex()
        self.tasks = {'WAIT': Task_WAIT,
                      'MOVE': Task_MOVE,
                      'PICKUP': Task_PICKUP,
                      'EAT': Task_EAT,
                      'DROP': Task_DROP}
        self.commands = {'GEN_WORLD': cmd_GEN_WORLD,
                         'GET_GAMESTATE': cmd_GET_GAMESTATE,
                         'SEED': cmd_SEED,
                         'MAP_SIZE': cmd_MAP_SIZE,
                         'MAP': cmd_MAP,
                         'THING_TYPE': cmd_THING_TYPE,
                         'THING_POS': cmd_THING_POS,
                         'THING_HEALTH': cmd_THING_HEALTH,
                         'THING_INVENTORY': cmd_THING_INVENTORY,
                         'TERRAIN_LINE': cmd_TERRAIN_LINE,
                         'GET_PICKABLE_ITEMS': cmd_GET_PICKABLE_ITEMS,
                         'PLAYER_ID': cmd_PLAYER_ID,
                         'TURN': cmd_TURN,
                         'SWITCH_PLAYER': cmd_SWITCH_PLAYER,
                         'SAVE': cmd_SAVE}
        self.thing_type = Thing
        self.thing_types = {'human': ThingHuman,
                            'monster': ThingMonster,
                            'food': ThingFood}
        self.player_id = 0
        self.player_is_alive = True
        self.maps = {}
        self.rand = PRNGod(0)

    def get_string_options(self, string_option_type):
        if string_option_type == 'direction':
            return self.map_geometry.get_directions()
        elif string_option_type == 'thingtype':
            return list(self.thing_types.keys())
        return None

    def send_gamestate(self, connection_id=None):
        """Send out game state data relevant to clients."""

        def send_thing(thing):
            view_pos = self.map_geometry.pos_in_view(thing.position,
                                                     self.player.view_offset,
                                                     self.map_size)
            self.io.send('THING_TYPE %s %s' % (thing.id_, thing.type_))
            self.io.send('THING_POS %s %s' % (thing.id_, view_pos))

        self.io.send('TURN ' + str(self.turn))
        visible_map = self.player.get_visible_map()
        self.io.send('VISIBLE_MAP %s %s' % (visible_map.size,
                                            visible_map.start_indented))
        for y, line in visible_map.lines():
            self.io.send('VISIBLE_MAP_LINE %5s %s' % (y, quote(line)))
        visible_things = self.player.get_visible_things()
        for thing in visible_things:
            send_thing(thing)
            if hasattr(thing, 'health'):
                self.io.send('THING_HEALTH %s %s' % (thing.id_,
                                                     thing.health))
        if len(self.player.inventory) > 0:
            self.io.send('PLAYER_INVENTORY %s' %
                         ','.join([str(i) for i in self.player.inventory]))
        else:
            self.io.send('PLAYER_INVENTORY ,')
        for id_ in self.player.inventory:
            thing = self.get_thing(id_)
            send_thing(thing)
        self.io.send('GAME_STATE_COMPLETE')

    def proceed(self):
        """Send turn finish signal, run game world, send new world data.

        First sends 'TURN_FINISHED' message, then runs game world
        until new player input is needed, then sends game state.
        """
        self.io.send('TURN_FINISHED ' + str(self.turn))
        self.proceed_to_next_player_turn()
        msg = str(self.player._last_task_result)
        self.io.send('LAST_PLAYER_TASK_RESULT ' + quote(msg))
        self.send_gamestate()

    def get_command(self, command_name):

        def partial_with_attrs(f, *args, **kwargs):
            from functools import partial
            p = partial(f, *args, **kwargs)
            p.__dict__.update(f.__dict__)
            return p

        def cmd_TASK_colon(task_name, game, *args):
            if not game.player_is_alive:
                raise GameError('You are dead.')
            game.player.set_task(task_name, args)
            game.proceed()

        def cmd_SET_TASK_colon(task_name, game, thing_id, todo, *args):
            t = game.get_thing(thing_id, False)
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

    @property
    def player(self):
        return self.get_thing(self.player_id)

    def new_thing_id(self):
        if len(self.things) == 0:
            return 0
        return self.things[-1].id_ + 1

    def get_map(self, map_pos, create_unfound=True):
        if not (map_pos in self.maps and
                self.maps[map_pos].size == self.map_size):
            if create_unfound:
                self.maps[map_pos] = Map(self.map_size)
                for pos in self.maps[map_pos]:
                    self.maps[map_pos][pos] = '.'
            else:
                return None
        return self.maps[map_pos]

    def proceed_to_next_player_turn(self):
        """Run game world turns until player can decide their next step.

        Iterates through all non-player things, on each step
        furthering them in their tasks (and letting them decide new
        ones if they finish). The iteration order is: first all things
        that come after the player in the world things list, then
        (after incrementing the world turn) all that come before the
        player; then the player's .proceed() is run, and if it does
        not finish his task, the loop starts at the beginning. Once
        the player's task is finished, or the player is dead, the loop
        breaks.

        """
        while True:
            player_i = self.things.index(self.player)
            for thing in self.things[player_i+1:]:
                thing.proceed()
            self.turn += 1
            for pos in self.maps[YX(0,0)]:
                if self.maps[YX(0,0)][pos] == '.' and \
                   len(self.things_at_pos((YX(0,0), pos))) == 0 and \
                   self.rand.random() > 0.999:
                    self.add_thing_at('food', (YX(0,0), pos))
            for thing in self.things[:player_i]:
                thing.proceed()
            self.player.proceed(is_AI=False)
            if self.player.task is None or not self.player_is_alive:
                break

    def add_thing_at(self, type_, pos):
        t = self.thing_types[type_](self)
        t.position = pos
        self.things += [t]
        return t

    def make_new_world(self, yx, seed):

        def add_thing_at_random(type_):
            while True:
                new_pos = (YX(0,0),
                           YX(self.rand.randint(0, yx.y - 1),
                              self.rand.randint(0, yx.x - 1)))
                if self.maps[new_pos[0]][new_pos[1]] != '.':
                    continue
                if len(self.things_at_pos(new_pos)) > 0:
                    continue
                return self.add_thing_at(type_, new_pos)

        self.things = []
        self.rand.seed(seed)
        self.turn = 0
        self.maps = {}
        self.map_size = yx
        map_ = self.get_map(YX(0,0))
        for pos in map_:
            map_[pos] = self.rand.choice(('.', '.', '.', '~', 'x'))
        player = add_thing_at_random('human')
        self.player_id = player.id_
        add_thing_at_random('monster')
        add_thing_at_random('monster')
        add_thing_at_random('food')
        add_thing_at_random('food')
        add_thing_at_random('food')
        add_thing_at_random('food')
        return 'success'

