import os
from typing import Generator, List, Union

import pandas as pd
import pyodbc

ColumnDataTypes = List[Union[str, int, None]]


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
                'Port=1433',
            ]
        else:
            connection_args = [
                'Driver={SQL Server}',
                'Server=%(server)s',
                'Database=%(database)s',
                'Trusted_Connection=yes',
            ]
        connection_string = ';'.join(connection_args) % db_settings
        self.connection: pyodbc.Connection = pyodbc.connect(connection_string)

    def cursor(self):
        return self.connection.cursor()

    def select_dataframe(self, query: str, params: ColumnDataTypes = None, **kwargs) -> pd.DataFrame:
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            columns = [column[0] for column in cursor.description]

            rows = []
            for row in cursor:
                row = [c for c in row]
                rows.append(row)

        return pd.DataFrame(rows, dtype='str', columns=columns, **kwargs)


    def select(self, query: str, params: ColumnDataTypes = None, normalize: bool = False,
               date_fields: list = None) -> Generator[dict, None, None]:
        if 'SELECT' not in query:
            raise Exception('Not a SELECT query')
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            columns = [column[0] for column in cursor.description]
            for row in cursor.fetchall():
                row = dict(zip(columns, row))
                if normalize:
                    self.normalize_row(row, date_fields=date_fields)
                yield row

    @staticmethod
    def normalize_row(row: dict, date_fields: List[str] = None) -> None:
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
            else:
                row[k] = str(row[k]).strip()
                if row[k] == '':
                    row[k] = None
