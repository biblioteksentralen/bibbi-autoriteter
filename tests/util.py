from collections import namedtuple
from typing import Dict, Union

from bibbi.constants import TYPE_TOPICAL, TYPE_GEOGRAPHIC, TYPE_PERSON, TYPE_CORPORATION
from bibbi.promus_service import DataRow, TopicTable, GeographicTable, CorporationTable, PersonTable

row_types = {
    TYPE_TOPICAL: TopicTable,
    TYPE_GEOGRAPHIC: GeographicTable,
    TYPE_PERSON: PersonTable,
    TYPE_CORPORATION: CorporationTable,
}

extra_columns = {
    TYPE_TOPICAL: [],
    TYPE_GEOGRAPHIC: [],
    TYPE_PERSON: ['items_as_entry', 'items_as_subject'],
    TYPE_CORPORATION: ['items_as_entry', 'items_as_subject'],
}


def get_table_type(row_type):
    return row_types[row_type]


def make_row(row_type: str, params: Dict[str, Union[str, int, None]]) -> DataRow:
    table = get_table_type(row_type)
    keys = list(table.columns.values()) + extra_columns[row_type]
    values = {k: None for k in keys}
    values.update(params)
    print(params)
    RowTuple = namedtuple('Row', keys)
    row_tuple = RowTuple(**values)
    return table.make_row(row_tuple)
