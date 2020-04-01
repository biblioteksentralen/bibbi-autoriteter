from __future__ import annotations
import logging
import re
from typing import TYPE_CHECKING, Optional

import rdflib
import os
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, SKOS, DCTERMS, XSD
from otsrdflib import OrderedTurtleSerializer
import skosify

from ..util import ensure_parent_dir_exists
from ..constants import TYPE_PERSON, TYPE_TOPIC, TYPE_GEOGRAPHIC, TYPE_PERSON, TYPE_CORPORATION

if TYPE_CHECKING:
    from ..entities import Entity, Entities

# TYPE_TOPIC = 'topic'
# TYPE_GEOGRAPHIC = 'geographic'
# TYPE_CORPORATION = 'corporation'
# TYPE_PERSON = 'person'
# TYPE_QUALIFIER = 'qualifier'
# TYPE_COMPLEX = 'complex'
# TYPE_LAW = 'law'

log = logging.getLogger(__name__)

# namespaces: bibbi eller bibsent ?
ISOTHES = Namespace('http://purl.org/iso25964/skos-thes#')
ONTO = Namespace('http://schema.bibbi.dev/')


def initialize_filters(filters: list) -> dict:
    out = {}
    for filter_name in filters:
        if filter_name == 'type:topic':
            out[filter_name] = lambda entity: entity.source_type == TYPE_TOPIC
        elif filter_name == 'type:geographic':
            out[filter_name] = lambda entity: entity.source_type == TYPE_GEOGRAPHIC
        elif filter_name == 'type:person':
            out[filter_name] = lambda entity: entity.source_type == TYPE_PERSON
        elif filter_name == 'type:corporation':
            out[filter_name] = lambda entity: entity.source_type == TYPE_CORPORATION
        else:
            raise ValueError('Unknown filter: %s' % filter_name)
    return out


class RdfSerializers:

    def __init__(self, config: dict):
        self.serializers = []

        typemap = {
            'entities': RdfEntitySerializer,
            'entities+mappings': RdfEntityAndMappingSerializer,
            'forward_mappings': RdfMappingSerializer,
            'reverse_mappings': RdfReverseMappingSerializer,
        }

        for variant in config['variants']:
            extras = {k: v for k, v in variant.items() if k not in ['type']}
            serializer_type = typemap[variant['type']]
            serializer = serializer_type(graph_options=config['graph'],
                                         includes=config.get('includes', []),
                                         **extras)
            self.serializers.append(serializer)

    def serialize(self, entities: Entities, destination_dir: str):
        for serializer in self.serializers:
            log.info('Starting %s', type(serializer).__name__)
            serializer.serialize(entities, destination_dir)


class RdfSerializer:

    def __init__(self, graph_options, includes=[], filters=[], products=[]):
        self.graph = Graph(**graph_options)
        self.includes = includes
        self.filters = initialize_filters(filters)
        self.products = products

    def filter(self, entities: Entities):
        for filter_name, filter_fn in self.filters.items():
            before = len(entities)
            entities = entities.filter(filter_fn)
            after = len(entities)
            log.info('Filter "%s": %d -> %d entities', filter_name, before, after)
        return entities

    def serialize(self, entities: Entities, destination_dir: str):
        self.load_includes()
        entities = self.filter(entities)
        self.populate_graph(entities)
        log.info('Generated mappings graph with %d triples', len(self.graph))
        self.store(destination_dir)

    def load_includes(self):
        pass

    def skosify(self):
        s0 = len(self.graph)
        self.graph.skosify()
        s1 = len(self.graph)
        log.info('Skosify: %d -> %d triples', s0, s1)

    def store(self, destination_dir: str):
        for product in self.products:
            dest_path = os.path.join(destination_dir, product['filename'])
            self.graph.serialize(dest_path, product['format'])
            log.info('Wrote %s', dest_path)

    def populate_graph(self, entities: Entities):
        pass


class RdfEntitySerializer(RdfSerializer):

    def load_includes(self):
        for filename in self.includes:
            self.graph.load(filename, format='turtle')

    def populate_graph(self, entities: Entities):
        self.graph.add_entities(entities)
        self.skosify()

        # if config['delete_unused']:
        #     log.info('Deleting unused')
        #     triples_before = len(graph.graph)
        #     graph.delete_unused()
        #     triples_after = len(graph.graph)
        #     log.info('Triples changed from %d to %d', triples_before, triples_after)


class RdfEntityAndMappingSerializer(RdfEntitySerializer):

    def populate_graph(self, entities: Entities):
        self.graph.add_entities(entities)
        self.graph.add_mappings(entities)
        self.skosify()


class RdfMappingSerializer(RdfSerializer):
    reverse = False

    def populate_graph(self, entities: Entities):
        self.graph.add_mappings(entities, reverse=self.reverse)


class RdfReverseMappingSerializer(RdfMappingSerializer):
    reverse = True


class Graph:

    class_order = [
        SKOS.ConceptScheme,
        SKOS.Concept,
        ISOTHES.ThesaurusArray,
    ]

    def __init__(self, concept_scheme: str, entity_ns: str, group_ns: str):

        self.scheme_uri = URIRef(concept_scheme)
        self.entity_ns = Namespace(entity_ns)
        self.group_ns = Namespace(group_ns)

        # Note to self: Memory store is slightly faster than IOMemory store, but we cannot load turtle files into it,
        # so just use the more convenient IOMemory store for now.
        # rdflib.plugin.register('Memory', rdflib.store.Store,
        # 'rdflib.plugins.memory', 'Memory')
        self.graph = rdflib.Graph('IOMemory')

    def __len__(self) -> int:
        return len(self.graph)

    def uri(self, entity: Entity) -> URIRef:
        return self.entity_ns[entity.id]

    def add(self, entity: Entity, prop, val):
        self.graph.add((self.uri(entity), prop, val))

    def add_raw(self, s, p, o):
        self.graph.add((s, p, o))

    def add_mappings(self, entities: Entities, reverse: bool = False):
        for entity in entities:
            self.add_entity_mappings(entity, reverse)

    def add_entity_mappings(self, entity: Entity, reverse: bool = False):

        if entity.webdewey_nr is not None and entity.webdewey_approved == '1':
            # Note that we skip numbers that are not approved!
            webdewey_nr = re.sub('[^0-9.]', '', entity.webdewey_nr)
            webdewey_uri = URIRef('http://dewey.info/class/%s/e23/' % webdewey_nr)
            if reverse:
                self.add_raw(webdewey_uri, SKOS.closeMatch, self.uri(entity))
            else:
                self.add_raw(self.uri(entity), SKOS.closeMatch, webdewey_uri)

        if entity.noraf_id is not None:
            # Note: authority.bibsys.no doesn't deliver RDF, and livedata.bibsys.no is no more.
            uri = URIRef('http://authority.bibsys.no/authority/rest/authorities/html/' + entity.noraf_id)
            self.add(entity, SKOS.exactMatch, uri)

    def add_entities(self, entities: Entities):
        for entity in entities:
            self.add_entity(entity)

    def add_entity(self, entity: Entity):
        types = {
            'topic': {
                'uri': ONTO.Topic,
                'group': self.group_ns.topic,
            },
            'geographic': {
                'uri': ONTO.Place,
                'group': self.group_ns.place,
            },
            'corporation': {
                'uri': ONTO.Corporation,
                'group': self.group_ns.corporation,
            },
            'person': {
                'uri': ONTO.Person,
                'group': self.group_ns.person,
            },
            'corporation-topic': {
                'uri': ONTO.CorporationTopic,
                'group': self.group_ns.corporationTopic,
            },
            'person-topic': {
                'uri': ONTO.PersonTopic,
                'group': self.group_ns.personTopic,
            },
            'qualifier': {
                'uri': ONTO.Qualifier,
                'group': self.group_ns.qualifier,
            },
            'complex': {
                'uri': ONTO.Complex,
                'group': self.group_ns.complex,
            },
            'law': {
                'uri': ONTO.Law,
                'group': self.group_ns.law,
            },
            'title': {
                'uri': ONTO.Title,
                'group': self.group_ns.title,
            },
        }

        # ------------------------------------------------------------
        # Base data: Type, Scheme, Labels, Creation/Modification dates

        if entity.type not in types:
            log.warning('Skipping entity of unknown entity type: %s', entity.type)
            print(entity.data)
            return

        self.add(entity, RDF.type, types[entity.type]['uri'])

        # self.graph.add((types[entity.type]['group'], SKOS.member, self.uri(entity)))

        if '-' in entity.id:
            self.add(entity, RDF.type, ONTO.EntityCandidate)
        else:
            self.add(entity, RDF.type, ONTO.Entity)

        self.add(entity, SKOS.inScheme, self.scheme_uri)

        for lang, value in entity.pref_label.items():
            self.add(entity, SKOS.prefLabel, Literal(value, lang))

        for label in entity.alt_label:
            for lang, value in label.items():
                self.add(entity, SKOS.altLabel, Literal(value, lang))

        if entity.created is not None:
            value = entity.created.strftime('%Y-%m-%dT%H:%M:%S')
            self.add(entity, DCTERMS.created, Literal(value, datatype=XSD.dateTime))

        if entity.modified is not None:
            value = entity.modified.strftime('%Y-%m-%dT%H:%M:%S')
            self.add(entity, DCTERMS.modified, Literal(value, datatype=XSD.dateTime))

        if entity.items_as_entry is not None:
            self.add(entity, ONTO.itemsAsEntry, Literal(entity.items_as_entry, datatype=XSD.integer))

        if entity.items_as_subject is not None:
            self.add(entity, ONTO.itemsAsSubject, Literal(entity.items_as_subject, datatype=XSD.integer))

        if entity.noraf_id is not None:
            self.add(entity, ONTO.noraf, Literal(entity.noraf_id))

        if entity.nationality is not None:
            self.add(entity, ONTO.nationality, Literal(entity.nationality))

        if entity.date is not None:
            dates = entity.date.split('-')
            if entity.type == TYPE_PERSON:
                if len(dates[0]):
                    self.add(entity, ONTO.birthDate, Literal(dates[0]))
                if len(dates) > 1 and len(dates[1]):
                    self.add(entity, ONTO.deathDate, Literal(dates[1]))

        # ------------------------------------------------------------
        # Dewey

        if entity.ddk5_nr is not None:
            self.add(entity, ONTO.ddk5, Literal(entity.ddk5_nr))

        if entity.webdewey_nr is not None:
            if entity.webdewey_approved == '1':
                self.add(entity, ONTO.webdewey, Literal(entity.webdewey_nr))
            else:
                self.add(entity, ONTO.webdeweyDraft, Literal(entity.webdewey_nr))

        self.add_entity_mappings(entity)

        # ------------------------------------------------------------
        # Relations
        for broader_entity in entity.broader:
            self.add(entity, SKOS.broader, self.uri(broader_entity))

        # ------------------------------------------------------------
        # Misc

        if entity.qualifier is not None:
            self.add(entity, ONTO.qualifier, Literal(entity.qualifier))

        if entity.detail is not None:
            self.add(entity, ONTO.detail, Literal(entity.detail))

        if entity.legislation is not None:
            # Temporary solution. We should entify these!
            self.add(entity, ONTO.legislation, Literal(entity.legislation['nb'], 'nb'))
            self.add(entity, ONTO.legislation, Literal(entity.legislation['nn'], 'nn'))

    def skosify(self):
        # Infer parent classes
        skosify.infer.rdfs_classes(self.graph)
        skosify.infer.rdfs_properties(self.graph)
        skosify.infer.skos_related(self.graph)
        # skosify.infer.skos_topConcept(self.graph):
        skosify.infer.skos_hierarchical(self.graph, narrower=True)
        skosify.infer.skos_symmetric_mappings(self.graph, related=False)
        # skosify.infer.skos_transitive(self.graph, narrower=True)

    def delete_unused(self):
        """
        Note: This is very slow :/
        """
        before = len(self.graph)
        query = """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX bs: <http://schema.bibbi.dev/>

        DELETE {
            ?c ?p1 ?o1 .
            ?c2 ?p2 ?c .
        }
        WHERE {
            ?c a bs:Entity ;
                bs:itemCount 0 ;
                ?p1 ?o1 .
            OPTIONAL { ?c2 ?p2 ?c . }
            FILTER NOT EXISTS {
                ?c skos:narrower ?c3 .
                # ?c skos:narrower+ ?c3 ; ?c3 bs:itemCount ?i3 . FILTER(?i3 != 0)
            }
        }
        """
        self.graph.update(query)
        after = len(self.graph)
        log.info('Deleted %d triples for unused concepts' % (before - after))

    def load(self, filename: str, format: str):
        self.graph.load(filename, format=format)

    def serialize(self, filename: str, file_format: str):
        if file_format == 'ntriples':
            self.serialize_nt(filename)
        elif file_format == 'turtle':
            self.serialize_ttl(filename)
        else:
            raise ValueError('Invalid file format')

    def serialize_nt(self, filename: str):
        # The nt serialization is the most efficient (by far)
        ensure_parent_dir_exists(filename)
        self.graph.serialize(filename, format='nt')
        log.info('Serialized graph as: %s', filename)

    def serialize_ttl(self, filename: str):
        # Ordered Turtle serialization is super slow, but produces a nice-looking output
        ensure_parent_dir_exists(filename)
        serializer = OrderedTurtleSerializer(self.graph)
        serializer.class_order = self.class_order
        with open(filename, 'wb') as fp:
            serializer.serialize(fp)
        log.info('Serialized graph as: %s', filename)

    def triples(self, s=None, p=None, o=None):
        return self.graph.triples((s, p, o))
