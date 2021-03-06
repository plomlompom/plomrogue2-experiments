#!/usr/bin/env python3
import curses
import socket
import threading
from plomrogue.parser import ArgError, Parser
from plomrogue.commands import cmd_PLAYER_ID, cmd_THING_HEALTH
from plomrogue.game import GameBase
from plomrogue.mapping import Map, MapGeometryHex, YX
from plomrogue.io import PlomSocket
from plomrogue.things import ThingBase
import types
import queue


class ClientMap(Map):

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

    def format_to_view(self, map_cells, center, size):

        def map_cells_to_lines(map_cells):
            map_view_chars = []
            if self.start_indented:
                map_view_chars += ['0']
            x = 0
            y = 0
            for cell in map_cells:
                if type(cell) == str:
                    map_view_chars += [cell, ' ']
                else:
                    map_view_chars += [cell[0], cell[1]]
                x += 1
                if x == self.size.x:
                    map_view_chars += ['\n']
                    x = 0
                    y += 1
                    if y % 2 == int(not self.start_indented):
                        map_view_chars += ['0']
            if y % 2 == int(not self.start_indented):
                map_view_chars = map_view_chars[:-1]
            map_view_chars = map_view_chars[:-1]
            return ''.join(map_view_chars).split('\n')

        map_lines = map_cells_to_lines(map_cells)
        self.y_cut(map_lines, center[1].y, size.y)
        map_width = self.size.x * 2 + 1
        self.x_cut(map_lines, center[1].x * 2, size.x, map_width)
        return map_lines


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
    game.turn = n
    game.things = []
    game.pickable_items[:] = []
cmd_TURN.argtypes = 'int:nonneg'


def cmd_VISIBLE_MAP(game, size, indent_first_line):
    game.new_map(size, indent_first_line)
cmd_VISIBLE_MAP.argtypes = 'yx_tuple:pos bool'


def cmd_VISIBLE_MAP_LINE(game, y, terrain_line):
    game.map_.set_line(y, terrain_line)
cmd_VISIBLE_MAP_LINE.argtypes = 'int:nonneg string'


def cmd_GAME_STATE_COMPLETE(game):
    game.tui.to_update['turn'] = True
    game.tui.to_update['map'] = True
    game.tui.to_update['inventory'] = True


def cmd_THING_TYPE(game, i, type_):
    t = game.get_thing(i)
    t.type_ = type_
cmd_THING_TYPE.argtypes = 'int:nonneg string'


def cmd_THING_POS(game, i, yx):
    t = game.get_thing(i)
    t.position = YX(0,0), yx
cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'


def cmd_PLAYER_INVENTORY(game, ids):
    game.player_inventory[:] = ids  # TODO: test whether valid IDs
    game.tui.to_update['inventory'] = True
cmd_PLAYER_INVENTORY.argtypes = 'seq:int:nonneg'


def cmd_PICKABLE_ITEMS(game, ids):
    game.pickable_items[:] = ids
    game.tui.to_update['pickable_items'] = True
cmd_PICKABLE_ITEMS.argtypes = 'seq:int:nonneg'


class Game(GameBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.map_ = ClientMap()  # we need an empty default map cause we draw
        self.offset = YX(0,0)    # the map widget even before we get a real one
        self.player_inventory = []
        self.player_id = 0
        self.pickable_items = []
        self.parser = Parser(self)
        self.map_geometry = MapGeometryHex()
        self.thing_type = ThingBase
        self.commands = {'LAST_PLAYER_TASK_RESULT': cmd_LAST_PLAYER_TASK_RESULT,
                         'TURN_FINISHED': cmd_TURN_FINISHED,
                         'TURN': cmd_TURN,
                         'VISIBLE_MAP_LINE': cmd_VISIBLE_MAP_LINE,
                         'PLAYER_ID': cmd_PLAYER_ID,
                         'PLAYER_INVENTORY': cmd_PLAYER_INVENTORY,
                         'GAME_STATE_COMPLETE': cmd_GAME_STATE_COMPLETE,
                         'VISIBLE_MAP': cmd_VISIBLE_MAP,
                         'PICKABLE_ITEMS': cmd_PICKABLE_ITEMS,
                         'THING_TYPE': cmd_THING_TYPE,
                         'THING_HEALTH': cmd_THING_HEALTH,
                         'THING_POS': cmd_THING_POS}
        self.log_text = ''
        self.do_quit = False
        self.tui = None

    def new_map(self, size, indent_first_line):
        self.map_ = ClientMap(size, start_indented=indent_first_line)

    @property
    def player(self):
        return self.get_thing(self.player_id)

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
        elif type_ == 'food':
            symbol = 'f'
        return symbol


ASCII_printable = ' !"#$%&\'\(\)*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWX'\
                  'YZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~'


def recv_loop(plom_socket, game, q):
    for msg in plom_socket.recv():
        q.put(msg)


class Widget:

    def __init__(self, tui, start, size, check_updates=[], visible=True):
        self.check_updates = check_updates
        self.tui = tui
        self.start = start
        self.win = curses.newwin(1, 1, self.start.y, self.start.x)
        self.size_def = size  # store for re-calling .size on SIGWINCH
        self.size = size
        self.do_update = True
        self.visible = visible
        self.children = []

    @property
    def size(self):
        return YX(*self.win.getmaxyx())

    @size.setter
    def size(self, size):
        """Set window size. Size be y,x tuple. If y or x None, use legal max."""
        n_lines, n_cols = size
        getmaxyx = YX(*self.tui.stdscr.getmaxyx())
        if n_lines is None:
            n_lines = getmaxyx.y - self.start.y
        if n_cols is None:
            n_cols = getmaxyx.x - self.start.x
        self.win.resize(n_lines, n_cols)

    def __len__(self):
        getmaxyx = YX(*self.win.getmaxyx())
        return getmaxyx.y * getmaxyx.x

    def safe_write(self, foo):

        def to_chars_with_attrs(part):
            attr = curses.A_NORMAL
            part_string = part
            if not type(part) == str:
                part_string = part[0]
                attr = part[1]
            return [(char, attr) for char in part_string]

        chars_with_attrs = []
        if type(foo) == str or (len(foo) == 2 and type(foo[1]) == int):
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
            self.win.addstr(self.size.y - 1, self.size.x - 2,
                            last_char_with_attr[0], last_char_with_attr[1])
            self.win.insstr(self.size.y - 1, self.size.x - 2, ' ')
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


class TextLinesWidget(Widget):

    def draw(self):
        lines = self.get_text_lines()
        line_width = self.size.x
        to_join = []
        for line in lines:
            to_pad = line_width - (len(line) % line_width)
            if to_pad == line_width:
                to_pad = 0
            to_join += [line + ' '*to_pad]
        self.safe_write((''.join(to_join), curses.color_pair(3)))


class LogWidget(TextLinesWidget):

    def get_text_lines(self):
        return self.tui.game.log_text.split('\n')


class DescriptorWidget(TextLinesWidget):

    def get_text_lines(self):
        lines = []
        pos_i = self.tui.game.map_.\
                get_position_index(self.tui.examiner_position[1])
        terrain = self.tui.game.map_.terrain[pos_i]
        lines = [terrain]
        for t in self.tui.game.things_at_pos(self.tui.examiner_position):
            lines += [t.type_]
        return lines


class PopUpWidget(Widget):

    def draw(self):
        self.safe_write(self.tui.popup_text)

    def reconfigure(self):
        size = (1, len(self.tui.popup_text))
        self.size = size
        self.size_def = size
        getmaxyx = YX(*self.tui.stdscr.getmaxyx())
        offset_y = int(getmaxyx.y / 2 - size.y / 2)
        offset_x = int(getmaxyx.x / 2 - size.x / 2)
        self.start = YX(offset_y, offset_x)
        self.win.mvwin(self.start.y, self.start.x)


class ItemsSelectorWidget(Widget):

    def __init__(self, headline, selection, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headline = headline
        self.selection = selection

    def ensure_freshness(self, *args, **kwargs):
        # We only update pointer on non-empty selection so that the zero-ing
        # of the selection at TURN_FINISHED etc. before pulling in a new
        # state does not destroy any memory of previous item pointer positions.
        if len(self.selection) > 0 and\
           len(self.selection) < self.tui.item_pointer + 1 and\
           self.tui.item_pointer > 0:
            self.tui.item_pointer = max(0, len(self.selection) - 1)
            self.tui.to_update[self.check_updates[0]] = True
        super().ensure_freshness(*args, **kwargs)

    def draw(self):
        lines = [self.headline]
        counter = 0
        for id_ in self.selection:
            pointer = '*' if counter == self.tui.item_pointer else ' '
            t = self.tui.game.get_thing(id_)
            lines += ['%s %s' % (pointer, t.type_)]
            counter += 1
        line_width = self.size.x
        to_join = []
        for line in lines:
            to_pad = line_width - (len(line) % line_width)
            if to_pad == line_width:
                to_pad = 0
            to_join += [line + ' '*to_pad]
        self.safe_write((''.join(to_join), curses.color_pair(3)))


class MapWidget(Widget):

    def draw(self):

        def annotated_terrain():
            terrain_as_list = list(self.tui.game.map_.terrain[:])
            for t in self.tui.game.things:
                if t.id_ in self.tui.game.player_inventory:
                    continue
                pos_i = self.tui.game.map_.get_position_index(t.position[1])
                symbol = self.tui.game.symbol_for_type(t.type_)
                if terrain_as_list[pos_i][0] in {'f', '@', 'm'}:
                    old_symbol = terrain_as_list[pos_i][0]
                    if old_symbol in {'@', 'm'}:
                        symbol = old_symbol
                    terrain_as_list[pos_i] = (symbol, '+')
                else:
                    terrain_as_list[pos_i] = symbol
            if self.tui.examiner_mode:
                pos_i = self.tui.game.map_.\
                        get_position_index(self.tui.examiner_position[1])
                terrain_as_list[pos_i] = (terrain_as_list[pos_i][0], '?')
            return terrain_as_list

        def pad_or_cut_x(lines):
            line_width = self.size.x
            for y in range(len(lines)):
                line = lines[y]
                if line_width > len(line):
                    to_pad = line_width - (len(line) % line_width)
                    lines[y] = line + '0' * to_pad
                else:
                    lines[y] = line[:line_width]

        def pad_y(lines):
            if len(lines) < self.size.y:
                to_pad = self.size.y - len(lines)
                lines += to_pad * ['0' * self.size.x]

        def lines_to_colored_chars(lines):
            chars_with_attrs = []
            for c in ''.join(lines):
                if c in {'@', 'm'}:
                    chars_with_attrs += [(c, curses.color_pair(1))]
                elif c == 'f':
                    chars_with_attrs += [(c, curses.color_pair(4))]
                elif c == '.':
                    chars_with_attrs += [(c, curses.color_pair(2))]
                elif c in {'x', 'X', '#'}:
                    chars_with_attrs += [(c, curses.color_pair(3))]
                elif c == '?':
                    chars_with_attrs += [(c, curses.color_pair(5))]
                else:
                    chars_with_attrs += [c]
            return chars_with_attrs

        if self.tui.game.map_.terrain == '':
            lines = []
            pad_y(lines)
            self.safe_write(''.join(lines))
            return

        annotated_terrain = annotated_terrain()
        center = self.tui.game.player.position
        if self.tui.examiner_mode:
            center = self.tui.examiner_position
        lines = self.tui.game.map_.\
                format_to_view(annotated_terrain, center, self.size)
        pad_or_cut_x(lines)
        pad_y(lines)
        self.safe_write(lines_to_colored_chars(lines))


class TurnWidget(Widget):

    def draw(self):
        self.safe_write((str(self.tui.game.turn), curses.color_pair(2)))


class HealthWidget(Widget):

    def draw(self):
        if hasattr(self.tui.game.player, 'health'):
            self.safe_write((str(self.tui.game.player.health),
                             curses.color_pair(2)))


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
        self.examiner_position = (YX(0,0), YX(0, 0))
        self.examiner_mode = False
        self.popup_text = 'Hi bob'
        self.to_send = []
        self.draw_popup_if_visible = True
        curses.wrapper(self.loop)

    def loop(self, stdscr):

        def setup_screen(stdscr):
            self.stdscr = stdscr
            self.stdscr.refresh()  # will be called by getkey else, clearing screen
            self.stdscr.timeout(10)

        def switch_widgets(widget_1, widget_2):
            widget_1.visible = False
            widget_2.visible = True
            trigger = widget_2.check_updates[0]
            self.to_update[trigger] = True

        def selectables_menu(key, widget, selectables, f):
            if key == 'c':
                switch_widgets(widget, map_widget)
            elif key == 'j':
                self.item_pointer += 1
            elif key == 'k' and self.item_pointer > 0:
                self.item_pointer -= 1
            elif not f(key, selectables):
                return
            trigger = widget.check_updates[0]
            self.to_update[trigger] = True

        def pickup_menu(key):

            def f(key, selectables):
                if key == 'p' and len(selectables) > 0:
                    id_ = selectables[self.item_pointer]
                    self.socket.send('TASK:PICKUP %s' % id_)
                    self.socket.send('GET_PICKABLE_ITEMS')
                else:
                    return False
                return True

            selectables_menu(key, pickable_items_widget,
                             self.game.pickable_items, f)

        def inventory_menu(key):

            def f(key, selectables):
                if key == 'd' and len(selectables) > 0:
                    id_ = selectables[self.item_pointer]
                    self.socket.send('TASK:DROP %s' % id_)
                elif key == 'e' and len(selectables) > 0:
                    id_ = selectables[self.item_pointer]
                    self.socket.send('TASK:EAT %s' % id_)
                else:
                    return False
                return True

            selectables_menu(key, inventory_widget,
                             self.game.player_inventory, f)

        def move_examiner(direction):
            start_pos = self.examiner_position
            new_examine_pos = self.game.map_geometry.move(start_pos, direction,
                                                          self.game.map_.size,
                                                          self.game.map_.start_indented)
            if new_examine_pos[0] == (0,0):
                self.examiner_position = new_examine_pos
            self.to_update['map'] = True

        def switch_to_pick_or_drop(target_widget):
            self.item_pointer = 0
            switch_widgets(map_widget, target_widget)
            if self.examiner_mode:
                self.examiner_mode = False
                switch_widgets(descriptor_widget, log_widget)

        def toggle_examiner_mode():
            if self.examiner_mode:
                self.examiner_mode = False
                switch_widgets(descriptor_widget, log_widget)
            else:
                self.examiner_mode = True
                self.examiner_position = self.game.player.position
                switch_widgets(log_widget, descriptor_widget)
            self.to_update['map'] = True

        def toggle_popup():
            if popup_widget.visible:
                popup_widget.visible = False
                for w in top_widgets:
                    w.ensure_freshness(True)
            else:
                self.to_update['popup'] = True
                popup_widget.visible = True
                popup_widget.reconfigure()
                self.draw_popup_if_visible = True

        def try_write_keys():
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

        def try_examiner_keys():
            if key == 'w':
                move_examiner('UPLEFT')
            elif key == 'e':
                move_examiner('UPRIGHT')
            elif key == 's':
                move_examiner('LEFT')
            elif key == 'd':
                move_examiner('RIGHT')
            elif key == 'x':
                move_examiner('DOWNLEFT')
            elif key == 'c':
                move_examiner('DOWNRIGHT')

        def try_player_move_keys():
            if key == 'w':
                self.socket.send('TASK:MOVE UPLEFT')
            elif key == 'e':
                self.socket.send('TASK:MOVE UPRIGHT')
            elif key == 's':
                self.socket.send('TASK:MOVE LEFT')
            elif key == 'd':
                self.socket.send('TASK:MOVE RIGHT')
            elif key == 'x':
                self.socket.send('TASK:MOVE DOWNLEFT')
            elif key == 'c':
                self.socket.send('TASK:MOVE DOWNRIGHT')

        def init_colors():
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_RED)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
            curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_BLUE)
            curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)

        # Basic curses initialization work.
        setup_screen(stdscr)
        curses.curs_set(False)  # hide cursor
        init_colors()

        # With screen initialized, set up widgets with their curses windows.
        edit_widget = TextLineWidget('SEND:', self, YX(0, 0), YX(1, 20))
        edit_line_widget = EditWidget(self, YX(0, 6), YX(1, 14), ['edit'])
        edit_widget.children += [edit_line_widget]
        turn_widget = TextLineWidget('TURN:', self, YX(2, 0), YX(1, 20))
        turn_widget.children += [TurnWidget(self, YX(2, 6), YX(1, 14), ['turn'])]
        health_widget = TextLineWidget('HEALTH:', self, YX(3, 0), YX(1, 20))
        health_widget.children += [HealthWidget(self, YX(3, 8), YX(1, 12), ['turn'])]
        log_widget = LogWidget(self, YX(5, 0), YX(None, 20), ['log'])
        descriptor_widget = DescriptorWidget(self, YX(5, 0), YX(None, 20),
                                             ['map'], False)
        map_widget = MapWidget(self, YX(0, 21), YX(None, None), ['map'])
        inventory_widget = ItemsSelectorWidget('INVENTORY:',
                                               self.game.player_inventory,
                                               self, YX(0, 21), YX(None, None),
                                               ['inventory'], False)
        pickable_items_widget = ItemsSelectorWidget('PICKABLE:',
                                                    self.game.pickable_items,
                                                    self, YX(0, 21),
                                                    YX(None, None),
                                                    ['pickable_items'],
                                                    False)
        top_widgets = [edit_widget, turn_widget, health_widget, log_widget,
                       descriptor_widget, map_widget, inventory_widget,
                       pickable_items_widget]
        popup_widget = PopUpWidget(self, YX(0, 0), YX(1, 1), visible=False)

        # Ensure initial window state before loop starts.
        for w in top_widgets:
            w.ensure_freshness(True)
        self.socket.send('GET_GAMESTATE')
        write_mode = False
        while True:

            # Draw screen.
            for w in top_widgets:
                if w.ensure_freshness():
                    self.draw_popup_if_visible = True
            if popup_widget.visible and self.draw_popup_if_visible:
                popup_widget.ensure_freshness(True)
                self.draw_popup_if_visible = False
            for k in self.to_update.keys():
                self.to_update[k] = False

            # Handle input from server.
            while True:
                try:
                    command = self.queue.get(block=False)
                except queue.Empty:
                    break
                self.game.handle_input(command)

            # Handle keys (and resize event read as key).
            try:
                key = self.stdscr.getkey()
                if key == 'KEY_RESIZE':
                    curses.endwin()
                    setup_screen(curses.initscr())
                    for w in top_widgets:
                        w.size = w.size_def
                        w.ensure_freshness(True)
                elif key == '\t':  # Tabulator key.
                    write_mode = False if write_mode else True
                elif write_mode:
                    try_write_keys()
                elif key == 't':
                    toggle_popup()
                elif map_widget.visible:
                    if key == '?':
                        toggle_examiner_mode()
                    elif key == 'p':
                        self.socket.send('GET_PICKABLE_ITEMS')
                        switch_to_pick_or_drop(pickable_items_widget)
                    elif key == 'i':
                        switch_to_pick_or_drop(inventory_widget)
                    elif self.examiner_mode:
                        try_examiner_keys()
                    else:
                        try_player_move_keys()
                elif pickable_items_widget.visible:
                    pickup_menu(key)
                elif inventory_widget.visible:
                    inventory_menu(key)
            except curses.error:
                pass

            # Quit when server recommends it.
            if self.game.do_quit:
                break


s = socket.create_connection(('127.0.0.1', 5000))
plom_socket = PlomSocket(s)
game = Game()
q = queue.Queue()
t = threading.Thread(target=recv_loop, args=(plom_socket, game, q))
t.start()
TUI(plom_socket, game, q)
