from plomrogue.misc import quote



def cmd_GEN_WORLD(game, yx, seed):
    game.make_new_world(yx, seed)
cmd_GEN_WORLD.argtypes = 'yx_tuple:pos int:nonneg'

def cmd_GET_GAMESTATE(game, connection_id):
    """Send game state to caller."""
    game.send_gamestate(connection_id)

def cmd_SEED(game, seed):
    game.rand.prngod_seed = seed
cmd_SEED.argtypes = 'int:nonneg'

def cmd_MAP_SIZE(game, size):
    game.map_size = size
cmd_MAP_SIZE.argtypes = 'yx_tuple:pos'

def cmd_MAP(game, map_pos):
    """Ensure (possibly empty/'?'-filled) map at position map_pos."""
    game.get_map(map_pos)
cmd_MAP.argtypes = 'yx_tuple'

def cmd_THING_TYPE(game, i, type_):
    t_old = game.get_thing(i)
    t_new = game.thing_types[type_](game, i)
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
    t_new.in_inventory = t_old.in_inventory
    t_old_index = game.things.index(t_old)
    game.things[t_old_index] = t_new
cmd_THING_TYPE.argtypes = 'int:nonneg string:thingtype'

def cmd_THING_POS(game, i, big_yx, small_yx):
    t = game.get_thing(i)
    t.position = (big_yx, small_yx)
cmd_THING_POS.argtypes = 'int:nonneg yx_tuple yx_tuple:nonneg'

def cmd_THING_INVENTORY(game, id_, ids):
    carrier = game.get_thing(id_)
    carrier.inventory = ids
    for id_ in ids:
        t = game.get_thing(id_)
        t.in_inventory = True
        t.position = carrier.position
cmd_THING_INVENTORY.argtypes = 'int:nonneg seq:int:nonneg'

def cmd_THING_HEALTH(game, id_, health):
    t = game.get_thing(id_)
    t.health = health
cmd_THING_HEALTH.argtypes = 'int:nonneg int:nonneg'

def cmd_GET_PICKABLE_ITEMS(game, connection_id):
    pickable_ids = game.player.get_pickable_items()
    if len(pickable_ids) > 0:
        game.io.send('PICKABLE_ITEMS %s' %
                     ','.join([str(id_) for id_ in pickable_ids]))
    else:
        game.io.send('PICKABLE_ITEMS ,')

def cmd_TERRAIN_LINE(game, big_yx, y, terrain_line):
    game.maps[big_yx].set_line(y, terrain_line)
cmd_TERRAIN_LINE.argtypes = 'yx_tuple int:nonneg string'

def cmd_PLAYER_ID(game, id_):
    # TODO: test whether valid thing ID
    game.player_id = id_
cmd_PLAYER_ID.argtypes = 'int:nonneg'

def cmd_TURN(game, n):
    game.turn = n
cmd_TURN.argtypes = 'int:nonneg'

def cmd_SWITCH_PLAYER(game):
    game.player.set_task('WAIT')
    thing_ids = [t.id_ for t in game.things]
    player_index = thing_ids.index(game.player.id_)
    if player_index == len(thing_ids) - 1:
        game.player_id = thing_ids[0]
    else:
        game.player_id = thing_ids[player_index + 1]
    game.proceed()

def cmd_SAVE(game):

    def write(f, msg):
        f.write(msg + '\n')

    save_file_name = game.io.game_file_name + '.save'
    with open(save_file_name, 'w') as f:
        write(f, 'TURN %s' % game.turn)
        write(f, 'SEED %s' % game.rand.prngod_seed)
        write(f, 'MAP_SIZE %s' % (game.map_size,))
        for map_pos in game.maps:
            write(f, 'MAP %s' % (map_pos,))
        for map_pos in game.maps:
            for y, line in game.maps[map_pos].lines():
                 write(f, 'TERRAIN_LINE %s %5s %s' % (map_pos, y, quote(line)))
        for thing in game.things:
            write(f, 'THING_TYPE %s %s' % (thing.id_, thing.type_))
            write(f, 'THING_POS %s %s %s' % (thing.id_, thing.position[0],
                                             thing.position[1]))
            if hasattr(thing, 'health'):
                write(f, 'THING_HEALTH %s %s' % (thing.id_, thing.health))
            if len(thing.inventory) > 0:
                write(f, 'THING_INVENTORY %s %s' %
                      (thing.id_,','.join([str(i) for i in thing.inventory])))
            else:
                write(f, 'THING_INVENTORY %s ,' % thing.id_)
            if hasattr(thing, 'task'):
                task = thing.task
                if task is not None:
                    task_args = task.get_args_string()
                    task_name = [k for k in game.tasks.keys()
                                 if game.tasks[k] == task.__class__][0]
                    write(f, 'SET_TASK:%s %s %s %s' % (task_name, thing.id_,
                                                       task.todo, task_args))
        write(f, 'PLAYER_ID %s' % game.player_id)
cmd_SAVE.dont_save = True
