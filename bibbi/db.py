import logging
import os
from typing import Generator, List, Union
from urllib.parse import quote_plus
from time import time

import pandas as pd
import numpy as np
import pyodbc
import sqlalchemy as sa
from sqlalchemy import Table, Column, create_engine
from sqlalchemy.sql import select


ColumnDataTypes = List[Union[str, int, None]]
log = logging.getLogger(__name__)


class Db:

    def __init__(self, **db_settings):
        if os.name == 'posix':
            connection_args = [
                'DRIVER={FreeTDS}',
                'Server=%(server)s',
                'Database=%(database)s',
                'UID=%(user)s',
                'PWD=%(password)s',
                'TDS_Version=8.0',
                'Port=%(port)s',
            ]
        else:
            connection_args = [
                'Driver={ODBC Driver 17 for SQL Server}',
                'Server=tcp:%(server)s,%(port)s',
                'Database=%(database)s',
                'UID=%(user)s',
                'PWD=%(password)s',
            ]
        log.info('Connecting to %s from %s', db_settings['server'], os.name)
        connection_string = ';'.join(connection_args) % db_settings
        self.connection: pyodbc.Connection = pyodbc.connect(connection_string)
        log.info('Connected (pyodbc)')

        params = quote_plus(connection_string)
        engine = create_engine("mssql+pyodbc:///?odbc_connect=%s" % params)
        self.alchemy = engine.connect()
        log.info('Connected (alchemy)')

    def cursor(self):
        return self.connection.cursor()

    def select_dataframe_sa(self, query: str, params: ColumnDataTypes = None,
                            date_fields: List[str] = None, dont_touch: list = None):
        date_fields = date_fields or []
        dont_touch = dont_touch or []
        params = params or []
        t0 = time()
        df = pd.read_sql_query(query,
                               self.alchemy,
                               params=params,
                               parse_dates=date_fields)

        for key in df.keys():  # columns
            ct = df[key].dtype
            if ct != np.object:
                log.info('"%s" column: %s', key, ct.type)

                if key not in dont_touch and key not in date_fields:
                    log.info('Converting "%s" column to str', key)
                    if ct == np.float64:
                        # Need to convert to int first to avoid decimal
                        df[key] = df[key].astype('int64', copy=False).astype('object', copy=False)
                    elif ct == np.int64:
                        # Need to convert to int first to avoid decimal :/
                        df[key] = df[key].astype('object', copy=False)
                    elif ct == np.bool:
                        pass

        t1 = time()
        log.info('Fetched %d rows (%d MB) in %.1f secs', df.shape[0],
                 df.memory_usage().sum() / 1024 ** 2, t1 - t0)
        return df

    def select_dataframe(self, query: str, params: ColumnDataTypes = None, **kwargs) -> pd.DataFrame:
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            columns = [column[0] for column in cursor.description]

            rows = []
            for row in cursor:
                row = [str(c) for c in row]
                rows.append(row)

        return pd.DataFrame(rows, dtype='str', columns=columns, **kwargs)

    def select(self, query: str, params: ColumnDataTypes = None, normalize: bool = False,
               date_fields: list = None, int_fields: list = None) -> Generator[dict, None, None]:
        if 'SELECT' not in query:
            raise Exception('Not a SELECT query')
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            columns = [column[0] for column in cursor.description]
            for row in cursor.fetchall():
                row = dict(zip(columns, row))
                if normalize:
                    self.normalize_row(row, date_fields=date_fields, int_fields=int_fields)
                yield row

    @staticmethod
    def normalize_row(row: dict, date_fields: List[str] = None, int_fields: List[str] = None) -> None:
        """
        In-place normalization of a row:

        - Ensures values are either strings or dates
        - Empty strings are converted to NULLs
        - Numbers are converted to strings
        - All strings are trimmed
        """
        date_fields = date_fields or []
        for k in row.keys():
            if row[k] is None:
                continue
            elif k in date_fields:
                row[k] = row[k].date() if row[k] else None
            elif k in int_fields:
                row[k] = int(row[k]) if not pd.isnull(row[k]) else None
            else:
                row[k] = str(row[k]).strip()
                if row[k] == '':
                    row[k] = None
