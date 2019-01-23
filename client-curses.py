#!/usr/bin/env python3
import curses
import plom_socket_io
import socket
import threading

ASCII_printable = ' !"#$%&\'\(\)*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWX'\
                  'YZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~'


def recv_loop(server_output):
    for msg in plom_socket_io.recv(s):
        while len(server_output) > 0:
            pass
        server_output += [msg]


class Widget:

    def __init__(self, content, tui, start, size):
        self.tui = tui
        self.content = content
        self.start = start
        self.win = curses.newwin(1, 1, self.start[0], self.start[1])
        self.size_def = size  # store for re-calling .size on SIGWINCH
        self.size = size
        self.update = True

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

    def safe_write(self, string):
        if len(string) < len(self):
            self.win.addstr(0, 0, string)
        else:  # workaround to <https://stackoverflow.com/q/7063128>
            cut = string[:len(self) - 1]
            self.win.addch(self.size[0] - 1, self.size[1] - 2,
                           string[len(self) - 1])
            self.win.insstr(self.size[0] - 1, self.size[1] - 2, " ")
            self.win.addstr(0, 0, cut)

    def draw(self):
        if self.content is not None:
            self.safe_write(''.join(self.content))

    def draw_and_refresh(self):
        self.win.erase()
        self.draw()
        self.win.refresh()


class LogWidget(Widget):

    def draw(self):
        line_width = self.size[1]
        to_join = []
        for line in self.content:
            to_pad = line_width - (len(line) % line_width)
            if to_pad == line_width:
                to_pad = 0
            to_join += [line + ' '*to_pad]
        self.safe_write(''.join(to_join))

class MapWidget(Widget):

    def draw(self):
        from datetime import datetime
        with open('log', 'a') as f:
            f.write(str(datetime.now()) + ' TRIGGERED ' + str(len(self)) + '\n')
        self.safe_write('#'*len(self))


class TUI:

    def __init__(self, server_output):
        self.server_output = server_output
        curses.wrapper(self.loop)

    def setup_screen(self, stdscr):
        self.stdscr = stdscr
        self.stdscr.refresh()  # will be called by getkey else, clearing screen
        self.stdscr.timeout(10)
        self.stdscr.addstr(0, 0, 'SEND:')

    def loop(self, stdscr):
        self.setup_screen(stdscr)
        curses.curs_set(False)  # hide cursor
        to_send = []
        log = []
        edit_line = Widget(to_send, self, (0, 6), (1, 14))
        log_display = LogWidget(log, self, (1, 0), (None, 20))
        map_view = MapWidget(None, self, (0, 20), (None, None))
        map_view.update = True
        widgets = [edit_line, log_display, map_view]
        do_update = True
        while True:
            if do_update:
                for w in widgets:
                    w.draw_and_refresh()
                do_update = False
            try:
                key = self.stdscr.getkey()
                do_update = True
                if len(key) == 1 and key in ASCII_printable and \
                        len(to_send) < len(edit_line):
                    to_send += [key]
                elif key == 'KEY_BACKSPACE':
                    to_send[:] = to_send[:-1]
                elif key == '\n':
                    plom_socket_io.send(s, ''.join(to_send))
                    to_send[:] = []
                elif key == 'KEY_RESIZE':
                    curses.endwin()
                    self.setup_screen(curses.initscr())
                    for w in widgets:
                        w.size = w.size_def
                else:
                    do_update = False
            except curses.error:
                pass
            if len(self.server_output) > 0:
                log[:0] = [self.server_output[0]]
                self.server_output[:] = []
                do_update = True


server_output = []
s = socket.create_connection(('127.0.0.1', 5000))
t = threading.Thread(target=recv_loop, args=(server_output,))
t.start()
TUI(server_output)
