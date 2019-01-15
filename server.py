#!/usr/bin/env python3
import sys
import os
import parser
import server_.game
import server_.io
import game_common


def fib(n):
    """Calculate n-th Fibonacci number. Very inefficiently."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


class CommandHandler(server_.game.Commander):

    def __init__(self, game_file_name):
        self.queues_out = {}
        self.world = server_.game.World()
        self.parser = parser.Parser(self)
        self.game_file_name = game_file_name
        # self.pool and self.pool_result are currently only needed by the FIB
        # command and the demo of a parallelized game loop in cmd_inc_p.
        from multiprocessing import Pool
        self.pool = Pool()
        self.pool_result = None

    def quote(self, string):
        """Quote & escape string so client interprets it as single token."""
        quoted = []
        quoted += ['"']
        for c in string:
            if c in {'"', '\\'}:
                quoted += ['\\']
            quoted += [c]
        quoted += ['"']
        return ''.join(quoted)

    def handle_input(self, input_, connection_id=None, store=True):
        """Process input_ to command grammar, call command handler if found."""
        from inspect import signature

        def answer(connection_id, msg):
            if connection_id:
                self.send(msg, connection_id)
            else:
                print(msg)

        try:
            command = self.parser.parse(input_)
            if command is None:
                answer(connection_id, 'UNHANDLED_INPUT')
            else:
                if 'connection_id' in list(signature(command).parameters):
                    command(connection_id=connection_id)
                else:
                    command()
                    if store:
                        with open(self.game_file_name, 'a') as f:
                            f.write(input_ + '\n')
        except parser.ArgError as e:
            answer(connection_id, 'ARGUMENT_ERROR ' + self.quote(str(e)))
        except server_.game.GameError as e:
            answer(connection_id, 'GAME_ERROR ' + self.quote(str(e)))

    def send(self, msg, connection_id=None):
        if connection_id:
            self.queues_out[connection_id].put(msg)
        else:
            for connection_id in self.queues_out:
                self.queues_out[connection_id].put(msg)

    def send_gamestate(self, connection_id=None):
        """Send out game state data relevant to clients."""

        def stringify_yx(tuple_):
            """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
            return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])

        self.send('NEW_TURN ' + str(self.world.turn))
        self.send('MAP_SIZE ' + stringify_yx(self.world.map_.size))
        visible_map = self.world.get_player().get_visible_map()
        for y in range(self.world.map_.size[0]):
            self.send('VISIBLE_MAP_LINE %5s %s' %
                      (y, self.quote(visible_map.get_line(y))))
        visible_things = self.world.get_player().get_visible_things()
        for thing in visible_things:
            self.send('THING_TYPE %s %s' % (thing.id_, thing.type_))
            self.send('THING_POS %s %s' % (thing.id_,
                                           stringify_yx(thing.position)))

    def proceed(self):
        """Send turn finish signal, run game world, send new world data.

        First sends 'TURN_FINISHED' message, then runs game world
        until new player input is needed, then sends game state.
        """
        self.send('TURN_FINISHED ' + str(self.world.turn))
        self.world.proceed_to_next_player_turn()
        msg = str(self.world.get_player().last_task_result)
        self.send('LAST_PLAYER_TASK_RESULT ' + self.quote(msg))
        self.send_gamestate()

    def cmd_FIB(self, numbers, connection_id):
        """Reply with n-th Fibonacci numbers, n taken from tokens[1:].

        Numbers are calculated in parallel as far as possible, using fib().
        A 'CALCULATING …' message is sent to caller before the result.
        """
        self.send('CALCULATING …', connection_id)
        results = self.pool.map(fib, numbers)
        reply = ' '.join([str(r) for r in results])
        self.send(reply, connection_id)
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
        self.send('TURN_FINISHED ' + str(self.world.turn))
        sleep(1)
        self.world.turn += 1
        self.send_gamestate()
        self.pool_result = self.pool.map_async(fib, (35, 35))


if len(sys.argv) != 2:
    print('wrong number of arguments, expected one (game file)')
    exit(1)
game_file_name = sys.argv[1]
command_handler = CommandHandler(game_file_name)
if os.path.exists(game_file_name):
    if not os.path.isfile(game_file_name):
        print('game file name does not refer to a valid game file')
    else:
        with open(game_file_name, 'r') as f:
            lines = f.readlines()
        for i in range(len(lines)):
            line = lines[i]
            print("FILE INPUT LINE %s: %s" % (i, line), end='')
            command_handler.handle_input(line, store=False)
else:
    command_handler.handle_input('MAP_SIZE Y:5,X:5')
    command_handler.handle_input('TERRAIN_LINE 0 "xxxxx"')
    command_handler.handle_input('TERRAIN_LINE 1 "x...x"')
    command_handler.handle_input('TERRAIN_LINE 2 "x.X.x"')
    command_handler.handle_input('TERRAIN_LINE 3 "x...x"')
    command_handler.handle_input('TERRAIN_LINE 4 "xxxxx"')
    command_handler.handle_input('THING_TYPE 0 human')
    command_handler.handle_input('THING_POS 0 Y:3,X:3')
    command_handler.handle_input('THING_TYPE 1 monster')
    command_handler.handle_input('THING_POS 1 Y:1,X:1')


server_.io.run_server_with_io_loop(command_handler)
