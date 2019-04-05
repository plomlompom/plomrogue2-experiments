#!/usr/bin/env python3
import curses
import socket
import threading
from plomrogue.parser import ArgError, Parser
from plomrogue.commands import cmd_MAP, cmd_THING_POS, cmd_PLAYER_ID
from plomrogue.game import Game, WorldBase
from plomrogue.mapping import MapBase
from plomrogue.io import PlomSocket
from plomrogue.things import ThingBase
import types
import queue


class Map(MapBase):

    def y_cut(self, map_lines, center_y, view_height):
        map_height = len(map_lines)
        if map_height > view_height and center_y > view_height / 2:
            if center_y > map_height - view_height / 2:
                map_lines[:] = map_lines[map_height - view_height:]
            else:
                start = center_y - int(view_height / 2) - 1
                map_lines[:] = map_lines[start:start + view_height]

    def x_cut(self, map_lines, center_x, view_width, map_width):
        if map_width > view_width and center_x > view_width / 2:
            if center_x > map_width - view_width / 2:
                cut_start = map_width - view_width
                cut_end = None
            else:
                cut_start = center_x - int(view_width / 2)
                cut_end = cut_start + view_width
            map_lines[:] = [line[cut_start:cut_end] for line in map_lines]

    def format_to_view(self, map_string, center, size):

        def map_string_to_lines(map_string):
            map_view_chars = ['0']
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
                        map_view_chars += ['0']
            if y % 2 == 0:
                map_view_chars = map_view_chars[:-1]
            map_view_chars = map_view_chars[:-1]
            return ''.join(map_view_chars).split('\n')

        map_lines = map_string_to_lines(map_string)
        self.y_cut(map_lines, center[0], size[0])
        map_width = self.size[1] * 2 + 1
        self.x_cut(map_lines, center[1] * 2, size[1], map_width)
        return map_lines


class World(WorldBase):

    def __init__(self, *args, **kwargs):
        """Extend original with local classes and empty default map.

        We need the empty default map because we draw the map widget
        on any update, even before we actually receive map data.
        """
        super().__init__(*args, **kwargs)
        self.map_ = Map()
        self.player_inventory = []
        self.player_id = 0
        self.pickable_items = []

    def new_map(self, yx):
        self.map_ = Map(yx)

    @property
    def player(self):
        return self.get_thing(self.player_id)


def cmd_LAST_PLAYER_TASK_RESULT(game, msg):
    if msg != "success":
        game.log(msg)
cmd_LAST_PLAYER_TASK_RESULT.argtypes = 'string'

def cmd_TURN_FINISHED(game, n):
    """Do nothing. (This may be extended later.)"""
    pass
cmd_TURN_FINISHED.argtypes = 'int:nonneg'

def cmd_TURN(game, n):
    """Set game.turn to n, empty game.things."""
    game.world.turn = n
    game.world.things = []
    game.world.pickable_items = []
cmd_TURN.argtypes = 'int:nonneg'

def cmd_VISIBLE_MAP_LINE(game, y, terrain_line):
    game.world.map_.set_line(y, terrain_line)
cmd_VISIBLE_MAP_LINE.argtypes = 'int:nonneg string'

def cmd_GAME_STATE_COMPLETE(game):
    game.tui.to_update['turn'] = True
    game.tui.to_update['map'] = True

def cmd_THING_TYPE(game, i, type_):
    t = game.world.get_thing(i)
    t.type_ = type_
cmd_THING_TYPE.argtypes = 'int:nonneg string'

def cmd_PLAYER_INVENTORY(game, ids):
    game.world.player_inventory = ids  # TODO: test whether valid IDs
cmd_PLAYER_INVENTORY.argtypes = 'seq:int:nonneg'

def cmd_PICKABLE_ITEMS(game, ids):
    game.world.pickable_items = ids
    game.tui.to_update['map'] = True
cmd_PICKABLE_ITEMS.argtypes = 'seq:int:nonneg'


class Game:

    def __init__(self):
        self.parser = Parser(self)
        self.world = World(self)
        self.thing_type = ThingBase
        self.commands = {'LAST_PLAYER_TASK_RESULT': cmd_LAST_PLAYER_TASK_RESULT,
                         'TURN_FINISHED': cmd_TURN_FINISHED,
                         'TURN': cmd_TURN,
                         'VISIBLE_MAP_LINE': cmd_VISIBLE_MAP_LINE,
                         'PLAYER_ID': cmd_PLAYER_ID,
                         'PLAYER_INVENTORY': cmd_PLAYER_INVENTORY,
                         'GAME_STATE_COMPLETE': cmd_GAME_STATE_COMPLETE,
                         'MAP': cmd_MAP,
                         'PICKABLE_ITEMS': cmd_PICKABLE_ITEMS,
                         'THING_TYPE': cmd_THING_TYPE,
                         'THING_POS': cmd_THING_POS}
        self.log_text = ''
        self.do_quit = False
        self.tui = None

    def get_command(self, command_name):
        from functools import partial
        if command_name in self.commands:
            f = partial(self.commands[command_name], self)
            if hasattr(self.commands[command_name], 'argtypes'):
                f.argtypes = self.commands[command_name].argtypes
            return f
        return None

    def get_string_options(self, string_option_type):
        return None

    def handle_input(self, msg):
        self.log(msg)
        if msg == 'BYE':
            self.do_quit = True
            return
        try:
            command, args = self.parser.parse(msg)
            if command is None:
                self.log('UNHANDLED INPUT: ' + msg)
            else:
                command(*args)
        except ArgError as e:
            self.log('ARGUMENT ERROR: ' + msg + '\n' + str(e))

    def log(self, msg):
        """Prefix msg plus newline to self.log_text."""
        self.log_text = msg + '\n' + self.log_text
        self.tui.to_update['log'] = True

    def symbol_for_type(self, type_):
        symbol = '?'
        if type_ == 'human':
            symbol = '@'
        elif type_ == 'monster':
            symbol = 'm'
        elif type_ == 'item':
            symbol = 'i'
        return symbol


ASCII_printable = ' !"#$%&\'\(\)*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWX'\
                  'YZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~'


def recv_loop(plom_socket, game, q):
    for msg in plom_socket.recv():
        q.put(msg)


class Widget:

    def __init__(self, tui, start, size, check_updates=[]):
        self.check_updates = check_updates
        self.tui = tui
        self.start = start
        self.win = curses.newwin(1, 1, self.start[0], self.start[1])
        self.size_def = size  # store for re-calling .size on SIGWINCH
        self.size = size
        self.do_update = True
        self.visible = True
        self.children = []

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
        did_refresh = False
        if self.visible:
            if not do_refresh:
                for key in self.check_updates:
                    if key in self.tui.to_update and self.tui.to_update[key]:
                        do_refresh = True
                        break
            if do_refresh:
                self.win.erase()
                self.draw()
                self.win.refresh()
                did_refresh = True
            for child in self.children:
                did_refresh = child.ensure_freshness(do_refresh) | did_refresh
        return did_refresh


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


class PopUpWidget(Widget):

    def draw(self):
        self.safe_write(self.tui.popup_text)

    def reconfigure(self):
        self.visible = True
        size = (1, len(self.tui.popup_text))
        self.size = size
        self.size_def = size
        offset_y = int((self.tui.stdscr.getmaxyx()[0] / 2) - (size[0] / 2))
        offset_x = int((self.tui.stdscr.getmaxyx()[1] / 2) - (size[1] / 2))
        self.start = (offset_y, offset_x)
        self.win.mvwin(self.start[0], self.start[1])


class MapWidget(Widget):

    def draw(self):
        if self.tui.view == 'map':
            self.draw_map()
        elif self.tui.view == 'inventory':
            self.draw_item_selector('INVENTORY:',
                                    self.tui.game.world.player_inventory)
        elif self.tui.view == 'pickable_items':
            self.draw_item_selector('PICKABLE:',
                                    self.tui.game.world.pickable_items)

    def draw_item_selector(self, title, selection):
        lines = [title]
        counter = 0
        for id_ in selection:
            pointer = '*' if counter == self.tui.item_pointer else ' '
            t = self.tui.game.world.get_thing(id_)
            lines += ['%s %s' % (pointer, t.type_)]
            counter += 1
        line_width = self.size[1]
        to_join = []
        for line in lines:
            to_pad = line_width - (len(line) % line_width)
            if to_pad == line_width:
                to_pad = 0
            to_join += [line + ' '*to_pad]
        self.safe_write((''.join(to_join), curses.color_pair(3)))

    def draw_map(self):

        def terrain_with_objects():
            terrain_as_list = list(self.tui.game.world.map_.terrain[:])
            for t in self.tui.game.world.things:
                pos_i = self.tui.game.world.map_.get_position_index(t.position)
                symbol = self.tui.game.symbol_for_type(t.type_)
                if symbol in {'i'} and terrain_as_list[pos_i] in {'@', 'm'}:
                    continue
                terrain_as_list[pos_i] = symbol
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
                elif c == 'i':
                    chars_with_attrs += [(c, curses.color_pair(4))]
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
        center = self.tui.game.world.player.position
        lines = self.tui.game.world.map_.format_to_view(terrain_with_objects,
                                                        center, self.size)
        pad_or_cut_x(lines)
        pad_y(lines)
        self.safe_write(lines_to_colored_chars(lines))


class TurnWidget(Widget):

    def draw(self):
        self.safe_write((str(self.tui.game.world.turn), curses.color_pair(2)))


class TextLineWidget(Widget):

    def __init__(self, text_line, *args, **kwargs):
        self.text_line = text_line
        super().__init__(*args, **kwargs)

    def draw(self):
        self.safe_write(self.text_line)


class TUI:

    def __init__(self, plom_socket, game, q):
        self.socket = plom_socket
        self.game = game
        self.game.tui = self
        self.queue = q
        self.parser = Parser(self.game)
        self.to_update = {}
        self.item_pointer = 0
        curses.wrapper(self.loop)

    def setup_screen(self, stdscr):
        self.stdscr = stdscr
        self.stdscr.refresh()  # will be called by getkey else, clearing screen
        self.stdscr.timeout(10)

    def loop(self, stdscr):
        self.setup_screen(stdscr)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.curs_set(False)  # hide cursor
        self.to_send = []
        edit_widget = TextLineWidget('SEND:', self, (0, 0), (1, 20))
        edit_line_widget = EditWidget(self, (0, 6), (1, 14), ['edit'])
        edit_widget.children += [edit_line_widget]
        turn_widget = TextLineWidget('TURN:', self, (2, 0), (1, 20))
        turn_widget.children += [TurnWidget(self, (2, 6), (1, 14), ['turn'])]
        log_widget = LogWidget(self, (4, 0), (None, 20), ['log'])
        map_widget = MapWidget(self, (0, 21), (None, None), ['map'])
        top_widgets = [edit_widget, turn_widget, log_widget, map_widget]
        popup_widget = PopUpWidget(self, (0, 0), (1, 1))
        popup_widget.visible = False
        self.popup_text = 'Hi bob'
        write_mode = True
        self.view = 'map'
        for w in top_widgets:
            w.ensure_freshness(True)
        draw_popup_if_visible = True
        while True:
            for w in top_widgets:
                did_refresh = w.ensure_freshness()
                draw_popup_if_visible = did_refresh | draw_popup_if_visible
            if popup_widget.visible and draw_popup_if_visible:
                popup_widget.ensure_freshness(True)
                draw_popup_if_visible = False
            for k in self.to_update.keys():
                self.to_update[k] = False
            while True:
                try:
                    command = self.queue.get(block=False)
                except queue.Empty:
                    break
                self.game.handle_input(command)
            try:
                key = self.stdscr.getkey()
                if key == 'KEY_RESIZE':
                    curses.endwin()
                    self.setup_screen(curses.initscr())
                    for w in top_widgets:
                        w.size = w.size_def
                        w.ensure_freshness(True)
                elif key == '\t':  # Tabulator key.
                    write_mode = False if write_mode else True
                elif write_mode:
                    if len(key) == 1 and key in ASCII_printable and \
                            len(self.to_send) < len(edit_line_widget):
                        self.to_send += [key]
                        self.to_update['edit'] = True
                    elif key == 'KEY_BACKSPACE':
                        self.to_send[:] = self.to_send[:-1]
                        self.to_update['edit'] = True
                    elif key == '\n':  # Return key
                        self.socket.send(''.join(self.to_send))
                        self.to_send[:] = []
                        self.to_update['edit'] = True
                elif self.view == 'map':
                    if key == 'w':
                        self.socket.send('TASK:MOVE UPLEFT')
                    elif key == 'e':
                        self.socket.send('TASK:MOVE UPRIGHT')
                    if key == 's':
                        self.socket.send('TASK:MOVE LEFT')
                    elif key == 'd':
                        self.socket.send('TASK:MOVE RIGHT')
                    if key == 'x':
                        self.socket.send('TASK:MOVE DOWNLEFT')
                    elif key == 'c':
                        self.socket.send('TASK:MOVE DOWNRIGHT')
                    elif key == 't':
                        if not popup_widget.visible:
                            self.to_update['popup'] = True
                            popup_widget.visible = True
                            popup_widget.reconfigure()
                            draw_popup_if_visible = True
                        else:
                            popup_widget.visible = False
                            for w in top_widgets:
                                w.ensure_freshness(True)
                    elif key == 'p':
                        self.socket.send('GET_PICKABLE_ITEMS')
                        self.item_pointer = 0
                        self.view = 'pickable_items'
                    elif key == 'i':
                        self.item_pointer = 0
                        self.view = 'inventory'
                        self.to_update['map'] = True
                elif self.view == 'pickable_items':
                    if key == 'c':
                        self.view = 'map'
                    elif key == 'j' and \
                         len(self.game.world.pickable_items) > \
                         self.item_pointer + 1:
                        self.item_pointer += 1
                    elif key == 'k' and self.item_pointer > 0:
                        self.item_pointer -= 1
                    elif key == 'p' and \
                         len(self.game.world.pickable_items) > 0:
                        id_ = self.game.world.pickable_items[self.item_pointer]
                        self.socket.send('TASK:PICKUP %s' % id_)
                        self.socket.send('GET_PICKABLE_ITEMS')
                        if self.item_pointer > 0:
                            self.item_pointer -= 1
                    else:
                        continue
                    self.to_update['map'] = True
                elif self.view == 'inventory':
                    if key == 'c':
                        self.view = 'map'
                    elif key == 'j' and \
                         len(self.game.world.player_inventory) > \
                         self.item_pointer + 1:
                        self.item_pointer += 1
                    elif key == 'k' and self.item_pointer > 0:
                        self.item_pointer -= 1
                    elif key == 'd' and \
                         len(self.game.world.player_inventory) > 0:
                        id_ = self.game.world.player_inventory[self.item_pointer]
                        self.socket.send('TASK:DROP %s' % id_)
                        if self.item_pointer > 0:
                            self.item_pointer -= 1
                    else:
                        continue
                    self.to_update['map'] = True
            except curses.error:
                pass
            if self.game.do_quit:
                break


s = socket.create_connection(('127.0.0.1', 5000))
plom_socket = PlomSocket(s)
game = Game()
q = queue.Queue()
t = threading.Thread(target=recv_loop, args=(plom_socket, game, q))
t.start()
TUI(plom_socket, game, q)
