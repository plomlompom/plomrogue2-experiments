class BrokenSocketConnection(Exception):
    pass


def send(socket, message):
    """Send message via socket, encoded and delimited the way recv() expects.

    In detail, all \ and $ in message are escaped with prefixed \, and an
    unescaped $ is appended as a message delimiter. Then, socket.send() is
    called as often as necessary to ensure message is sent fully, as
    socket.send() due to buffering may not send all of it right away.

    Assuming socket is blocking, it's rather improbable that socket.send() will
    be partial / return a positive value less than the (byte) length of msg –
    but not entirely out of the question. See:
    - <http://stackoverflow.com/q/19697218>
    - <http://stackoverflow.com/q/2618736>
    - <http://stackoverflow.com/q/8900474>

    This also handles a socket.send() return value of 0, which might be
    possible or not (?) for blocking sockets:
    - <http://stackoverflow.com/q/34919846>
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
            sent = socket.send(data[totalsent:])
            socket_broken = sent == 0
        except OSError as err:
            if err.errno == 9:  # "Bad file descriptor", when connection broken
                socket_broken = True
            else:
                raise err
        if socket_broken:
            raise BrokenSocketConnection
        totalsent = totalsent + sent


def recv(socket):
    """Get full send()-prepared message from socket.

    In detail, socket.recv() is looped over for sequences of bytes that can be
    decoded as a Unicode string delimited by an unescaped $, with \ and $
    escapable by \. If a sequence of characters that ends in an unescaped $
    cannot be decoded as Unicode, None is returned as its representation. Stop
    once socket.recv() returns nothing.

    Under the hood, the TCP stack receives packets that construct the input
    payload in an internal buffer; socket.recv(BUFSIZE) pops up to BUFSIZE
    bytes from that buffer, without knowledge either about the input's
    segmentation into packets, or whether the input is segmented in any other
    meaningful way; that's why we do our own message segmentation with $ as a
    delimiter.
    """
    esc = False
    data = b''
    msg = b''
    while True:
        data += socket.recv(1024)
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
