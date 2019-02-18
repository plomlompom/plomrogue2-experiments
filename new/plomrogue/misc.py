def quote(string):
    """Quote & escape string so client interprets it as single token."""
    quoted = []
    quoted += ['"']
    for c in string:
        if c in {'"', '\\'}:
            quoted += ['\\']
        quoted += [c]
    quoted += ['"']
    return ''.join(quoted)


def stringify_yx(tuple_):
    """Transform tuple (y,x) into string 'Y:'+str(y)+',X:'+str(x)."""
    return 'Y:' + str(tuple_[0]) + ',X:' + str(tuple_[1])
