#!/usr/bin/env python3

import socketserver
import plom_socket_io 

# Avoid "Address already in use" errors.
socketserver.TCPServer.allow_reuse_address = True


def fib(n):
    """Calculate n-th Fibonacci number."""
    if n in (1, 2):
        return 1
    else:
        return fib(n-1) + fib(n-2)


def handle_message(message):
    """Evaluate message for computing-heavy tasks to perform, yield result.

    Accepts one command: FIB, followed by positive integers, all tokens
    separated by whitespace. Will calculate and return for each such integer n
    the n-th Fibonacci number. Uses multiprocessing to perform multiple such
    calculations in parallel. Yields a 'CALCULATING …' message before the
    calculation starts, and finally yields a message containing the results.
    (The 'CALCULATING …' message coming before the results message is currently
    the main reason this works as a generator function using yield.)

    When no command can be read into the message, just yields a 'NO COMMAND
    UNDERSTOOD:', followed by the message.
    """
    tokens = message.split(' ')
    if tokens[0] == 'FIB':
        msg_fail_fib = 'MALFORMED FIB REQUEST'
        if len(tokens) < 2:
            yield msg_fail_fib
            return
        numbers = []
        fail = False
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
        from multiprocessing import Pool
        with Pool(len(numbers)) as p:
            results = p.map(fib, numbers)
        reply = ' '.join([str(r) for r in results])
        yield reply
        return
    yield 'NO COMMAND UNDERSTOOD: %s' % message


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Enables threading on TCP server for asynchronous IO handling."""
    pass


class MyTCPHandler(socketserver.BaseRequestHandler):

    def handle(self):
        """Loop recv for input, act on it, send reply.

        If input is 'QUIT', send reply 'BYE' and end loop / connection.
        Otherwise, use handle_message.
        """

        print('CONNECTION FROM:', str(self.client_address))
        for message in plom_socket_io.recv(self.request):
            if message is None:
                print('RECEIVED MALFORMED MESSAGE')
                plom_socket_io.send(self.request, 'bad message')
            elif 'QUIT' == message:
                plom_socket_io.send(self.request, 'BYE')
                break
            else:
                print('RECEIVED MESSAGE:', message)
                for reply in handle_message(message):
                    plom_socket_io.send(self.request, reply)
        print('CONNECTION CLOSED:', str(self.client_address))
        self.request.close()


server = ThreadedTCPServer(('localhost', 5000), MyTCPHandler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
