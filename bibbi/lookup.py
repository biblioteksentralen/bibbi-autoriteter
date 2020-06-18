from __future__ import annotations
import sqlite3

import pandas as pd
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bibbi.entities import Entity
    from bibbi.util import LanguageMap

"""
class SqliteLookupService:

    def __init__(self):
        self.conn = sqlite3.connect(':memory:', isolation_level=None)
        self.conn.execute('''CREATE TABLE data
                     (entity_id text, label text, source_type text, entity_type text, preferred text)''')

    def add(self, label: LanguageMap, preferred: bool, entity: Entity):
        label_str = label.nb.lower()
        self.conn.execute('INSERT INTO data (entity_id, entity_type, source_type, label, preferred) VALUES(?, ?, ?, ?, ?)', [
            entity.id,
            entity.type,
            entity.source_type,
            label_str,
            preferred,
        ])

    def find(self, **kwargs) -> list:

        where_part = ' AND '.join(['%s=?' % x for x in kwargs.keys()])
        query = 'SELECT * FROM data WHERE ' + where_part
        query_args = list(kwargs.values())

        return list(self.conn.execute(query, query_args))

    def find_one(self, **kwargs) -> Optional[dict]:
        res = self.find(**kwargs)
        if len(res) == 0:
            return None
        return res[0]
"""

class LookupService:

    def __init__(self):
        self.indices = {
            'label-entity_type': {},
            'label-source_type': {},
        }

    def add(self, label: LanguageMap, preferred: bool, entity: Entity):
        label_str = label.nb.lower()

        key = label_str + '@' + entity.type
        self.add_to('label-entity_type', key, entity.id)

    def add_to(self, idx, key, eid):
        if key not in self.indices[idx]:
            self.indices[idx][key] = []
        self.indices[idx][key].append(eid)

    def find(self, label: str, entity_type=None, source_type=None) -> list:
        label = label.lower()
        if entity_type is not None:
            return self.indices['label-entity_type'].get(label + '@' + entity_type) or []
        if source_type is not None:
            return self.indices['label-source_type'].get(label + '@' + source_type) or []
