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
