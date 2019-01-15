import socketserver
import threading
import queue


# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


# Our default server port.
SERVER_PORT=5000


class Server(socketserver.ThreadingTCPServer):
    """Bind together threaded IO handling server and message queue."""

    def __init__(self, queue, *args, **kwargs):
        super().__init__(('localhost', SERVER_PORT), IO_Handler, *args, **kwargs)
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
        from the outside via self.server.queue_out into the game IO
        loop. Ends connection once a 'QUIT' message is received from
        socket, and then also calls for a kill of its own queue.

        All messages to the game IO loop are tuples, with the first
        element a meta command ('ADD_QUEUE' for queue creation,
        'KILL_QUEUE' for queue deletion, and 'COMMAND' for everything
        else), the second element a UUID that uniquely identifies the
        thread (so that the game IO loop knows whom to send replies
        back to), and optionally a third element for further
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


def io_loop(q, game_command_handler):
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
            game_command_handler.queues_out[connection_id] = content
        elif command_type == 'COMMAND':
            game_command_handler.handle_input(content, connection_id)
        elif command_type == 'KILL_QUEUE':
            del game_command_handler.queues_out[connection_id]


def run_server_with_io_loop(command_handler):
    """Run connection of server talking to clients and game IO loop.

    We have the TCP server (an instance of Server) and we have the
    game IO loop, a thread running io_loop. Both communicate with each
    other via a queue.Queue. While the TCP server may spawn parallel
    threads to many clients, the IO loop works sequentially through
    game commands received from the TCP server's threads (= client
    connections to the TCP server), calling command_handler to process
    them. A processed command may trigger messages to the commanding
    client or to all clients, delivered from the IO loop to the TCP
    server via the queue.

    """
    q = queue.Queue()
    c = threading.Thread(target=io_loop, daemon=True, args=(q, command_handler))
    c.start()
    server = Server(q)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print('Killing server')
        server.server_close()
