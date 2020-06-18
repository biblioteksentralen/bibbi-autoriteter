from __future__ import annotations

import re
import weakref
from typing import Optional, Iterator

import pandas as pd
import logging

from .constants import TYPE_CORPORATION, TYPE_LAW, TYPE_COMPLEX, TYPE_PERSON, TYPE_CORPORATION_SUBJECT, \
    TYPE_PERSON_SUBJECT, \
    TYPE_TITLE, TYPE_TITLE_SUBJECT
from .label import LabelService
from .lookup import LookupService
from .repository import DataRow, LanguageMap, Repository

log = logging.getLogger(__name__)


class Entity:

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

    def __init__(self, bibbi_id: str):
        self.row: Optional[DataRow] = None
        self.data = {
            'id': bibbi_id,
            'type': None,
            'pref_label': None,
            'alt_label': [],
            'broader': [],
            'components': [],
            'items_as_subject': 0,
            'items_as_entry': 0,
        }

    def __getattr__(self, attr):
        return self.data.get(attr)

    def add(self, key, value):
        self.data[key] = self.data.get(key, []) + [value]

    def set(self, key: str, value):
        self.data[key] = value

    def set_pref_label(self, label):
        self.data['pref_label'] = label

    def add_alt_label(self, label):
        self.data['alt_label'].append(label)

    def from_row(self, row: DataRow):
        # Import data from a DataRow object

        self.row = row

        for key in Entity.properties:
            if key in row and pd.notnull(row[key]):
                self.set(key, row[key])

        # Define type

        self.set('source_type', row.type)
        self.set('type', row.type)

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


# class Label:
#
#     def __init__(self, value, lang):
#         self.value = value[0].upper() + value[1:]
#         self.lang = lang
#
#     def lower(self):
#         return self.value.lower()
#
#


class Entities:

    def __init__(self, entities={}):
        self._entities = entities
        self.lookup = LookupService()
        self.labels = LabelService()

        # self.components = Components()
        # if component_file:
        #     self.components.load(component_file)
        #
        # Map: {type: {label: id}}
        # self.label_ids = {
        #     'topic': {},
        #     'geographic': {},
        #     'corporation': {},
        # }

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities.values())

    def get(self, bibbi_id, create: bool = True) -> Optional[Entity]:
        """
        Get a single entity by its (global) bibbi_id.

        :param bibbi_id:
        :return: Entity
        """
        if bibbi_id is None:
            return None
        if bibbi_id not in self._entities:
            if not create:
                return None
            self._entities[bibbi_id] = Entity(bibbi_id)
        return self._entities[bibbi_id]

    # def __iter__(self):
    #     # Iterate over the entities
    #     for item in self._entities.values():
    #         yield item
    #
    # def __len__(self):
    #     return len(self._items)

    def filter(self, filter_fn) -> Entities:
        return Entities({k: v for k, v in self._entities.items() if filter_fn(v)})


    def load(self, repo: Repository):
        for table in repo.get():
            for row in table.rows():

                label = self.labels.get_label(row)

                if target_id := table.refers_to(row):
                    entity = self.get(target_id)
                    entity.add_alt_label(label)

                else:
                    entity = self.get(row.bibsent_id)
                    entity.set_pref_label(label)
                    entity.from_row(row)

            log.info('Constructed entities: %s', table.entity_type)

        to_remove = []
        for entity_id, entity in self._entities.items():
            if entity.pref_label is None:
                to_remove.append(entity_id)
            else:
                self.lookup.add(entity.pref_label, True, entity)
                for label in entity.alt_label:
                    self.lookup.add(label, False, entity)

        for entity_id in to_remove:
            log.warning('Removing invalid entity: %s', entity_id)
            del self._entities[entity_id]

        self.generate_relations()
        log.info('Generated relations')

    def generate_relations(self):

        entity_map = {
            TYPE_TITLE_SUBJECT: TYPE_TITLE,
            #TYPE_CORPORATION_SUBJECT: TYPE_CORPORATION,
            #TYPE_PERSON_SUBJECT: TYPE_PERSON,
        }

        for entity_id, entity in self._entities.items():

            if entity.type in entity_map:
                broader = self.lookup.find(label=entity.pref_label.nb, entity_type=entity_map[entity.type])
                if len(broader) != 0:
                    entity.add('broader', self.get(broader[0]))
                    continue

            if entity.row.has('felles_id') and entity.row.get('felles_id') != entity.row.get('bibsent_id'):
                broader = self.get(entity.row.get('felles_id'), create=False)
                if broader is not None:
                    entity.add('broader', broader)
                # else:
                #    log.warning('Warning: No broader entity found for %s', entity.row.get('bibsent_id'))

