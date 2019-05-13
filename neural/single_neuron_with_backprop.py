import random

def sigmoid(x):
    import math
    return 1 / (1 + math.exp(-x))

def d_sigmoid(x):
    return sigmoid(x) * (1 - sigmoid(x))

def result(inputs):
    end_node['inputs'] = inputs[:]
    s = 0
    for i in range(len(inputs)):
        s += inputs[i] * end_node['weights'][i]
    end_node['weighted_biased_input'] = s + end_node['bias']
    end_node['sigmoid_output'] = sigmoid(end_node['weighted_biased_input'])
    return end_node['sigmoid_output']

def backprop(end_result, target, cost):
    d_cost_over_sigmoid_output = 2*(end_result - target)
    for i in range(len(end_node['weights'])):
        d_weighted_biased_input_over_weight = end_node['inputs'][i]
        d_sigmoid_output_over_weighted_biased_input = d_sigmoid(end_node['weighted_biased_input'])
        d_cost_over_weight = d_cost_over_sigmoid_output * d_sigmoid_output_over_weighted_biased_input * d_weighted_biased_input_over_weight
        end_node['weights'][i] -= d_cost_over_weight
    d_cost_over_bias = d_cost_over_sigmoid_output
    end_node['bias'] -= d_cost_over_bias

# identity
training_set = [((0,), 0),
                ((1,), 1)]

# NOT
#training_set = [((0,), 1),
#                ((1,), 0)]

# AND
#training_set = [((0,0), 0),
#                ((1,0), 0),
#                ((0,1), 0),
#                ((1,1), 1)]

# OR
#training_set = [((0,0), 0),
#                ((1,0), 1),
#                ((0,1), 1),
#                ((1,1), 1)]

# NOT (with one irrelevant column)
#training_set = [((0,0), 1),
#                ((1,0), 0),
#                ((0,1), 1),
#                ((1,1), 0)]

# XOR (will fail)
#training_set = [((0,0), 0),
#                ((1,0), 1),
#                ((0,1), 1),
#                ((1,1), 0)]

# 1 if above f(x)=x line, else 0
#training_set = [((0,1), 1),
#                ((2,3), 1),
#                ((1,1), 0),
#                ((2,2), 0)]

# 1 if above f(x)=x**2, else 0 (will fail: no linear separability)
#training_set = [((2,4), 0),
#                ((2,5), 1),
#                ((3,9), 0),
#                ((3,10), 1)]

end_node = {'weights': [random.random() for i in range(len(training_set[0][0]))],
            'bias': random.random()}
n_training_runs = 100
for i in range(n_training_runs):
    print()
    for element in training_set:
        inputs = element[0]
        target = element[1]
        result_ = result(inputs)
        cost = (result_ - target)**2
        formatted_weights = []
        for w in end_node['weights']:
            formatted_weights += ['%1.3f' % w]
        print("inputs %s target %s result %0.9f cost %0.9f weights [%s] bias %1.3f" % (inputs, target, result_, cost, ','.join(formatted_weights), end_node['bias']))
        backprop(result_, target, cost)
