import unittest
from functools import partial


class ArgError(Exception):
    pass


class Parser:

    def __init__(self, game=None):
        self.game = game

    def tokenize(self, msg):
        """Parse msg string into tokens.

        Separates by ' ' and '\n', but allows whitespace in tokens quoted by
        '"', and allows escaping within quoted tokens by a prefixed backslash.
        """
        tokens = []
        token = ''
        quoted = False
        escaped = False
        for c in msg:
            if quoted:
                if escaped:
                    token += c
                    escaped = False
                elif c == '\\':
                    escaped = True
                elif c == '"':
                    quoted = False
                else:
                    token += c
            elif c == '"':
                quoted = True
            elif c in {' ', '\n'}:
                if len(token) > 0:
                    tokens += [token]
                    token = ''
            else:
                token += c
        if len(token) > 0:
            tokens += [token]
        return tokens

    def parse(self, msg):
        """Parse msg as call to self.game method, return method with arguments.

        Respects method signatures defined in methods' .argtypes attributes.
        """
        tokens = self.tokenize(msg)
        if len(tokens) == 0:
            return None
        method_candidate = 'cmd_' + tokens[0]
        if not hasattr(self.game, method_candidate):
            return None
        method = getattr(self.game, method_candidate)
        if len(tokens) == 1:
            if not hasattr(method, 'argtypes'):
                return method
            else:
                raise ArgError('Command expects argument(s).')
        args_candidates = tokens[1:]
        if not hasattr(method, 'argtypes'):
            raise ArgError('Command expects no argument(s).')
        args, kwargs = self.argsparse(method.argtypes, args_candidates)
        return partial(method, *args, **kwargs)

    def parse_yx_tuple(self, yx_string):
        """Parse yx_string as yx_tuple:nonneg argtype, return result."""

        def get_axis_position_from_argument(axis, token):
            if len(token) < 3 or token[:2] != axis + ':' or \
                    not token[2:].isdigit():
                raise ArgError('Non-int arg for ' + axis + ' position.')
            n = int(token[2:])
            if n < 1:
                raise ArgError('Arg for ' + axis + ' position < 1.')
            return n

        tokens = yx_string.split(',')
        if len(tokens) != 2:
            raise ArgError('Wrong number of yx-tuple arguments.')
        y = get_axis_position_from_argument('Y', tokens[0])
        x = get_axis_position_from_argument('X', tokens[1])
        return (y, x)

    def argsparse(self, signature, args_tokens):
        """Parse into / return args_tokens as args/kwargs defined by signature.

        Expects signature to be a ' '-delimited sequence of any of the strings
        'int:nonneg', 'yx_tuple:nonneg', 'string', 'seq:int:nonneg', defining
        the respective argument types.
        """
        tmpl_tokens = signature.split()
        if len(tmpl_tokens) != len(args_tokens):
            raise ArgError('Number of arguments (' + str(len(args_tokens)) +
                           ') not expected number (' + str(len(tmpl_tokens))
                           + ').')
        args = []
        for i in range(len(tmpl_tokens)):
            tmpl = tmpl_tokens[i]
            arg = args_tokens[i]
            if tmpl == 'int:nonneg':
                if not arg.isdigit():
                    raise ArgError('Argument must be non-negative integer.')
                args += [int(arg)]
            elif tmpl == 'yx_tuple:nonneg':
                args += [self.parse_yx_tuple(arg)]
            elif tmpl == 'string':
                args += [arg]
            elif tmpl == 'seq:int:nonneg':
                sub_tokens = arg.split(',')
                if len(sub_tokens) < 1:
                    raise ArgError('Argument must be non-empty sequence.')
                seq = []
                for tok in sub_tokens:
                    if not tok.isdigit():
                        raise ArgError('Argument sequence must only contain '
                                       'non-negative integers.')
                    seq += [int(tok)]
                args += [seq]
            else:
                raise ArgError('Unknown argument type.')
        return args, {}


class TestParser(unittest.TestCase):

    def test_tokenizer(self):
        p = Parser()
        self.assertEqual(p.tokenize(''), [])
        self.assertEqual(p.tokenize(' '), [])
        self.assertEqual(p.tokenize('abc'), ['abc'])
        self.assertEqual(p.tokenize('a b\nc  "d"'), ['a', 'b', 'c', 'd'])
        self.assertEqual(p.tokenize('a "b\nc d"'), ['a', 'b\nc d'])
        self.assertEqual(p.tokenize('a"b"c'), ['abc'])
        self.assertEqual(p.tokenize('a\\b'), ['a\\b'])
        self.assertEqual(p.tokenize('"a\\b"'), ['ab'])
        self.assertEqual(p.tokenize('a"b'), ['ab'])
        self.assertEqual(p.tokenize('a"\\"b'), ['a"b'])

    def test_unhandled(self):
        p = Parser()
        self.assertEqual(p.parse(''), None)
        self.assertEqual(p.parse(' '), None)
        self.assertEqual(p.parse('x'), None)

    def test_argsparse(self):
        from functools import partial
        p = Parser()
        assertErr = partial(self.assertRaises, ArgError, p.argsparse)
        assertErr('', ['foo'])
        assertErr('string', [])
        assertErr('string string', ['foo'])
        self.assertEqual(p.argsparse('string', ('foo',)),
                         (['foo'], {}))
        self.assertEqual(p.argsparse('string string', ('foo', 'bar')),
                         (['foo', 'bar'], {}))
        assertErr('int:nonneg', [''])
        assertErr('int:nonneg', ['x'])
        assertErr('int:nonneg', ['-1'])
        assertErr('int:nonneg', ['0.1'])
        self.assertEqual(p.argsparse('int:nonneg', ('0',)),
                         ([0], {}))
        assertErr('yx_tuple:nonneg', ['x'])
        assertErr('yx_tuple:nonneg', ['Y:0,X:1'])
        assertErr('yx_tuple:nonneg', ['Y:1,X:0'])
        assertErr('yx_tuple:nonneg', ['Y:1.1,X:1'])
        assertErr('yx_tuple:nonneg', ['Y:1,X:1.1'])
        self.assertEqual(p.argsparse('yx_tuple:nonneg', ('Y:1,X:2',)),
                         ([(1, 2)], {}))
        assertErr('seq:int:nonneg', [''])
        assertErr('seq:int:nonneg', [','])
        assertErr('seq:int:nonneg', ['a'])
        assertErr('seq:int:nonneg', ['a,1'])
        assertErr('seq:int:nonneg', [',1'])
        assertErr('seq:int:nonneg', ['1,'])
        self.assertEqual(p.argsparse('seq:int:nonneg', ('1,2,3',)),
                         ([[1, 2, 3]], {}))