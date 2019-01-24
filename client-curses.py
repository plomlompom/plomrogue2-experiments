#!/usr/bin/env python3
import curses
import plom_socket_io
import socket
import threading
from parser import ArgError, Parser
import game_common


class MapSquare(game_common.Map):

    def list_terrain_to_lines(self, terrain_as_list):
        terrain = ''.join(terrain_as_list)
        map_lines = []
        start_cut = 0
        while start_cut < len(terrain):
            limit = start_cut + self.size[1]
            map_lines += [terrain[start_cut:limit]]
            start_cut = limit
        return map_lines


class MapHex(game_common.Map):

    def list_terrain_to_lines(self, terrain_as_list):
        new_terrain_list = [' ']
        x = 0
        y = 0
        for c in terrain_as_list:
            new_terrain_list += [c, ' ']
            x += 1
            if x == self.size[1]:
                new_terrain_list += ['\n']
                x = 0
                y += 1
                if y % 2 == 0:
                    new_terrain_list += [' ']
        return ''.join(new_terrain_list).split('\n')


map_manager = game_common.MapManager(globals())


class World(game_common.World):

    def __init__(self, game, *args, **kwargs):
        """Extend original with local classes and empty default map.

        We need the empty default map because we draw the map widget
        on any update, even before we actually receive map data.
        """
        super().__init__(*args, **kwargs)
        self.game = game
        self.map_ = self.game.map_manager.get_map_class('Hex')()


class Game(game_common.CommonCommandsMixin):

    def __init__(self, tui):
        self.tui = tui
        self.map_manager = map_manager
        self.parser = Parser(self)
        self.world = World(self)
        self.log_text = ''

    def log(self, msg):
        """Prefix msg plus newline to self.log_text."""
        self.log_text = msg + '\n' + self.log_text

    def symbol_for_type(self, type_):
        symbol = '?'
        if type_ == 'human':
            symbol = '@'
        elif type_ == 'monster':
            symbol = 'm'
        return symbol

    def cmd_LAST_PLAYER_TASK_RESULT(self, msg):
        if msg != "success":
            self.log(msg)
            self.tui.log.do_update = True
    cmd_LAST_PLAYER_TASK_RESULT.argtypes = 'string'

    def cmd_TURN_FINISHED(self, n):
        """Do nothing. (This may be extended later.)"""
        pass
    cmd_TURN_FINISHED.argtypes = 'int:nonneg'

    def cmd_NEW_TURN(self, n):
        """Set self.turn to n, empty self.things."""
        self.world.turn = n
        self.tui.turn.do_update = True
        self.world.things = []
    cmd_NEW_TURN.argtypes = 'int:nonneg'

    def cmd_VISIBLE_MAP_LINE(self, y, terrain_line):
        self.world.map_.set_line(y, terrain_line)
    cmd_VISIBLE_MAP_LINE.argtypes = 'int:nonneg string'

    def cmd_VISIBLE_MAP_COMPLETE(self):
        self.tui.map_.do_update = True


ASCII_printable = ' !"#$%&\'\(\)*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWX'\
                  'YZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~'


def recv_loop(server_output):
    for msg in plom_socket_io.recv(s):
        while len(server_output) > 0:
            pass
        server_output += [msg]


class Widget:

    def __init__(self, tui, start, size):
        self.tui = tui
        self.start = start
        self.win = curses.newwin(1, 1, self.start[0], self.start[1])
        self.size_def = size  # store for re-calling .size on SIGWINCH
        self.size = size
        self.do_update = True

    @property
    def size(self):
        return self.win.getmaxyx()

    @size.setter
    def size(self, size):
        """Set window size. Size be y,x tuple. If y or x None, use legal max."""
        n_lines, n_cols = size
        if n_lines is None:
            n_lines = self.tui.stdscr.getmaxyx()[0] - self.start[0]
        if n_cols is None:
            n_cols = self.tui.stdscr.getmaxyx()[1] - self.start[1]
        self.win.resize(n_lines, n_cols)

    def __len__(self):
        return self.win.getmaxyx()[0] * self.win.getmaxyx()[1]

    def safe_write(self, foo):

        def to_chars_with_attrs(part):
            attr = curses.A_NORMAL
            part_string = part
            if not type(part) == str:
                part_string = part[0]
                attr = part[1]
            if len(part_string) > 0:
                return [(char, attr) for char in part_string]
            elif len(part_string) == 1:
                return [part]
            return []

        chars_with_attrs = []
        if type(foo) == str or len(foo) == 2 and type(foo[1]) == int:
            chars_with_attrs += to_chars_with_attrs(foo)
        else:
            for part in foo:
                chars_with_attrs += to_chars_with_attrs(part)
        self.win.move(0, 0)
        if len(chars_with_attrs) < len(self):
            for char_with_attr in chars_with_attrs:
                self.win.addstr(char_with_attr[0], char_with_attr[1])
        else:  # workaround to <https://stackoverflow.com/q/7063128>
            cut = chars_with_attrs[:len(self) - 1]
            last_char_with_attr = chars_with_attrs[len(self) - 1]
            self.win.addstr(self.size[0] - 1, self.size[1] - 2,
                            last_char_with_attr[0], last_char_with_attr[1])
            self.win.insstr(self.size[0] - 1, self.size[1] - 2, ' ')
            self.win.move(0, 0)
            for char_with_attr in cut:
                self.win.addstr(char_with_attr[0], char_with_attr[1])

    def draw_and_refresh(self):
        self.win.erase()
        self.draw()
        self.win.refresh()


class EditWidget(Widget):

    def draw(self):
        self.safe_write((''.join(self.tui.to_send), curses.color_pair(1)))


class LogWidget(Widget):

    def draw(self):
        line_width = self.size[1]
        log_lines = self.tui.game.log_text.split('\n')
        to_join = []
        for line in log_lines:
            to_pad = line_width - (len(line) % line_width)
            if to_pad == line_width:
                to_pad = 0
            to_join += [line + ' '*to_pad]
        self.safe_write((''.join(to_join), curses.color_pair(3)))


class MapWidget(Widget):

    def draw(self):
        to_join = []
        if len(self.tui.game.world.map_.terrain) > 0:
            terrain_as_list = list(self.tui.game.world.map_.terrain[:])
            for t in self.tui.game.world.things:
                pos_i = self.tui.game.world.map_.get_position_index(t.position)
                terrain_as_list[pos_i] = self.tui.game.symbol_for_type(t.type_)
            lines = self.tui.game.world.map_.list_terrain_to_lines(terrain_as_list)
            line_width = self.size[1]
            for line in lines:
                if line_width > len(line):
                    to_pad = line_width - (len(line) % line_width)
                    to_join += [line + '0' * to_pad]
                else:
                    to_join += [line[:line_width]]
        if len(to_join) < self.size[0]:
            to_pad = self.size[0] - len(to_join)
            to_join += to_pad * ['0' * self.size[1]]
        text = ''.join(to_join)
        text_as_list = []
        for c in text:
            if c in {'@', 'm'}:
                text_as_list += [(c, curses.color_pair(1))]
            elif c == '.':
                text_as_list += [(c, curses.color_pair(2))]
            elif c in {'x', 'X', '#'}:
                text_as_list += [(c, curses.color_pair(3))]
            else:
                text_as_list += [c]
        self.safe_write(text_as_list)


class TurnWidget(Widget):

    def draw(self):
        self.safe_write((str(self.tui.game.world.turn), curses.color_pair(2)))


class TUI:

    def __init__(self, server_output):
        self.server_output = server_output
        self.game = Game(self)
        self.parser = Parser(self.game)
        self.do_update = True
        curses.wrapper(self.loop)

    def setup_screen(self, stdscr):
        self.stdscr = stdscr
        self.stdscr.refresh()  # will be called by getkey else, clearing screen
        self.stdscr.timeout(1)
        self.stdscr.addstr(0, 0, 'SEND:')
        self.stdscr.addstr(2, 0, 'TURN:')

    def loop(self, stdscr):
        self.setup_screen(stdscr)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.curs_set(False)  # hide cursor
        self.to_send = []
        self.edit = EditWidget(self, (0, 6), (1, 14))
        self.turn = TurnWidget(self, (2, 6), (1, 14))
        self.log = LogWidget(self, (4, 0), (None, 20))
        self.map_ = MapWidget(self, (0, 21), (None, None))
        widgets = (self.edit, self.turn, self.log, self.map_)
        while True:
            for w in widgets:
                if w.do_update:
                    w.draw_and_refresh()
                    w.do_update = False
            try:
                key = self.stdscr.getkey()
                if len(key) == 1 and key in ASCII_printable and \
                        len(self.to_send) < len(self.edit):
                    self.to_send += [key]
                    self.edit.do_update = True
                elif key == 'KEY_BACKSPACE':
                    self.to_send[:] = self.to_send[:-1]
                    self.edit.do_update = True
                elif key == '\n':
                    plom_socket_io.send(s, ''.join(self.to_send))
                    self.to_send[:] = []
                    self.edit.do_update = True
                elif key == 'KEY_RESIZE':
                    curses.endwin()
                    self.setup_screen(curses.initscr())
                    for w in widgets:
                        w.size = w.size_def
                        w.do_update = True
            except curses.error:
                pass
            if len(self.server_output) > 0:
                do_quit = self.handle_input(self.server_output[0])
                if do_quit:
                    break
                self.server_output[:] = []
                self.do_update = True

    def handle_input(self, msg):
        if msg == 'BYE':
            return True
        try:
            command = self.parser.parse(msg)
            if command is None:
                self.game.log('UNHANDLED INPUT: ' + msg)
                self.log.do_update = True
            else:
                command()
        except ArgError as e:
                self.game.log('ARGUMENT ERROR: ' + msg + '\n' + str(e))
                self.log.do_update = True
        return False


server_output = []
s = socket.create_connection(('127.0.0.1', 5000))
t = threading.Thread(target=recv_loop, args=(server_output,))
t.start()
TUI(server_output)
