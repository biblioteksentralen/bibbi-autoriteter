import logging
import sys
import os
from copy import copy
import functools
import pandas as pd
import feather

log = logging.getLogger(__name__)


class DataTable:
    entity_type = None
    table_name = None
    columns = []

    # Override these
    field_code = 'X00'
    id_field = 'AuthID'

    def __init__(self):
        self.df = pd.DataFrame()

    def to_str(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return '1' if value else '0'
        return str(value)

    def trim(self, value):
        if value is None:
            return None
        value = value.strip()
        if value == '':
            value = None
        return value

    def load_from_db(self, db):

        log.info('[%s] Retrieving records from database', self.entity_type)
        with db.cursor() as cursor:
            cursor.execute('SELECT * FROM dbo.%s WHERE Approved=1 AND Bibsent_ID IS NOT NULL' % self.table_name)
            columns = []
            for column in cursor.description:
                if column[0] not in self.columns:
                    log.error('[%s] Encountered unknown column "%s" in "%s" table', self.entity_type, column[0], self.table_name)
                    sys.exit(1)
                columns.append(self.columns[column[0]])

            rows = []
            for row in cursor:
                row = [self.trim(self.to_str(c)) for c in row]
                rows.append(row)
                # break
            df = pd.DataFrame(rows, dtype='str', columns=columns)
            df = self.validate(df)
            df.set_index('bibsent_id', drop=False, inplace=True)

        self.df = df
        log.info('[%s] Loaded %d x %d table', self.entity_type, self.df.shape[0], self.df.shape[1])
        self.add_document_counts(db)
        log.info('[%s] Table extended to %d x %d', self.entity_type, self.df.shape[0], self.df.shape[1])

    def add_document_counts(self, db):
        with db.cursor() as cursor:
            field_code_map = {
                'items_as_entry': [self.field_code.replace('X', '1'), self.field_code.replace('X', '7')],
                'items_as_subject': [self.field_code.replace('X', '6')],
            }
            for key, field_codes in field_code_map.items():
                cursor.execute("""SELECT a.Bibsent_ID, COUNT(i.Item_ID) FROM %(table)s AS a
                    LEFT JOIN ItemField AS f ON f.Authority_ID = a.%(id_field)s AND f.FieldCode IN (%(field_codes)s)
                    LEFT JOIN Item AS i ON i.Item_ID = f.Item_ID AND i.ApproveDate IS NOT NULL
                    WHERE a.Approved = 1 AND a.Bibsent_ID IS NOT NULL
                    GROUP BY a.Bibsent_ID
                """ % {
                    'table': self.table_name,
                    'id_field': self.id_field,
                    'field_codes': ', '.join(["'%s'" % field_code for field_code in field_codes]),
                })
                rows = []
                for row in cursor:
                    row = [self.trim(self.to_str(c)) for c in row]
                    rows.append(row)
                    # break
                tmp_df = pd.DataFrame(rows, dtype='str', columns=['bibsent_id', key])
                tmp_df.set_index('bibsent_id', inplace=True)
                self.df = self.df.join(tmp_df)
                # Note: We cannot have NaN values in the item_column, or Pandas will convert the integer column to float
                # since int does not support NaN
                self.df[key] = pd.to_numeric(self.df[key], downcast='integer')  #.astype('int8')  # pd.to_numeric(item_count_df.item_count, downcast='integer')
                log.info('[%s] Document counts (%s): %d', self.entity_type, key, self.df[key].sum())

    def load_from_feather(self, folder):
        filename = '%s/%s.feather' % (folder, self.entity_type)
        self.df = feather.read_dataframe(filename)
        log.info('[%s] Loaded %d x %d table from cache', self.entity_type, self.df.shape[0], self.df.shape[1])

    def save_as_feather(self, folder):
        if not os.path.exists(folder):
            os.mkdir(folder)
        filename = '%s/%s.feather' % (folder, self.entity_type)
        feather.write_dataframe(self.df, filename)
        log.info('[%s] Saved %d x %d table to cache', self.entity_type, self.df.shape[0], self.df.shape[1])

    def validate(self, df):
        df.created = pd.to_datetime(df.created)
        df.modified = pd.to_datetime(df.modified)
        rows_before = df.shape[0]
        rows_after = 0
        df = df[df.apply(self.validate_row, axis=1)]
        ids = set(df.row_id.tolist())

        df_refs = df[df.ref_id.notnull()]
        refs = dict(zip(df_refs.row_id, df_refs.ref_id))
        invalid = set()
        for n in range(5):
            # If A -> B and B -> NULL, the first pass will mark B as invalid
            # and the second pass will mark A as invalid.
            # We also self-references (A -> A)
            log.info('[%s] Validating references: Pass %d', self.entity_type, n)
            n1 = len(invalid)
            for k, v in refs.items():
                if k == v or v not in ids or v in invalid:
                    invalid.add(k)
                    # del refs[k]
            n2 = len(invalid)
            if n1 == n2:
                break

        log.info('[%s] %d out of %d references were invalid', self.entity_type, len(invalid), len(refs))

        # Remove all invalid rows
        df = df[~df.row_id.isin(list(invalid))]

        rows_after = df.shape[0]
        if rows_before == rows_after:
            log.info('[%s] Validated dataframe', self.entity_type)
        else:
            log.info('[%s] Validated dataframe. Rows reduced from %d to %d', self.entity_type, rows_before, rows_after)
        return df

    def validate_row(self, row):
        # Trim all values
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
            log.error('[%s] Row failed validation: id is NULL', self.entity_type)
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
            log.error('[%s] Row %s failed validation: Title/Label is NULL', self.entity_type, row.row_id)
            return False

        return True


class TopicTable(DataTable):
    entity_type = 'topic'
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
        'Forkortelse': 'forkortelse',  # Brukt 80 ganger
    }


class GeographicTable(DataTable):
    entity_type = 'geographic'
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


class CorporationTable(DataTable):
    entity_type = 'corporation'
    table_name = 'AuthorityCorp'
    id_field = 'CorpID'
    field_code = 'X10'
    columns = {
        'CorpID': 'row_id',
        'CorpName': 'label',
        'CorpName_N': 'label_nn',  # $a Corporate name or juridiction name
        'CorpDep': 'sub_unit',  # $b Subordinate unit
        'CorpPlace': 'location',  # $c Location of meeting  (Nesten ikke i bruk)
        'CorpDate': 'date',  # $d Date of meeting or treaty signing
        'CorpFunc': 'corp_func',  # (ikke i bruk)
        'CorpNr': 'corp_nr',  # $n Number of part/section/meeting ? (ikke i bruk)
        'CorpDetail': 'detail',  # (Forklarende parentes)
        'CorpDetail_N': 'detail_nn',  #
        'SortingTitle': 'sorting_title',
        'TopicTitle': 'work_title',  # $t Title of a work? Brukt om lover og musikkalbum
        'SortingSubTitle': 'sorting_subtitle',  #
        'UnderTopic': 'sub_topic',                 # Underinndeling ($x), med –
        'UnderTopic_N': 'sub_topic_nn',
        'Qualifier': 'qualifier',  # : kvalifikator ($0 i NORMARC)
        'Qualifier_N': 'qualifier_nn',  #
        'DeweyNr': 'ddk5_nr',
        'TopicDetail': 'detail_topic',
        'TopicLang': 'topic_lang',  # (ikke i bruk, ser ut til å være generert)
        'MusicNr': 'music_nr',
        'MusicCast': 'music_cast',
        'Arrangment': 'music_arr',
        'ToneArt': 'music_key',
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
        'NB_ID': 'nb_id',             # BARE-ID
        'NB_Origin': 'nb_origin',     # 'adabas'
        'Bibsent_ID': 'bibsent_id',   # Verdi for $0
        'Felles_ID': 'felles_id',     # Felles ID når vi har både hoved- og biautoriteter
        'MainPerson': 'main_record',  # (bool) hovedautoritet eller biautoritet
        'Origin': 'origin',
        'KatStatus': 'kat_status',
        'Comment': 'comment',
        'Lov': 'law',               # Flagg (0 eller 1) som brukes for å angi at det er en lov
        'Handle_ID': 'handle_id',
    }


class PersonTable(DataTable):
    entity_type = 'person'
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
        'MusicCast': 'music_cast',
        'MusicNr': 'music_nr',
        'Arrangment': 'music_arr',
        'Toneart': 'music_key',
        'TopicTitle': 'work_title', # $t - Title of a work / Tittel for dokument som emne
        'SortingSubTitle': 'sorting_subtitle',
        'UnderTopic': 'sub_topic',                 # Underinndeling ($x), med –
        'UnderTopic_N': 'sub_topic_nn',
        'Qualifier': 'qualifier',  # : kvalifikator ($0 i NORMARC)
        'Qualifier_N': 'qualifier_nn',  #
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
    }
