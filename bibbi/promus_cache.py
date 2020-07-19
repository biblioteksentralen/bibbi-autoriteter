from __future__ import annotations

import time
import datetime
from pathlib import Path
import logging
from typing import Optional

import feather
from bibbi.promus_service import PromusTable, TopicTable

log = logging.getLogger(__name__)


class PromusCache:

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.mkdir()

    def age(self) -> Optional[datetime.timedelta]:
        cache_file = self.filename(TopicTable())
        if not cache_file.exists():
            return None
        return datetime.timedelta(seconds=time.time() - cache_file.stat().st_mtime)

    def filename(self, table: PromusTable) -> Path:
        return Path('%s/%s.feather' % (self.path, table.type))

    def extract(self, table: PromusTable):
        df = feather.read_dataframe(self.filename(table))
        df.set_index(table.index_column, drop=False, inplace=True)
        log.info('[%s] Loaded %d x %d table from cache',
                 table.type, df.shape[0], df.shape[1])
        table.df = df
        table.after_load_from_cache()
        return table

    def store(self, table: PromusTable):
        feather.write_dataframe(table.df, self.filename(table))
        log.info('[%s] Saved %d x %d table to cache',
                 table.type, table.df.shape[0], table.df.shape[1])
        return table
