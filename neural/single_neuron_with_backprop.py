def sigmoid(x):
    import math
    return 1 / (1 + math.exp(-x))

def d_sigmoid(x):
    return sigmoid(x) * (1 - sigmoid(x))

class Node:

    def __init__(self, size):
        self.n_inputs = size
        self.weights = [0] * self.n_inputs
        self.bias = 0

    def output(self, inputs):
        self.inputs = inputs
        weighted_inputs_sum = 0
        for i in range(self.n_inputs):
            weighted_inputs_sum += inputs[i] * self.weights[i]
        self.weighted_biased_input = weighted_inputs_sum + self.bias
        self.sigmoid_output = sigmoid(self.weighted_biased_input)
        return self.sigmoid_output

    def backprop(self, target):
        d_cost_over_sigmoid_output = 2*(self.sigmoid_output - target)
        for i in range(self.n_inputs):
            d_weighted_biased_input_over_weight = self.inputs[i]
            d_sigmoid_output_over_weighted_biased_input = d_sigmoid(self.weighted_biased_input)
            d_cost_over_weight = d_cost_over_sigmoid_output * d_sigmoid_output_over_weighted_biased_input * d_weighted_biased_input_over_weight
            self.weights[i] -= d_cost_over_weight
        d_cost_over_bias = d_cost_over_sigmoid_output
        self.bias -= d_cost_over_bias


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

end_node = Node(len(training_set[0].inputs))
n_training_runs = 100
for i in range(n_training_runs):
    print()
    for unit in training_set:
        result_ = end_node.output(unit.inputs)
        cost = (result_ - unit.target)**2
        formatted_inputs = []
        for i in unit.inputs:
            formatted_inputs += ['%2d' % i]
        formatted_weights = []
        for w in end_node.weights:
            formatted_weights += ['%1.3f' % w]
        print("inputs (%s) target %s result %0.9f cost %0.9f weights [%s] bias %1.3f" % (', '.join(formatted_inputs), unit.target, result_, cost, ', '.join(formatted_weights), end_node.bias))
        end_node.backprop(unit.target)
