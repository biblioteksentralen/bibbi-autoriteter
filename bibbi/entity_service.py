from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, field
import logging
from typing import Iterator, TYPE_CHECKING, List, Set, Dict, Optional

from rdflib import Namespace, URIRef

if TYPE_CHECKING:
    from .util import LanguageMap
    from .promus_service import DataRow, PromusTable

log = logging.getLogger(__name__)


@dataclass
class Entity:
    id: str
    namespace: Namespace
    row: DataRow
    source_type: str
    type: str
    pref_label: LanguageMap
    alt_labels: List[LanguageMap]
    local_id: str
    complex: bool = False

    def uri(self) -> URIRef:
        return self.namespace.term(self.id)


@dataclass
class Nation(Entity):
    label: Optional[str] = None
    demonym: Optional[str] = None
    iso3166_2_code: Optional[str] = None
    marc21_code: Optional[str] = None
    abbreviation: Optional[str] = None
    description: Optional[str] = None
    geographic_concept_id: Optional[str] = None


@dataclass
class BibbiEntity(Entity):
    approved: Optional[str] = None
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    items_as_subject: int = 0
    items_as_entry: int = 0
    ddk5_nr: Optional[str] = None
    webdewey_nr: Optional[str] = None
    webdewey_approved: Optional[str] = None
    noraf_id: Optional[str] = None
    concept_group: Optional[str] = None
    external_uri: Optional[str] = None
    nationality: Optional[str] = None
    nationality_entities: List[BibbiEntity] = field(default_factory=list)
    date: Optional[str] = None
    work_title: Optional[str] = None
    qualifier: Optional[str] = None
    detail: Optional[str] = None
    bs_nasj_id: Optional[str] = None
    legislation: Optional[LanguageMap] = None
    broader: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    creator: Optional[BibbiEntity] = None
    original_language: Optional[str] = None
    original_year: Optional[str] = None
    name: Optional[LanguageMap] = None

    exact_match: List[str] = field(default_factory=list)

    # Type: DemographicGroup
    country: Optional[BibbiEntity] = None
    demographicGroup: Optional[BibbiEntity] = None
    country_name: Optional[str] = None  # Fallback when entity not found

    # Type: Geographic
    iso3166_2_code: Optional[str] = None
    marc21_code: Optional[str] = None
    demonym: Optional[str] = None

    scopeNote: Optional[str] = None


class EntityIndex:

    def __init__(self):
        self.indices = {
            'label+entity_type': {},
            'label+source_type': {},
            'local_id+entity_type': {},
        }

    def add_label(self, label: LanguageMap, entity: Entity):
        label_str = label.nb.lower()
        key = label_str + '@' + entity.type
        self.add_to('label+entity_type', key, entity.id)

    def add_to(self, idx, key, eid):
        if key not in self.indices[idx]:
            self.indices[idx][key] = []
        self.indices[idx][key].append(eid)

    def find(self, label: str = None, entity_type=None, source_type=None, local_id=None) -> list:
        """
        Find an entity, either by label + entity type, or label + source_type, or local_id + entity_type

        Args:
            label: The entity's label
            entity_type: The type of the
            source_type: The source type, e.g.
            local_id: Originating table primary key

        Returns:

        """
        if label is not None:
            label = label.lower()
            if entity_type is not None:
                return self.indices['label+entity_type'].get(label + '@' + entity_type) or []
            # if source_type is not None:
            #     return self.indices['label+source_type'].get(label + '@' + source_type) or []
        elif local_id is not None:
            if entity_type is not None:
                return self.indices['local_id+entity_type'].get(local_id + '@' + entity_type) or []
        raise ValueError('Invalid argument combination')

    def add_entity(self, entity):
        self.add_to('local_id+entity_type', entity.local_id + '@' + entity.type, entity.id)
        if entity.pref_label.nb is not None:
            self.add_label(entity.pref_label, entity)
        for alt_label in entity.alt_labels:
            self.add_label(alt_label, entity)


class EntityCollection:

    def __init__(self, vocabulary_code, members=None):
        self._members: Dict[str, Entity] = members or {}
        self.index = EntityIndex()
        self.vocabulary_code = vocabulary_code

    def __len__(self) -> int:
        return len(self._members)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._members.values())

    def add(self, entity: Entity):
        self._members[entity.id] = entity

    def get(self, entity_id: str, default=None):
        return self._members.get(entity_id, default)

    def find(self, **kwargs):
        return [self.get(entity_id) for entity_id in self.index.find(**kwargs)]

    def find_first(self, **kwargs) -> Optional[Entity]:
        results = self.find(**kwargs)
        return results[0] if len(results) else None

    def filter(self, filter_fn) -> EntityCollection:
        return EntityCollection(self.vocabulary_code, {k: v for k, v in self._members.items() if filter_fn(v)})

    def update_index(self):
        self.index = EntityIndex()
        for entity_id, entity in self._members.items():
            self.index.add_entity(entity)

    def import_table(self, table: PromusTable):
        n = 0
        for entity in table.make_entities():
            self.add(entity)
            n += 1
        log.info('Constructed %d entities from: %s', n, table.type)

    def get_last_modified(self):
        last_modified = datetime(2000, 1, 1, 0, 0, 0)
        for entity in self._members.values():
            if isinstance(entity, BibbiEntity) and entity.modified is not None:
                if entity.modified > last_modified:
                    last_modified = entity.modified
        log.info('Concept scheme (%d members) last modified: %s', len(self._members), last_modified.isoformat())
        return last_modified
