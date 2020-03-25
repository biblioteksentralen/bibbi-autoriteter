import pandas as pd
import logging

from .components import Components
from .constants import TYPE_CORPORATION, TYPE_LAW, TYPE_COMPLEX
from .repository import DataRow, LanguageMap

log = logging.getLogger(__name__)


class Entities:

    def __init__(self, entities={}):
        self._entities = entities

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

    def __len__(self):
        return len(self._entities)

    def __iter__(self):
        return iter(self._entities.values())

    def get(self, bibbi_id):
        """
        Get a single entity by its (global) bibbi_id.

        :param bibbi_id:
        :return: Entity
        """
        if bibbi_id is None:
            return None
        if bibbi_id not in self._entities:
            self._entities[bibbi_id] = Entity(bibbi_id)
        return self._entities[bibbi_id]

    # def __iter__(self):
    #     # Iterate over the entities
    #     for item in self._entities.values():
    #         yield item
    #
    # def __len__(self):
    #     return len(self._items)

    def load(self, repo):
        for table in repo.get():
            for row in table.rows():

                label = row.get_raw_label()

                if target_id := table.refers_to(row):
                    entity = self.get(target_id)
                    entity.add_alt_label(label)

                else:
                    entity = self.get(row.bibsent_id)
                    entity.set_pref_label(label)
                    entity.from_row(row)

            log.info('[%s] Constructed entities', table.entity_type)

    def filter(self, filter_fn):
        return Entities({k: v for k, v in self._entities.items() if filter_fn(v)})


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

    def __init__(self, bibbi_id):
        self.data = {
            'id': bibbi_id,
            'type': None,
            'pref_label': None,
            'alt_label': [],
            'components': [],
            'items_as_subject': 0,
            'items_as_entry': 0,
        }

    def __getattr__(self, attr):
        return self.data.get(attr)

    def add(self, key, value):
        self.data[key] = self.data.get(key, []) + [value]

    def set(self, key, value):
        self.data[key] = value

    def set_pref_label(self, label):
        self.data['pref_label'] = label

    def add_alt_label(self, label):
        self.data['alt_label'].append(label)

        # if lang not in self.data[key]:
        #     self.data[key][lang] = []
        # self.data[key][lang].append(Label(value, lang))

    def from_row(self, row: DataRow):
        # Import data from a DataRow object

        self.set('type', row.type)

        for key in Entity.properties:
            if key in row and pd.notnull(row[key]):
                self.set(key, row[key])

        if row.type == TYPE_CORPORATION and row.has('work_title') and row.law == '1':
            self.set('type', TYPE_LAW)
            self.set('jurisdiction', LanguageMap(nb=row.label, nn=row.label_nn))
            # self.set_label('preferred_label', row.work_title, 'nn')   # ???
            # OBS: Alle lovene har samme Felles_ID !! De er altså alle biautoriteter uten en hovedautoritet?

        # if not row.is_main_entry():
        #    self.set('type', TYPE_COMPLEX)

#
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
