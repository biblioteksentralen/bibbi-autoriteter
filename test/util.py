from collections import namedtuple

from bibbi.constants import TYPE_TOPIC, TYPE_GEOGRAPHIC, TYPE_PERSON, TYPE_CORPORATION
from bibbi.entities import DataRow
from bibbi.repository import TopicTable, GeographicTable, CorporationTable, PersonTable

row_types = {
    TYPE_TOPIC: TopicTable,
    TYPE_GEOGRAPHIC: GeographicTable,
    TYPE_PERSON: PersonTable,
    TYPE_CORPORATION: CorporationTable,
}


def make_datarow(row_type, **kwargs):
    table = row_types[row_type]
    keys = list(table.columns.values()) + ['item_count']
    values = {k: None for k in keys}
    values.update(kwargs)
    Row = namedtuple('Row', keys)
    row = Row(**values)
    return DataRow(row, table.entity_type)

