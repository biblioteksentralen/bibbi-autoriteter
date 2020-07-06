import argparse
import logging
import os
import sys
from functools import wraps
from time import time
from typing import Dict, List, Union, Callable, Optional

from rdflib import URIRef

from bibbi.wikidata_service import WikidataService

from bibbi.label import LabelFactory

from bibbi.serializers.rdf import RdfEntityAndMappingSerializer, RdfEntitySerializer, RdfReverseMappingSerializer, \
    ConceptScheme

from bibbi.constants import TYPE_TITLE_SUBJECT, TYPE_TITLE, TYPE_PERSON, TYPE_PERSON_SUBJECT, TYPE_CORPORATION_SUBJECT, \
    TYPE_DEMOGRAPHIC_GROUP, TYPE_GEOGRAPHIC, TYPE_GENRE, TYPE_TOPICAL, TYPE_CORPORATION
from dotenv import load_dotenv

from bibbi.db import Db
from bibbi.entity_service import BibbiEntity, Entity, EntityCollection, Nation
from bibbi.logging import configure_logging
from bibbi.promus_cache import PromusCache
from bibbi.promus_service import PromusService, GenreTable, PromusTable, PersonTable, TopicTable, \
    GeographicTable, CorporationTable, NationTable

log = logging.getLogger(__name__)


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        result = f(*args, **kw)
        te = time()
        log.info('%r took: %2.4f sec', f.__name__, te - ts)
        return result
    return wrap


PromusInterface = Union[PromusCache, PromusService]
TableDict = Dict[str, PromusTable]

# ------------------------------------------------------------------------------------------------
# Extract

@timing
def extract_tables(promus_adapter: PromusInterface, tables: List[Callable]) -> TableDict:
    tables = [table() for table in tables]
    return {table.type: promus_adapter.extract(table) for table in tables}


@timing
def update_cache(promus_cache: PromusCache, tables: TableDict) -> TableDict:
    for table in tables.values():
        promus_cache.store(table)
    return tables


# ------------------------------------------------------------------------------------------------
# Transform

@timing
def transform_to_entities(tables: TableDict, collections):
    for table in tables.values():
        collections[table.vocabulary_code].import_table(table)
    for collection in collections.values():
        collection.update_index()
    return collections


def warning(msg: str, entity: Entity):
    log.warning('%s: %s "%s"', msg, entity.id, entity.pref_label.nb)


def add_relation_to_main_entity(label_factory: LabelFactory, collection: EntityCollection, entity: BibbiEntity, entity_map: dict):
    """
    Hvis entiteten er en biautoritet av type <Tittel som emne>, sjekk først om vi finner
    den assosierte entiteten av type <Tittel>.

    Eksempel:
       Fra: 1084433 "Tolkien, John Ronald Reuel, eng., 1892-1973 - Humor - Ringenes herre"
       Til: 1062553 "Tolkien, John Ronald Reuel, eng., 1892-1973 - Ringenes herre"

    I Promus er det ingen relasjon mellom disse, annet enn at begge er knyttet til samme
    personentitet, via feltet "felles_id".

    I alle andre tilfeller, lager vi en relasjon fra biautoriteten til hovedautoriteten.
    """

    if entity.type in entity_map:
        broader = collection.index.find(
            label=label_factory.make(entity.row, include_subdivisions=False).nb,
            entity_type=entity_map[entity.type],
        )
        if len(broader) == 0:
            warning('<Tittel som emne> mangler assosiert <Tittel>', entity)
        elif len(broader) > 1:
            warning('<Tittel som emne> har mer enn én mulig <Tittel>', entity)
        else:
            entity.broader.append(collection.get(broader[0]))
            return True

    if entity.row.has('felles_id') and entity.row.get('felles_id') != entity.row.get('bibsent_id'):
        broader = collection.get(entity.row.get('felles_id'))
        if broader is None:
            warning('Biautoritet mangler hovedautoritet', entity)
        else:
            entity.broader.append(broader)
            return True


def transform_person_nationality(entity: BibbiEntity, bibbi_map: dict):
    """
    For entiteter av type `Person`, som har `nationality` angitt:
    Slå opp `nationality`-verdiene for å finne de korresponderende
    `DemographicGroup`-entitetene (fra Bibbi-emner) og lenk til dem.

    Eksempel: For nasjonalitetsverdien "somal.-n.", slå opp kodene "somal."
    og "n." og lenk til de matchende entitetene 1130466:"Somaliere" og
    1177317:"Nordmenn".
    """
    if entity.nationality is not None:
        for nationality_code in entity.nationality.split('-'):
            if nationality_code in bibbi_map:
                bibbi_entity = bibbi_map[nationality_code]
                entity.nationality_entities.append(bibbi_entity)
            else:
                warning('Nasjonalitetskode ble ikke funnet i Bibbi-emner: "%s"' % nationality_code, entity)

        return True


def transform_demographic_group(entity: BibbiEntity, countries: EntityCollection, bibbi: EntityCollection, wikidata_country_map):
    """
    For entiteter av type `DemographicGroup` (fra Bibbi-emner), slå opp
    nasjonalitetskoden mot og legg til landinformasjon fra EnumCountries.
    Finn også den matchende `Place`-entiteten fra Bibbio-geografisk.

    Eksempel: For entiteten 1130466:"Somaliere", legg til ISO 3166-kode "SO",
    MARC21-kode "so", demonym "somalisk", land 1163875:"Somalia", samt
    en invers relasjon 1163875:"Somalia" <demografisk gruppe> 1130466:"Somaliere".
    """

    manual_bibbi_map = {
        'England': 'Storbritannia - England',
        'Forente arabiske emirater': 'De Forente arabiske emirater',
        'Irland': 'Irland (republikken)',
        'Komorene': 'Komorene (stat)',
        'Kongo (Den demokratiske republikken)': 'Kongo (demokratisk republikk)',
        'Kongo-Brazzaville': 'Kongo-Brazzaville (republikk)',
        'Skottland': 'Storbritannia - Skottland',
        'Taiwan': 'Kina - Taiwan',
        'Tibet': 'Kina - Tibet',
        'Wales': 'Storbritannia - Wales',
    }

    nation: Optional[Nation] = countries.get(entity.bs_nasj_id)
    if nation is not None:
        entity.scopeNote = nation.description
        if nation.label is not None:
            nation_label = manual_bibbi_map.get(nation.label, nation.label)
            entity.country = bibbi.find_first(label=nation_label, entity_type=TYPE_GEOGRAPHIC)
            if entity.country is not None:
                entity.country.demographicGroup = entity  # Reverse relation
                entity.country.iso3166_2_code = nation.iso3166_2_code
                entity.country.marc21_code = nation.marc21_code
                entity.country.demonym = nation.demonym
                if entity.country.iso3166_2_code in wikidata_country_map:
                    entity.country.exact_match.append(wikidata_country_map[entity.country.iso3166_2_code])
                elif entity.country.iso3166_2_code is not None:
                    warning('Landskode ikke funnet på Wikidata: "%s"' % entity.country.iso3166_2_code, entity)
            else:
                warning('Fant ikke geografisk entitet med navn "%s"' % nation_label, entity)
        return True
    else:
        warning('Nasjonalitetskode ble ikke funnet i nasjonalitetstabell: "%s"' % entity.bs_nasj_id, entity)


@timing
def transform_entities(label_factory: LabelFactory,
                       collections: Dict[str, EntityCollection],
                       tables: TableDict,
                       wikidata_country_map):
    """
    Deduserer flere relasjoner mellom entiteter.
    """
    entity_map = {
        TYPE_TITLE_SUBJECT: TYPE_TITLE,

        # Disse to håndteres vel allerede greit av felles_id-relasjonen?? Fjerne?
        # TYPE_CORPORATION_SUBJECT: TYPE_CORPORATION,
        # TYPE_PERSON_SUBJECT: TYPE_PERSON,
    }
    countries = collections['bs-nasj']
    bibbi = collections['bibbi']

    nationality_bibbi_map = tables[TopicTable.type].get_nationality_map()
    nationality_bibbi_map = {
        nationality_code: collections['bibbi'].get(bibbi_item)
        for nationality_code, bibbi_item in nationality_bibbi_map.items()
    }

    counters = {'bi': 0, 'cn': 0, 'dm': 0}
    for collection in collections.values():
        for entity in collection:

            # Legg til relasjon mellom biautoritet og hovedautoritet
            if entity.type in [TYPE_PERSON_SUBJECT, TYPE_CORPORATION_SUBJECT, TYPE_TITLE_SUBJECT, TYPE_TITLE]:
                if add_relation_to_main_entity(label_factory, collection, entity, entity_map):
                    counters['bi'] += 1

            if entity.type in [TYPE_PERSON]:
                if transform_person_nationality(entity, nationality_bibbi_map):
                    counters['cn'] += 1

            if entity.type in [TYPE_DEMOGRAPHIC_GROUP]:
                if transform_demographic_group(entity, countries, bibbi, wikidata_country_map):
                    counters['dm'] += 1

    log.info('Relations added: broader: %(bi)s, nationality: %(cn)s, demographic_group: %(dm)s', counters)

#
# @timing
# def remove_unused_entities(concept_schemes: ConceptSchemeCollection):
#     for concept_scheme in concept_schemes:
#         concept_scheme._entities = []
#     if not isinstance(entity, BibbiEntity):
#         return entity
#     if entity.items_as_entry > 0 or entity.items_as_subject > 0:
#         return entity


# ------------------------------------------------------------------------------------------------
# Serialize


@timing
def serialize_as_rdf(collections):

    # RdfEntitySerializer() \
    #     .load('src/bs.ttl', 'turtle') \
    #     .load('src/bs-nasj.scheme.ttl', 'turtle') \
    #     .set_concept_scheme('http://id.bibbi.dev/bs-nasj/') \
    #     .add_entities(collections['bs-nasj'], ) \
    #     .serialize('out/bs-nasj.nt', 'ntriples')

    last_modified = collections['bibbi'].get_last_modified()
    bibbi = ConceptScheme(
        URIRef('http://id.bibbi.dev/bibbi/'),
        last_modified
    )

    for source_type in [TYPE_GENRE, TYPE_TOPICAL, TYPE_GEOGRAPHIC, TYPE_PERSON, TYPE_CORPORATION]:
        entities = collections['bibbi'].filter(lambda entity: entity.source_type == source_type)
        RdfEntityAndMappingSerializer() \
            .load('src/bs.ttl') \
            .load('src/bibbi.scheme.ttl') \
            .set_concept_schemes([bibbi]) \
            .add_entities(entities) \
            .serialize('out/bibbi-%s.nt' % source_type, 'ntriples')

    RdfReverseMappingSerializer() \
        .add_entities(collections['bibbi'], ) \
        .serialize('out/webdewey-bibbi-mappings.nt', 'ntriples')


# ------------------------------------------------------------------------------------------------
# Config and glue

def run(services: dict, use_cache: bool, remove_unused: bool):

    wikidata_country_list = services['wikidata'].get_country_map()

    # 1. Extract data, either from the database or from cache
    tables = extract_tables(services['promus_adapter'], [
        NationTable,
        TopicTable,
        GeographicTable,
        GenreTable,
        CorporationTable,
        PersonTable,
    ])

    # 2. If extracted from database, update the cache
    if not use_cache:
        update_cache(services['promus_cache'], tables)

    # 3. Transform to entities
    collections = transform_to_entities(tables, {
        'bibbi': EntityCollection('bibbi'),
        'bs-nasj': EntityCollection('bs-nasj'),
    })

    # 4. Add relations between entities
    transform_entities(
        services['label_factory'],
        collections,
        tables,
        wikidata_country_list
    )

    # 5. Serialize
    serialize_as_rdf(collections)


def get_services(use_cache: bool):
    promus_cache = PromusCache('cache')
    if use_cache:
        promus_adapter = promus_cache
    else:
        promus_adapter = PromusService(connection=Db(**{
            'server': os.getenv('DB_SERVER'),
            'database': os.getenv('DB_DB'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
        }))

    return {
        'promus_cache': promus_cache,
        'promus_adapter': promus_adapter,
        'label_factory': LabelFactory(),
        'wikidata': WikidataService(),
    }


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description='Bibbi authorities conversion pipeline.'
    )
    parser.add_argument('--use-cache', action='store_true', default=False)
    parser.add_argument('--remove-unused', action='store_true', default=False)
    options = parser.parse_args()

    configure_logging()
    services = get_services(options.use_cache)
    run(services, options.use_cache, options.remove_unused)


if __name__ == '__main__':
    main()
