from __future__ import annotations
from pathlib import Path
import logging
import feather
from bibbi.promus_service import PromusTable

log = logging.getLogger(__name__)


class PromusCache:

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.mkdir()

    def filename(self, table: PromusTable):
        return '%s/%s.feather' % (self.path, table.entity_type)

    def extract(self, table: PromusTable):
        df = feather.read_dataframe(self.filename(table))
        df.set_index(table.index_column, drop=False, inplace=True)
        log.info('[%s] Loaded %d x %d table from cache',
                 table.entity_type, df.shape[0], df.shape[1])
        table.df = df
        table.after_load_from_cache()
        return table

    def store(self, table: PromusTable):
        feather.write_dataframe(table.df, self.filename(table))
        log.info('[%s] Saved %d x %d table to cache',
                 table.entity_type, table.df.shape[0], table.df.shape[1])
        return table
