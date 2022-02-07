from __future__ import annotations
import logging
import re
import sys
from collections import namedtuple
from dataclasses import fields
from typing import Optional, Generator, List, Dict

import pandas as pd
from rdflib import Namespace, URIRef

from bibbi.entity_service import BibbiEntity, Entity, Nation

from bibbi.label import LabelFactory

from .constants import TYPE_GEOGRAPHIC, TYPE_PERSON, TYPE_TITLE_SUBJECT, TYPE_TITLE, TYPE_PERSON_SUBJECT, \
    TYPE_CORPORATION, TYPE_LAW, TYPE_CORPORATION_SUBJECT, TYPE_DEMOGRAPHIC_GROUP, TYPE_FICTIVE_PERSON, TYPE_EVENT, \
    TYPE_EVENT_SUBJECT, TYPE_WORK
from .db import Db
from .util import trim, to_str, LanguageMap
from .references import ReferenceMap

log = logging.getLogger(__name__)


class PromusService:

    def __init__(self, connection: Db):
        self.connection = connection

    def extract(self, table: PromusTable) -> PromusTable:
        """
        Load rows for a given entity type into a DataFrame for further processing.
        Skips invalid rows and adds document counts.
        """
        log.info('[%s] Retrieving records from database', table.type)
        with self.connection.cursor() as cursor:
            cursor.execute(table.get_select_query())
            columns = []
            for column in cursor.description:
                if column[0] not in table.columns:
                    log.error('[%s] Encountered unknown column "%s" in "%s" table', table.type, column[0],
                              table.table_name)
                    sys.exit(1)
                columns.append(table.columns[column[0]])

            rows = []
            for row in cursor:
                row = [trim(to_str(c)) for c in row]
                rows.append(row)

        df = pd.DataFrame(rows, dtype='str', columns=columns)
        df.set_index(table.index_column, drop=False, inplace=True)
        log.info('[%s] Loaded %d x %d table', table.type, df.shape[0], df.shape[1])
        table.df = df
        table.after_load_from_db(self.connection)
        return table


class DataRow:
    # Wrapper around a DataFrame row that adds domain specific methods for data extraction

    def __init__(self, data: namedtuple, row_type: str, index_column: str, display_column: str):
        self.data = data
        self.type = row_type
        self.index_column = index_column
        self.display_column = display_column

    def __getattr__(self, key):
        return getattr(self.data, key)

    def __getitem__(self, key):
        return getattr(self.data, key)

    def __contains__(self, key):
        return hasattr(self.data, key)

    def __repr__(self):
        params = [
            '%s="%s"' % (k, str(v))
            for k, v in self.data._asdict().items()
            if v is not None and k not in [self.index_column, self.display_column]
        ]
        return '<DataRow type="%s" id="%s" label="%s" %s>' % (self.type,
                                                              getattr(self, self.index_column),
                                                              getattr(self, self.display_column),
                                                              ', '.join(params))

    def has(self, key):
        return key in self and not pd.isnull(getattr(self.data, key))

    def get(self, *keys) -> Optional[str]:
        # Fallback chain, get first non-null value
        for key in keys:
            try:
                value = getattr(self.data, key)
                if pd.notnull(value):
                    return value
            except AttributeError:
                pass

    def get_lang_map(self, nb: str, nn: Optional[str] = None) -> Optional[LanguageMap]:
        """
        Get a LanguageMap object for some property.

        :param nb: The property name to retrieve.
        :param nn: The Nynorsk property name. Defaults to the nb property name + '_nn'
        :return: LanguageMap or None if the property is not in use.
        """
        nn = nn or nb + '_nn'
        if not self.has(nb):
            return None
        return LanguageMap(nb=self.get(nb), nn=self.get(nn, nb))

    def is_main_entry(self):
        if self.get('qualifier') or self.get('sub_topic'):
            return False
        if self.get('sub_geo') and self.type != TYPE_GEOGRAPHIC:
            return False
        return True

    def get_subdivisions(self, subdiv_type: str):
        """
        Generates list of individual subdivisions as language maps.

        Args:
            subdiv_type (str): A valid subdivision type ('sub_topic', 'sub_geo' or 'sub_unit')
        """
        if subdiv_type not in ['sub_geo', 'sub_topic', 'sub_unit']:
            raise ValueError('Invalid subdivision type: %s', subdiv_type)
        if not self.has(subdiv_type):
            return
        nb_parts = re.split(r' - |\$z|\$x', self.get(subdiv_type))
        nn_parts = []
        if self.has(subdiv_type + '_nn'):
            nn_parts = re.split(r' - |\$z|\$x', self.get(subdiv_type + '_nn'))
        for k, part in enumerate(nb_parts):
            if len(nb_parts) == len(nn_parts):
                yield LanguageMap(nb=part, nn=nn_parts[k])
            else:
                if len(nn_parts) != 0:
                    log.warning('Number of "%s" subdivisions differs for %s: "%s"@nb != "%s"@nn',
                                subdiv_type,
                                self.data.bibsent_id,
                                # self.get('label'),
                                ' - '.join(nb_parts),
                                # self.get('label_nn') or self.get('label'),
                                ' - '.join(nn_parts))
                yield LanguageMap(nb=part, nn=part)  # fallback to nb for nn

    def get_qualifier(self):
        return LanguageMap(nb=self.data.qualifier, nn=self.data.qualifier_nn)


class PromusTable:
    vocabulary_code = None
    namespace = Namespace('#')
    entity_class = Entity
    type: str = None
    table_name: str = None
    columns: dict = {}

    # Override these
    field_code = 'X00'
    id_field = 'AuthID'

    # Optionally, override these
    index_column = 'bibsent_id'
    display_column = 'display_value'

    def __init__(self, df: Optional[pd.DataFrame] = None):
        self.df = df or pd.DataFrame()

    def get_select_query(self) -> str:
        return 'SELECT * FROM dbo.%s' % self.table_name

    def after_load_from_db(self, db):
        return self

    def after_load_from_cache(self):
        return self

    @classmethod
    def make_row(cls, values: namedtuple) -> DataRow:
        return DataRow(values, cls.type, cls.index_column, cls.display_column)

    def get_row(self, row_id: str) -> DataRow:
        return self.make_row(self.df.loc[str(row_id)])

    def rows(self) -> Generator[DataRow]:
        """
        DataRow generator
        """
        for row in self.df.itertuples():  # Note: itertuples is *much* faster than iterrows! Cut loading time from 28s to 4s
            yield self.make_row(row)

    def search(self, value: str) -> Generator[DataRow]:
        results = self.df[self.df.apply(lambda row: row.str.contains(value, case=False).any(), axis=1)]
        for res in results.itertuples():
            yield self.make_row(res)

    def get_entity_id(self, row) -> str:
        return row[self.index_column]

    def make_entities(self):
        for row in self.rows():
            kwargs = {
                'id': self.get_entity_id(row),
                'local_id': row['row_id'],
                'row': row,
                'namespace': self.namespace,
                'type': row.type,
                'source_type': row.type,
                'pref_label': LanguageMap(nb=row.label, nn=row.label),
                'alt_labels': [],
            }
            for field in fields(self.entity_class):
                if field.name == 'approved' and field.name not in row:
                    # Auto-approve form/genre terms that lack the 'approved' field
                    kwargs['approved'] = '1'
                elif field.name not in kwargs and field.name in row and pd.notnull(row[field.name]):
                    kwargs[field.name] = row[field.name]

            yield self.entity_class(**kwargs)


class PromusAuthorityTable(PromusTable):
    vocabulary_code = 'bibbi'
    namespace = Namespace('https://id.bs.no/bibbi/')
    entity_class = BibbiEntity

    def __init__(self, df: Optional[pd.DataFrame] = None):
        super(PromusAuthorityTable, self).__init__(df)
        self.references = ReferenceMap()

    def get_select_query(self) -> str:
        return 'SELECT * FROM dbo.%s WHERE NotInUse=0 AND Bibsent_ID IS NOT NULL' % self.table_name

    def get_item_count_query(self, field_codes: list) -> str:
        return """SELECT a.Bibsent_ID, COUNT(i.Item_ID) FROM %(table)s AS a
            LEFT JOIN ItemField AS f ON f.Authority_ID = a.%(id_field)s AND f.FieldCode IN (%(field_codes)s)
            LEFT JOIN Item AS i ON i.Item_ID = f.Item_ID AND i.CurrentStatus = 1
            WHERE a.NotInUse = 0 AND a.Bibsent_ID IS NOT NULL
            GROUP BY a.Bibsent_ID
        """ % {
            'table': self.table_name,
            'id_field': self.id_field,
            'field_codes': ', '.join(["'%s'" % field_code for field_code in field_codes]),
        }

    def add_document_counts(self, db):
        with db.cursor() as cursor:
            field_code_map = {
                'items_as_entry': [self.field_code.replace('X', '1'), self.field_code.replace('X', '7')],
                'items_as_subject': [self.field_code.replace('X', '6')],
            }
            for key, field_codes in field_code_map.items():
                query = self.get_item_count_query(field_codes)
                log.debug(query)
                cursor.execute(query)
                rows = []
                for row in cursor:
                    row = [trim(to_str(c)) for c in row]
                    rows.append(row)
                    # break
                tmp_df = pd.DataFrame(rows, dtype='str', columns=['bibsent_id', key])
                tmp_df.set_index('bibsent_id', inplace=True)
                self.df = self.df.join(tmp_df)
                # Note: We cannot have NaN values in the item_column, or Pandas will convert the integer column to float
                # since int does not support NaN
                self.df[key] = pd.to_numeric(self.df[key], downcast='integer')  #.astype('int8')  # pd.to_numeric(item_count_df.item_count, downcast='integer')
                log.info('[%s] Document counts (%s): %d', self.type, key, self.df[key].sum())

    def after_load_from_db(self, db):
        """
        Do some initial normalization of the data.
        """
        self.df.created = pd.to_datetime(self.df.created)
        self.df.modified = pd.to_datetime(self.df.modified)
        self.df = self.df[self.df.apply(self.normalize_row, axis=1)]

        self.add_document_counts(db)
        log.info('[%s] Table extended to %d x %d', self.type, self.df.shape[0], self.df.shape[1])
        print(self.df.dtypes)

        self.validate_references()
        self.references.load(self)
        return self

    def after_load_from_cache(self):
        self.references.load(self)

    def validate_references(self):
        """
        Validate references and remove rows containing invalid ones.
        """
        ids = set(self.df.row_id.tolist())
        df_refs = self.df[self.df.ref_id.notnull()]
        refs = dict(zip(df_refs.row_id, df_refs.ref_id))
        invalid = set()
        for n in range(5):
            # If A -> B and B -> NULL, the first pass will mark B as invalid
            # and the second pass will mark A as invalid.
            # We also mark self-references (A -> A)
            log.info('[%s] Validating references: Pass %d', self.type, n + 1)
            n1 = len(invalid)
            for k, v in refs.items():
                if k == v or v not in ids or v in invalid:
                    invalid.add(k)
                    # del refs[k]
            n2 = len(invalid)
            if n1 == n2:
                break

        log.info('[%s] %d out of %d references were invalid', self.type, len(invalid), len(refs))

        # Remove all invalid rows
        rows_before = self.df.shape[0]
        self.df = self.df[~self.df.row_id.isin(list(invalid))]
        rows_after = self.df.shape[0]
        if rows_before == rows_after:
            log.info('[%s] Validated dataframe', self.type)
        else:
            log.info('[%s] Validated dataframe. Rows reduced from %d to %d', self.type, rows_before, rows_after)

    def normalize_row(self, row):
        """
        Validate and trim all values.
        """
        for key, value in row.items():
            if pd.notnull(value) and isinstance(value, str) and value.strip() != value:
                log.debug('Trimming cell value %s="%s"', key, value)
                row[key] = value.strip()
            if pd.notnull(value) and isinstance(value, str) and value.replace('  ', ' ') != value:
                log.debug('Trimming double spacing from %s="%s"', key, value)
                row[key] = value.replace('  ', ' ')
            if row[key] == '':
                row[key] = None

        if pd.isnull(row.row_id):
            log.error('[%s] Row failed validation: id is NULL', self.type)
            return False

        # if pd.notnull(row.referenceId) and pd.notnull(row.webDeweyNr):
        #    log.warning('Row %s: Both WebDeweyNr and ReferenceId are non-NULL', row.row_id)

        # if pd.notnull(row.referenceId) and pd.notnull(row.deweyNr):
        #    log.warning('Row %s: Both DeweyNr and ReferenceId are non-NULL', row.row_id)

        # if pd.isnull(row.BibbiNr) and pd.isnull(row.ReferenceId):
        # Det ser ut som godkjente emneord, som f.eks. "3D-printing" mangler BibbiNr.
        # Hva betyr det at noe har BibbiNr eller ikke har det?
        # log.warning('Row %s: Both BibbiNr and ReferenceId are NULL', row.Id)
        # return False
        if pd.isnull(row.label):
            log.error('[%s] Row %s failed validation: Title/Label is NULL', self.type, row.row_id)
            return False

        # Validate
        if row.get('webdewey_approved') == '1' and row.webdewey_nr is not None and not re.match(r'^[0-9]{3}(/\.[0-9]+|\.[0-9]+(/?[0-9]+)?)?$', row.webdewey_nr):
            log.warning('Invalid approved WebDewey number [%s | %s | %s]\t"%s"',
                        self.type,
                        row.bibsent_id,
                        row.display_value,
                        row.webdewey_nr)

        return True

    def refers_to(self, row: DataRow) -> Optional[str]:
        return self.references.get(row.bibsent_id)

    def fast_search(self, value: str) -> Generator[DataRow]:

        search_fields = ['label', 'sub_topic', 'sub_geo', 'sub_unit', 'qualifier', 'detail']
        search_fields = [x for x in search_fields if x in self.columns.values()]

        query = ' | '.join(['(%s == "%s")' % (field, value) for field in search_fields])

        results = self.df.query(query)

        for res in results.itertuples():
            yield self.make_row(res)

    def _group_references(self) -> Dict[str, List[DataRow]]:
        """
        Group main entries and all references to each entry together, using a single for loop.
        Returns the following structure:
        {
            "bibbi_id for main row": [main row, reference row 1, reference row 2, ...]
        }
        """
        out = {}

        for row in self.rows():
            bibbi_id = self.refers_to(row)
            if bibbi_id is not None:
                if bibbi_id not in out:
                    out[bibbi_id] = [None, row]
                else:
                    out[bibbi_id] += [row]
            else:
                bibbi_id = self.get_entity_id(row)
                if bibbi_id not in out:
                    out[bibbi_id] = [row]
                else:
                    out[bibbi_id][0] = row

        return out

    def make_entity(self, label_factory: LabelFactory, main_row: DataRow, reference_rows: List[DataRow]) -> Optional[Entity]:
        entity_id = main_row[self.index_column]
        pref_label = label_factory.make(main_row)
        alt_labels = [label_factory.make(value) for value in reference_rows]

        if pref_label is None:
            log.error('Preferred label is empty for Bibbi ID: %s', entity_id)
            return

        kwargs = {
            'id': entity_id,
            'local_id': main_row.row_id,
            'namespace': self.namespace,
            'row': main_row,
            'type': main_row.type,
            'complex': False,
            'source_type': main_row.type,
            'pref_label': pref_label,
            'alt_labels': alt_labels,
        }

        if not main_row.is_main_entry():
            kwargs['complex'] = True

        if main_row.has('bs_nasj_id'):
            kwargs['type'] = TYPE_DEMOGRAPHIC_GROUP

        if main_row.get('detail') == 'fiktiv person':
            kwargs['type'] = TYPE_FICTIVE_PERSON

        if main_row.has('date'):
            kwargs['date'] = main_row.get('date')

        # Simplify work title by joining together $t $i $p
        work_title = ' : '.join([
            main_row.get(x) for x in [
                'work_title',
                'music_scoring',
                'music_nr',
                'music_arr',
                'work_title_part',
            ] if main_row.has(x)
        ])
        kwargs['work_title'] = work_title if work_title != '' else None

        if main_row.type == TYPE_WORK:
            kwargs['work_title'] = main_row.label

        if main_row.has('felles_id') and main_row.get('felles_id') == main_row.get('bibsent_id'):
            # Hovedautoriteter
            if main_row.type == TYPE_PERSON:
                person_name = main_row.label
                if ', ' in person_name:
                    m = re.match(r'^([^,]+), (.*)$', person_name)
                    if m:
                        person_name = f'{m.group(2)} {m.group(1)}'
                kwargs['name'] = LanguageMap(nb=person_name, nn=person_name)
            elif main_row.type == TYPE_CORPORATION:
                kwargs['name'] = LanguageMap(nb=main_row.label, nn=main_row.label_nn)

        if main_row.has('felles_id') and main_row.get('felles_id') != main_row.get('bibsent_id'):
            # Biautoriteter

            if main_row.type == TYPE_PERSON:
                if main_row.has('work_title') or main_row.has('work_title_part'):
                    if main_row.get('webdewey_nr') or main_row.get('ddk5_nr'):
                        kwargs['type'] = TYPE_TITLE_SUBJECT
                    else:
                        kwargs['type'] = TYPE_TITLE
                else:
                    kwargs['type'] = TYPE_PERSON_SUBJECT

            elif main_row.type == TYPE_CORPORATION:
                if main_row.has('work_title'):
                    if main_row.law == '1':
                        kwargs['type'] = TYPE_LAW
                        kwargs['legislation'] = LanguageMap(nb=main_row.label, nn=main_row.label_nn)
                        # OBS: Alle lovene har samme Felles_ID ! De er altså alle biautoriteter uten en hovedautoritet
                    #else:
                    #    kwargs['type'] = TYPE_LAW or TYPE_MUSICALBUM or other?
                else:
                    kwargs['type'] = TYPE_CORPORATION_SUBJECT

            elif main_row.type == TYPE_EVENT:
                kwargs['type'] = TYPE_EVENT_SUBJECT

        for field in fields(self.entity_class):
            if field.name not in kwargs:
                if field.name in main_row and pd.notnull(main_row[field.name]):
                    kwargs[field.name] = main_row[field.name]
                # elif field.default is MISSING and field.default_factory is MISSING:
                #     kwargs[field.name] = None
        return self.entity_class(**kwargs)

    def make_entities(self):
        label_factory = LabelFactory()
        grouped_rows = self._group_references()
        for entity_id, row_group in grouped_rows.items():
            if row_group[0] is None:
                log.warning('Ignoring entity without pref label: %s', entity_id)
                continue
            entity = self.make_entity(label_factory, row_group[0], row_group[1:])
            if entity is not None:
                yield entity


class TopicTable(PromusAuthorityTable):
    type = 'topical'
    table_name = 'AuthorityTopic'
    id_field = 'AuthID'
    field_code = 'X50'
    columns = {
        'AuthID': 'row_id',  # Lokal id for denne tabellen
        'Title': 'label',  # Emne ($a), 13439 unike verdier
        'Title_N': 'label_nn',  #
        'CorpDetail': 'detail',  # (Forklarende tilføyelse i parentes, $q), f.eks. 'dokumentarfilm', 139 unike
        'CorpDetail_N': 'detail_nn',  #
        'SortingTitle': 'sorting_title',  # Sorteringstittel ($w)
        'UnderTopic': 'sub_topic',  # - Underavdeling ($x), 1504 unike
        'Qualifier': 'qualifier',  # : kvalifikator ($0), 958 unike
        'Qualifier_N': 'qualifier_nn',  #
        'DeweyNr': 'ddk5_nr',  # Tilsvarende klassenummer ($1). Alltid DDK5?
        'TopicDetail': 'detail_topic',  # (ikke i bruk)
        'TopicLang': 'topic_lang',  # ('ikke i bruk', brukt på 22 rader)
        'FieldCode': 'field_code',  # 650 (27347 stk.), 950 (14 stk.)
        'Security_ID': 'security_id',  # (bool)
        'UserID': 'userId',  # (ikke i bruk?)
        'LastChanged': 'modified',  # (datetime)
        'Created': 'created',  # (datetime)
        'Approved': 'approved',  # (bool)
        'ApproveDate': 'approve_date',  # (datetime)
        'ApprovedUserID': 'approved_by',  # NULL eller 1
        'Reference': 'ref',  # hvorvidt noe er en henvisning, muligens ikke i bruk
        'ReferenceNr': 'ref_id',  # AuthId henvisningen peker til
        '_DisplayValue': 'display_value',  # (computed)
        'BibbiNr': 'bibbi_nr',  # (ikke i bruk)
        'NotInUse': 'not_in_use',  # (ikke i bruk)
        'Source': 'source',  # ('ikke i bruk': BS, NULL eller 1)
        'BibbiReferenceNr': 'bibbi_ref',  # Bibbinummer henvisningen går til? Ikke alltid fylt ut!
        'GeoUnderTopic': 'sub_geo',  # - Geografisk underinndeling ($z), 879 unike
        'GeoUnderTopic_N': 'sub_geo_nn',  # 280 unike
        'UnderTopic_N': 'sub_topic_nn',  #
        'WebDeweyNr': 'webdewey_nr',  # WebDewey
        'WebDeweyApproved': 'webdewey_approved',
        'BS_Fortsettelser_Fjern': 'bsFortsettelserFjern',
        'BS_Fortsettelser_Serietittel': 'bsFortsettelserSerietittel',
        'BS_Fortsettelser_Kommentar': 'bsFortsettelserKommentar',
        'WebDeweyKun': 'webDeweyKun',
        'Bibsent_ID': 'bibsent_id',  # Identifikator for bruk i $0
        'Comment': 'comment',  # Intern note, bare brukt 4 ganger
        'Forkortelse': 'bs_nasj_id',  # Brukes kun for nasjonaliteter (I bruk på 80 rader).
                                      # Fungerer som nøkkel for å koble med EnumCountries.CountryShortName
    }

    def get_nationality_map(self) -> Dict[str, str]:
        return {
            row.bs_nasj_id: str(row.bibsent_id)
            for row in self.df[self.df.bs_nasj_id.notnull()].itertuples()
        }


class GeographicTable(PromusAuthorityTable):
    type = 'geographic'
    table_name = 'AuthorityGeographic'
    id_field = 'TopicID'
    field_code = 'X51'
    columns = {
        'TopicID': 'row_id',                         # Lokal ID for tabellen
        'GeoName': 'label',                      # Emne ($a), 13439 unike verdier
        'GeoName_N': 'label_nn',                   #
        'GeoDetail': 'detail',                     # Forklarende tilføyelse i parentes, tilsv. kvalifikator
        'GeoDetail_N': 'detail_nn',                  #
        'UnderTopic': 'sub_topic',                 # Underinndeling ($x), med –, 3180 unike, ser ut som det er mye form/sjanger (Historie, Reisehåndbøker, ...)
        'GeoUnderTopic': 'sub_geo',              # Geografisk underinndeling ($z), 1315 unike, ofte administrative underinndelinger.
        'Qualifier': 'qualifier',                  # Kun brukt på 41 autoriteter
        'Qualifier_N': 'qualifier_nn',               #
        'DeweyNr': 'ddk5_nr',                    # Alltid DDK5?
        'TopicLang': 'topic_lang',                  #
        'FieldCode': 'field_code',                  # 650 (27347 stk.), 950 (14 stk.)
        'Security_ID': 'security_id',                 # (bool)
        'UserID': 'user_id',                     # (ikke i bruk?)
        'LastChanged': 'modified',                # (datetime)
        'Created': 'created',                    # (datetime)
        'Approved': 'approved',                   # (bool)
        'ApprovedDate': 'approve_date',                # (datetime)
        'ApprovedUserID': 'approved_by',             # NULL eller 1
        'Reference': 'ref',                  # hvorvidt noe er en henvisning, muligens ikke i bruk
        'ReferenceNr': 'ref_id',                # AuthId henvisningen peker til
        '_DisplayValue': 'display_value',               # (computed)
        'BibbiNr': 'bibbi_nr',                    # (ukjent, ikke bruk)
        'NotInUse': 'not_in_use',                   # (ikke i bruk)
        'Source': 'source',                     # ('ikke i bruk': BS, NULL eller 1)
        'BibbiReferenceNr': 'bibbi_ref',           # Bibbinummer henvisningen går til?
        'UnderTopic_N': 'sub_topic_nn',              #
        'GeoUnderTopic_N': 'sub_geo_nn',           #
        'SortingTitle': 'sorting_title',               # Sorteringstittel
        'WebDeweyNr': 'webdewey_nr',                 # WebDewey
        'WebDeweyApproved': 'webdewey_approved',
        'WebDeweyKun': 'webdewey_kun',
        'Bibsent_ID': 'bibsent_id',                  # Globalt unik autoritets-ID for Biblioteksentralen ($0)
        'Comment': 'comment',                    # Intern note, omtrent ikke i bruk
    }


class GenreTable(PromusAuthorityTable):
    type = 'genre'
    table_name = 'AuthorityGenre'
    id_field = 'TopicID'
    field_code = 'X55'
    columns = {
        'TopicID': 'row_id',  # Lokal id for denne tabellen
        'Title': 'label',  # Emne ($a), 13439 unike verdier
        'Title_N': 'label_nn',  #
        'GeoUnderTopic': 'sub_geo',  # - Geografisk underinndeling ($z), 879 unike
        'GeoUnderTopic_N': 'sub_geo_nn',  # 280 unike
        'TopicLang': 'topic_lang',  # ('ikke i bruk'?)
        'FieldCode': 'field_code',  # 655
        'Security_ID': 'security_id',  # (bool)
        'UserID': 'userId',  # (ikke i bruk?)
        'LastChanged': 'modified',  # (datetime)
        'Created': 'created',  # (datetime)
        'ApproveDate': 'approve_date',  # (ikke brukt)
        'ApprovedUserID': 'approved_by',  # (ikke brukt)
        'Reference': 'ref',  # hvorvidt noe er en henvisning, muligens ikke i bruk
        'ReferenceNr': 'ref_id',  # TopicID henvisningen peker til
        '_DisplayValue': 'display_value',  # (computed)
        'BibbiNr': 'bibbi_nr',  # (ikke i bruk)
        'NotInUse': 'not_in_use',  # (ikke i bruk)
        'Source': 'source',  # (ikke i bruk)
        'Bibsent_ID': 'bibsent_id',  # Identifikator for bruk i $0
        'Comment': 'comment',  # Intern note, ikke i bruk
        'URI': 'external_uri',  # NTSF
        'ConceptGroup': 'concept_group',  # film/spill
        'Approved': 'approved',  # (bool)
    }


class CorporationTable(PromusAuthorityTable):
    type = 'corporation'
    table_name = 'AuthorityCorp'
    id_field = 'CorpID'
    field_code = 'X10'
    columns = {
        'CorpID': 'row_id',
        'CorpName': 'label',
        'CorpName_N': 'label_nn',  # $a Corporate name or juridiction name
        'CorpDep': 'sub_unit',  # $b Subordinate unit
        'CorpPlace': 'event_location',  # $c Location of meeting  (Nesten ikke i bruk)
        'CorpDate': 'event_date',  # $d Date of meeting or treaty signing
        'CorpFunc': 'corp_func',  # (ikke i bruk)
        'CorpNr': 'event_no',  # $n Number of part/section/meeting ? (ikke i bruk)
        'CorpDetail': 'detail',  # (Forklarende parentes)
        'CorpDetail_N': 'detail_nn',  #
        'SortingTitle': 'sorting_title',
        'SortingSubTitle': 'sorting_subtitle',  #
        'UnderTopic': 'sub_topic',                 # Underinndeling ($x), med –
        'UnderTopic_N': 'sub_topic_nn',
        'Qualifier': 'qualifier',  # : kvalifikator ($0 i NORMARC)
        'Qualifier_N': 'qualifier_nn',  #
        'DeweyNr': 'ddk5_nr',
        'TopicDetail': 'detail_topic',
        'TopicLang': 'topic_lang',  # (ikke i bruk, ser ut til å være generert)

        # Work title components
        'TopicTitle': 'work_title',  # $t - Title of a work / Tittel for dokument som emne
        'MusicCast': 'music_scoring',  # $m Besetning / "Medium of performance for music"
        'MusicNr': 'music_nr',  # $i f.eks. "op 150, nr. 2"
        'Arrangment': 'music_arr',  # $o "Arranged statement for music"
        'ToneArt': 'music_key',  # $r - "Key for music"

        'FieldCode': 'field_code',
        'Security_ID': 'security_id',
        'UserID': 'userid',
        'LastChanged': 'modified',
        'Created': 'created',
        'Approved': 'approved',
        'ApproveDate': 'approve_date',
        'ApprovedUserID': 'approved_by',
        'BibbiNr': 'bibbi_nr',
        'NotInUse': 'not_in_use',
        'Reference': 'ref',
        'ReferenceNr': 'ref_id',
        'Source': 'source',
        'bibbireferencenr': 'bibi_ref_nr',
        '_DisplayValue': 'display_value',
        'GeoUnderTopic': 'sub_geo',
        'GeoUnderTopic_N': 'sub_geo_nn',
        'WebDeweyNr': 'webdewey_nr',
        'WebDeweyApproved': 'webdewey_approved',
        'WebDeweyKun': 'webdewey_kun',
        'NB_ID': 'noraf_id',          # BARE-ID
        'NB_Origin': 'nb_origin',     # 'adabas'
        'Bibsent_ID': 'bibsent_id',   # Verdi for $0
        'Felles_ID': 'felles_id',     # Felles ID når vi har både hoved- og biautoriteter
        'MainPerson': 'main_record',  # (bool) hovedautoritet eller biautoritet
        'Origin': 'origin',
        'KatStatus': 'kat_status',
        'Comment': 'comment',
        'Lov': 'law',               # Flagg (0 eller 1) som brukes for å angi at det er en lov
        'Handle_ID': 'handle_id',
        'CorpType': 'corp_type',   # ?
    }


class PersonTable(PromusAuthorityTable):
    type = 'person'
    table_name = 'AuthorityPerson'
    id_field = 'PersonId'
    field_code = 'X00'
    columns = {
        'PersonId': 'row_id',
        'PersonName': 'label', # $a Personal name
        'PersonNr': 'numeration',  # $b Numeration
        'PersonTitle': 'title',  # $c Titles and other words associated with a name
        'PersonTitle_N': 'title_nn', #
        'PersonYear': 'date',  # $d Dates associated with name
        'PersonNation': 'nationality',
        'SortingTitle': 'sorting_title',
        'SortingSubTitle': 'sorting_subtitle',
        'UnderTopic': 'sub_topic',                 # Underinndeling ($x), med –
        'UnderTopic_N': 'sub_topic_nn',
        'Qualifier': 'qualifier',  # : kvalifikator ($0 i NORMARC)
        'Qualifier_N': 'qualifier_nn',  #

        # Work title components
        'TopicTitle': 'work_title', # $t - Title of a work / Tittel for dokument som emne
        'MusicCast': 'music_scoring',  # $m Besetning / "Medium of performance for music"
        'MusicNr': 'music_nr',  # $i f.eks. "op 150, nr. 2"
        'Arrangment': 'music_arr',  # $o "Arranged statement for music"
        'Toneart': 'music_key',  # $r - "Key for music"
        'UnderMainText': 'work_title_part',  # $p Name of part/section of a work / Tittel for del av verk
        'LanguageText': 'work_lang',  # $l Language of a work

        'DeweyNr': 'ddk5_nr',
        'TopicLang': 'topic_lang',  # (ikke i bruk, ser ut til å være generert)
        'IssnNr': 'issn_nr',  # Why?? Ikke i bruk
        'FieldCode': 'field_code',
        'Security_ID': 'security_id',
        'UserID': 'userid',
        'LastChanged': 'modified',
        'Created': 'created',
        'Approved': 'approved',
        'ApproveDate': 'approve_date',
        'ApprovedUserID': 'approved_by',
        '_DisplayValue': 'display_value',
        'BibbiNr': 'bibbi_nr',
        'NotInUse': 'not_in_use',
        'Reference': 'ref',
        'ReferenceNr': 'ref_id',
        'Source': 'source',
        'bibbireferencenr': 'bibi_ref_nr',

        'PersonForm': 'person_form',
        'NotNovelette': 'not_novelette',

        'WebDeweyNr': 'webdewey_nr',
        'WebDeweyApproved': 'webdewey_approved',
        'WebDeweyKun': 'webdewey_kun',
        'Bibsent_ID': 'bibsent_id',   # Verdi for $0
        'Felles_ID': 'felles_id',     # Felles ID når vi har både hoved- og biautoriteter

        'NB_ID': 'noraf_id',             # BARE-ID
        'NB_PersonNation': 'nb_person_nation',
        'NB_Origin': 'nb_origin',     # 'adabas'

        'MainPerson': 'main_record',  # (bool) hovedautoritet eller biautoritet
        'Comment': 'comment',

        'Origin': 'origin',
        'KatStatus': 'kat_status',
        'Gender': 'gender',
        'Handle_ID': 'handle_id',
        'Nametype': 'name_type',   # ?

        'KlasseSpraak_Tid': 'klassespraak_tid',  # Ny oktober 2020
        'KlasseSpraak_Tid_Approved': 'klassespraak_tid_approved',  # Ny oktober 2020
        'KlasseTid': 'klasse_tid', # Ny nov 2020
        'KlasseComic': 'klasse_comic', # Ny nov 2020
    }


class ConferenceTable(PromusAuthorityTable):
    type = 'event'
    table_name = 'AuthorityConf'
    id_field = 'ConfID'
    field_code = 'X11'
    columns = {
        'ConfID': 'row_id',
        'ConfName': 'label',
        'ConfName_N': 'label_nn',  #
        'ConfPlace': 'event_location',  # $c Location of meeting
        'ConfDate': 'event_date',  # $d Date of meeting or treaty signing
        'ConfNr': 'event_no',  # $n Number of part/section/meeting ?
        'ConfDetail': 'detail',  # (Forklarende parentes)
        'SortingTitle': 'sorting_title',
        'TopicTitle': 'work_title',  # $t - Title of a work / Tittel for dokument som emne
        'SortingSubTitle': 'sorting_subtitle',  #
        'UnderTopic': 'sub_topic',  # Underinndeling ($x), med –
        'UnderTopic_N': 'sub_topic_nn',
        'Qualifier': 'qualifier',  # : kvalifikator ($0 i NORMARC)
        'DeweyNr': 'ddk5_nr',
        'TopicDetail': 'detail_topic',
        'TopicLang': 'topic_lang',  # (ikke i bruk, ser ut til å være generert)
        'FieldCode': 'field_code',
        'Security_ID': 'security_id',
        'UserID': 'userid',
        'LastChanged': 'modified',
        'Created': 'created',
        'Approved': 'approved',
        'ApproveDate': 'approve_date',
        'ApprovedUserID': 'approved_by',
        'BibbiNr': 'bibbi_nr',
        'NotInUse': 'not_in_use',
        'Reference': 'ref',
        'ReferenceNr': 'ref_id',
        'Source': 'source',
        'bibbireferencenr': 'bibi_ref_nr',
        'WebDeweyNr': 'webdewey_nr',
        'WebDeweyApproved': 'webdewey_approved',
        'WebDeweyKun': 'webdewey_kun',
        'NB_ID': 'noraf_id',  # BARE-ID
        'NB_Origin': 'nb_origin',  # 'adabas'
        'Bibsent_ID': 'bibsent_id',  # Verdi for $0
        'Felles_ID': 'felles_id',  # Felles ID når vi har både hoved- og biautoriteter
        'MainPerson': 'main_record',  # (bool) hovedautoritet eller biautoritet
        'Origin': 'origin',
        'KatStatus': 'kat_status',
        'Comment': 'comment',
        'Handle_ID': 'handle_id',
        '_DisplayValue': 'display_value',
        'ConfType': 'conf_type',   # ?

        # 'ConfDetail_N': 'detail_nn',  #
        # 'Qualifier_N': 'qualifier_nn',  #
        # 'ConfFunc': 'corp_func',  # (ikke i bruk)

        # Work title components
        # 'MusicCast': 'music_scoring',  # $m Besetning / "Medium of performance for music"
        # 'MusicNr': 'music_nr',  # $i f.eks. "op 150, nr. 2"
        # 'Arrangment': 'music_arr',  # $o "Arranged statement for music"
        # 'ToneArt': 'music_key',  # $r - "Key for music"

        # 'GeoUnderTopic': 'sub_geo',
        # 'GeoUnderTopic_N': 'sub_geo_nn',
        # 'Lov': 'law',               # Flagg (0 eller 1) som brukes for å angi at det er en lov
    }


class NationTable(PromusTable):
    vocabulary_code = 'bs-nasj'  # @deprecated
    namespace = Namespace('https://id.bs.no/bs-nasj/')  # @deprecated
    entity_class = Nation
    type = 'nation'
    table_name = 'EnumCountries'
    id_field = 'CountryID'
    index_column = 'abbreviation'
    display_column = 'label'

    columns = {
        'CountryID': 'row_id',
        'CountryName': 'demonym',
        'CountryShortName': 'abbreviation',
        'CountryName2': 'label',  # Note: Only filled for countries
        'CountryDescription': 'description',
        'ISO_3166_Alpha_2': 'iso3166_2_code',
        'ISO_3166_Alpha_3': 'iso3166_3_code',
        'ISO_3166_Numeric': 'iso3166_numeric',
        'Marc21_Name': 'marc21_code',
        'NotInUse': 'not_in_use',
        'BSSpecific': 'bs_specific',  # not in use
        'AuthorityGeographic_ID': 'geographic_concept_id',
        '_AuthorityGeographicDisplay': 'geographic_concept_label',
    }

    def get_select_query(self) -> str:
        return 'SELECT * FROM dbo.%s WHERE NotInUse=0' % self.table_name

    def get_entity_id(self, row):
        return row[self.index_column]


class WorkTable(PromusAuthorityTable):
    type = 'work'
    table_name = 'AuthorityWork'
    id_field = 'WorkID'
    field_code = '101'
    columns = {
        'WorkID': 'row_id',  # lokal id
        'TitlePreferred': 'label',
        'Verk_ID_temp': 'tmp',  # internt
        'PersonID': 'creator_id',  # lokal ID fra AuthorityPerson, må konverteres til URI
        'PersonName': 'creator_name',
        'FirstLanguage': 'original_language',
        'FirstYear': 'original_year',
        'Bibsent_ID': 'bibsent_id',  # verdi for $0
        'NB_ID': 'noraf_id',   # (ikke i bruk)
        'Antall': 'antall',   # (ikke i bruk)
        'ReferenceNr': 'ref_id',   # (ikke i bruk)
        '_DisplayValue': 'display_value',
        'Verksaar_260': 'work_year_260',
        'Verksaar_503': 'work_year_503',
        'Verksaar_NB': 'work_year_nb',
        'Temp': 'tmp2',
        'NotInUse': 'not_in_use',  # (ikke i bruk)
        'Approved': 'approved',
        'AutomaticApproved': 'automatic_approved',
        'LastChanged': 'modified',  # (datetime)
        'Created': 'created',  # (datetime)
        'SortingIndicator': 'sorting_indicator',
        'Number_PartOfWork': 'number_partofwork',
        'Title_PartOfWork': 'title_partofwork',
        'WorkID_NB': 'workid_nb',
        'WorkID_Deichman': 'workid_deichman',
    }
