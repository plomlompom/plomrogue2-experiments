#!/usr/bin/env python3

import urwid
import plom_socket_io
import socket
import threading


class ArgumentError(Exception):
    pass


class UrwidSetup:

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
        self.server_output (which is known to the urwid thread), then use the
        pipe to urwid to trigger it pulling new data from self.server_output to
        handle via self.InputHandler. (We *could* pipe socket.recv output
        directly, but then we get complicated buffering situations here as well
        as in the urwid code that receives the pipe output. It's easier to just
        tell the urwid code where it finds full new server messages to handle.)
        """
        self.socket = socket
        self.main_loop = urwid.MainLoop(self.setup_widgets())
        self.server_output = []
        input_handler = getattr(self.InputHandler(self.reply_widget,
                                                  self.map_widget,
                                                  self.server_output),
                                'handle_input')
        self.urwid_pipe_write_fd = self.main_loop.watch_pipe(input_handler)
        self.recv_loop_thread = threading.Thread(target=self.recv_loop)

    def setup_widgets(self):
        """Return container widget with all widgets we want on our screen.

        Sets up an urwid.Pile inside a returned urwid.Filler; top to bottom:
        - an EditToSocketWidget, prefixing self.socket input with 'SEND: '
        - a 50-col wide urwid.Padding container for self.map_widget, which is
          to print clipped map representations
        - self.reply_widget, a urwid.Text widget printing self.socket replies
        """
        edit_widget = self.EditToSocketWidget(self.socket, 'SEND: ')
        self.reply_widget = self.LogWidget('')
        self.map_widget = self.MapWidget('', wrap='clip')
        map_box = urwid.Padding(self.map_widget, width=50)
        widget_pile = urwid.Pile([edit_widget, map_box, self.reply_widget])
        return urwid.Filler(widget_pile, valign='top')

    class EditToSocketWidget(urwid.Edit):
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

    class LogWidget(urwid.Text):
        """Display client log, newest message on top."""

        def add(self, text):
            """Add text to (top of) log."""
            self.set_text(text + '\n' + self.text)

    class MapWidget(urwid.Text):
        """Stores/updates/draws game map."""
        map_size = (5, 5)
        terrain_map = ' ' * 25
        position = (0, 0)
        things = []

        class Thing:
            def __init__(self, position, symbol):
                self.position = position
                self.symbol = symbol

        def draw_map(self):
            """Draw map view from .map_size, .terrain_map, .position."""
            whole_map = []
            for c in self.terrain_map:
                whole_map += [c]
            for t in self.things:
                pos_i = t.position[0] * (self.map_size[1] + 1) + t.position[1]
                whole_map[pos_i] = t.symbol
            self.set_text(''.join(whole_map))

        def get_yx(self, yx_string):

            def get_axis_position_from_argument(axis, token):
                if len(token) < 3 or token[:2] != axis + ':' or \
                        not token[2:].isdigit():
                    raise ArgumentError('Bad arg for ' + axis + ' position.')
                return int(token[2:])

            tokens = yx_string.split(',')
            if len(tokens) != 2:
                raise ArgumentError('wrong number of ","-separated arguments')
            y = get_axis_position_from_argument('Y', tokens[0])
            x = get_axis_position_from_argument('X', tokens[1])
            return (y, x)

        def update_map_size(self, size_string):
            """Set map size, redo self.terrain_map in new size, '?'-filled."""
            new_map_size = self.get_yx(size_string)
            if 0 in new_map_size:
                raise ArgumentError('size value for either axis must be >0')
            self.map_size = new_map_size
            self.terrain_map = ''
            for y in range(self.map_size[0]):
                self.terrain_map += '?' * self.map_size[1] + '\n'
            self.draw_map()

        def update_terrain(self, terrain_map):
            """Update self.terrain_map. Ensure size matching self.map_size."""
            lines = terrain_map.split('\n')
            if len(lines) != self.map_size[0]:
                raise ArgumentError('wrong map height')
            for line in lines:
                if len(line) != self.map_size[1]:
                    raise ArgumentError('wrong map width')
            self.terrain_map = terrain_map
            self.draw_map()

        def update_things(self, thing_description):
            """Append thing of thing_description to self.things."""
            thing_types = {'human': '@', 'monster': 'M'}
            tokens = thing_description.split()
            if len(tokens) != 2:
                raise ArgumentError('Wrong number of tokens.')
            yx = self.get_yx(tokens[1])
            if yx[0] >= self.map_size[0] or yx[1] >= self.map_size[1]:
                raise ArgumentError('Position outside of map size bounds.')
            type_token = tokens[0]
            prefix = 'TYPE:'
            type_ = '?'
            if len(type_token) <= len(prefix) or \
                    type_token[:len(prefix)] != prefix:
                raise ArgumentError('Invalid type token.')
            type_ = type_token[len(prefix):]
            if type_ not in thing_types:
                raise ArgumentError('Unknown thing type.')
            self.things += [self.Thing(yx, thing_types[type_])]
            self.draw_map()

        def clear_things(self, _):
            self.things = []

    class InputHandler:
        """Delivers data from other thread to widget via message_container.

        The class only exists to provide handle_input as a bound method, with
        widget and message_container pre-set, as (bound) handle_input is used
        as a callback in urwid's watch_pipe – which merely provides its
        callback target with one parameter for a pipe to read data from an
        urwid-external thread.
        """

        def __init__(self, log_widget, map_widget, message_container):
            self.log_widget = log_widget
            self.map_widget = map_widget
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

            If the message delivered is 'BYE', quits Urwid.
            """

            def mapdraw_command(prefix, func):
                n = len(prefix)
                if len(msg) > n and msg[:n] == prefix:
                    m = getattr(self.map_widget, func)
                    m(msg[n:])
                    return True
                return False

            msg = self.message_container[0]
            if msg == 'BYE':
                raise urwid.ExitMainLoop()
                return
            found_command = False
            try:
                found_command = (
                    mapdraw_command('NEW_TURN ', 'clear_things') or
                    mapdraw_command('TERRAIN\n', 'update_terrain') or
                    mapdraw_command('THING ', 'update_things') or
                    mapdraw_command('MAP_SIZE ', 'update_map_size'))
            except ArgumentError as e:
                self.log_widget.add('ARGUMENT ERROR: ' + msg + '\n' + str(e))
            else:
                if not found_command:
                    self.log_widget.add('UNHANDLED INPUT: ' + msg)
            del self.message_container[0]

    def recv_loop(self):
        """Loop to receive messages from socket and deliver them to urwid.

        Waits for self.server_output to become empty (this signals that the
        input handler is finished / ready to receive new input), then writes
        finished message from socket to self.server_output, then sends a single
        b' ' through self.urwid_pipe_write_fd to trigger the input handler.
        """
        import os
        for msg in plom_socket_io.recv(self.socket):
            while len(self.server_output) > 0:
                pass
            self.server_output += [msg]
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
