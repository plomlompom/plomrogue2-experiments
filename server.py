#!/usr/bin/env python3

import socketserver
import plom_socket_io
import threading
import time

# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


class Server(socketserver.ThreadingTCPServer):
    """Bind together threaded IO handling server and world state (counter)."""

    def __init__(self, counter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = counter
        self.daemon_threads = True  # Else, server's threads have daemon=False.


def fib(n):
    """Calculate n-th Fibonacci number."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


class IO_Handler(socketserver.BaseRequestHandler):

    def handle(self):
        """Loop recv for input, send replies; also, send regular counter value.

        If input is 'QUIT', send reply 'BYE' and end loop / connection.
        Otherwise, use handle_message to interpret and enact commands.
        """
        def caught_send(socket, message):
            """Send message by socket, catch broken socket connection error."""
            try:
                plom_socket_io.send(socket, message)
            except plom_socket_io.BrokenSocketConnection:
                pass

        def send_counter_loop(socket, counter, kill):
            """Every 5 seconds, send state of counter[0] until kill[0] set."""
            while not kill[0]:
                caught_send(socket, 'COUNTER ' + str(counter[0]))
                time.sleep(5)

        def handle_message(message):
            """Evaluate message for tasks to perform, yield result.

            Accepts one command: FIB, followed by positive integers, all tokens
            separated by whitespace. Will calculate and return for each such
            integer n the n-th Fibonacci number. Uses multiprocessing to
            perform multiple such calculations in parallel. Yields a
            'CALCULATING …' message before the calculation starts, and finally
            yields a message containing the results. (The 'CALCULATING …'
            message coming before the results message is currently the main
            reason this works as a generator function using yield.)

            When no command can be read into the message, just yields a 'NO
            COMMAND UNDERSTOOD:', followed by the message.
            """
            from multiprocessing import Pool
            tokens = message.split(' ')
            if tokens[0] == 'FIB':
                msg_fail_fib = 'MALFORMED FIB REQUEST'
                if len(tokens) < 2:
                    yield msg_fail_fib
                    return
                numbers = []
                for token in tokens[1:]:
                    if token != '0' and token.isdigit():
                        numbers += [int(token)]
                    elif token == '':
                        continue
                    else:
                        yield msg_fail_fib
                        return
                yield 'CALCULATING …'
                reply = ''
                with Pool(len(numbers)) as p:
                    results = p.map(fib, numbers)
                reply = ' '.join([str(r) for r in results])
                yield reply
                return
            yield 'NO COMMAND UNDERSTOOD: %s' % message

        print('CONNECTION FROM:', str(self.client_address))
        counter_loop_killer = [False]
        send_count = threading.Thread(target=send_counter_loop,
                                      kwargs={'counter': self.server.counter,
                                              'socket': self.request,
                                              'kill': counter_loop_killer})
        send_count.start()
        for message in plom_socket_io.recv(self.request):
            if message is None:
                print('RECEIVED MALFORMED MESSAGE')
                caught_send(self.request, 'bad message')
            elif 'QUIT' == message:
                caught_send(self.request, 'BYE')
                break
            else:
                print('RECEIVED MESSAGE:', message)
                for reply in handle_message(message):
                    caught_send(self.request, reply)
        counter_loop_killer = [True]
        print('CONNECTION CLOSED:', str(self.client_address))
        self.request.close()


def inc_loop(counter, interval):
    """Loop incrementing counter every interval seconds."""
    while True:
        time.sleep(interval)
        counter[0] += 1


counter = [0]
b = threading.Thread(target=inc_loop, daemon=True, kwargs={'counter': counter,
                                                           'interval': 1})
b.start()
server = Server(counter, ('localhost', 5000), IO_Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    print('Killing server')
    server.server_close()
