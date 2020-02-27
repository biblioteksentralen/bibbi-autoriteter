import logging
import re
import rdflib
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, SKOS, DCTERMS, XSD
from otsrdflib import OrderedTurtleSerializer
import skosify

log = logging.getLogger(__name__)

# namespaces: bibbi eller bibsent ?
ISOTHES = Namespace('http://purl.org/iso25964/skos-thes#')
ONTO = Namespace('http://schema.bibbi.dev/')

class Graph:

    class_order = [
        SKOS.ConceptScheme,
        SKOS.Concept,
        ISOTHES.ThesaurusArray,
    ]

    def __init__(self, entity_space, concept_scheme, group_space):

        self.scheme_uri = URIRef(concept_scheme)
        self.entity_ns = Namespace(entity_space)
        self.group_ns = Namespace(group_space)

        # Note to self: Memory store is slightly faster than IOMemory store, but we cannot load turtle files into it,
        # so just use the more convenient IOMemory store for now.
        # rdflib.plugin.register('Memory', rdflib.store.Store,
        # 'rdflib.plugins.memory', 'Memory')
        self.graph = rdflib.Graph('IOMemory')

    def uri(self, entity):
        return self.entity_ns[entity.id]

    def webdewey_uri(self, entity):
        if entity.webdewey_nr is None:
            return None
        if entity.webdewey_approved != '1':
            # Skip numbers that are not approved
            return None
        nr = re.sub('[^0-9.]', '', entity.webdewey_nr)
        if not re.match(r'^[0-9]{3}(\.[0-9]*)?$', nr):
            log.warning('Invalid WebDewey Number: %s', entity.webdewey_nr)
            return None
        return URIRef('http://dewey.info/class/%s/e23/' % nr)

    def add(self, entity, prop, val):
        self.graph.add((self.uri(entity), prop, val))

    def add_entities(self, entities, include_unused=True):
        for entity in entities:
            if include_unused is True or entity.items_as_entry > 0 or entity.items_as_subject > 0:
                self.add_entity(entity)
        log.info('Generated graph with %d triples', len(self.graph))

    def add_mappings(self, entities):
        for entity in entities:
            self.add_entity_mappings(entity)
        log.info('Generated graph with %d triples', len(self.graph))

    def add_entity_mappings(self, entity):
        webdewey_uri = self.webdewey_uri(entity)
        if webdewey_uri is not None:
            # self.add(entity, ONTO.webDeweyNr, Literal(entity.webdewey_nr)))
            # ONTO.webdewey ?
            self.add(entity, SKOS.closeMatch, webdewey_uri)

        # Note: data.unit.no is not live, nor is data.bibsys.no
        # if entity.noraf_id is not None:
        #     self.add(entity, SKOS.exactMatch, 'https://data.unit.no/authority/noraf/' + entity.noraf_id)

    def add_entity(self, entity):
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
            'qualifier':{
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
        }

        # ------------------------------------------------------------
        # Base data: Type, Scheme, Labels, Creation/Modification dates

        if entity.type not in types:
            log.warning('Skipping entity of unknown entity type: %s', entity.type)
            print(entity.data)
            return

        self.add(entity, RDF.type, types[entity.type]['uri'])

        self.graph.add((types[entity.type]['group'], SKOS.member, self.uri(entity)))

        if '-' in entity.id:
            self.add(entity, RDF.type, ONTO.EntityCandidate)
        else:
            self.add(entity, RDF.type, ONTO.Entity)

        self.add(entity, SKOS.inScheme, self.scheme_uri)

        for label in entity.preferred_label.values():
            self.add(entity, SKOS.prefLabel, Literal(label.value, label.lang))

        for labels in entity.alternative_labels.values():
            for label in labels:
                self.add(entity, SKOS.altLabel, Literal(label.value, label.lang))

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
        # Components

        if entity.qualifier is not None:
            self.add(entity, ONTO.qualifier, Literal(entity.qualifier))

        if entity.detail is not None:
            self.add(entity, ONTO.detail, Literal(entity.detail))

        if entity.legislation is not None:
            # Temporary solution. We should entify these!
            self.add(entity, ONTO.legislation, Literal(entity.legislation['nb'], 'nb'))
            self.add(entity, ONTO.legislation, Literal(entity.legislation['nn'], 'nn'))

        for component in entity.components:
            # SKOS.broader is perhaps a bit questionable here?
            if entity.id != component.id:
                self.add(entity, SKOS.broader, self.uri(component))

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

    def load(self, filename, format):
        self.graph.load(filename, format=format)

    def serialize_nt(self, filename):
        # The nt serialization is the most efficient (by far)
        self.graph.serialize(filename, format='nt')
        log.info('Serialized graph as: %s', filename)

    def serialize_ttl(self, filename):
        # Ordered Turtle serialization is super slow, but produces a nice-looking output
        serializer = OrderedTurtleSerializer(self.graph)
        serializer.class_order = self.class_order
        with open(filename, 'wb') as fp:
            serializer.serialize(fp)
        log.info('Serialized graph as: %s', filename)

    def triples(self, s=None, p=None, o=None):
        return self.graph.triples((s, p, o))
