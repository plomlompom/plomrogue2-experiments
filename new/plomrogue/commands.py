from plomrogue.misc import quote, stringify_yx



def cmd_GEN_WORLD(game, yx, seed):
    game.world.make_new(yx, seed)
cmd_GEN_WORLD.argtypes = 'yx_tuple:pos string'

def cmd_GET_GAMESTATE(game, connection_id):
    """Send game state to caller."""
    game.send_gamestate(connection_id)

def cmd_MAP(game, yx):
    """Create new map of size yx and only '?' cells."""
    game.world.new_map(yx)
cmd_MAP.argtypes = 'yx_tuple:pos'

def cmd_THING_TYPE(game, i, type_):
    t_old = game.world.get_thing(i)
    t_new = game.thing_types[type_](game.world, i)
    #attr_names_of_old = [name for name in dir(t_old) where name[:2] != '__']
    #attr_names_of_new = [name for name in dir(t_new) where name[:2] != '__']
    #class_new = type(t_new)
    #for attr_name in [v for v in attr_names_of_old if v in attr_names_of_new]:
    #    if hasattr(class_new, attr_name):
    #        attr_new = getattr(class_new, attr_name)
    #        if type(attr_new) == property and attr_new.fset is None:
    #            continue  # ignore read-only properties on t_new
    #    attr_old = getattr(t_old, attr_name)
    #    attr_new = getattr(t_new, attr_name)
    #    if type(attr_old) != type(attr_new):
    #        continue
    #    setattr(t_new, attr_name, attr_old)
    t_new.position = t_old.position
    t_old_index = game.world.things.index(t_old)
    game.world.things[t_old_index] = t_new
cmd_THING_TYPE.argtypes = 'int:nonneg string:thingtype'

def cmd_THING_POS(game, i, yx):
    t = game.world.get_thing(i)
    t.position = list(yx)
cmd_THING_POS.argtypes = 'int:nonneg yx_tuple:nonneg'

def cmd_TERRAIN_LINE(game, y, terrain_line):
    game.world.map_.set_line(y, terrain_line)
cmd_TERRAIN_LINE.argtypes = 'int:nonneg string'

def cmd_PLAYER_ID(game, id_):
    # TODO: test whether valid thing ID
    game.world.player_id = id_
cmd_PLAYER_ID.argtypes = 'int:nonneg'

def cmd_TURN(game, n):
    game.world.turn = n
cmd_TURN.argtypes = 'int:nonneg'

def cmd_SWITCH_PLAYER(game):
    player = game.world.get_player()
    player.set_task('WAIT')
    thing_ids = [t.id_ for t in game.world.things]
    player_index = thing_ids.index(player.id_)
    if player_index == len(thing_ids) - 1:
        game.world.player_id = thing_ids[0]
    else:
        game.world.player_id = thing_ids[player_index + 1]
    game.proceed()

def cmd_SAVE(game):

    def write(f, msg):
        f.write(msg + '\n')

    save_file_name = game.io.game_file_name + '.save'
    with open(save_file_name, 'w') as f:
        write(f, 'TURN %s' % game.world.turn)
        write(f, 'MAP ' + stringify_yx(game.world.map_.size))
        for y, line in game.world.map_.lines():
            write(f, 'TERRAIN_LINE %5s %s' % (y, quote(line)))
        for thing in game.world.things:
            write(f, 'THING_TYPE %s %s' % (thing.id_, thing.type_))
            write(f, 'THING_POS %s %s' % (thing.id_,
                                          stringify_yx(thing.position)))
            task = thing.task
            if task is not None:
                task_args = task.get_args_string()
                task_name = [k for k in game.tasks.keys()
                             if game.tasks[k] == task.__class__][0]
                write(f, 'SET_TASK:%s %s %s %s' % (task_name, thing.id_,
                                                   task.todo, task_args))
        write(f, 'PLAYER_ID %s' % game.world.player_id)
cmd_SAVE.dont_save = True
