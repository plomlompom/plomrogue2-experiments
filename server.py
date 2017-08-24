#!/usr/bin/env python3

import socketserver
import threading
import queue

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


class Task:

    def __init__(self, name, args=(), kwargs={}):
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.todo = 1


class Thing:

    def __init__(self, type_, position):
        self.type = type_
        self.position = position
        self.task = Task('wait')

    def task_wait(self):
        pass

    def task_move(self, direction):
        if direction == 'UP':
            self.position[0] -= 1
        elif direction == 'DOWN':
            self.position[0] += 1
        elif direction == 'RIGHT':
            self.position[1] += 1
        elif direction == 'LEFT':
            self.position[1] -= 1

    def decide_task(self):
        if self.position[1] > 1:
            self.set_task('move', 'LEFT')
        elif self.position[1] < 3:
            self.set_task('move', 'RIGHT')
        else:
            self.set_task('wait')

    def set_task(self, task, *args, **kwargs):
        self.task = Task(task, args, kwargs)

    def proceed(self, is_AI=True):
        """Further the thing in its tasks.

        Decrements .task.todo; if it thus falls to <= 0, enacts method whose
        name is 'task_' + self.task.name and sets .task = None. If is_AI, calls
        .decide_task to decide a self.task.
        """
        self.task.todo -= 1
        if self.task.todo <= 0:
            task= getattr(self, 'task_' + self.task.name)
            task(*self.task.args, **self.task.kwargs)
            self.task = None
        if is_AI and self.task is None:
            self.decide_task()


class World:

    def __init__(self):
        self.turn = 0
        self.map_size = (5, 5)
        self.map_ = 'xxxxx\n'+\
                    'x...x\n'+\
                    'x.X.x\n'+\
                    'x...x\n'+\
                    'xxxxx'
        self.things = [Thing('human', [3, 3]), Thing('monster', [1, 1])]
        self.player_i = 0
        self.player = self.things[self.player_i]


def fib(n):
    """Calculate n-th Fibonacci number. Very inefficiently."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


class ArgumentError(Exception):
    pass


class CommandHandler:

    def __init__(self, queues_out):
        from multiprocessing import Pool
        self.queues_out = queues_out
        self.world = World()
        # self.pool and self.pool_result are currently only needed by the FIB
        # command and the demo of a parallelized game loop in cmd_inc_p.
        self.pool = Pool()
        self.pool_result = None

    def send_to(self, connection_id, msg):
        """Send msg to client of connection_id."""
        self.queues_out[connection_id].put(msg)

    def send_all(self, msg):
        """Send msg to all clients."""
        for connection_id in self.queues_out:
            self.send_to(connection_id, msg)

    def stringify_yx(self, tuple_):
        """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
        return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])

    def proceed_to_next_player_turn(self, connection_id):
        """Run game world turns until player can decide their next step.

        Sends a 'TURN_FINISHED' message, then iterates through all non-player
        things, on each step furthering them in their tasks (and letting them
        decide new ones if they finish). The iteration order is: first all
        things that come after the player in the world things list, then (after
        incrementing the world turn) all that come before the player; then the
        player's .proceed() is run, and if it does not finish his task, the
        loop starts at the beginning. Once the player's task is finished, the
        loop breaks, and client-relevant game data is sent.
        """
        self.send_all('TURN_FINISHED ' + str(self.world.turn))
        while True:
            for thing in self.world.things[self.world.player_i+1:]:
                thing.proceed()
            self.world.turn += 1
            for thing  in self.world.things[:self.world.player_i]:
                thing.proceed()
            self.world.player.proceed(is_AI=False)
            if self.world.player.task is None:
                break
        self.send_all('NEW_TURN ' + str(self.world.turn))
        self.send_all('MAP_SIZE ' + self.stringify_yx(self.world.map_size))
        self.send_all('TERRAIN\n' + self.world.map_)
        for thing in self.world.things:
            self.send_all('THING TYPE:' + thing.type + ' '
                          + self.stringify_yx(thing.position))

    def cmd_fib(self, tokens, connection_id):
        """Reply with n-th Fibonacci numbers, n taken from tokens[1:].

        Numbers are calculated in parallel as far as possible, using fib().
        A 'CALCULATING …' message is sent to caller before the result.
        """
        if len(tokens) < 2:
            raise ArgumentError('FIB NEEDS AT LEAST ONE ARGUMENT')
        numbers = []
        for token in tokens[1:]:
            if token == '0' or not token.isdigit():
                raise ArgumentError('FIB ARGUMENTS MUST BE INTEGERS > 0')
            numbers += [int(token)]
        self.send_to(connection_id, 'CALCULATING …')
        results = self.pool.map(fib, numbers)
        reply = ' '.join([str(r) for r in results])
        self.send_to(connection_id, reply)

    def cmd_inc_p(self, connection_id):
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
        self.send_all('NEW_TURN ' + str(self.world.turn))
        self.send_all('MAP_SIZE ' + self.stringify_yx(self.world.map_size))
        self.send_all('TERRAIN\n' + self.world.map_)
        for thing in self.world.things:
            self.send_all('THING TYPE:' + thing.type + ' '
                          + self.stringify_yx(thing.position))
        self.pool_result = self.pool.map_async(fib, (35, 35))

    def cmd_get_turn(self, connection_id):
        """Send world.turn to caller."""
        self.send_to(connection_id, str(self.world.turn))

    def cmd_move(self, direction, connection_id):
        """Set player task to 'move' with direction arg, finish player turn."""
        if not direction in {'UP', 'DOWN', 'RIGHT', 'LEFT'}:
            raise ArgumentError('MOVE ARGUMENT MUST BE ONE OF: '
                                'UP, DOWN, RIGHT, LEFT')
        self.world.player.set_task('move', direction=direction)
        self.proceed_to_next_player_turn(connection_id)

    def cmd_wait(self, connection_id):
        """Set player task to 'wait', finish player turn."""
        self.world.player.set_task('wait')
        self.proceed_to_next_player_turn(connection_id)

    def cmd_echo(self, tokens, input_, connection_id):
        """Send message in input_ beyond tokens[0] to caller."""
        msg = input_[len(tokens[0]) + 1:]
        self.send_to(connection_id, msg)

    def cmd_all(self, tokens, input_):
        """Send message in input_ beyond tokens[0] to all clients."""
        msg = input_[len(tokens[0]) + 1:]
        self.send_all(msg)

    def handle_input(self, input_, connection_id):
        """Process input_ to command grammar, call command handler if found."""
        tokens = [token for token in input_.split(' ') if len(token) > 0]
        try:
            if len(tokens) == 0:
                self.send_to(connection_id, 'EMPTY COMMAND')
            elif len(tokens) == 1 and tokens[0] == 'INC_P':
                self.cmd_inc_p(connection_id)
            elif len(tokens) == 1 and tokens[0] == 'GET_TURN':
                self.cmd_get_turn(connection_id)
            elif len(tokens) == 1 and tokens[0] == 'WAIT':
                self.cmd_wait(connection_id)
            elif len(tokens) == 2 and tokens[0] == 'MOVE':
                self.cmd_move(tokens[1], connection_id)
            elif len(tokens) >= 1 and tokens[0] == 'ECHO':
                self.cmd_echo(tokens, input_, connection_id)
            elif len(tokens) >= 1 and tokens[0] == 'ALL':
                self.cmd_all(tokens, input_)
            elif len(tokens) >= 1 and tokens[0] == 'FIB':
                # TODO: Should this really block the whole loop?
                self.cmd_fib(tokens, connection_id)
            else:
                self.send_to(connection_id, 'UNKNOWN COMMAND')
        except ArgumentError as e:
            self.send_to(connection_id, 'ARGUMENT ERROR: ' + str(e))


def io_loop(q):
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
    tuple's third element. CommandHandler takes care of processing this and
    sending out replies.
    """
    queues_out = {}
    command_handler = CommandHandler(queues_out)
    while True:
        x = q.get()
        command_type = x[0]
        connection_id = x[1]
        content = None if len(x) == 2 else x[2]
        if command_type == 'ADD_QUEUE':
            queues_out[connection_id] = content
        elif command_type == 'COMMAND':
            command_handler.handle_input(content, connection_id)
        elif command_type == 'KILL_QUEUE':
            del queues_out[connection_id]


q = queue.Queue()
c = threading.Thread(target=io_loop, daemon=True, args=(q,))
c.start()
server = Server(q, ('localhost', 5000), IO_Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    print('Killing server')
    server.server_close()
