from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Iterable, List

import rdflib
import os
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, SKOS, DCTERMS, XSD
from otsrdflib import OrderedTurtleSerializer
import skosify

from ..util import ensure_parent_dir_exists
from ..constants import TYPE_PERSON, TYPE_TOPICAL, TYPE_GEOGRAPHIC, TYPE_GENRE, TYPE_PERSON, TYPE_CORPORATION, \
    TYPE_TITLE, TYPE_LAW, TYPE_CORPORATION_SUBJECT, TYPE_PERSON_SUBJECT, TYPE_QUALIFIER, TYPE_COMPLEX, \
    TYPE_TITLE_SUBJECT, TYPE_NATION, TYPE_DEMOGRAPHIC_GROUP
from ..entity_service import Entity, BibbiEntity, Nation

log = logging.getLogger(__name__)

# namespaces: bibbi eller bibsent ?
ISOTHES = Namespace('http://purl.org/iso25964/skos-thes#')
ONTO = Namespace('http://schema.bibbi.dev/')


def initialize_filters(filters: list) -> dict:
    out = {}
    for filter_name in filters:
        if match := re.match('^(.+?):(.+)$', filter_name):
            filter_name = match.group(1)
            filter_value = match.group(2)
            out[filter_name] = lambda entity: getattr(entity, filter_name) == filter_value
        else:
            raise ValueError('Unknown filter: %s' % filter_name)
    return out


@dataclass
class ConceptScheme:
    uri: URIRef
    modified: datetime


class RdfSerializer:

    def __init__(self, graph=None):
        self.graph = graph or Graph()
        self.staged = []
        self.concept_schemes: List[ConceptScheme] = []

    def load(self, filename, format='turtle'):
        self.graph.load(filename, format=format)
        return self

    def set_concept_schemes(self, concept_schemes: List[ConceptScheme]):
        self.concept_schemes = concept_schemes
        for concept_scheme in concept_schemes:
            self.graph.add_raw(
                concept_scheme.uri,
                DCTERMS.modified,
                Literal(concept_scheme.modified.strftime('%Y-%m-%dT%H:%M:%S'), datatype=XSD.dateTime)
            )

        return self

    def add_entities(self, entities: Iterable[Entity]):
        self.staged += list(entities)
        return self

    def serialize(self, target, format):
        self.build_graph()
        log.info('Built graph with %d triples', len(self.graph))
        self.graph.serialize(target, format)
        return self

    def build_graph(self):
        pass

    def skosify(self):
        s0 = len(self.graph)
        self.graph.skosify()
        s1 = len(self.graph)
        log.info('Skosify: %d -> %d triples', s0, s1)


class RdfEntitySerializer(RdfSerializer):

    def build_graph(self):
        self.graph.add_entities(self.staged, self.concept_schemes)
        self.skosify()

        # if config['delete_unused']:
        #     log.info('Deleting unused')
        #     triples_before = len(graph.graph)
        #     graph.delete_unused()
        #     triples_after = len(graph.graph)
        #     log.info('Triples changed from %d to %d', triples_before, triples_after)


class RdfEntityAndMappingSerializer(RdfEntitySerializer):

    def build_graph(self):
        self.graph.add_entities(self.staged, self.concept_schemes)
        self.graph.add_mappings(self.staged)
        self.skosify()


class RdfMappingSerializer(RdfSerializer):
    reverse = False

    def build_graph(self):
        self.graph.add_mappings(self.staged, reverse=self.reverse)


class RdfReverseMappingSerializer(RdfMappingSerializer):
    reverse = True


class Graph:

    class_order = [
        SKOS.ConceptScheme,
        SKOS.Concept,
        ISOTHES.ThesaurusArray,
    ]

    def __init__(self):
        # Note to self: Memory store is slightly faster than IOMemory store, but we cannot load turtle files into it,
        # so just use the more convenient IOMemory store for now.
        # rdflib.plugin.register('Memory', rdflib.store.Store,
        # 'rdflib.plugins.memory', 'Memory')
        self.graph = rdflib.Graph('IOMemory')

    def __len__(self) -> int:
        return len(self.graph)

    def add(self, entity: Entity, prop, val):
        self.graph.add((entity.uri(), prop, val))

    def add_raw(self, s, p, o):
        self.graph.add((s, p, o))

    def add_mappings(self, entities: Iterable[Entity], reverse: bool = False):
        for entity in entities:
            self.add_entity_mappings(entity, reverse)

    def add_entity_mappings(self, entity: Entity, reverse: bool = False):

        if entity.webdewey_nr is not None and entity.webdewey_approved == '1':
            # Note that we skip numbers that are not approved!
            webdewey_nr = re.sub('[^0-9.]', '', entity.webdewey_nr)
            webdewey_uri = URIRef('http://dewey.info/class/%s/e23/' % webdewey_nr)
            if reverse:
                self.add_raw(webdewey_uri, SKOS.closeMatch, entity.uri())
            else:
                self.add_raw(entity.uri(), SKOS.closeMatch, webdewey_uri)

        if entity.noraf_id is not None:
            # Note: authority.bibsys.no doesn't deliver RDF, and livedata.bibsys.no is no more.
            uri = URIRef('http://authority.bibsys.no/authority/rest/authorities/html/' + entity.noraf_id)
            self.add(entity, SKOS.exactMatch, uri)

    def add_entities(self, entities: Iterable[Entity], concept_schemes: List[ConceptScheme]):
        for entity in entities:
            self.add_entity(entity, concept_schemes)

    def add_entity(self, entity: Entity, concept_schemes: List[ConceptScheme]):
        types = {
            TYPE_TOPICAL: ONTO.Topic,
            TYPE_GEOGRAPHIC: ONTO.Place,
            TYPE_GENRE: ONTO.FormGenre,
            TYPE_CORPORATION: ONTO.Corporation,
            TYPE_PERSON: ONTO.Person,
            TYPE_CORPORATION_SUBJECT: ONTO.CorporationSubject,
            TYPE_PERSON_SUBJECT: ONTO.PersonSubject,
            TYPE_QUALIFIER: ONTO.Qualifier,
            TYPE_COMPLEX: ONTO.Complex,
            TYPE_LAW: ONTO.Law,
            TYPE_TITLE: ONTO.Title,
            TYPE_TITLE_SUBJECT: ONTO.TitleAsSubject,
            # TYPE_NATION: ONTO.Nation,
            TYPE_DEMOGRAPHIC_GROUP: ONTO.DemographicGroup,
        }

        # ------------------------------------------------------------
        # Base data: Type, Scheme, Labels, Creation/Modification dates

        if entity.type not in types:
            log.warning('Skipping entity of unknown entity type: %s', entity.type)
            print(entity.data)
            return

        self.add(entity, RDF.type, types[entity.type])

        # self.graph.add((types[entity.type]['group'], SKOS.member, entity.uri()))

        if '-' in entity.id:
            self.add(entity, RDF.type, ONTO.EntityCandidate)
        else:
            self.add(entity, RDF.type, ONTO.Entity)

        for concept_scheme in concept_schemes:
            self.add(entity, SKOS.inScheme, concept_scheme.uri)

        for lang, value in entity.pref_label.items():
            self.add(entity, SKOS.prefLabel, Literal(value, lang))

        for label in entity.alt_labels:
            for lang, value in label.items():
                self.add(entity, SKOS.altLabel, Literal(value, lang))

        # if isinstance(entity, Nationality):
        #     # TODO: How should we organize entity-specific formatters?
        #     # As methods on the Entity classes?? Will that increase memory use? Not necessarily. TEST!
        #     if entity.country_name is not None:
        #         self.add(entity, ONTO.country, Literal(entity.country_name))
        #
        #     if entity.label_short is not None:
        #         self.add(entity, ONTO.abbreviation, entity.label_short)
        #
        #     if entity.marc21_code is not None:
        #         self.add(entity, ONTO.marcCode, entity.marc21_code)

        if isinstance(entity, BibbiEntity):

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

            # if entity.nationality is not None:
            #    self.add(entity, ONTO.nationality, Literal(entity.nationality))

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
            for other_entity in entity.broader:
                self.add(entity, SKOS.broader, other_entity.uri())

            for other_entity_uri in entity.exact_match:
                self.add(entity, SKOS.exactMatch, URIRef(other_entity_uri))

            # ------------------------------------------------------------
            # Misc

            if entity.qualifier is not None:
                self.add(entity, ONTO.qualifier, Literal(entity.qualifier))

            if entity.detail is not None:
                self.add(entity, ONTO.detail, Literal(entity.detail))

            if entity.work_title is not None:
                self.add(entity, ONTO.workTitle, Literal(entity.work_title))

            if entity.legislation is not None:
                # Using Literal is a temporary solution. Should replace with
                # Country entities.
                self.add(entity, ONTO.legislation, Literal(entity.legislation.nb, 'nb'))
                self.add(entity, ONTO.legislation, Literal(entity.legislation.nn, 'nn'))

            if entity.type == TYPE_DEMOGRAPHIC_GROUP:
                # Temporary solution, we should have groups on the entity instead.
                self.add_raw(URIRef('http://id.bibbi.dev/bibbi/group/nasj'), SKOS.member, entity.uri())

            for nationality in entity.nationality_entities:
                self.add(entity, ONTO.nationality, nationality.uri())

            if entity.country is not None:
                self.add(entity, ONTO.country, entity.country.uri())

            if entity.demographicGroup is not None:
                self.add(entity, ONTO.demographicGroup, entity.demographicGroup.uri())

            if entity.bs_nasj_id is not None:
                self.add(entity, ONTO.abbreviation, Literal(entity.bs_nasj_id))

            if entity.demonym is not None:
                self.add(entity, ONTO.demonym, Literal(entity.demonym))

            if entity.iso3166_2_code is not None:
                self.add(entity, ONTO.iso3166, Literal(entity.iso3166_2_code))
                self.add(entity, RDF.type, ONTO.Country)

            if entity.marc21_code is not None:
                self.add(entity, ONTO.marcCountry, URIRef('http://id.loc.gov/vocabulary/countries/' + entity.marc21_code))

            if entity.scopeNote is not None:
                self.add(entity, SKOS.scopeNote, Literal(entity.scopeNote, 'nb'))


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
