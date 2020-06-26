import sys
import logging
from typing import Optional

log = logging.getLogger(__name__)


class ReferenceMap:
    # Map of references `{from_id: to_id}` where from_id and to_id are Bibsent IDs.

    def __init__(self):
        self._map = {}

    def load(self, table):
        # Build the map
        df = table.df
        if 'ref_id' not in df.columns:
            log.info('[%s] Skipping reference map generation', table.entity_type)
            return
        bibsent_ids = dict(zip(df.row_id, df.bibsent_id))
        df2 = df[df.ref_id.notnull()]
        refs = dict(zip(df2.row_id, df2.ref_id))
        self._map.update({bibsent_ids[k]: bibsent_ids[v] for k, v in refs.items()})
        log.info('[%s] Reference map loaded: %d references', table.entity_type, len(self))

    def get(self, bibbi_id) -> Optional[str]:
        # Returns the ID that the row with ID <bibbi_id> refers to, or None if the row is not a reference
        # In case the row refers to another row which is also a reference (multiple hops), the method
        # will continue until a main entry row is found.
        if bibbi_id not in self._map:
            return None
        parts = []
        while bibbi_id in self._map:
            parts.append(bibbi_id)
            if len(parts) > 10:
                log.info('Endless loop!')
                print(parts)
                sys.exit(1)
            bibbi_id = self._map[bibbi_id]
        return bibbi_id

    def __len__(self):
        return len(self._map)
