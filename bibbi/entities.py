import pandas as pd
from openpyxl import Workbook
from collections import OrderedDict, namedtuple
import logging
import re
import os
import rtyaml
import uuid
import sys
from .util import as_generator

log = logging.getLogger(__name__)

SUB_DELIM = ' - '
QUA_DELIM = ' : '
TYPE_TOPIC = 'topic'
TYPE_GEOGRAPHIC = 'geographic'
TYPE_CORPORATION = 'corporation'
TYPE_PERSON = 'person'
TYPE_QUALIFIER = 'qualifier'
TYPE_COMPLEX = 'complex'
TYPE_LAW = 'law'


class Components:
    # Class for extracting components from precoordinated subject chains,
    # assign UUIDs to not-yet-seen components and persist these to disk.

    def __init__(self):
        types = [
            TYPE_TOPIC,
            TYPE_GEOGRAPHIC,
            TYPE_CORPORATION,
            TYPE_QUALIFIER,
        ]
        self._ids = {
            x: OrderedDict() for x in types
        }
        self._labels = {
            x: OrderedDict() for x in types
        }

    def has(self, entity_type, label):
        # Check if have the component, but don't create an ID for it if not
        label = label.lower()
        return label in self._ids[entity_type]

    def get(self, entity_type, label):
        # Find or create an ID for the component
        lc_label = label.lower()

        # Try to find entity of correct type
        if lc_label in self._ids[entity_type]:
            return self._ids[entity_type][lc_label]

        # Try to find entity of wrong type
        if entity_type != TYPE_GEOGRAPHIC:  # Hint: Algerie - Alger
            for key, labels in self._ids.items():
                if lc_label in labels:
                    log.warning('Did not find "%s" as %s, re-using the %s ID %s', label, entity_type, key, labels[lc_label])
                    return self.set(entity_type, label, labels[lc_label])

        # Generate UUID
        return self.set(entity_type, label, str(uuid.uuid4()))

    def set(self, entity_type, label, id, force=False):
        lc_label = label.lower()
        if lc_label in self._ids[entity_type] and self._ids[entity_type][lc_label] != id:
            if force:
                log.warning('Overwriting existing ID for (%s:%s). Old: %s, new: %s',
                            entity_type, label, self._ids[entity_type][lc_label], id)
            else:
                log.warning('Won\'t overwrite existing ID for (%s:%s). Old: %s, new: %s',
                            entity_type, label, self._ids[entity_type][lc_label], id)
                return self._ids[entity_type][lc_label]

        self._ids[entity_type][lc_label] = id
        self._labels[entity_type][lc_label] = label
        return self._ids[entity_type][lc_label]

    def __len__(self):
        # Find the total number of components across bins
        return sum([len(bin) for bin in self._ids.values()])

    def sorted(self):
        out = {}
        for bin, items in self._ids.items():
            out[bin] = OrderedDict(
                sorted(
                    ((k, v) for k, v in items.items()),
                    key=lambda x: x[0]
                )
            )
        return out

    def load(self, filename):
        # Load component IDs from disk
        if not os.path.exists(filename):
            log.error('Component file does not exist: %s', filename)
            return
        with open(filename, encoding='utf-8') as fp:
            self._ids = rtyaml.load(fp)

    def serialize(self, include_non_uuids=False):
        # Serialize the component IDs into a YAML-compatible structure.

        out = self.sorted()
        if not include_non_uuids:
            for bin, items in out.items():
                out[bin] = OrderedDict(
                    ((k, v) for k, v in items.items() if '-' not in v)
                )
        return out

    def persist(self, filename, include_non_uuids=False):
        # Store the component IDs to disk
        with open(filename, 'w', encoding='utf-8') as fp:
            rtyaml.dump(self.serialize(include_non_uuids), fp)


class DataRow:
    # Wrapper around a DataFrame row that adds domain specific methods for data extraction

    def __init__(self, row: namedtuple, type: str):
        self.row = row
        self.type = type

    def __getattr__(self, key):
        return getattr(self.row, key)

    def __getitem__(self, key):
        return getattr(self.row, key)

    def __contains__(self, key):
        return key in self.row

    def get(self, *keys):
        # Fallback chain, get first non-null value
        for key in keys:
            try:
                value = getattr(self.row, key)
                if pd.notnull(value):
                    return value
            except AttributeError:
                pass

    def is_main_entry(self):
        if self.get('qualifier') or self.get('sub_topic'):
            return False
        if self.type != TYPE_GEOGRAPHIC and self.get('sub_geo'):
            return False
        return True

    def get_subdivisions(self, subdiv_type: str):
        """
        Get a list of individual subdivisions as language maps.

        Args:
            subdiv_type (str): Either 'sub_topic' or 'sub_geo'
        """
        if subdiv_type not in ['sub_geo', 'sub_topic', 'sub_unit']:
            raise Error('Invalid subdivision type: %s', subdiv_type)
        if pd.isnull(getattr(self.row, subdiv_type)):
            return
        nb_parts = getattr(self.row, subdiv_type).split(' - ')
        nn_parts = []
        if hasattr(self.row, subdiv_type + '_nn') and pd.notnull(getattr(self.row, subdiv_type + '_nn')):
            nn_parts = getattr(self.row, subdiv_type + '_nn').split(' - ')
        for k, part in enumerate(nb_parts):
            if len(nb_parts) == len(nn_parts):
                yield {'nb': part, 'nn': nn_parts[k]}
            else:
                if len(nn_parts) != 0:
                    log.warning('get_subdivisions(): Differing number of parts in nb and nn: "%s" != "%s"',
                                ' - '.join(nb_parts), ' - '.join(nn_parts))
                yield {'nb': part, 'nn': part}

    def get_main_component(self):
        # Get the "$a ($q)" part only
        # TODO: Check combinations of row.detail with custom labels

        # 1. Navn ($a)
        label = {
            'nb': self.row.label,
            'nn': self.get('label_nn', 'label')
        }

        # 2. Forklarende tilføyelse i parentes ($q)
        if self.get('detail'):
            label['nb'] += ' (%s)' % self.row.detail
            label['nn'] += ' (%s)' % self.get('detail_nn', 'detail')

        return {'label': label, 'entity_type': self.type, 'entity_id': None}

    def get_general_components(self):
        # Returns the general parts (6XX $x) of this subject heading as an array.
        for label in self.get_subdivisions('sub_topic'):
            yield {'label': label, 'entity_type': TYPE_TOPIC, 'entity_id': None}

    def get_geographic_component(self):
        # Returns the geographic parts (655 $a and 6XX $z) of this subject heading
        # combined into a single component, or None if there is no geographic part.
        parts = []
        if self.type == TYPE_GEOGRAPHIC:
            label = self.get_main_component()['label']
            parts.append(label)
        for label in self.get_subdivisions('sub_geo'):
            parts.append(label)

        if len(parts) == 0:
            return None

        out = parts.pop()
        if len(parts) > 0:
            out['nb'] += ' (%s)' % ', '.join([x['nb'] for x in parts[::-1]])
            out['nn'] += ' (%s)' % ', '.join([x['nn'] for x in parts[::-1]])
        return {'label': out, 'entity_type': TYPE_GEOGRAPHIC, 'entity_id': None}

    def  get_corporate_label(self):
        # Returns the corporate name components (X10 $a, $b or $t) of this subject heading
        # combined into a single component, or None if there is no corporate name part.
        if self.type != TYPE_CORPORATION:
            return None

        label = self.get_main_component()['label']

        for lab in self.get_subdivisions('sub_unit'):
            label['nb'] = '%s (%s)' % (lab['nb'], label['nb'])
            label['nn'] = '%s (%s)' % (lab['nn'], label['nn'])

        if pd.notnull(self.work_title):
            # Tittel på lover og musikkalbum (nynorsk-variant finnes ikke)
            label['nb'] = '%s (%s)' % (self.work_title, label['nb'])
            label['nn'] = '%s (%s)' % (self.work_title, label['nn'])

        return label

    def  get_person_label(self):
        # Returns the person name components (X00 $a, $b or $t) of this subject heading
        # combined into a single component, or None if there is no person name part.
        if self.type != TYPE_PERSON:
            return None

        label = self.get_main_component()['label']

        if numeration := self.get('numeration'):
            label['nb'] += ' ' + numeration
            label['nn'] += ' ' + numeration

        # OBS, OBS: Ikke bare enkeltpersoner. Typ "slekten", "familien"

        # if title_nb := self.get('title'):
        #     label['nb'] += ' ' + title_nb
        #     label['nn'] += ' ' + self.get('title_nn', 'title')


        # 'PersonYear': 'date',  # $d Dates associated with name
        # 'PersonNation': 'nationality',

        # TODO: ....

        # for lab in self.get_subdivisions('sub_unit'):
        #     label['nb'] = '%s (%s)' % (lab['nb'], label['nb'])
        #     label['nn'] = '%s (%s)' % (lab['nn'], label['nn'])

        # if pd.notnull(self.work_title):
        #     # Tittel på lover og musikkalbum (nynorsk-variant finnes ikke)
        #     label['nb'] = '%s (%s)' % (self.work_title, label['nb'])
        #     label['nn'] = '%s (%s)' % (self.work_title, label['nn'])

        return label

    def get_qualifier_component(self):
        if pd.notnull(self.row.qualifier):
            label = {
                'nb': self.row.qualifier,
                'nn': self.get('qualifier_nn', 'qualifier'),
            }
            return {'label': label, 'entity_type': TYPE_QUALIFIER, 'entity_id': None}
        return None

    def get_components(self):
        # Returns general (topical) and geographic subdivisions as components, plus qualifier if any
        if self.type == TYPE_TOPIC:
            yield {'label': self.get_main_component()['label'], 'entity_type': TYPE_TOPIC, 'entity_id': None}
        for component in as_generator(self.get_geographic_component()):
            yield component
        for component in self.get_general_components():
            yield component
        for component in as_generator(self.get_qualifier_component()):
            yield component

    def get_label(self, include_subdivisions=True, label_transforms=True):

        row = self.row

        label = self.get_main_component()['label']

        if include_subdivisions and not label_transforms:
            if self.get('sub_geo'):
                label['nb'] += SUB_DELIM + row.sub_geo
                label['nn'] += SUB_DELIM + self.get('sub_geo_nn', 'sub_geo')

            # Generell underinndeling ($x)
            if self.get('sub_topic'):
                label['nb'] += SUB_DELIM + row.sub_topic  # Merk: Kan bestå av flere ledd adskilt av -
                label['nn'] += SUB_DELIM + self.get('sub_topic_nn', 'sub_topic')

            # Tittel på lover og musikkalbum
            if self.type == TYPE_CORPORATION and pd.notnull(row.work_title):
                label['nb'] += SUB_DELIM + row.work_title
                label['nn'] += SUB_DELIM + row.work_title

            # Kolon-kvalifikator (Blir litt gæren av disse!)
            if self.get('qualifier'):
                label['nb'] += QUA_DELIM + row.qualifier
                label['nn'] += QUA_DELIM + self.get('qualifier_nn', 'qualifier')

            return label

        # -----------------------------------------------------------------------------------
        # Spesialtilfeller:

        # Spesialtilfelle 1: Geografiske emneord (655): $a og $z kombineres
        if self.type == TYPE_GEOGRAPHIC:
            label = self.get_geographic_component()['label']

        # Spesialtilfelle 2: Personer (X00): $a, $b, $t kombineres
        if self.type == TYPE_PERSON:
            label = self.get_person_label()

        # Spesialtilfelle 3: Korporasjoner (X10): $a, $b, $t kombineres
        if self.type == TYPE_CORPORATION:
            label = self.get_corporate_label()

        if not include_subdivisions:
            return label

        # -----------------------------------------------------------------------------------
        # Underinndelinger

        # Geografisk underinndeling ($z)
        if self.get('sub_geo') and self.type != TYPE_GEOGRAPHIC:
            geo_label = self.get_geographic_component()['label']
            label['nb'] += SUB_DELIM + geo_label['nb']
            label['nn'] += SUB_DELIM + geo_label['nn']

        # Generell underinndeling ($x)
        if self.get('sub_topic'):
            label['nb'] += SUB_DELIM + row.sub_topic  # Merk: Kan bestå av flere ledd adskilt av -
            label['nn'] += SUB_DELIM + self.get('sub_topic_nn', 'sub_topic')

        # Kolon-kvalifikator (Blir litt gæren av disse!)
        if self.get('qualifier'):
            label['nb'] += QUA_DELIM + row.qualifier
            label['nn'] += QUA_DELIM + self.get('qualifier_nn', 'qualifier')

        # entity.set_label('preferred_label', row.work_title, 'nn')   # ???
        # OBS: Alle lovene har samme Felles_ID. De er altså alle biautoriteter uten en hovedautoritet

        return label


class ReferenceMap:
    # Map of references `{from_id: to_id}` where from_id and to_id are Bibsent IDs.

    def __init__(self):
        self._map = {}

    def extend_from_df(self, df):
        # Build the map
        bibsent_ids = dict(zip(df.row_id, df.bibsent_id))
        df2 = df[df.ref_id.notnull()]
        refs = dict(zip(df2.row_id, df2.ref_id))
        self._map.update({bibsent_ids[k]: bibsent_ids[v] for k, v in refs.items()})
        log.info('Reference map extended to hold %d references', len(self))

    def get(self, bibbi_id):
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


class Entities:

    def __init__(self, component_file=None):
        self._items = {}
        self.references = ReferenceMap()
        self.components = Components()
        if component_file:
            self.components.load(component_file)
        # Map: {type: {label: id}}
        # self.label_ids = {
        #     'topic': {},
        #     'geographic': {},
        #     'corporation': {},
        # }

    def get(self, bibbi_id):
        """
        Get a single entity by its (global) bibbi_id.

        :param bibbi_id:
        :return: Entity
        """
        if bibbi_id is None:
            return None
        if bibbi_id not in self._items:
            self._items[bibbi_id] = Entity(bibbi_id)
        return self._items[bibbi_id]

    def __iter__(self):
        # Iterate over the entities
        for item in self._items.values():
            yield item

    def __len__(self):
        return len(self._items)

    def import_dataframe(self, df, entity_type, label_transforms: True, component_extraction: False):
        # Construct objets from a dataframe
        self.references.extend_from_df(df)
        n = 0
        for row in df.itertuples():  # Note: itertuples is *much* faster than iterrows! Cut loading time from 28s to 4s
            data_row = DataRow(row, entity_type)
            if self.import_row(data_row, label_transforms):
                n += 1
                if component_extraction:
                    self.extract_components(data_row)

        log.info('[%s] Constructed %d entities', entity_type, n)

    def import_row(self, row: DataRow, label_transforms=True):
        # Create an Entity object from a row

        # -----------------------------------------------------------
        # Construct the formatted labels
        label = row.get_label(label_transforms=label_transforms)

        # -----------------------------------------------------------
        # If the row is a reference, add the labels to the concept it refers
        # to and then return.
        refers_to = self.get(self.references.get(row.bibsent_id))
        if refers_to is not None:
            refers_to.add_label('alternative_labels', label['nb'], 'nb')
            refers_to.add_label('alternative_labels', label['nn'], 'nn')
            return False

        # -----------------------------------------------------------

        entity = self.get(row.bibsent_id)
        entity.set('type', row.type)
        entity.set_label('preferred_label', label['nb'], 'nb')
        entity.set_label('preferred_label', label['nn'], 'nn')

        props = [
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

        for key in props:
            if key in row and pd.notnull(row[key]):
                entity.set(key, row[key])

        if row.type == TYPE_CORPORATION and pd.notnull(row.work_title) and row.law == '1':
            entity.set('type', TYPE_LAW)
            jurisdiction = {'nb': row.label, 'nn': row.label_nn or row.label}
            entity.set('jurisdiction', jurisdiction)
            # entity.set_label('preferred_label', row.work_title, 'nn')   # ???
            # OBS: Alle lovene har samme Felles_ID !! De er altså alle biautoriteter uten en hovedautoritet?

        if not row.is_main_entry():
            entity.set('type', TYPE_COMPLEX)

        return True

    def extract_components(self, row):
        for component in row.get_components():
            entity.add('components', component)

        # Add all the entities we know about as components first, so that the IDs can be
        # looked up when we run `make_component_entities()` later on.
        if row.is_main_entry():
            if self.components.has(row.type, label['nb']):
                other_id = self.components.get(row.type, label['nb'])
                other = self.get(other_id)

                log.warning('CONFLICT: "%s"/%s found in OTHER(%s, wd-approved: %s, count: %s) and THIS(%s, wd-approved: %s, count: %s)',
                    label['nb'],
                    row.type,
                    other.id,
                    other.webdewey_approved,
                    other.item_count,
                    row.bibsent_id,
                    row.webdewey_approved,
                    row.item_count
                )
                if row.item_count > other.item_count:
                    # Overwrite
                    self.components.set(row.type, label['nb'], row.bibsent_id, True)
                elif other.webdewey_approved == '0' and row.webdewey_approved == '1':
                    # Overwrite
                    self.components.set(row.type, label['nb'], row.bibsent_id, True)

            else:
                self.components.set(row.type, label['nb'], row.bibsent_id)
            # self.label_ids[row.type][labels['nb']] = row.bibsent_id

    def make_component_entity(self, entity_type, label, entity_id=None):
        if entity_id is None:
            entity_id = self.components.get(entity_type, label['nb'])

        entity = self.get(entity_id)
        entity.set('type', entity_type)
        entity.set_label('preferred_label', label['nb'], 'nb')
        entity.set_label('preferred_label', label['nn'], 'nn')

        return entity

    def make_component_entities(self):
        for entity in list(self._items.values()):
            entity.components = [self.make_component_entity(**c) for c in entity.components]
        log.info('Made components')

    def to_excel_sheets(self):
        print('subdivisions:')
        for key, values in self.components.items():
            wb = Workbook()
            ws = wb.active
            for n, val in enumerate(sorted(list(values))):
                ws.cell(row=n + 2, column=1, value=val)
            wb.save('out/%s.xlsx' % key)
            print('- %s: %d unique' % (key, len(values)))


class Label:

    def __init__(self, value, lang):
        self.value = value[0].upper() + value[1:]
        self.lang = lang


class Entity:

    def __init__(self, bibbi_id):
        self.data = {
            'id': bibbi_id,
            'type': None,
            'preferred_label': {},
            'alternative_labels': {},
            'components': [],
            'item_count': 0,
        }

    def __getattr__(self, attr):
        return self.data.get(attr)

    def add(self, key, value):
        self.data[key] = self.data.get(key, []) + [value]

    def set(self, key, value):
        self.data[key] = value

    def set_label(self, key, value, lang):
        self.data[key][lang] = Label(value, lang)

    def add_label(self, key, value, lang):
        if lang not in self.data[key]:
            self.data[key][lang] = []
        self.data[key][lang].append(Label(value, lang))

