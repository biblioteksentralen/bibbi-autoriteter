from __future__ import annotations

from typing import Optional, Iterator, Dict, TYPE_CHECKING
import logging

import pandas as pd
from rdflib import URIRef, Namespace

from .constants import TYPE_CORPORATION, TYPE_LAW, TYPE_COMPLEX, TYPE_PERSON, TYPE_CORPORATION_SUBJECT, \
    TYPE_PERSON_SUBJECT, TYPE_TITLE, TYPE_TITLE_SUBJECT
from .label import LabelFactory
from .promus_service import DataRow, LanguageMap, NationalityTable, PromusTable, PromusAuthorityTable

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bibbi.util import LanguageMap


class EntityIndex:

    def __init__(self):
        self.indices = {
            'label+entity_type': {},
            'label+source_type': {},
        }

    def add(self, label: LanguageMap, preferred: bool, entity: Entity):
        label_str = label.nb.lower()
        key = label_str + '@' + entity.type
        self.add_to('label+entity_type', key, entity.id)

    def add_to(self, idx, key, eid):
        if key not in self.indices[idx]:
            self.indices[idx][key] = []
        self.indices[idx][key].append(eid)

    def find(self, label: str, entity_type=None, source_type=None) -> list:
        label = label.lower()
        if entity_type is not None:
            return self.indices['label+entity_type'].get(label + '@' + entity_type) or []
        if source_type is not None:
            return self.indices['label+source_type'].get(label + '@' + source_type) or []


class Entity:

    entity_ns = Namespace('#')
    concept_scheme = URIRef('#')

    properties = []

    def __init__(self, entity_id: str):
        self.row: Optional[DataRow] = None
        self.data = {
            'id': entity_id,
            'type': None,
            'pref_label': None,
            'alt_label': [],
        }

    def __getattr__(self, attr):
        return self.data.get(attr)

    def add(self, key, value):
        self.data[key] = self.data.get(key, []) + [value]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value

    def set_pref_label(self, label):
        self.data['pref_label'] = label

    def add_alt_label(self, label):
        self.data['alt_label'].append(label)

    def uri(self) -> URIRef:
        return self.entity_ns[self.id]

    def from_row(self, row: DataRow):
        # Import data from a DataRow object

        self.row = row

        for key in Entity.properties:
            if key in row and pd.notnull(row[key]):
                self.set(key, row[key])

        # Define type
        self.set('source_type', row.type)
        self.set('type', row.type)


class BsNasjEntity(Entity):
    vocabulary_code = 'bs-nasj'
    entity_ns = Namespace('http://id.bibbi.dev/bs-nasj/')
    concept_scheme = URIRef('http://id.bibbi.dev/bs-nasj/')


class BibbiEntity(Entity):
    vocabulary_code = 'bibbi'
    entity_ns = Namespace('http://id.bibbi.dev/bibbi/')
    concept_scheme = URIRef('http://id.bibbi.dev/bibbi/')

    properties = [
        'ddk5_nr',
        'webdewey_nr',
        'webdewey_approved',
        'created',
        'modified',
        'items_as_entry',
        'items_as_subject',
        'noraf_id',
        'nationality',
        'date',
    ]

    def __init__(self, entity_id: str):
        super().__init__(entity_id)
        self.row: Optional[DataRow] = None
        self.data = {
            'id': entity_id,
            'type': None,
            'pref_label': None,
            'alt_label': [],
            'broader': [],
            'components': [],
            'items_as_subject': 0,
            'items_as_entry': 0,
        }

    def from_row(self, row: DataRow):
        # Import data from a DataRow object
        super().from_row(row)

        if not row.is_main_entry():
            self.set('type', TYPE_COMPLEX)

        if row.has('felles_id') and row.get('felles_id') != row.get('bibsent_id'):
            # Biautoriteter

            if row.type == TYPE_PERSON:
                if row.has('work_title'):
                    if row.get('field_code') == '600':
                        self.set('type', TYPE_TITLE_SUBJECT)
                    else:
                        self.set('type', TYPE_TITLE)
                else:
                    self.set('type', TYPE_PERSON_SUBJECT)

            elif row.type == TYPE_CORPORATION:
                if row.has('work_title'):
                    if row.law == '1':
                        self.set('type', TYPE_LAW)
                        self.set('jurisdiction', LanguageMap(nb=row.label, nn=row.label_nn))
                        # OBS: Alle lovene har samme Felles_ID ! De er altså alle biautoriteter uten en hovedautoritet
                    else:
                        self.set('type', TYPE_LAW)
                else:
                    self.set('type', TYPE_CORPORATION_SUBJECT)


class ConceptSchemeCollection:

    def __init__(self, schemes: Dict[str, ConceptScheme]):
        self.schemes = schemes

    def get(self, table: PromusTable) -> ConceptScheme:
        return self.schemes[table.vocabulary_code]

    def __iter__(self) -> Iterator[Entity]:
        for scheme in self.schemes.values():
            return iter(scheme)

    def tables_imported(self):
        return sum([scheme.tables_imported for scheme in self.schemes.values()])


class ConceptScheme:

    def __init__(self, entity_cls=None, entities=None):
        self.entity_cls = entity_cls
        self._entities = entities or {}
        self.index = EntityIndex()
        self.label_factory = LabelFactory()
        self.tables_imported = 0

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities.values())

    def get(self, concept_id: str, create: bool = True) -> Optional[Entity]:
        if concept_id is None:
            return None
        if concept_id not in self._entities:
            if not create:
                return None

            self._entities[concept_id] = self.entity_cls(concept_id)
        return self._entities[concept_id]

    def filter(self, filter_fn) -> ConceptScheme:
        return ConceptScheme({k: v for k, v in self._entities.items() if filter_fn(v)})

    def import_table(self, table: PromusTable):
        n = 0
        if isinstance(table, PromusAuthorityTable):
            for row in table.rows():

                label = self.label_factory.make(row)

                if label is None:
                    log.warning('NO LABEL found for entity %s', row.id)
                    continue

                if target_id := table.refers_to(row):
                    entity = self.get(target_id)
                    entity.add_alt_label(label)
                    self.index.add(label, False, entity)

                else:
                    entity = self.get(row[table.index_column])
                    entity.set_pref_label(label)
                    entity.from_row(row)
                    self.index.add(label, True, entity)

                n += 1
                yield entity

        elif isinstance(table, PromusTable):
            for row in table.rows():
                label = LanguageMap(nb=row.label, nn=row.label)
                entity = self.get(row[table.index_column])
                entity.set_pref_label(label)
                entity.from_row(row)
                self.index.add(label, True, entity)
                n += 1
                yield entity

        else:
            log.error('Unknown table type: %s', str(table))

        log.info('Constructed %d entities from: %s', n, table.entity_type)
        self.tables_imported += 1
        return self

    def generate_relations(self, country_table):

        entity_map = {
            TYPE_TITLE_SUBJECT: TYPE_TITLE,
            #TYPE_CORPORATION_SUBJECT: TYPE_CORPORATION,
            #TYPE_PERSON_SUBJECT: TYPE_PERSON,
        }

        countries_map = country_table.short_name_dict()

        for entity in self._entities.values():

            if entity.type in entity_map:
                broader = self.index.find(label=entity.pref_label.nb, entity_type=entity_map[entity.type])
                if len(broader) != 0:
                    entity.add('broader', self.get(entity.vocabulary_code, broader[0]))
                    continue

            if entity.row.has('felles_id') and entity.row.get('felles_id') != entity.row.get('bibsent_id'):
                broader = self.get(entity.row.get('felles_id'), create=False)
                if broader is not None:
                    entity.add('broader', broader)
                # else:
                #    log.warning('Warning: No broader entity found for %s', entity.row.get('bibsent_id'))

            if entity.type in [TYPE_PERSON, TYPE_PERSON_SUBJECT]:
                self.add_country_codes(entity, countries_map)

    def add_country_codes(self, entity: Entity, countries_map: dict):
        """
        Deduce country codes from nationalities, using data from the EnumCountries table.
        """

        if entity.nationality is not None:
            for nationality in entity.nationality.split('-'):
                if nationality in countries_map:
                    country_code = countries_map[nationality]
                    if country_code is not None:
                        entity.add('country_codes', country_code)
                else:
                    log.warning(
                        'Invalid nationality: %s\t%s\t%s\t%s\t%s',
                        entity.id,
                        entity.pref_label.nb,
                        entity.modified.strftime('%Y-%m-%dT%H:%M:%S') if entity.modified is not None else '',
                        entity.nationality,
                        nationality
                    )

    def remove_invalid_entries(self):
        to_remove = []
        for entity_id, entity in self._entities.items():
            if entity.pref_label is None:
                to_remove.append(entity_id)

        for entity_id in to_remove:
            log.warning('Removing invalid entity: %s', entity_id)
            del self._entities[entity_id]
