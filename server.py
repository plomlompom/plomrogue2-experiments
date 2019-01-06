#!/usr/bin/env python3

import socketserver
import threading
import queue
import sys
import os
import parser
import server_.game
import game_common


# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


class Server(socketserver.ThreadingTCPServer):
    """Bind together threaded IO handling server and message queue."""

    def __init__(self, queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue_out = queue
        self.daemon_threads = True  # Else, server's threads have daemon=False.


class IO_Handler(socketserver.BaseRequestHandler):

    def handle(self):
        """Move messages between network socket and main thread via queues.

        On start, sets up new queue, sends it via self.server.queue_out to
        main thread, and from then on receives messages to send back from the
        main thread via that new queue.

        At the same time, loops over socket's recv to get messages from the
        outside via self.server.queue_out into the main thread. Ends connection
        once a 'QUIT' message is received from socket, and then also kills its
        own queue.

        All messages to the main thread are tuples, with the first element a
        meta command ('ADD_QUEUE' for queue creation, 'KILL_QUEUE' for queue
        deletion, and 'COMMAND' for everything else), the second element a UUID
        that uniquely identifies the thread (so that the main thread knows whom
        to send replies back to), and optionally a third element for further
        instructions.
        """
        import plom_socket_io

        def caught_send(socket, message):
            """Send message by socket, catch broken socket connection error."""
            try:
                plom_socket_io.send(socket, message)
            except plom_socket_io.BrokenSocketConnection:
                pass

        def send_queue_messages(socket, queue_in, thread_alive):
            """Send messages via socket from queue_in while thread_alive[0]."""
            while thread_alive[0]:
                try:
                    msg = queue_in.get(timeout=1)
                except queue.Empty:
                    continue
                caught_send(socket, msg)

        import uuid
        print('CONNECTION FROM:', str(self.client_address))
        connection_id = uuid.uuid4()
        queue_in = queue.Queue()
        self.server.queue_out.put(('ADD_QUEUE', connection_id, queue_in))
        thread_alive = [True]
        t = threading.Thread(target=send_queue_messages,
                             args=(self.request, queue_in, thread_alive))
        t.start()
        for message in plom_socket_io.recv(self.request):
            if message is None:
                caught_send(self.request, 'BAD MESSAGE')
            elif 'QUIT' == message:
                caught_send(self.request, 'BYE')
                break
            else:
                self.server.queue_out.put(('COMMAND', connection_id, message))
        self.server.queue_out.put(('KILL_QUEUE', connection_id))
        thread_alive[0] = False
        print('CONNECTION CLOSED FROM:', str(self.client_address))
        self.request.close()


def fib(n):
    """Calculate n-th Fibonacci number. Very inefficiently."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


class CommandHandler(game_common.Commander, server_.game.Commander):

    def __init__(self):
        from multiprocessing import Pool
        self.queues_out = {}
        self.world = server_.game.World()
        self.parser = parser.Parser(self)
        # self.pool and self.pool_result are currently only needed by the FIB
        # command and the demo of a parallelized game loop in cmd_inc_p.
        self.pool = Pool()
        self.pool_result = None

    def handle_input(self, input_, connection_id=None, abort_on_error=False):
        """Process input_ to command grammar, call command handler if found."""
        from inspect import signature
        try:
            command = self.parser.parse(input_)
            if command is None:
                self.send_to(connection_id, 'UNHANDLED INPUT')
            else:
                if 'connection_id' in list(signature(command).parameters):
                    command(connection_id=connection_id)
                else:
                    command()
        except parser.ArgError as e:
            self.send_to(connection_id, 'ARGUMENT ERROR: ' + str(e))
            if abort_on_error:
                exit(1)
        except server_.game.GameError as e:
            self.send_to(connection_id, 'GAME ERROR: ' + str(e))
            if abort_on_error:
                exit(1)

    def send_to(self, connection_id, msg):
        """Send msg to client of connection_id; if no later, print instead."""
        if connection_id:
            self.queues_out[connection_id].put(msg)
        else:
            print(msg)

    def send_all(self, msg):
        """Send msg to all clients."""
        for connection_id in self.queues_out:
            self.send_to(connection_id, msg)

    def send_all_gamestate(self):
        """Send out game state data relevant to clients."""

        def stringify_yx(tuple_):
            """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
            return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])

        def quoted(string):
            """Quote & escape string so client interprets it as single token."""
            quoted = []
            quoted += ['"']
            for c in string:
                if c in {'"', '\\'}:
                    quoted += ['\\']
                quoted += [c]
            quoted += ['"']
            return ''.join(quoted)

        self.send_all('NEW_TURN ' + str(self.world.turn))
        self.send_all('MAP_SIZE ' + stringify_yx(self.world.map_size))
        for y in range(self.world.map_size[0]):
            width = self.world.map_size[1]
            terrain_line = self.world.terrain_map[y * width:(y + 1) * width]
            self.send_all('TERRAIN_LINE %5s %s' % (y, quoted(terrain_line)))
        for thing in self.world.things:
            self.send_all('THING_TYPE %s %s' % (thing.id_, thing.type_))
            self.send_all('THING_POS %s %s' % (thing.id_,
                                               stringify_yx(thing.position)))

    def proceed(self):
        """Send turn finish signal, run game world, send new world data.

        First sends 'TURN_FINISHED' message, then runs game world
        until new player input is needed, then sends game state.
        """
        self.send_all('TURN_FINISHED ' + str(self.world.turn))
        self.world.proceed_to_next_player_turn()
        self.send_all_gamestate()

    def cmd_FIB(self, numbers, connection_id):
        """Reply with n-th Fibonacci numbers, n taken from tokens[1:].

        Numbers are calculated in parallel as far as possible, using fib().
        A 'CALCULATING …' message is sent to caller before the result.
        """
        self.send_to(connection_id, 'CALCULATING …')
        results = self.pool.map(fib, numbers)
        reply = ' '.join([str(r) for r in results])
        self.send_to(connection_id, reply)
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
        self.send_all('TURN_FINISHED ' + str(self.world.turn))
        sleep(1)
        self.world.turn += 1
        self.send_all_gamestate()
        self.pool_result = self.pool.map_async(fib, (35, 35))


def io_loop(q, commander):
    """Handle commands coming through queue q, send results back.

    Commands from q are expected to be tuples, with the first element either
    'ADD_QUEUE', 'COMMAND', or 'KILL_QUEUE', the second element a UUID, and
    an optional third element of arbitrary type. The UUID identifies a
    receiver for replies.

    An 'ADD_QUEUE' command should contain as third element a queue through
    which to send messages back to the sender of the command. A 'KILL_QUEUE'
    command removes the queue for that receiver from the list of queues through
    which to send replies.

    A 'COMMAND' command is specified in greater detail by a string that is the
    tuple's third element. The commander CommandHandler takes care of processing
    this and sending out replies.
    """
    while True:
        x = q.get()
        command_type = x[0]
        connection_id = x[1]
        content = None if len(x) == 2 else x[2]
        if command_type == 'ADD_QUEUE':
            commander.queues_out[connection_id] = content
        elif command_type == 'COMMAND':
            commander.handle_input(content, connection_id)
        elif command_type == 'KILL_QUEUE':
            del commander.queues_out[connection_id]


if len(sys.argv) != 2:
    print('wrong number of arguments, expected one (game file)')
    exit(1)
game_file_name = sys.argv[1]
commander = CommandHandler()
if os.path.exists(game_file_name):
    if not os.path.isfile(game_file_name):
        print('game file name does not refer to a valid game file')
    else:
        with open(game_file_name, 'r') as f:
            lines = f.readlines()
        for i in range(len(lines)):
            line = lines[i]
            print("FILE INPUT LINE %s: %s" % (i, line), end='')
            commander.handle_input(line, abort_on_error=True)
else:
    commander.handle_input('MAP_SIZE Y:5,X:5')
    commander.handle_input('TERRAIN_LINE 0 "xxxxx"')
    commander.handle_input('TERRAIN_LINE 1 "x...x"')
    commander.handle_input('TERRAIN_LINE 2 "x.X.x"')
    commander.handle_input('TERRAIN_LINE 3 "x...x"')
    commander.handle_input('TERRAIN_LINE 4 "xxxxx"')
    commander.handle_input('THING_TYPE 0 human')
    commander.handle_input('THING_POS 0 Y:3,X:3')
    commander.handle_input('THING_TYPE 1 monster')
    commander.handle_input('THING_POS 1 Y:1,X:1')
q = queue.Queue()
c = threading.Thread(target=io_loop, daemon=True, args=(q, commander))
c.start()
server = Server(q, ('localhost', 5000), IO_Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    print('Killing server')
    server.server_close()
