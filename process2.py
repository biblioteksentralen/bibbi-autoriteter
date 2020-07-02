import os

import bonobo
from bonobo.constants import NOT_MODIFIED

from bibbi.db import Db
from bonobo.config import use
from dotenv import load_dotenv
import logging

from bibbi.entity_service import ConceptSchemeCollection, BibbiEntity, BsNasjEntity, ConceptScheme, Entity
from bibbi.promus_cache import PromusCache
from bibbi.promus_service import PromusService, TopicTable, GeographicTable, GenreTable, CorporationTable, \
    PersonTable, NationalityTable, PromusTable
from bibbi.serializers.rdf import RdfSerializers, RdfSerializer

log = logging.getLogger(__name__)


tables = [
    NationalityTable,
    # TopicTable,
    # GeographicTable,
    GenreTable,
    # CorporationTable,
    # PersonTable,
]

# ------------------------------------------------------------------------------------------------

@use('promus')
def extract_from_db(promus: PromusService):
    for table in tables:
        yield promus.extract(table())


@use('promus_cache')
def extract_from_cache(promus_cache: PromusCache):
    for table in tables:
        yield promus_cache.extract(table())


@use('promus_cache')
def load_cache(table: PromusTable, promus_cache: PromusCache):
    promus_cache.store(table)
    return table


@use('concept_schemes')
def transform_to_entities(table: PromusTable, concept_schemes: ConceptSchemeCollection):
    # We need to ensure that all references have been added to each entity,
    # before passing them on.
    if isinstance(table, NationalityTable):
        concept_schemes.set_nationality_map(table.short_name_dict())

    return concept_schemes.get(table=table).import_table(table)


@use('concept_schemes')
def collect_entities(concept_scheme, concept_schemes: ConceptSchemeCollection):
    if concept_schemes.tables_imported() == len(tables):
        log.info('DONE')
        for concept_scheme in concept_schemes:
            for entity in concept_scheme:
                yield entity


@use('concept_schemes')
def add_relations(entity: Entity, concept_schemes: ConceptSchemeCollection):
    concept_schemes.get(entity=entity).add_relations(entity, concept_schemes.nationality_map)
    return entity


def remove_unused_entities(entity: Entity):
    if not isinstance(entity, BibbiEntity):
        return entity
    if entity.items_as_entry > 0 or entity.items_as_subject > 0:
        return entity


class SerializeAsRdf:

    def __init__(self, serializer):
        self.serializer = serializer

    def __call__(self, entity: Entity):
        self.serializer.add(entity)
        return NOT_MODIFIED


def get_graph(use_cache: bool = False, remove_unused: bool = False, **kwargs):
    """
    This function builds the graph that needs to be executed.

    :return: bonobo.Graph
    """
    graph = bonobo.Graph()

    # Tranform chain
    graph.add_chain(
        transform_to_entities,
        collect_entities,
        add_relations,
        _input=None,
        _name='transform'
    )

    # Load chain
    # serializer = RdfSerializer(
    #     graph=concept_schemes.get(code='bs-nasj').get_graph(),
    #     includes=[
    #         'src/bs-nasj.scheme.ttl',
    #     ],
    #     products=[{
    #         'filename': 'bs-nasj.nt',
    #         'format': 'ntriples',
    #     }]
    # )
    # graph.add_chain(
    #     SerializeAsRdf(serializer),
    #     _input=None,
    #     _name='serialize'
    # )
    #
    # # Extract chain
    # if use_cache:
    #     graph.add_chain(
    #         extract_from_cache,
    #         _output='transform'
    #     )
    # else:
    #     graph.add_chain(
    #         extract_from_db,
    #         load_cache,
    #         _output='transform'
    #     )
    #
    # if remove_unused:
    #     remove_unused_entities_node = graph.add_node(
    #         remove_unused_entities,
    #         _input=add_relations
    #     )
    #
    #     graph.get_cursor('transform') >> remove_unused_entities_node
    #     graph.get_cursor(remove_unused_entities_node) >> 'serialize'
    # else:
    #     graph.get_cursor('transform') >> 'serialize'
    #

    return graph


def get_services(use_cache: bool = False, **kwargs):
    """
    This function builds the services dictionary, which is a simple dict of names-to-implementation used
    by bonobo for runtime injection.

    It will be used on top of the defaults provided by bonobo (fs, http, ...). You can override those defaults,
    or just let the framework define them. You can also define your own services and naming is up to you.

    :return: dict
    """
    db = Db(**{
        'server': os.getenv('DB_SERVER'),
        'database': os.getenv('DB_DB'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
    })
    promus = PromusService(connection=db)
    promus_cache = PromusCache('cache')
    concept_schemes = ConceptSchemeCollection({
        'bibbi': ConceptScheme(BibbiEntity),
        'bs-nasj': ConceptScheme(BsNasjEntity),
    })

    return {
        'promus': promus,
        'promus_cache': promus_cache,
        'concept_schemes': concept_schemes,
    }


if __name__ == '__main__':
    load_dotenv()
    parser = bonobo.get_argument_parser()
    parser.add_argument('--use-cache', action='store_true', default=False)
    parser.add_argument('--remove-unused', action='store_true', default=False)
    with bonobo.parse_args(parser) as options:
        bonobo.run(
            get_graph(**options),
            services=get_services(**options)
        )
