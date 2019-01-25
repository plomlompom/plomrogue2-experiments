#!/usr/bin/env python3
import curses
import plom_socket_io
import socket
import threading
from parser import ArgError, Parser
import game_common


class Map(game_common.Map):

    def y_cut(self, map_lines, center_y, view_height):
        map_height = len(map_lines)
        if map_height > view_height and center_y > view_height / 2:
            if center_y > map_height - view_height / 2:
                map_lines = map_lines[map_height - view_height:]
            else:
                start = center_y - int(view_height / 2)
                map_lines[:] = map_lines[start:start + view_height]

    def x_cut(self, map_lines, center_x, view_width):
        map_width = len(map_lines[0])
        if map_width > view_width and center_x > view_width / 2:
            if center_x > map_width - view_width / 2:
                cut_start = map_width - view_width
                cut_end = None
            else:
                cut_start = center_x - int(view_width / 2)
                cut_end = cut_start + view_width
            map_lines[:] = [line[cut_start:cut_end] for line in map_lines]


class MapSquare(Map):

    def format_to_view(self, map_string, center, size):

        def map_string_to_lines(map_string):
            map_lines = []
            start_cut = 0
            while start_cut < len(map_string):
                limit = start_cut + self.size[1]
                map_lines += [map_string[start_cut:limit]]
                start_cut = limit
            return map_lines

        map_lines = map_string_to_lines(map_string)
        self.y_cut(map_lines, center[0], size[0])
        self.x_cut(map_lines, center[1], size[1])
        return map_lines


class MapHex(Map):

    def format_to_view(self, map_string, center, size):

        def map_string_to_lines(map_string):
            map_view_chars = [' ']
            x = 0
            y = 0
            for c in map_string:
                map_view_chars += [c, ' ']
                x += 1
                if x == self.size[1]:
                    map_view_chars += ['\n']
                    x = 0
                    y += 1
                    if y % 2 == 0:
                        map_view_chars += [' ']
            return ''.join(map_view_chars).split('\n')

        map_lines = map_string_to_lines(map_string)
        self.y_cut(map_lines, center[0], size[0])
        self.x_cut(map_lines, center[1] * 2, size[1])
        return map_lines


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
        self.player_position = (0, 0)


class Game(game_common.CommonCommandsMixin):

    def __init__(self):
        self.map_manager = map_manager
        self.parser = Parser(self)
        self.world = World(self)
        self.log_text = ''
        self.to_update = {
            'log': True,
            'map': True,
            'turn': True,
            }
        self.do_quit = False

    def handle_input(self, msg):
        if msg == 'BYE':
            self.do_quit = True
            return
        try:
            command = self.parser.parse(msg)
            if command is None:
                self.log('UNHANDLED INPUT: ' + msg)
                self.to_update['log'] = True
            else:
                command()
        except ArgError as e:
                self.log('ARGUMENT ERROR: ' + msg + '\n' + str(e))
                self.to_update['log'] = True

    def log(self, msg):
        """Prefix msg plus newline to self.log_text."""
        self.log_text = msg + '\n' + self.log_text
        self.to_update['log'] = True

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
    cmd_LAST_PLAYER_TASK_RESULT.argtypes = 'string'

    def cmd_TURN_FINISHED(self, n):
        """Do nothing. (This may be extended later.)"""
        pass
    cmd_TURN_FINISHED.argtypes = 'int:nonneg'

    def cmd_NEW_TURN(self, n):
        """Set self.turn to n, empty self.things."""
        self.world.turn = n
        self.world.things = []
    cmd_NEW_TURN.argtypes = 'int:nonneg'

    def cmd_VISIBLE_MAP_LINE(self, y, terrain_line):
        self.world.map_.set_line(y, terrain_line)
    cmd_VISIBLE_MAP_LINE.argtypes = 'int:nonneg string'

    def cmd_PLAYER_POS(self, yx):
        self.world.player_position = yx
    cmd_PLAYER_POS.argtypes = 'yx_tuple:pos'

    def cmd_GAME_STATE_COMPLETE(self):
        self.to_update['turn'] = True
        self.to_update['map'] = True


ASCII_printable = ' !"#$%&\'\(\)*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWX'\
                  'YZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~'


def recv_loop(socket, game):
    for msg in plom_socket_io.recv(s):
        game.handle_input(msg)


class Widget:

    def __init__(self, tui, start, size, check_game=[], check_tui=[]):
        self.check_game = check_game
        self.check_tui = check_tui
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

    def ensure_freshness(self, do_refresh=False):
        if not do_refresh:
            for key in self.check_game:
                if self.tui.game.to_update[key]:
                    do_refresh = True
                    break
        if not do_refresh:
            for key in self.check_tui:
                if self.tui.to_update[key]:
                    do_refresh = True
                    break
        if do_refresh:
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

        def terrain_with_objects():
            terrain_as_list = list(self.tui.game.world.map_.terrain[:])
            for t in self.tui.game.world.things:
                pos_i = self.tui.game.world.map_.get_position_index(t.position)
                terrain_as_list[pos_i] = self.tui.game.symbol_for_type(t.type_)
            return ''.join(terrain_as_list)

        def pad_or_cut_x(lines):
            line_width = self.size[1]
            for y in range(len(lines)):
                line = lines[y]
                if line_width > len(line):
                    to_pad = line_width - (len(line) % line_width)
                    lines[y] = line + '0' * to_pad
                else:
                    lines[y] = line[:line_width]

        def pad_y(lines):
            if len(lines) < self.size[0]:
                to_pad = self.size[0] - len(lines)
                lines += to_pad * ['0' * self.size[1]]

        def lines_to_colored_chars(lines):
            chars_with_attrs = []
            for c in ''.join(lines):
                if c in {'@', 'm'}:
                    chars_with_attrs += [(c, curses.color_pair(1))]
                elif c == '.':
                    chars_with_attrs += [(c, curses.color_pair(2))]
                elif c in {'x', 'X', '#'}:
                    chars_with_attrs += [(c, curses.color_pair(3))]
                else:
                    chars_with_attrs += [c]
            return chars_with_attrs

        if self.tui.game.world.map_.terrain == '':
            lines = []
            pad_y(lines)
            self.safe_write(''.join(lines))
            return

        terrain_with_objects = terrain_with_objects()
        center = self.tui.game.world.player_position
        lines = self.tui.game.world.map_.format_to_view(terrain_with_objects,
                                                        center, self.size)
        pad_or_cut_x(lines)
        pad_y(lines)
        self.safe_write(lines_to_colored_chars(lines))


class TurnWidget(Widget):

    def draw(self):
        self.safe_write((str(self.tui.game.world.turn), curses.color_pair(2)))


class TUI:

    def __init__(self, socket, game):
        self.socket = socket
        self.game = game
        self.parser = Parser(self.game)
        self.to_update = {'edit': False}
        curses.wrapper(self.loop)

    def setup_screen(self, stdscr):
        self.stdscr = stdscr
        self.stdscr.refresh()  # will be called by getkey else, clearing screen
        self.stdscr.timeout(10)
        self.stdscr.addstr(0, 0, 'SEND:')
        self.stdscr.addstr(2, 0, 'TURN:')

    def loop(self, stdscr):
        self.setup_screen(stdscr)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.curs_set(False)  # hide cursor
        self.to_send = []
        self.edit = EditWidget(self, (0, 6), (1, 14), check_tui = ['edit'])
        self.turn = TurnWidget(self, (2, 6), (1, 14), ['turn'])
        self.log = LogWidget(self, (4, 0), (None, 20), ['log'])
        self.map_ = MapWidget(self, (0, 21), (None, None), ['map'])
        widgets = (self.edit, self.turn, self.log, self.map_)
        map_mode = False
        while True:
            for w in widgets:
                w.ensure_freshness()
            for key in self.game.to_update:
                self.game.to_update[key] = False
            for key in self.to_update:
                self.to_update[key] = False
            try:
                key = self.stdscr.getkey()
                if key == 'KEY_RESIZE':
                    curses.endwin()
                    self.setup_screen(curses.initscr())
                    for w in widgets:
                        w.size = w.size_def
                        w.ensure_freshness(True)
                elif key == '\t':  # Tabulator key.
                    map_mode = False if map_mode else True
                elif map_mode:
                    if type(self.game.world.map_) == MapSquare:
                        if key == 'a':
                            plom_socket_io.send(self.socket, 'MOVE LEFT')
                        elif key == 'd':
                            plom_socket_io.send(self.socket, 'MOVE RIGHT')
                        elif key == 'w':
                            plom_socket_io.send(self.socket, 'MOVE UP')
                        elif key == 's':
                            plom_socket_io.send(self.socket, 'MOVE DOWN')
                    elif type(self.game.world.map_) == MapHex:
                        if key == 'w':
                            plom_socket_io.send(self.socket, 'MOVE UPLEFT')
                        elif key == 'e':
                            plom_socket_io.send(self.socket, 'MOVE UPRIGHT')
                        if key == 's':
                            plom_socket_io.send(self.socket, 'MOVE LEFT')
                        elif key == 'd':
                            plom_socket_io.send(self.socket, 'MOVE RIGHT')
                        if key == 'x':
                            plom_socket_io.send(self.socket, 'MOVE DOWNLEFT')
                        elif key == 'c':
                            plom_socket_io.send(self.socket, 'MOVE DOWNRIGHT')
                else:
                    if len(key) == 1 and key in ASCII_printable and \
                            len(self.to_send) < len(self.edit):
                        self.to_send += [key]
                        self.to_update['edit'] = True
                    elif key == 'KEY_BACKSPACE':
                        self.to_send[:] = self.to_send[:-1]
                        self.to_update['edit'] = True
                    elif key == '\n':  # Return key
                        plom_socket_io.send(self.socket, ''.join(self.to_send))
                        self.to_send[:] = []
                        self.to_update['edit'] = True
            except curses.error:
                pass
            if self.game.do_quit:
                break


s = socket.create_connection(('127.0.0.1', 5000))
game = Game()
t = threading.Thread(target=recv_loop, args=(s, game))
t.start()
TUI(s, game)
