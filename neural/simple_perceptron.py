def step(x):
    step = 0  # If 0.5, we need no bias for AND and OR; if 0, none for NOT.
              # With learning, the bias will slowly balance any choice.
    if x >= step:
        return 1
    else:
        return 0

def result(inputs):
    s = 0
    perceptron['inputs'] = inputs[:]
    for i in range(len(inputs)):
        s += inputs[i] * perceptron['weights'][i]
    return step(s + perceptron['bias'])

# identity
#training_set = [((0,), 0),
#                ((1,), 1)]

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

# XOR (will fail, as Minsky/Papert say)
#training_set = [((0,0), 0),
#                ((1,0), 1),
#                ((0,1), 1),
#                ((1,1), 0)]

# 1 if above f(x)=x line, else 0
training_set = [((0,1), 1),
                ((2,3), 1),
                ((1,1), 0),
                ((2,2), 0)]

# 1 if above f(x)=x**2, else 0 (will fail: no linear separability)
#training_set = [((2,4), 0),
#                ((2,5), 1),
#                ((3,9), 0),
#                ((3,10), 1)]

perceptron = {'weights': [0 for i in range(len(training_set[0][0]))],
              'bias': 0}
adaption_size = 0.1

for i in range(100):
    print()
    go_on = False
    for element in training_set:
        inputs = element[0]
        target = element[1]
        result_ = result(inputs)
        print("inputs %s target %s result %s correctness %5s weights %s bias %s" % (inputs, target, result_, target==result_, perceptron['weights'], perceptron['bias']))
        if target != result_:
            go_on=True
        perceptron['bias'] += adaption_size * (target - result_)
        for i in range(len(perceptron['weights'])):
            perceptron['weights'][i] += adaption_size * (target - result_) * perceptron['inputs'][i]
    if not go_on:
        break
print()
if go_on:
    print('COULD NOT SOLVE.')
else:
    print('SUCCESS')
