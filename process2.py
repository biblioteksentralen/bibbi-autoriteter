import os

import bonobo
from bibbi.db import Db
from bonobo.config import use
from dotenv import load_dotenv
import logging

from bibbi.entity_service import ConceptSchemeCollection, BibbiEntity, BsNasjEntity, ConceptScheme, Entity
from bibbi.promus_cache import PromusCache
from bibbi.promus_service import PromusService, TopicTable, GeographicTable, GenreTable, CorporationTable, \
    PersonTable, NationalityTable, PromusTable

log = logging.getLogger(__name__)


tables = [
    NationalityTable,
    TopicTable,
    GeographicTable,
    GenreTable,
    CorporationTable,
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
    return concept_schemes.get(table).import_table(table)


@use('concept_schemes')
def collect_entities(concept_scheme, concept_schemes: ConceptSchemeCollection):
    if concept_schemes.tables_imported() == len(tables):
        log.info('DONE')
        for entity in concept_schemes:
            yield entity


@use('concept_schemes')
def add_relations(entity: Entity, concept_schemes: ConceptSchemeCollection):
    return entity

# for scheme in self.schemes.values():
#     scheme.remove_invalid_entries()
#     log.info('Removed invalid entries')
#
#     scheme.add_to_lookup_table()
#     log.info('Updated lookup table')
#
#     country_tables = repo.get(NationalityTable)
#     scheme.generate_relations(country_table=country_tables[0])
#     log.info('Generated relations')

# ------------------------------------------------------------------------------------------------

def get_graph(use_cache: bool = False):
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

    # Extract chain
    if use_cache:
        graph.add_chain(
            extract_from_cache,
            _output='transform'
        )
    else:
        graph.add_chain(
            extract_from_db,
            load_cache,
            _output='transform'
        )

    return graph


def get_services(use_cache: bool = False):
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
    with bonobo.parse_args(parser) as options:
        bonobo.run(
            get_graph(**options),
            services=get_services(**options)
        )
