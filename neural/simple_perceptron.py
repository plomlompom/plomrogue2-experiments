class Perceptron:

    def __init__(self, size):
        self.n_inputs = size
        self.weights = [0] * self.n_inputs
        self.bias = 0

    def output(self, inputs):
        step = 0  # If 0.5, we need no bias for AND and OR; if 0, none for NOT.
                  # With learning, the bias will slowly balance any choice.
        weighted_inputs_sum = 0
        for i in range(self.n_inputs):
            weighted_inputs_sum += inputs[i] * self.weights[i]
        if weighted_inputs_sum + self.bias >= step:
            return 1
        else:
            return 0

class TrainingUnit:

    def __init__(self, inputs, target):
        self.inputs = inputs
        self.target = target

# identity
#training_set = [TrainingUnit((0,), 0),
#                TrainingUnit((1,), 1)]

# NOT
#training_set = [TrainingUnit((0,), 1),
#                TrainingUnit((1,), 0)]

# AND
#training_set = [TrainingUnit((0,0), 0),
#                TrainingUnit((1,0), 0),
#                TrainingUnit((0,1), 0),
#                TrainingUnit((1,1), 1)]

# OR
#training_set = [TrainingUnit((0,0), 0),
#                TrainingUnit((1,0), 1),
#                TrainingUnit((0,1), 1),
#                TrainingUnit((1,1), 1)]

# NOT (with one irrelevant column)
#training_set = [TrainingUnit((0,0), 0),
#                TrainingUnit((1,0), 1),
#                TrainingUnit((0,1), 0),
#                TrainingUnit((1,1), 1)]

# XOR (will fail, as Minsky/Papert say)
#training_set = [TrainingUnit((0,0), 0),
#                TrainingUnit((1,0), 1),
#                TrainingUnit((0,1), 1),
#                TrainingUnit((1,1), 0)]

# 1 if above f(x)=x line, else 0
training_set = [TrainingUnit((0,1), 1),
                TrainingUnit((2,3), 1),
                TrainingUnit((1,1), 0),
                TrainingUnit((2,2), 0)]

# 1 if above f(x)=x**2, else 0 (will fail: no linear separability)
#training_set = [TrainingUnit((2,4), 0),
#                TrainingUnit((2,5), 1),
#                TrainingUnit((3,9), 0),
#                TrainingUnit((3,10), 1)]


p = Perceptron(len(training_set[0].inputs))
adaption_step = 0.1
max_rounds = 100
for i in range(max_rounds):
    print()
    go_on = False
    for unit in training_set:
        result_ = p.output(unit.inputs)
        formatted_inputs = []
        for i in unit.inputs:
            formatted_inputs += ['%2d' % i]
        formatted_weights = []
        for w in p.weights:
            formatted_weights += ['% .1f' % w]
        print("inputs (%s) target %s result %s correctness %5s weights [%s] bias % .1f" % (', '.join(formatted_inputs), unit.target, result_, unit.target==result_, ', '.join(formatted_weights), p.bias))
        if unit.target != result_:
            go_on=True
        p.bias += adaption_step * (unit.target - result_)
        for i in range(p.n_inputs):
            p.weights[i] += adaption_step * (unit.target - result_) * unit.inputs[i]
    if not go_on:
        break
print()
if go_on:
    print('COULD NOT SOLVE WITHIN %s ROUNDS.' % max_rounds)
else:
    print('SUCCESS.')
