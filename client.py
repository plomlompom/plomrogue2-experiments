#!/usr/bin/env python3
import urwid
import plom_socket_io
import socket
import threading
from parser import ArgError, Parser


class Game:
    turn = 0
    log_text = ''
    map_size = (5, 5)
    terrain_map = ('?'*5+'\n')*4+'?'*5
    things = []

    class Thing:
        def __init__(self, position, symbol):
            self.position = position
            self.symbol = symbol

    def log(self, msg):
        """Prefix msg plus newline to self.log_text."""
        self.log_text = msg + '\n' + self.log_text

    def cmd_THING(self, type_, yx):
        """Add to self.things at .position yx with .symbol defined by type_."""
        symbol = '?'
        if type_ == 'TYPE:human':
            symbol = '@'
        elif type_ == 'TYPE:monster':
            symbol = 'm'
        self.things += [self.Thing(yx, symbol)]
    cmd_THING.argtypes = 'string yx_tuple:nonneg'

    def cmd_MAP_SIZE(self, yx):
        """Set self.map_size to yx, redraw self.terrain_map as '?' cells."""
        y, x = yx
        self.map_size = (y, x)
        self.terrain_map = ''
        for y in range(self.map_size[0]):
            self.terrain_map += '?' * self.map_size[1] + '\n'
        self.terrain_map = self.terrain_map[:-1]
    cmd_MAP_SIZE.argtypes = 'yx_tuple:nonneg'

    def cmd_TURN_FINISHED(self, n):
        """Do nothing. (This may be extended later.)"""
        pass
    cmd_TURN_FINISHED.argtypes = 'int:nonneg'

    def cmd_NEW_TURN(self, n):
        """Set self.turn to n, empty self.things."""
        self.turn = n
        self.things = []
    cmd_NEW_TURN.argtypes = 'int:nonneg'

    def cmd_TERRAIN(self, terrain_map):
        """Reset self.terrain_map from terrain_map."""
        lines = terrain_map.split('\n')
        if len(lines) != self.map_size[0]:
            raise ArgError('wrong map height %s' % len(lines))
        for line in lines:
            if len(line) != self.map_size[1]:
                raise ArgError('wrong map width')
        self.terrain_map = terrain_map
    cmd_TERRAIN.argtypes = 'string'


class WidgetManager:

    def __init__(self, socket, game):
        """Set up all urwid widgets we want on the screen."""
        self.game = game
        edit_widget = self.EditToSocketWidget(socket, 'SEND: ')
        self.map_widget = urwid.Text('', wrap='clip')
        self.turn_widget = urwid.Text('')
        self.log_widget = urwid.Text('')
        map_box = urwid.Padding(self.map_widget, width=50)
        widget_pile = urwid.Pile([edit_widget, map_box, self.turn_widget,
                                  self.log_widget])
        self.top = urwid.Filler(widget_pile, valign='top')

    def draw_map(self):
        """Draw map view from .game.terrain_map, .game.things."""
        whole_map = []
        for c in self.game.terrain_map:
            whole_map += [c]
        for t in self.game.things:
            pos_i = t.position[0] * (self.game.map_size[1] + 1) + t.position[1]
            whole_map[pos_i] = t.symbol
        return ''.join(whole_map)

    def update(self):
        """Redraw all non-edit widgets."""
        self.turn_widget.set_text('TURN: ' + str(self.game.turn))
        self.log_widget.set_text(self.game.log_text)
        self.map_widget.set_text(self.draw_map())

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


class PlomRogueClient:

    def __init__(self, game, socket):
        """Build client urwid interface around socket communication.

        Sets up all widgets for writing to the socket and representing data
        from it. Sending via a WidgetManager.EditToSocket widget is
        straightforward; polling the socket for input from the server in
        parallel to the urwid main loop not so much:

        The urwid developers warn against sharing urwid resources among
        threads, so having a socket polling thread for writing to an urwid
        widget while other widgets are handled in other threads would be
        dangerous. Urwid developers recommend using urwid's watch_pipe
        mechanism instead: using a pipe from non-urwid threads into a single
        urwid thread. We use self.recv_loop_thread to poll the socket, therein
        write socket.recv output to an object that is then linked to by
        self.server_output (which is known to the urwid thread), then use the
        pipe to urwid to trigger it pulling new data from self.server_output to
        handle via self.handle_input. (We *could* pipe socket.recv output
        directly, but then we get complicated buffering situations here as well
        as in the urwid code that receives the pipe output. It's easier to just
        tell the urwid code where it finds full new server messages to handle.)
        """
        self.game = game
        self.parser = Parser(self.game)
        self.socket = socket
        self.widget_manager = WidgetManager(self.socket, self.game)
        self.server_output = []
        self.urwid_loop = urwid.MainLoop(self.widget_manager.top)
        self.urwid_pipe_write_fd = self.urwid_loop.watch_pipe(self.
                                                              handle_input)
        self.recv_loop_thread = threading.Thread(target=self.recv_loop)

    def handle_input(self, trigger):
        """On input from recv_loop thread, parse and enact commands.

        Serves as a receiver to urwid's watch_pipe mechanism, with trigger the
        data that a pipe defined by watch_pipe delivers. To avoid buffering
        trouble, we don't care for that data beyond the fact that its receival
        triggers this function: The sender is to write the data it wants to
        deliver into the container referenced by self.server_output, and just
        pipe the trigger to inform us about this.

        If the message delivered is 'BYE', quits Urwid. Otherwise tries to
        parse it as a command, and enact it. In all cases but the 'BYE', calls
        self.widget_manager.update.
        """
        msg = self.server_output[0]
        if msg == 'BYE':
            raise urwid.ExitMainLoop()
        try:
            command = self.parser.parse(msg)
            if command is None:
                self.game.log('UNHANDLED INPUT: ' + msg)
            else:
                command()
        except ArgError as e:
            self.game.log('ARGUMENT ERROR: ' + msg + '\n' + str(e))
        self.widget_manager.update()
        del self.server_output[0]

    def recv_loop(self):
        """Loop to receive messages from socket, deliver them to urwid thread.

        Waits for self.server_output to become empty (this signals that the
        input handler is finished / ready to receive new input), then writes
        finished message from socket to self.server_output, then sends a single
        b' ' through self.urwid_pipe_write_fd to trigger the input handler.
        """
        import os
        for msg in plom_socket_io.recv(self.socket):
            while len(self.server_output) > 0:  # Wait until self.server_output
                pass                            # is emptied by input handler.
            self.server_output += [msg]
            os.write(self.urwid_pipe_write_fd, b' ')

    def run(self):
        """Run in parallel urwid_loop and recv_loop threads."""
        self.recv_loop_thread.start()
        self.urwid_loop.run()
        self.recv_loop_thread.join()


if __name__ == '__main__':
    game = Game()
    s = socket.create_connection(('127.0.0.1', 5000))
    p = PlomRogueClient(game, s)
    p.run()
    s.close()
