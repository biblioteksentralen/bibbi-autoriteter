from collections import namedtuple
from bibbi.entities import DataRow


def make_datarow(df_cls, **kwargs):
    keys = list(df_cls.columns.values()) + ['item_count']
    values = {k: None for k in keys}
    values.update(kwargs)
    Row = namedtuple('Row', keys)
    row = Row(**values)
    return DataRow(row, df_cls.entity_type)

