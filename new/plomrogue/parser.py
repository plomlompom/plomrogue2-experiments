import unittest
from plomrogue.errors import ArgError
from plomrogue.mapping import YX


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
        """Parse msg as call to function, return function with args tuple.

        Respects function signature defined in function's .argtypes attribute.
        """
        tokens = self.tokenize(msg)
        if len(tokens) == 0:
            return None, ()
        func = self.game.get_command(tokens[0])
        argtypes = ''
        if hasattr(func, 'argtypes'):
            argtypes = func.argtypes
        if func is None:
            return None, ()
        if len(argtypes) == 0:
            if len(tokens) > 1:
                raise ArgError('Command expects no argument(s).')
            return func, ()
        if len(tokens) == 1:
            raise ArgError('Command expects argument(s).')
        args_candidates = tokens[1:]
        args = self.argsparse(argtypes, args_candidates)
        return func, args

    def parse_yx_tuple(self, yx_string, range_=None):
        """Parse yx_string as yx_tuple, return result.

        The range_ argument may be 'nonneg' (non-negative, including
        0) or 'pos' (positive, excluding 0).

        """

        def get_axis_position_from_argument(axis, token):
            if len(token) < 3 or token[:2] != axis + ':' or \
                    not (token[2:].isdigit() or token[2] == '-'):
                raise ArgError('Non-int arg for ' + axis + ' position.')
            n = int(token[2:])
            if n < 1 and range_ == 'pos':
                raise ArgError('Arg for ' + axis + ' position < 1.')
            elif n < 0 and range_ == 'nonneg':
                raise ArgError('Arg for ' + axis + ' position < 0.')
            return n

        tokens = yx_string.split(',')
        if len(tokens) != 2:
            raise ArgError('Wrong number of yx-tuple arguments.')
        y = get_axis_position_from_argument('Y', tokens[0])
        x = get_axis_position_from_argument('X', tokens[1])
        return YX(y, x)

    def argsparse(self, signature, args_tokens):
        """Parse into / return args_tokens as args defined by signature.

        Expects signature to be a ' '-delimited sequence of any of the strings
        'int:nonneg', 'yx_tuple', 'yx_tuple:nonneg', 'yx_tuple:pos', 'string',
        'seq:int:nonneg', 'string:' + an option type string accepted by
        self.game.get_string_options, defining the respective argument types.
        """
        tmpl_tokens = signature.split()
        if len(tmpl_tokens) != len(args_tokens):
            raise ArgError('Number of arguments (' + str(len(args_tokens)) +
                           ') not expected number (' + str(len(tmpl_tokens))
                           + ').')
        args = []
        string_string = 'string'
        for i in range(len(tmpl_tokens)):
            tmpl = tmpl_tokens[i]
            arg = args_tokens[i]
            if tmpl == 'int:nonneg':
                if not arg.isdigit():
                    raise ArgError('Argument must be non-negative integer.')
                args += [int(arg)]
            elif tmpl == 'yx_tuple:nonneg':
                args += [self.parse_yx_tuple(arg, 'nonneg')]
            elif tmpl == 'yx_tuple:pos':
                args += [self.parse_yx_tuple(arg, 'pos')]
            elif tmpl == 'yx_tuple':
                args += [self.parse_yx_tuple(arg)]
            elif tmpl == 'seq:int:nonneg':
                if arg == ',':
                    args += [[]]
                    continue
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
            elif tmpl == string_string:
                args += [arg]
            elif tmpl[:len(string_string) + 1] == string_string + ':':
                if not hasattr(self.game, 'get_string_options'):
                    raise ArgError('No string option directory.')
                string_option_type = tmpl[len(string_string) + 1:]
                options = self.game.get_string_options(string_option_type)
                if options is None:
                    raise ArgError('Unknown string option type.')
                if arg not in options:
                    msg = 'Argument #%s must be one of: %s' % (i + 1, options)
                    raise ArgError(msg)
                args += [arg]
            else:
                raise ArgError('Unknown argument type.')
        return args


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
        self.assertEqual(p.parse(''), (None, ()))
        self.assertEqual(p.parse(' '), (None, ()))
        #self.assertEqual(p.parse('x'), (None, ()))

    def test_argsparse(self):
        from functools import partial
        p = Parser()
        assertErr = partial(self.assertRaises, ArgError, p.argsparse)
        assertErr('', ['foo'])
        assertErr('string', [])
        assertErr('string string', ['foo'])
        self.assertEqual(p.argsparse('string', ('foo',)), ['foo'])
        self.assertEqual(p.argsparse('string string', ('foo', 'bar')),
                         ['foo', 'bar'])
        assertErr('int:nonneg', [''])
        assertErr('int:nonneg', ['x'])
        assertErr('int:nonneg', ['-1'])
        assertErr('int:nonneg', ['0.1'])
        self.assertEqual(p.argsparse('int:nonneg', ('0',)), [0])
        assertErr('yx_tuple', ['x'])
        assertErr('yx_tuple', ['Y:1.1,X:1'])
        self.assertEqual(p.argsparse('yx_tuple', ('Y:1,X:-2',)), [(1, -2)])
        assertErr('yx_tuple:nonneg', ['Y:0,X:-1'])
        assertErr('yx_tuple:nonneg', ['Y:-1,X:0'])
        assertErr('yx_tuple:nonneg', ['Y:1,X:1.1'])
        self.assertEqual(p.argsparse('yx_tuple:nonneg', ('Y:1,X:2',)),
                         [(1, 2)])
        assertErr('yx_tuple:pos', ['Y:0,X:1'])
        assertErr('yx_tuple:pos', ['Y:1,X:0'])
        assertErr('seq:int:nonneg', [''])
        self.assertEqual(p.argsparse('seq:int:nonneg', [',']), [[]])
        assertErr('seq:int:nonneg', ['a'])
        assertErr('seq:int:nonneg', ['a,1'])
        assertErr('seq:int:nonneg', [',1'])
        assertErr('seq:int:nonneg', ['1,'])
        self.assertEqual(p.argsparse('seq:int:nonneg', ('1,2,3',)),
                         [[1, 2, 3]])
