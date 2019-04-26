from plomrogue.errors import GameError



class ThingBase:
    type_ = '?'

    def __init__(self, world, id_=None, position=((0,0), (0,0))):
        self.world = world
        self.position = position
        if id_ is None:
            self.id_ = self.world.new_thing_id()
        else:
            self.id_ = id_



class Thing(ThingBase):
    blocking = False
    in_inventory = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventory = []

    def proceed(self):
        pass



class ThingItem(Thing):
    pass



class ThingFood(ThingItem):
    type_ = 'food'



class ThingAnimate(Thing):
    blocking = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_task('WAIT')
        self._last_task_result = None
        self._radius = 8
        self.unset_surroundings()

    def move_on_dijkstra_map(self, own_pos, targets):
        visible_map = self.get_visible_map()
        dijkstra_map = self.world.game.map_type(visible_map.size)
        n_max = 256
        dijkstra_map.terrain = [n_max for i in range(dijkstra_map.size_i)]
        for target in targets:
            dijkstra_map[target] = 0
        shrunk = True
        while shrunk:
            shrunk = False
            for pos in dijkstra_map:
                if visible_map[pos] != '.':
                    continue
                neighbors = dijkstra_map.get_neighbors(tuple(pos))
                for direction in neighbors:
                    yx = neighbors[direction]
                    if yx is not None and dijkstra_map[yx] < dijkstra_map[pos] - 1:
                        dijkstra_map[pos] = dijkstra_map[yx] + 1
                        shrunk = True
        neighbors = dijkstra_map.get_neighbors(own_pos)
        n = n_max
        target_direction = None
        for direction in sorted(neighbors.keys()):
            yx = neighbors[direction]
            if yx is not None:
                n_new = dijkstra_map[yx]
                if n_new < n:
                    n = n_new
                    target_direction = direction
        return target_direction

    def hunt_player(self):
        visible_things, offset = self.get_visible_things()
        target = None
        for t in visible_things:
            if t.type_ == 'human':
                target = (t.position[1][0] - offset[0],
                          t.position[1][1] - offset[1])
                break
        if target is not None:
            try:
                offset_self_pos = (self.position[1][0] - offset[0],
                                   self.position[1][1] - offset[1])
                target_dir = self.move_on_dijkstra_map(offset_self_pos,
                                                       [target])
                if target_dir is not None:
                    self.set_task('MOVE', (target_dir,))
                    return True
            except GameError:
                pass
        return False

    def hunt_food_satisfaction(self):
        for id_ in self.inventory:
            t = self.world.get_thing(id_)
            if t.type_ == 'food':
                self.set_task('EAT', (id_,))
                return True
        for id_ in self.get_pickable_items():
            t = self.world.get_thing(id_)
            if t.type_ == 'food':
                self.set_task('PICKUP', (id_,))
                return True
        visible_things, offset = self.get_visible_things()
        food_targets = []
        for t in visible_things:
            if t.type_ == 'food':
                food_targets += [(t.position[1][0] - offset[0],
                                  t.position[1][1] - offset[1])]
        offset_self_pos = (self.position[1][0] - offset[0],
                           self.position[1][1] - offset[1])
        target_dir = self.move_on_dijkstra_map(offset_self_pos,
                                               food_targets)
        if target_dir:
            try:
                self.set_task('MOVE', (target_dir,))
                return True
            except GameError:
                pass
        return False

    def decide_task(self):
        #if not self.hunt_player():
        if not self.hunt_food_satisfaction():
            self.set_task('WAIT')

    def set_task(self, task_name, args=()):
        task_class = self.world.game.tasks[task_name]
        self.task = task_class(self, args)
        self.task.check()  # will throw GameError if necessary

    def proceed(self, is_AI=True):
        """Further the thing in its tasks, decrease its health.

        First, ensures an empty map, decrements .health and kills
        thing if crossing zero (removes from self.world.things for AI
        thing, or unsets self.world.player_is_alive for player thing);
        then checks that self.task is still possible and aborts if
        otherwise (for AI things, decides a new task).

        Then decrements .task.todo; if it thus falls to <= 0, enacts
        method whose name is 'task_' + self.task.name and sets .task =
        None. If is_AI, calls .decide_task to decide a self.task.

        """
        self.unset_surroundings()
        self.health -= 1
        if self.health <= 0:
            if self is self.world.player:
                self.world.player_is_alive = False
            else:
                del self.world.things[self.world.things.index(self)]
            return
        try:
            self.task.check()
        except GameError as e:
            self.task = None
            self._last_task_result = e
            if is_AI:
                try:
                    self.decide_task()
                except GameError:
                    self.set_task('WAIT')
            return
        self.task.todo -= 1
        if self.task.todo <= 0:
            self._last_task_result = self.task.do()
            self.task = None
        if is_AI and self.task is None:
            try:
                self.decide_task()
            except GameError:
                self.set_task('WAIT')

    def unset_surroundings(self):
        self._stencil = None
        self._surrounding_map = None
        self._surroundings_offset = None

    def must_fix_indentation(self):
        return self._radius % 2 != self.position[1][0] % 2

    def get_surroundings_offset(self):
        if self._surroundings_offset is not None:
            return self._surroundings_offset
        add_line = self.must_fix_indentation()
        offset_y = self.position[1][0] - self._radius - int(add_line)
        offset_x = self.position[1][1] - self._radius
        self._surroundings_offset = (offset_y, offset_x)
        return self._surroundings_offset

    def get_surrounding_map(self):
        if self._surrounding_map is not None:
            return self._surrounding_map

        def pan_and_scan(size_of_axis, pos, offset):
            big_pos = 0
            small_pos = pos + offset
            if small_pos < 0:
                big_pos = -1
                small_pos = size_of_axis + small_pos
            elif small_pos >= size_of_axis:
                big_pos = 1
                small_pos = small_pos - size_of_axis
            return big_pos, small_pos

        add_line = self.must_fix_indentation()
        self._surrounding_map = self.world.game.\
                                map_type(size=(self._radius*2+1+int(add_line),
                                               self._radius*2+1))
        size = self.world.maps[(0,0)].size
        offset = self.get_surroundings_offset()
        for pos in self._surrounding_map:
            big_y, small_y = pan_and_scan(size[0], pos[0], offset[0])
            big_x, small_x = pan_and_scan(size[1], pos[1], offset[1])
            big_yx = (big_y, big_x)
            small_yx = (small_y, small_x)
            self._surrounding_map[pos] = self.world.maps[big_yx][small_yx]
        return self._surrounding_map

    def get_stencil(self):
        if self._stencil is not None:
            return self._stencil
        surrounding_map = self.get_surrounding_map()
        m = surrounding_map.new_from_shape(' ')
        for pos in surrounding_map:
            if surrounding_map[pos] in {'.', '~'}:
                m[pos] = '.'
        offset = self.get_surroundings_offset()
        fov_center = (self.position[1][0] - offset[0],
                      self.position[1][1] - offset[1])
        self._stencil = m.get_fov_map(fov_center)
        return self._stencil

    def get_visible_map(self):
        stencil = self.get_stencil()
        m = self.get_surrounding_map().new_from_shape(' ')
        for pos in m:
            if stencil[pos] == '.':
                m[pos] = self._surrounding_map[pos]
        return m

    def get_visible_things(self):

        def calc_pos_in_fov(big_pos, small_pos, offset, size_of_axis):
            pos = small_pos - offset
            if big_pos == -1:
                pos = small_pos - size_of_axis - offset
            elif big_pos == 1:
                pos = small_pos + size_of_axis - offset
            return pos

        stencil = self.get_stencil()
        offset = self.get_surroundings_offset()
        visible_things = []
        size = self.world.maps[(0,0)].size
        fov_size = self.get_surrounding_map().size
        for thing in self.world.things:
            big_pos = thing.position[0]
            small_pos = thing.position[1]
            pos_y = calc_pos_in_fov(big_pos[0], small_pos[0], offset[0], size[0])
            pos_x = calc_pos_in_fov(big_pos[1], small_pos[1], offset[1], size[1])
            if pos_y < 0 or pos_x < 0 or pos_y >= fov_size[0] or pos_x >= fov_size[1]:
                continue
            if (not thing.in_inventory) and stencil[(pos_y, pos_x)] == '.':
                visible_things += [thing]
        return visible_things, offset

    def get_pickable_items(self):
        pickable_ids = []
        visible_things, _ = self.get_visible_things()
        for t in [t for t in visible_things if
                  isinstance(t, ThingItem) and
                  (t.position == self.position or
                   t.position[1] in
                   self.world.maps[(0,0)].get_neighbors(self.position[1]).values())]:
            pickable_ids += [t.id_]
        return pickable_ids



class ThingHuman(ThingAnimate):
    type_ = 'human'
    health = 100



class ThingMonster(ThingAnimate):
    type_ = 'monster'
    health = 50
