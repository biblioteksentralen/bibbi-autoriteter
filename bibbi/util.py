import os
import pandas as pd


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


class LanguageMap:

    def __init__(self, nb, nn):
        self.nb = nb
        self.nn = nn if pd.notnull(nn) else nb

    def __add__(self, other):
        if isinstance(other, LanguageMap):
            return LanguageMap(nb=self.nb + other.nb, nn=self.nn + other.nn)
        elif isinstance(other, str):
            return LanguageMap(nb=self.nb + other, nn=self.nn + other)
        else:
            raise TypeError

    def items(self):
        return (
            ('nb', self.nb),
            ('nn', self.nn),
        )

    def __repr__(self):
        return '<Languagemap nb="%s" nn="%s">' % (self.nb, self.nn)
