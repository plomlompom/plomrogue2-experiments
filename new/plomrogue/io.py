import queue
import threading
import socketserver
from plomrogue.errors import GameError, ArgError, BrokenSocketConnection
from plomrogue.parser import Parser
from plomrogue.misc import quote



# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True



class PlomSocket:

    def __init__(self, socket):
        self.socket = socket

    def send(self, message, silent_connection_break=False):
        """Send via self.socket, encoded/delimited as way recv() expects.

        In detail, all \ and $ in message are escaped with prefixed \,
        and an unescaped $ is appended as a message delimiter. Then,
        socket.send() is called as often as necessary to ensure
        message is sent fully, as socket.send() due to buffering may
        not send all of it right away.

        Assuming socket is blocking, it's rather improbable that
        socket.send() will be partial / return a positive value less
        than the (byte) length of msg – but not entirely out of the
        question. See: - <http://stackoverflow.com/q/19697218> -
        <http://stackoverflow.com/q/2618736> -
        <http://stackoverflow.com/q/8900474>

        This also handles a socket.send() return value of 0, which
        might be possible or not (?) for blocking sockets: -
        <http://stackoverflow.com/q/34919846>

        """
        escaped_message = ''
        for char in message:
            if char in ('\\', '$'):
                escaped_message += '\\'
            escaped_message += char
        escaped_message += '$'
        data = escaped_message.encode()
        totalsent = 0
        while totalsent < len(data):
            socket_broken = False
            try:
                sent = self.socket.send(data[totalsent:])
                socket_broken = sent == 0
            except OSError as err:
                if err.errno == 9:  # "Bad file descriptor", when connection broken
                    socket_broken = True
                else:
                    raise err
            if socket_broken and not silent_connection_break:
                raise BrokenSocketConnection
            totalsent = totalsent + sent

    def recv(self):
        """Get full send()-prepared message from self.socket.

        In detail, socket.recv() is looped over for sequences of bytes
        that can be decoded as a Unicode string delimited by an
        unescaped $, with \ and $ escapable by \. If a sequence of
        characters that ends in an unescaped $ cannot be decoded as
        Unicode, None is returned as its representation. Stop once
        socket.recv() returns nothing.

        Under the hood, the TCP stack receives packets that construct
        the input payload in an internal buffer; socket.recv(BUFSIZE)
        pops up to BUFSIZE bytes from that buffer, without knowledge
        either about the input's segmentation into packets, or whether
        the input is segmented in any other meaningful way; that's why
        we do our own message segmentation with $ as a delimiter.

        """
        esc = False
        data = b''
        msg = b''
        while True:
            data += self.socket.recv(1024)
            if 0 == len(data):
                return
            cut_off = 0
            for c in data:
                cut_off += 1
                if esc:
                    msg += bytes([c])
                    esc = False
                elif chr(c) == '\\':
                    esc = True
                elif chr(c) == '$':
                    try:
                        yield msg.decode()
                    except UnicodeDecodeError:
                        yield None
                    data = data[cut_off:]
                    msg = b''
                else:
                    msg += bytes([c])



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
        plom_socket = PlomSocket(self.request)
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
        self.parser = Parser(game)

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
        except ArgError as e:
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
