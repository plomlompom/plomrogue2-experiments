#!/usr/bin/env python3

import socketserver
import plom_socket_io
import threading
import time
import queue

# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


class Server(socketserver.ThreadingTCPServer):
    """Bind together threaded IO handling server and message queue."""

    def __init__(self, queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue_out = queue
        self.daemon_threads = True  # Else, server's threads have daemon=False.


def fib(n):
    """Calculate n-th Fibonacci number. Very inefficiently."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


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
        print('CONNECTION CLOSED:', str(self.client_address))
        self.request.close()


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
    tuple's third element. Here, the following commands are understood:
    - A string starting with 'PRIVMSG' returns the space-separated tokens
      following 'PRIVMSG' to the sender via its receiver queue.
    - A string starting with 'ALL' sends the space-separated tokens following
      'ALL' to all receiver queues.
    - A string starting with 'FIB' followed by space-separated positive
      integers returns to the receiver queue first a 'CALCULATING …' messsage,
      and afterwards for each such integer n the n-th Fibonacci number as a
      space-separated sequence of integers. Fibonacci numbers are calculated
      in parallel if possible.
    """
    from multiprocessing import Pool
    queues_out = {}
    while True:
        x = q.get()
        command_type = x[0]
        connection_id = x[1]
        content = None if len(x) == 2 else x[2]
        if command_type == 'ADD_QUEUE':
            queues_out[connection_id] = content
        elif command_type == 'COMMAND':
            tokens = [token for token in content.split(' ') if len(token) > 0]
            if len(tokens) == 0:
                queues_out[connection_id].put('EMPTY COMMAND')
                continue
            if  tokens[0] == 'PRIVMSG':
                reply = ' '.join(tokens[1:])
                queues_out[connection_id].put(reply)
            elif tokens[0] == 'ALL':
                reply = ' '.join(tokens[1:])
                for key in queues_out:
                    queues_out[key].put(reply)
            elif tokens[0] == 'FIB':
                fib_fail = 'MALFORMED FIB REQUEST'
                if len(tokens) < 2:
                    queues_out[connection_id].put(fib_fail)
                    continue
                numbers = []
                fail = False
                for token in tokens[1:]:
                    if token != '0' and token.isdigit():
                        numbers += [int(token)]
                    else:
                        queues_out[connection_id].put(fib_fail)
                        fail = True
                        break
                if fail:
                    continue
                queues_out[connection_id].put('CALCULATING …')
                reply = ''
                # this blocks the whole loop, BAD
                with Pool(len(numbers)) as p:
                    results = p.map(fib, numbers)
                reply = ' '.join([str(r) for r in results])
                queues_out[connection_id].put(reply)
            else:
                queues_out[connection_id].put('UNKNOWN COMMAND')
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
