#!/usr/bin/env python3
import sys
import os
from plomrogue.game import Game

if len(sys.argv) != 2:
    print('wrong number of arguments, expected one (game file)')
    exit(1)
game_file_name = sys.argv[1]
game = Game(game_file_name)
if os.path.exists(game_file_name):
    if not os.path.isfile(game_file_name):
        print('game file name does not refer to a valid game file')
    else:
        with open(game_file_name, 'r') as f:
            lines = f.readlines()
        for i in range(len(lines)):
            line = lines[i]
            print("FILE INPUT LINE %5s: %s" % (i, line), end='')
            game.io.handle_input(line, store=False)
else:
    game.io.handle_input('GEN_WORLD Y:16,X:16 bar')
game.io.run_loop_with_server()
