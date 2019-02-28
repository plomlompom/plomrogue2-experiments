from plomrogue.errors import GameError



class ThingBase:
    type_ = '?'

    def __init__(self, world, id_=None, position=(0,0)):
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
    type_ = 'item'



class ThingAnimate(Thing):
    blocking = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_task('WAIT')
        self._last_task_result = None
        self._stencil = None

    def move_towards_target(self, target):
        dijkstra_map = type(self.world.map_)(self.world.map_.size)
        n_max = 256
        dijkstra_map.terrain = [n_max for i in range(dijkstra_map.size_i)]
        dijkstra_map[target] = 0
        shrunk = True
        visible_map = self.get_visible_map()
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
        neighbors = dijkstra_map.get_neighbors(tuple(self.position))
        n = n_max
        target_direction = None
        for direction in sorted(neighbors.keys()):
            yx = neighbors[direction]
            if yx is not None:
                n_new = dijkstra_map[yx]
                if n_new < n:
                    n = n_new
                    target_direction = direction
        if target_direction:
            self.set_task('MOVE', (target_direction,))

    def decide_task(self):
        visible_things = self.get_visible_things()
        target = None
        for t in visible_things:
            if t.type_ == 'human':
                target = t.position
                break
        if target is not None:
            try:
                self.move_towards_target(target)
                return
            except GameError:
                pass
        self.set_task('WAIT')

    def set_task(self, task_name, args=()):
        task_class = self.world.game.tasks[task_name]
        self.task = task_class(self, args)
        self.task.check()  # will throw GameError if necessary

    def proceed(self, is_AI=True):
        """Further the thing in its tasks.

        Decrements .task.todo; if it thus falls to <= 0, enacts method
        whose name is 'task_' + self.task.name and sets .task =
        None. If is_AI, calls .decide_task to decide a self.task.

        Before doing anything, ensures an empty map visibility stencil
        and checks that task is still possible, and aborts it
        otherwise (for AI things, decides a new task).

        """
        self._stencil = None
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

    def get_stencil(self):
        if self._stencil is not None:
            return self._stencil
        self._stencil = self.world.map_.get_fov_map(self.position)
        return self._stencil

    def get_visible_map(self):
        stencil = self.get_stencil()
        m = self.world.map_.new_from_shape(' ')
        for pos in m:
            if stencil[pos] == '.':
                m[pos] = self.world.map_[pos]
        return m

    def get_visible_things(self):
        stencil = self.get_stencil()
        visible_things = []
        for thing in self.world.things:
            if (not thing.in_inventory) and stencil[thing.position] == '.':
                visible_things += [thing]
        return visible_things



class ThingHuman(ThingAnimate):
    type_ = 'human'



class ThingMonster(ThingAnimate):
    type_ = 'monster'
