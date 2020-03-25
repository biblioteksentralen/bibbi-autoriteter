from collections import namedtuple
from bibbi.entities import DataRow


def make_datarow(table, **kwargs):
    keys = list(table.columns.values()) + ['item_count']
    values = {k: None for k in keys}
    values.update(kwargs)
    Row = namedtuple('Row', keys)
    row = Row(**values)
    return DataRow(row, table.entity_type)

