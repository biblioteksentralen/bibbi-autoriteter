import os


def as_generator(result):
    # Convenience method
    if result is not None:
        yield result


def ensure_parent_dir_exists(filename):
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.mkdir(dirname)


def trim(value):
    if value is None:
        return None
    value = value.strip()
    if value == '':
        value = None
    return value


def to_str(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)
