#!/usr/bin/env python3

import urwid
import plom_socket_io 
import socket
import threading


class RecvThread(threading.Thread):
    """Background thread that delivers messages from the socket to urwid.

    The message transfer to urwid is a bit weird. The urwid developers warn
    against sharing urwid resources among threads, and recommend using urwid's
    watch_pipe mechanism: using a pipe from non-urwid threads into a single
    urwid thread. We could pipe the recv output directly, but then we get
    complicated buffering situations here as well as in the urwid code that
    receives the pipe content. It's much easier to update a third resource
    (server_output, which references an object that's also known to the urwid
    code) to contain the new message, and then just use the urwid pipe
    (urwid_pipe_write_fd) to trigger the urwid code to pull the message in from
    that third resource. We send a single b' ' through the pipe to trigger it.
    """

    def __init__(self, socket, urwid_pipe_write_fd, server_output):
        super().__init__()
        self.socket = socket
        self.urwid_pipe = urwid_pipe_write_fd
        self.server_output = server_output

    def run(self):
        """On message receive, write to self.server_output, ping urwid pipe."""
        import os
        for msg in plom_socket_io.recv(self.socket):
            self.server_output[0] = msg
            os.write(self.urwid_pipe, b' ')


class InputHandler:
    """Helps delivering data from other thread to widget via message_container.
    
    The whole class only exists to provide handle_input as a bound method, with
    widget and message_container pre-set, as (bound) handle_input is used as a
    callback in urwid's watch_pipe – which merely provides its callback target
    with one parameter for a pipe to read data from an urwid-external thread.
    """

    def __init__(self, widget, message_container):
        self.widget = widget
        self.message_container = message_container

    def handle_input(self, trigger):
        """On input from other thread, either quit, or write to widget text.

        Serves as a receiver to urwid's watch_pipe mechanism, with trigger the
        data that a pipe defined by watch_pipe delivers. To avoid buffering
        trouble, we don't care for that data beyond the fact that its receival
        triggers this function: The sender is to write the data it wants to
        deliver into the container referenced by self.message_container, and
        just pipe the trigger to inform us about this.

        If the message delivered is 'BYE', quits Urbit.
        """
        if self.message_container[0] == 'BYE':
            raise urwid.ExitMainLoop()
            return
        self.widget.set_text('REPLY: ' + self.message_container[0])


class SocketInputWidget(urwid.Filler):

    def __init__(self, socket, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.socket = socket

    def keypress(self, size, key):
        """Act like super(), except on Enter: send .edit_text, and empty it."""
        if key != 'enter':
            return super().keypress(size, key)
        plom_socket_io.send(self.socket, edit.edit_text)
        edit.edit_text = ''


s = socket.create_connection(('127.0.0.1', 5000))

edit = urwid.Edit('SEND: ')
txt = urwid.Text('')
pile = urwid.Pile([edit, txt])
fill = SocketInputWidget(s, pile)
loop = urwid.MainLoop(fill)

server_output = ['']
write_fd = loop.watch_pipe(getattr(InputHandler(txt, server_output),
                                   'handle_input'))
thread = RecvThread(s, write_fd, server_output)
thread.start()

loop.run()

thread.join()
s.close()
