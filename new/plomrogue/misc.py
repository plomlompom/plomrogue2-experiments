#!/usr/bin/env python3
import socketserver
import threading
import queue
import sys
import parser


class GameError(Exception):
    pass


# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


class Server(socketserver.ThreadingTCPServer):
    """Bind together threaded IO handling server and message queue."""

    def __init__(self, queue, port, *args, **kwargs):
        super().__init__(('localhost', port), IO_Handler, *args, **kwargs)
        self.queue_out = queue
        self.daemon_threads = True  # Else, server's threads have daemon=False.


class IO_Handler(socketserver.BaseRequestHandler):

    def handle(self):
        """Move messages between network socket and game IO loop via queues.

        On start (a new connection from client to server), sets up a
        new queue, sends it via self.server.queue_out to the game IO
        loop thread, and from then on receives messages to send back
        from the game IO loop via that new queue.

        At the same time, loops over socket's recv to get messages
        from the outside into the game IO loop by way of
        self.server.queue_out into the game IO. Ends connection once a
        'QUIT' message is received from socket, and then also calls
        for a kill of its own queue.

        All messages to the game IO loop are tuples, with the first
        element a meta command ('ADD_QUEUE' for queue creation,
        'KILL_QUEUE' for queue deletion, and 'COMMAND' for everything
        else), the second element a UUID that uniquely identifies the
        thread (so that the game IO loop knows whom to send replies
        back to), and optionally a third element for further
        instructions.

        """

        def send_queue_messages(plom_socket, queue_in, thread_alive):
            """Send messages via socket from queue_in while thread_alive[0]."""
            while thread_alive[0]:
                try:
                    msg = queue_in.get(timeout=1)
                except queue.Empty:
                    continue
                plom_socket.send(msg, True)

        import uuid
        import plom_socket
        plom_socket = plom_socket.PlomSocket(self.request)
        print('CONNECTION FROM:', str(self.client_address))
        connection_id = uuid.uuid4()
        queue_in = queue.Queue()
        self.server.queue_out.put(('ADD_QUEUE', connection_id, queue_in))
        thread_alive = [True]
        t = threading.Thread(target=send_queue_messages,
                             args=(plom_socket, queue_in, thread_alive))
        t.start()
        for message in plom_socket.recv():
            if message is None:
                plom_socket.send('BAD MESSAGE', True)
            elif 'QUIT' == message:
                plom_socket.send('BYE', True)
                break
            else:
                self.server.queue_out.put(('COMMAND', connection_id, message))
        self.server.queue_out.put(('KILL_QUEUE', connection_id))
        thread_alive[0] = False
        print('CONNECTION CLOSED FROM:', str(self.client_address))
        plom_socket.socket.close()


class GameIO():

    def __init__(self, game_file_name, game):
        self.game_file_name = game_file_name
        self.queues_out = {}
        self.parser = parser.Parser(game)

    def loop(self, q):
        """Handle commands coming through queue q, send results back.

        Commands from q are expected to be tuples, with the first element
        either 'ADD_QUEUE', 'COMMAND', or 'KILL_QUEUE', the second element
        a UUID, and an optional third element of arbitrary type. The UUID
        identifies a receiver for replies.

        An 'ADD_QUEUE' command should contain as third element a queue
        through which to send messages back to the sender of the
        command. A 'KILL_QUEUE' command removes the queue for that
        receiver from the list of queues through which to send replies.

        A 'COMMAND' command is specified in greater detail by a string
        that is the tuple's third element. The game_command_handler takes
        care of processing this and sending out replies.

        """
        while True:
            x = q.get()
            command_type = x[0]
            connection_id = x[1]
            content = None if len(x) == 2 else x[2]
            if command_type == 'ADD_QUEUE':
                self.queues_out[connection_id] = content
            elif command_type == 'KILL_QUEUE':
                del self.queues_out[connection_id]
            elif command_type == 'COMMAND':
                self.handle_input(content, connection_id)

    def run_loop_with_server(self):
        """Run connection of server talking to clients and game IO loop.

        We have the TCP server (an instance of Server) and we have the
        game IO loop, a thread running self.loop. Both communicate with
        each other via a queue.Queue. While the TCP server may spawn
        parallel threads to many clients, the IO loop works sequentially
        through game commands received from the TCP server's threads (=
        client connections to the TCP server). A processed command may
        trigger messages to the commanding client or to all clients,
        delivered from the IO loop to the TCP server via the queue.

        """
        q = queue.Queue()
        c = threading.Thread(target=self.loop, daemon=True, args=(q,))
        c.start()
        server = Server(q, 5000)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            print('Killing server')
            server.server_close()

    def handle_input(self, input_, connection_id=None, store=True):
        """Process input_ to command grammar, call command handler if found."""
        from inspect import signature

        def answer(connection_id, msg):
            if connection_id:
                self.send(msg, connection_id)
            else:
                print(msg)

        try:
            command, args = self.parser.parse(input_)
            if command is None:
                answer(connection_id, 'UNHANDLED_INPUT')
            else:
                if 'connection_id' in list(signature(command).parameters):
                    command(*args, connection_id=connection_id)
                else:
                    command(*args)
                    if store and not hasattr(command, 'dont_save'):
                        with open(self.game_file_name, 'a') as f:
                            f.write(input_ + '\n')
        except parser.ArgError as e:
            answer(connection_id, 'ARGUMENT_ERROR ' + quote(str(e)))
        except GameError as e:
            answer(connection_id, 'GAME_ERROR ' + quote(str(e)))

    def send(self, msg, connection_id=None):
        """Send message msg to server's client(s) via self.queues_out.

        If a specific client is identified by connection_id, only
        sends msg to that one. Else, sends it to all clients
        identified in self.queues_out.

        """
        if connection_id:
            self.queues_out[connection_id].put(msg)
        else:
            for connection_id in self.queues_out:
                self.queues_out[connection_id].put(msg)


class MapBase:

    def __init__(self, size=(0, 0)):
        self.size = size
        self.terrain = '?'*self.size_i

    @property
    def size_i(self):
        return self.size[0] * self.size[1]

    def set_line(self, y, line):
        height_map = self.size[0]
        width_map = self.size[1]
        if y >= height_map:
            raise ArgError('too large row number %s' % y)
        width_line = len(line)
        if width_line > width_map:
            raise ArgError('too large map line width %s' % width_line)
        self.terrain = self.terrain[:y * width_map] + line +\
                       self.terrain[(y + 1) * width_map:]

    def get_position_index(self, yx):
        return yx[0] * self.size[1] + yx[1]


class Map(MapBase):

    def __getitem__(self, yx):
        return self.terrain[self.get_position_index(yx)]

    def __setitem__(self, yx, c):
        pos_i = self.get_position_index(yx)
        if type(c) == str:
            self.terrain = self.terrain[:pos_i] + c + self.terrain[pos_i + 1:]
        else:
            self.terrain[pos_i] = c

    def __iter__(self):
        """Iterate over YX position coordinates."""
        for y in range(self.size[0]):
            for x in range(self.size[1]):
                yield [y, x]

    def lines(self):
        width = self.size[1]
        for y in range(self.size[0]):
            yield (y, self.terrain[y * width:(y + 1) * width])

    def get_fov_map(self, yx):
        return self.fov_map_type(self, yx)

    def get_directions(self):
        directions = []
        for name in dir(self):
            if name[:5] == 'move_':
                directions += [name[5:]]
        return directions

    def get_neighbors(self, pos):
        neighbors = {}
        if not hasattr(self, 'neighbors_to'):
            self.neighbors_to = {}
        if pos in self.neighbors_to:
            return self.neighbors_to[pos]
        for direction in self.get_directions():
            neighbors[direction] = None
            try:
                neighbors[direction] = self.move(pos, direction)
            except GameError:
                pass
        self.neighbors_to[pos] = neighbors
        return neighbors

    def new_from_shape(self, init_char):
        import copy
        new_map = copy.deepcopy(self)
        for pos in new_map:
            new_map[pos] = init_char
        return new_map

    def move(self, start_pos, direction):
        mover = getattr(self, 'move_' + direction)
        new_pos = mover(start_pos)
        if new_pos[0] < 0 or new_pos[1] < 0 or \
                new_pos[0] >= self.size[0] or new_pos[1] >= self.size[1]:
            raise GameError('would move outside map bounds')
        return new_pos

    def move_LEFT(self, start_pos):
        return [start_pos[0], start_pos[1] - 1]

    def move_RIGHT(self, start_pos):
        return [start_pos[0], start_pos[1] + 1]



class MapHex(Map):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fov_map_type = FovMapHex

    def move_UPLEFT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] - 1, start_pos[1] - 1]
        else:
            return [start_pos[0] - 1, start_pos[1]]

    def move_UPRIGHT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] - 1, start_pos[1]]
        else:
            return [start_pos[0] - 1, start_pos[1] + 1]

    def move_DOWNLEFT(self, start_pos):
        if start_pos[0] % 2 == 1:
             return [start_pos[0] + 1, start_pos[1] - 1]
        else:
               return [start_pos[0] + 1, start_pos[1]]

    def move_DOWNRIGHT(self, start_pos):
        if start_pos[0] % 2 == 1:
            return [start_pos[0] + 1, start_pos[1]]
        else:
            return [start_pos[0] + 1, start_pos[1] + 1]



class FovMap:

    def __init__(self, source_map, yx):
        self.source_map = source_map
        self.size = self.source_map.size
        self.terrain = '?' * self.size_i
        self[yx] = '.'
        self.shadow_cones = []
        self.circle_out(yx, self.shadow_process_hex)

    def shadow_process_hex(self, yx, distance_to_center, dir_i, dir_progress):
        # Possible optimization: If no shadow_cones yet and self[yx] == '.',
        # skip all.
        CIRCLE = 360  # Since we'll float anyways, number is actually arbitrary.

        def correct_arm(arm):
            if arm < 0:
                arm += CIRCLE
            return arm

        def in_shadow_cone(new_cone):
            for old_cone in self.shadow_cones:
                if old_cone[0] >= new_cone[0] and \
                    new_cone[1] >= old_cone[1]:
                    #print('DEBUG shadowed by:', old_cone)
                    return True
                # We might want to also shade hexes whose middle arm is inside a
                # shadow cone for a darker FOV. Note that we then could not for
                # optimization purposes rely anymore on the assumption that a
                # shaded hex cannot add growth to existing shadow cones.
            return False

        def merge_cone(new_cone):
            import math
            for old_cone in self.shadow_cones:
                if new_cone[0] > old_cone[0] and \
                    (new_cone[1] < old_cone[0] or
                     math.isclose(new_cone[1], old_cone[0])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[0] = new_cone[0]
                    #print('DEBUG merged cone:', old_cone)
                    return True
                if new_cone[1] < old_cone[1] and \
                    (new_cone[0] > old_cone[1] or
                     math.isclose(new_cone[0], old_cone[1])):
                    #print('DEBUG merging to', old_cone)
                    old_cone[1] = new_cone[1]
                    #print('DEBUG merged cone:', old_cone)
                    return True
            return False

        def eval_cone(cone):
            #print('DEBUG CONE', cone, '(', step_size, distance_to_center, number_steps, ')')
            if in_shadow_cone(cone):
                return
            self[yx] = '.'
            if self.source_map[yx] != '.':
                #print('DEBUG throws shadow', cone)
                unmerged = True
                while merge_cone(cone):
                    unmerged = False
                if unmerged:
                    self.shadow_cones += [cone]

        #print('DEBUG', yx)
        step_size = (CIRCLE/len(self.circle_out_directions)) / distance_to_center
        number_steps = dir_i * distance_to_center + dir_progress
        left_arm = correct_arm(-(step_size/2) - step_size*number_steps)
        right_arm = correct_arm(left_arm - step_size)
        # Optimization potential: left cone could be derived from previous
        # right cone. Better even: Precalculate all cones.
        if right_arm > left_arm:
            eval_cone([left_arm, 0])
            eval_cone([CIRCLE, right_arm])
        else:
            eval_cone([left_arm, right_arm])

    def basic_circle_out_move(self, pos, direction):
        """Move position pos into direction. Return whether still in map."""
        mover = getattr(self, 'move_' + direction)
        pos[:] = mover(pos)
        if pos[0] < 0 or pos[1] < 0 or \
            pos[0] >= self.size[0] or pos[1] >= self.size[1]:
            return False
        return True

    def circle_out(self, yx, f):
        # Optimization potential: Precalculate movement positions. (How to check
        # circle_in_map then?)
        # Optimization potential: Precalculate what hexes are shaded by what hex
        # and skip evaluation of already shaded hexes. (This only works if hex
        # shading implies they completely lie in existing shades; otherwise we
        # would lose shade growth through hexes at shade borders.)

        # TODO: Start circling only in earliest obstacle distance.
        circle_in_map = True
        distance = 1
        yx = yx[:]
        #print('DEBUG CIRCLE_OUT', yx)
        while circle_in_map:
            circle_in_map = False
            self.basic_circle_out_move(yx, 'RIGHT')
            for dir_i in range(len(self.circle_out_directions)):
                for dir_progress in range(distance):
                    direction = self.circle_out_directions[dir_i]
                    if self.circle_out_move(yx, direction):
                        f(yx, distance, dir_i, dir_progress)
                        circle_in_map = True
            distance += 1



class FovMapHex(FovMap, MapHex):
    circle_out_directions = ('DOWNLEFT', 'LEFT', 'UPLEFT',
                             'UPRIGHT', 'RIGHT', 'DOWNRIGHT')

    def circle_out_move(self, yx, direction):
        return self.basic_circle_out_move(yx, direction)



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
                stringed_args += [quote(arg)]
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



def cmd_GEN_WORLD(self, yx, seed):
    self.world.make_new(yx, seed)
cmd_GEN_WORLD.argtypes = 'yx_tuple:pos string'

def cmd_GET_GAMESTATE(self, connection_id):
    """Send game state to caller."""
    self.send_gamestate(connection_id)

def cmd_MAP(self, yx):
    """Create new map of size yx and only '?' cells."""
    self.world.new_map(yx)
cmd_MAP.argtypes = 'yx_tuple:pos'

def cmd_THING_TYPE(self, i, type_):
    t = self.world.get_thing(i)
    t.type_ = type_
cmd_THING_TYPE.argtypes = 'int:nonneg string'

def cmd_THING_POS(self, i, yx):
    t = self.world.get_thing(i)
    t.position = list(yx)
cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'

def cmd_TERRAIN_LINE(self, y, terrain_line):
    self.world.map_.set_line(y, terrain_line)
cmd_TERRAIN_LINE.argtypes = 'int:nonneg string'

def cmd_PLAYER_ID(self, id_):
    # TODO: test whether valid thing ID
    self.world.player_id = id_
cmd_PLAYER_ID.argtypes = 'int:nonneg'

def cmd_TURN(self, n):
    self.world.turn = n
cmd_TURN.argtypes = 'int:nonneg'

def cmd_SWITCH_PLAYER(self):
    player = self.world.get_player()
    player.set_task('WAIT')
    thing_ids = [t.id_ for t in self.world.things]
    player_index = thing_ids.index(player.id_)
    if player_index == len(thing_ids) - 1:
        self.world.player_id = thing_ids[0]
    else:
        self.world.player_id = thing_ids[player_index + 1]
    self.proceed()

def cmd_SAVE(self):

    def write(f, msg):
        f.write(msg + '\n')

    save_file_name = self.io.game_file_name + '.save'
    with open(save_file_name, 'w') as f:
        write(f, 'TURN %s' % self.world.turn)
        write(f, 'MAP ' + stringify_yx(self.world.map_.size))
        for y, line in self.world.map_.lines():
            write(f, 'TERRAIN_LINE %5s %s' % (y, quote(line)))
        for thing in self.world.things:
            write(f, 'THING_TYPE %s %s' % (thing.id_, thing.type_))
            write(f, 'THING_POS %s %s' % (thing.id_,
                                          stringify_yx(thing.position)))
            task = thing.task
            if task is not None:
                task_args = task.get_args_string()
                write(f, 'SET_TASK:%s %s %s %s' % (task.name, thing.id_,
                                                   task.todo, task_args))
        write(f, 'PLAYER_ID %s' % self.world.player_id)
cmd_SAVE.dont_save = True


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
        from functools import partial

        def cmd_TASK_colon(task_name, game, *args):
            game.world.get_player().set_task(task_name, args)
            game.proceed()

        def cmd_SET_TASK_colon(task_name, game, thing_id, todo, *args):
            t = game.world.get_thing(thing_id, False)
            if t is None:
                raiseArgError('No such Thing.')
            task_class = game.tasks[task_name]
            t.task = task_class(t, args)
            t.task.todo = todo

        def task_prefixed(command_name, task_prefix, task_command,
                          argtypes_prefix=None):
            if command_name[:len(task_prefix)] == task_prefix:
                task_name = command_name[len(task_prefix):]
                if task_name in self.tasks:
                    f = partial(task_command, task_name, self)
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
            f = partial(self.commands[command_name], self)
            if hasattr(self.commands[command_name], 'argtypes'):
                f.argtypes = self.commands[command_name].argtypes
            return f
        return None



def quote(string):
    """Quote & escape string so client interprets it as single token."""
    quoted = []
    quoted += ['"']
    for c in string:
        if c in {'"', '\\'}:
            quoted += ['\\']
        quoted += [c]
    quoted += ['"']
    return ''.join(quoted)


def stringify_yx(tuple_):
    """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
    return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])



if __name__ == "__main__":
    import sys
    import os
    if len(sys.argv) != 2:
        print('wrong number of arguments, expected one (game file)')
        exit(1)
    game_file_name = sys.argv[1]
    game = Game(game_file_name)
    if os.path.exists(game_file_name):
        if not os.path.isfile(game_file_name):
            print('game file name does not refer to a valid game file')
        else:
            with open(game_file_name, 'r') as f:
                lines = f.readlines()
            for i in range(len(lines)):
                line = lines[i]
                print("FILE INPUT LINE %5s: %s" % (i, line), end='')
                game.io.handle_input(line, store=False)
    else:
        game.io.handle_input('GEN_WORLD Y:16,X:16 bar')
    game.io.run_loop_with_server()
