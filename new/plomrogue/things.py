from plomrogue.errors import GameError
from plomrogue.mapping import YX, Map, FovMapHex



class ThingBase:
    type_ = '?'

    def __init__(self, game, id_=None, position=(YX(0,0), YX(0,0))):
        self.game = game
        if id_ is None:
            self.id_ = self.game.new_thing_id()
        else:
            self.id_ = id_
        self.position = position

    @property
    def position(self):
        return self._position

    def _position_set(self, pos):
        """Set self._position to pos.

        We use this setter as core to the @position.setter property
        method due to property setter subclassing not yet working
        properly, see <https://bugs.python.org/issue14965>. We will
        therefore super() _position_set instead of @position.setter in
        subclasses.

        """
        self._position = pos

    @position.setter
    def position(self, pos):
        self._position_set(pos)



class Thing(ThingBase):
    blocking = False
    in_inventory = False

    def __init__(self, *args, **kwargs):
        self.inventory = []
        self._radius = 8
        super().__init__(*args, **kwargs)

    def proceed(self):
        pass

    def _position_set(self, pos):
        super()._position_set(pos)
        for t_id in self.inventory:
            t = self.game.get_thing(t_id)
            t.position = self.position
        if not self.id_ == self.game.player_id:
            return
        edge_left = self.position[1].x - self._radius
        edge_right = self.position[1].x + self._radius
        edge_up = self.position[1].y - self._radius
        edge_down = self.position[1].y + self._radius
        if edge_left < 0:
            self.game.get_map(self.position[0] + YX(1,-1))
            self.game.get_map(self.position[0] + YX(0,-1))
            self.game.get_map(self.position[0] + YX(-1,-1))
        if edge_right >= self.game.map_size.x:
            self.game.get_map(self.position[0] + YX(1,1))
            self.game.get_map(self.position[0] + YX(0,1))
            self.game.get_map(self.position[0] + YX(-1,1))
        if edge_up < 0:
            self.game.get_map(self.position[0] + YX(-1,1))
            self.game.get_map(self.position[0] + YX(-1,0))
            self.game.get_map(self.position[0] + YX(-1,-1))
        if edge_down >= self.game.map_size.y:
            self.game.get_map(self.position[0] + YX(1,1))
            self.game.get_map(self.position[0] + YX(1,0))
            self.game.get_map(self.position[0] + YX(1,-1))
        #alternative
        #if self.position[1].x < self._radius:
        #    self.game.get_map(self.position[0] - YX(0,1))
        #if self.position[1].y < self._radius:
        #    self.game.get_map(self.position[0] - YX(1,0))
        #if self.position[1].x > self.game.map_size.x - self._radius:
        #    self.game.get_map(self.position[0] + YX(0,1))
        #if self.position[1].y > self.game.map_size.y - self._radius:
        #    self.game.get_map(self.position[0] + YX(1,0))
        #if self.position[1].y < self._radius and \
        #   self.position[1].x <= [pos for pos in
        #                          diagonal_distance_edge
        #                          if pos.y == self.position[1].y][0].x:
        #    self.game.get_map(self.position[0] - YX(1,1))



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
        self.unset_surroundings()

    def move_on_dijkstra_map(self, own_pos, targets):
        visible_map = self.get_visible_map()
        dijkstra_map = Map(visible_map.size,
                           start_indented=visible_map.start_indented)
        n_max = 256
        dijkstra_map.terrain = [n_max for i in range(dijkstra_map.size_i)]
        for target in targets:
            dijkstra_map[target] = 0
        shrunk = True
        get_neighbors = self.game.map_geometry.get_neighbors
        while shrunk:
            shrunk = False
            for pos in dijkstra_map:
                if visible_map[pos] != '.':
                    continue
                neighbors = get_neighbors((YX(0,0), pos), dijkstra_map.size,
                                          dijkstra_map.start_indented)
                for direction in neighbors:
                    big_yx, small_yx = neighbors[direction]
                    if big_yx == YX(0,0) and \
                       dijkstra_map[small_yx] < dijkstra_map[pos] - 1:
                        dijkstra_map[pos] = dijkstra_map[small_yx] + 1
                        shrunk = True
        get_neighbors((YX(0,0), own_pos), dijkstra_map.size,
                      dijkstra_map.start_indented)
        n = n_max
        target_direction = None
        for direction in sorted(neighbors.keys()):
            big_yx, small_yx = neighbors[direction]
            if big_yx == (0,0):
                n_new = dijkstra_map[small_yx]
                if n_new < n:
                    n = n_new
                    target_direction = direction
        return target_direction

    def hunt_player(self):
        visible_things = self.get_visible_things()
        target = None
        for t in visible_things:
            if t.type_ == 'human':
                target = t.position[1] - self.view_offset
                break
        if target is not None:
            try:
                offset_self_pos = self.position[1] - self.view_offset
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
            t = self.game.get_thing(id_)
            if t.type_ == 'food':
                self.set_task('EAT', (id_,))
                return True
        for id_ in self.get_pickable_items():
            t = self.game.get_thing(id_)
            if t.type_ == 'food':
                self.set_task('PICKUP', (id_,))
                return True
        visible_things = self.get_visible_things()
        food_targets = []
        for t in visible_things:
            if t.type_ == 'food':
                food_targets += [t.position[1] - self.view_offset]
        offset_self_pos = self.position[1] - self.view_offset
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
        task_class = self.game.tasks[task_name]
        self.task = task_class(self, args)
        self.task.check()  # will throw GameError if necessary

    def proceed(self, is_AI=True):
        """Further the thing in its tasks, decrease its health.

        First, ensures an empty map, decrements .health and kills
        thing if crossing zero (removes from self.game.things for AI
        thing, or unsets self.game.player_is_alive for player thing);
        then checks that self.task is still possible and aborts if
        otherwise (for AI things, decides a new task).

        Then decrements .task.todo; if it thus falls to <= 0, enacts
        method whose name is 'task_' + self.task.name and sets .task =
        None. If is_AI, calls .decide_task to decide a self.task.

        """
        self.unset_surroundings()
        self.health -= 1
        if self.health <= 0:
            if self is self.game.player:
                self.game.player_is_alive = False
            else:
                del self.game.things[self.game.things.index(self)]
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
        self._surroundings = None

    @property
    def view_offset(self):
        return self.game.map_geometry.get_view_offset(self.game.map_size,
                                                      self.position,
                                                      self._radius)

    @property
    def surroundings(self):
        if self._surroundings is not None:
            return self._surroundings
        s = self.game.map_geometry.get_view(self.game.map_size,
                                            self.game.get_map,
                                            self._radius, self.view_offset)
        self._surroundings = s
        return self._surroundings

    def get_stencil(self):
        if self._stencil is not None:
            return self._stencil
        m = Map(self.surroundings.size, ' ', self.surroundings.start_indented)
        for pos in self.surroundings:
            if self.surroundings[pos] in {'.', '~'}:
                m[pos] = '.'
        fov_center = YX((m.size.y) // 2, m.size.x // 2)
        self._stencil = FovMapHex(m, fov_center)
        return self._stencil

    def get_visible_map(self):
        stencil = self.get_stencil()
        m = Map(self.surroundings.size, ' ')
        for pos in m:
            if stencil[pos] == '.':
                m[pos] = self.surroundings[pos]
        return m

    def get_visible_things(self):
        stencil = self.get_stencil()
        visible_things = []
        for thing in self.game.things:
            pos = self.game.map_geometry.pos_in_view(thing.position,
                                                     self.view_offset,
                                                     self.game.map_size)
            if pos.y < 0 or pos.x < 0 or\
               pos.y >= stencil.size.y or pos.x >= stencil.size.x:
                continue
            if (not thing.in_inventory) and stencil[pos] == '.':
                visible_things += [thing]
        return visible_things

    def get_pickable_items(self):
        pickable_ids = []
        visible_things = self.get_visible_things()
        neighbor_fields = self.game.map_geometry.get_neighbors(self.position,
                                                               self.game.map_size)
        for t in [t for t in visible_things
                  if isinstance(t, ThingItem) and
                  (t.position == self.position or
                   t.position in neighbor_fields.values())]:
            pickable_ids += [t.id_]
        return pickable_ids



class ThingHuman(ThingAnimate):
    type_ = 'human'
    health = 100



class ThingMonster(ThingAnimate):
    type_ = 'monster'
    health = 50
