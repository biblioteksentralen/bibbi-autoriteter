from __future__ import annotations
import logging
import os
from typing import TYPE_CHECKING, Optional

import rtyaml
import uuid
from collections import OrderedDict

from .label import LabelService
from .util import ensure_parent_dir_exists
from .constants import TYPE_TOPICAL, TYPE_GEOGRAPHIC, TYPE_CORPORATION, TYPE_PERSON, TYPE_QUALIFIER, TYPE_PERSON_SUBJECT, \
    TYPE_CORPORATION_SUBJECT

if TYPE_CHECKING:
    from .entities import Entities
    from .entities import Entity
    from .lookup import LookupService

log = logging.getLogger(__name__)


class Components:
    # Class for extracting components from precoordinated subject chains,
    # assign UUIDs to not-yet-seen components and persist these to disk.

    def __init__(self, entities: Entities, lookup: LookupService):
        self.labels = LabelService()
        self.entities = entities
        self.lookup = lookup

    def find_component(self, entity: Entity, label: str, source_type: str) -> Optional[dict]:
        candidates = self.lookup.find(label=label, source_type=source_type)
        if len(candidates) is None:
            return None

        c0 = len(candidates)
        """
        if entity.type == TYPE_PERSON_SUBJECT:
            candidates = [x for x in candidates if x['type'] == TYPE_PERSON]
        elif entity.type == TYPE_CORPORATION_SUBJECT:
            candidates = [x for x in candidates if x['type'] == TYPE_CORPORATION]
        else:
            candidates = [x for x in candidates if x['type'] not in [TYPE_PERSON_SUBJECT, TYPE_CORPORATION_SUBJECT]]

        candidates = [x for x in candidates if x['preferred'] is True]

        candidates = [x for x in candidates if x['source_type'] == source_type]

        if len(candidates) > 1:
            log.info('%s "%s" : Found multiple matches for "%s"', entity.type, entity.pref_label.nb, label)
            for lab in candidates:
                log.info(lab)

        elif len(candidates) == 0:
            log.info('%s "%s" : No remaining matches for "%s"', entity.type, entity.pref_label.nb, label)
            for lab in self.lookup.find(label=label):
                log.info(lab)

        else:
            return candidates[0]
        """

    def load(self):
        log.info('Components..')

        # 2nd pass to link and extract components
        counts = {}
        for entity in self.entities:
            if not entity.row.is_main_entry():
                label = self.labels.get_base_label(entity.row).nb.lower()
                if entity.source_type not in counts:
                    counts[entity.source_type] = {'found': 0, 'notfound': 0}

                if component := self.find_component(entity, label, entity.source_type):
                    counts[entity.source_type]['found'] += 1
                    component_entity = self.entities.get(component['id'])
                    entity.add('component', component_entity)
                else:
                    counts[entity.source_type]['notfound'] += 1

        for k, v in counts.items():
            log.warning('%s: %d labels found, %d not found', k, v['found'], v['notfound'])

    def has(self, entity_type: str, label: str) -> bool:
        # Check if have the component, but don't create an ID for it if not
        label = label.lower()
        return label in self._ids[entity_type]

    def get(self, entity_type: str, label: str):
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

    """
    def load(self, filename):
        # Load component IDs from disk
        if not os.path.exists(filename):
            log.error('Component file does not exist: %s', filename)
            return
        with open(filename, encoding='utf-8') as fp:
            self._ids = rtyaml.load(fp)
    """

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
        ensure_parent_dir_exists(filename)
        with open(filename, 'w', encoding='utf-8') as fp:
            rtyaml.dump(self.serialize(include_non_uuids), fp)

    def get_general_components(self, row):
        # Returns the general parts (6XX $x) of this subject heading as an array.
        for label in row.get_subdivisions('sub_topic'):
            yield {
                'label': label,
                'entity_type': TYPE_TOPICAL,
                'entity_id': None
            }

    def get_geographic_component(self):
        # Returns the geographic parts (655 $a and 6XX $z) of this subject heading
        # combined into a single component, or None if there is no geographic part.
        labels = []
        if self.type == TYPE_GEOGRAPHIC:
            labels.append(self.get_base_label())

        for label in self.get_subdivisions('sub_geo'):
            labels.append(label)

        if len(labels) == 0:
            return None

        out = labels.pop()
        if len(labels) > 0:
            out['nb'] += ' (%s)' % ', '.join([label['nb'] for label in labels[::-1]])
            out['nn'] += ' (%s)' % ', '.join([label['nn'] for label in labels[::-1]])

        return {
            'label': out,
            'entity_type': TYPE_GEOGRAPHIC,
            'entity_id': None
        }

    def get_qualifier_component(self):
        if self.has('qualifier'):
            label = {
                'nb': self.data.qualifier,
                'nn': self.get('qualifier_nn', 'qualifier'),
            }
            return {
                'label': label,
                'entity_type': TYPE_QUALIFIER,
                'entity_id': None
            }
        return None

    def get_components(self):
        # Returns general (topical) and geographic subdivisions as components, plus qualifier if any
        if self.type == TYPE_TOPICAL:
            yield {
                'label': self.get_base_label(),
                'entity_type': TYPE_TOPICAL,
                'entity_id': None
            }
        for component in as_generator(self.get_geographic_component()):
            yield component
        for component in self.get_general_components():
            yield component
        for component in as_generator(self.get_qualifier_component()):
            yield component
