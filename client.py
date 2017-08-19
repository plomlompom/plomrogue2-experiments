#!/usr/bin/env python3

import urwid
import plom_socket_io
import socket
import threading


class UrwidSetup():

    def __init__(self, socket):
        """Build client urwid interface around socket communication.

        Sets up all widgets for writing to the socket and representing data
        from it. Sending via a self.EditToSocket widget is straightforward;
        polling the socket for input from the server in parallel to the urwid
        main loop not so much:

        The urwid developers warn against sharing urwid resources among
        threads, so having a socket polling thread for writing to an urwid
        widget while other widgets are handled in other threads would be
        dangerous. Urwid developers recommend using urwid's watch_pipe
        mechanism instead: using a pipe from non-urwid threads into a single
        urwid thread. We use self.recv_loop_thread to poll the socket, therein
        write socket.recv output to an object that is then linked to by
        self.server_output (which is known the urwid thread), and then use the
        pipe to urwid to trigger it pulling new data from self.server_output to
        handle via self.InputHandler. (We *could* pipe socket.recv output
        directly, but then we get complicated buffering situations here as well
        as in the urwid code that receives the pipe output. It's much easier to
        just tell the urwid code where it finds a full new server message to
        handle.)
        """
        self.socket = socket
        self.main_loop = urwid.MainLoop(self.setup_widgets())
        self.server_output = ['']
        input_handler = getattr(self.InputHandler(self.reply_widget,
                                                  self.map_widget,
                                                  self.server_output),
                                'handle_input')
        self.urwid_pipe_write_fd = self.main_loop.watch_pipe(input_handler)
        self.recv_loop_thread = threading.Thread(target=self.recv_loop)

    def setup_widgets(self):
        """Return container widget with all widgets we want on our screen.

        Sets up an urwid.Pile inside a returned urwid.Filler; top to bottom:
        - an EditToSocket widget, prefixing self.socket input with 'SEND: '
        - self.reply_widget, a urwid.Text widget printing self.socket replies
        - a 50-col wide urwid.Padding container for self.map_widget, which is
          to print clipped map representations
        """
        edit_widget = self.EditToSocket(self.socket, 'SEND: ')
        self.reply_widget = urwid.Text('')
        self.map_widget = urwid.Text('', wrap='clip')
        map_box = urwid.Padding(self.map_widget, width=50)
        widget_pile = urwid.Pile([edit_widget, self.reply_widget, map_box])
        return urwid.Filler(widget_pile)

    class EditToSocket(urwid.Edit):
        """Extends urwid.Edit with socket to send input on 'enter' to."""

        def __init__(self, socket, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.socket = socket

        def keypress(self, size, key):
            """Extend super(): on Enter, send .edit_text, and empty it."""
            if key != 'enter':
                return super().keypress(size, key)
            plom_socket_io.send(self.socket, self.edit_text)
            self.edit_text = ''

    class InputHandler:
        """Delivers data from other thread to widget via message_container.

        The class only exists to provide handle_input as a bound method, with
        widget and message_container pre-set, as (bound) handle_input is used
        as a callback in urwid's watch_pipe – which merely provides its
        callback target with one parameter for a pipe to read data from an
        urwid-external thread.
        """

        def __init__(self, widget1, widget2, message_container):
            self.widget1 = widget1
            self.widget2 = widget2
            self.message_container = message_container

        def handle_input(self, trigger):
            """On input from other thread, either quit or write to widget text.

            Serves as a receiver to urwid's watch_pipe mechanism, with trigger
            the data that a pipe defined by watch_pipe delivers. To avoid
            buffering trouble, we don't care for that data beyond the fact that
            its receival triggers this function: The sender is to write the
            data it wants to deliver into the container referenced by
            self.message_container, and just pipe the trigger to inform us
            about this.

            If the message delivered is 'BYE', quits Urbit.
            """
            if self.message_container[0] == 'BYE':
                raise urwid.ExitMainLoop()
                return
            self.widget1.set_text('SERVER: ' + self.message_container[0])
            self.widget2.set_text('loremipsumdolorsitamet '
                                  'loremipsumdolorsitamet'
                                  'loremipsumdolorsitamet '
                                  'loremipsumdolorsitamet\n'
                                  'loremipsumdolorsitamet '
                                  'loremipsumdolorsitamet')

    def recv_loop(self):
        """Loop to receive messages from socket and deliver them to urwid.

        Writes finished messages from the socket to self.server_output[0],
        then sends a single b' ' through self.urwid_pipe_write_fd to trigger
        the urwid code to read from it.
        """
        import os
        for msg in plom_socket_io.recv(self.socket):
            self.server_output[0] = msg
            os.write(self.urwid_pipe_write_fd, b' ')

    def run(self):
        """Run in parallel main and recv_loop thread."""
        self.recv_loop_thread.start()
        self.main_loop.run()
        self.recv_loop_thread.join()


s = socket.create_connection(('127.0.0.1', 5000))
u = UrwidSetup(s)
u.run()
s.close()
