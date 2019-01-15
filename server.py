#!/usr/bin/env python3
import sys
import os
import server_.game


if len(sys.argv) != 2:
    print('wrong number of arguments, expected one (game file)')
    exit(1)
game_file_name = sys.argv[1]
game = server_.game.Game(game_file_name)
if os.path.exists(game_file_name):
    if not os.path.isfile(game_file_name):
        print('game file name does not refer to a valid game file')
    else:
        with open(game_file_name, 'r') as f:
            lines = f.readlines()
        for i in range(len(lines)):
            line = lines[i]
            print("FILE INPUT LINE %s: %s" % (i, line), end='')
            game.io.handle_input(line, store=False)
else:
    game.io.handle_input('MAP_SIZE Y:5,X:5')
    game.io.handle_input('TERRAIN_LINE 0 "xxxxx"')
    game.io.handle_input('TERRAIN_LINE 1 "x...x"')
    game.io.handle_input('TERRAIN_LINE 2 "x.X.x"')
    game.io.handle_input('TERRAIN_LINE 3 "x...x"')
    game.io.handle_input('TERRAIN_LINE 4 "xxxxx"')
    game.io.handle_input('THING_TYPE 0 human')
    game.io.handle_input('THING_POS 0 Y:3,X:3')
    game.io.handle_input('THING_TYPE 1 monster')
    game.io.handle_input('THING_POS 1 Y:1,X:1')
game.io.run_loop_with_server()
