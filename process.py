# encoding=utf-8
import pandas as pd
import logging
import logging.config
import yaml
import psutil
import time
import os

from dotenv import load_dotenv

from bibbi.datatable import TopicTable, GeographicTable, CorporationTable, PersonTable
from bibbi.entities import Entities
from bibbi.graph import Graph
from bibbi.db import Db

# gnd: / gndo:
# bibs.ent, men .ent finnes ikke
# 'entities' eller 'authority' eller...


configs = {
    'common': {
        'load_from_cache': True,
    },
    's1': {
        'uri_space': 'http://id.bibbi.dev/ex1/',
        'delete_unused': False,
        'entity_candidates': False,
        'label_transforms': False,
        'component_extraction': False,
        'vocabulary_dest_nt': 'out/bibbi-s1.nt',
        'mapping_dest_nt': 'out/wd-bibbi-mappings-s1.nt',
    },
    's2': {
        'uri_space': 'http://id.bibbi.dev/ex2/',
        'delete_unused': True,
        'entity_candidates': True,
        'label_transforms': True,
        'component_extraction': True,
        'vocabulary_dest_nt': 'out/bibbi-s2.nt',
        'mapping_dest_nt': 'out/wd-bibbi-mappings-s2.nt'
    },
    's3': {
        'uri_space': 'http://id.bibbi.dev/ex3/',
        'delete_unused': False,
        'entity_candidates': False,
        'label_transforms': True,
        'component_extraction': False,
        'vocabulary_dest_nt': 'out/bibbi-s3.nt',
        'mapping_dest_nt': 'out/wd-bibbi-mappings-s3.nt'
    },
}

class AppFilter(logging.Filter):

    def __init__(self, name=''):
        super().__init__(name)
        self.process = psutil.Process(os.getpid())

    def get_mem_usage(self):
        """ Returns memory usage in MBs """
        return self.process.memory_info().rss / 1024. ** 2

    @staticmethod
    def format_as_mins_and_secs(msecs):
        secs = msecs / 1000.
        mins = secs / 60.
        secs = secs % 60.
        return '%3.f:%02.f' % (mins, secs)

    def filter(self, record):
        record.mem_usage = '%.0f' % (self.get_mem_usage(),)
        record.relativeSecs = AppFilter.format_as_mins_and_secs(record.relativeCreated)
        return True


def main(config):
    # Load everything into dataframes first (famous last words?)
    dataframes = {}
    for Importer in [
        PersonTable,
        #GeographicTable,
        #CorporationTable,
        #TopicTable,
    ]:
        importer = Importer()
        if config['load_from_cache']:
            importer.load_from_feather('cache')
        else:
            # print(os.getenv('DB_USER'))
            db = Db(server=os.getenv('DB_SERVER'), database=os.getenv('DB_DB'),
                    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'))
            importer.load_from_db(db)
            importer.save_as_feather('cache')
        dataframes[Importer.entity_type] = importer.df

    # Construct Entities object from the dataframes
    if config['component_extraction']:
        entities = Entities(component_file='storage/components.yml')
        for entity_type, df in dataframes.items():
            entities.import_dataframe(
                df,
                entity_type,
                label_transforms=config['label_transforms'],
                component_extraction=config['component_extraction']
            )
        entities.make_component_entities()
        entities.components.persist('storage/components.yml')

    # Construct graph from the objects
    graph = Graph(
        concept_scheme=config['uri_space'],
        entity_space=config['uri_space'],
        group_space=config['uri_space'] + 'group/'
    )
    graph.load('src/bibbi.scheme.ttl', format='turtle')
    graph.load('src/bs.ttl', format='turtle')
    graph.add_entities(entities)

    log.info('Skosify')
    triples_before = len(graph.graph)
    graph.skosify()
    triples_after = len(graph.graph)
    log.info('Triples changed from %d to %d', triples_before, triples_after)

    if config['delete_unused']:
        log.info('Deleting unused')
        triples_before = len(graph.graph)
        graph.delete_unused()
        triples_after = len(graph.graph)
        log.info('Triples changed from %d to %d', triples_before, triples_after)

    log.info('Serializing vocabulary')
    if config.get('vocabulary_dest_nt') is not None:
        graph.serialize_nt(config['vocabulary_dest_nt'])
    if config.get('vocabulary_dest_ttl') is not None:
        graph.serialize_ttl(config['vocabulary_dest_ttl'])

    log.info('Serializing mappings')
    graph = Graph()
    graph.add_mappings(entities)
    graph.skosify()
    if config.get('mapping_dest_nt') is not None:
        graph.serialize_nt(config['mapping_dest_nt'])
    if config.get('mapping_dest_ttl') is not None:
        graph.serialize_nt(config['mapping_dest_ttl'])

    # entities.to_excel_sheets()
    # entities.to_graph()


    # def test():
    #     reg = TopicRegistry.load()
    #     graph = reg.concepts.to_graph()
    #     graph.serialize('bibbi-aut.ttl', format='turtle')
    #     return reg
    #
    # Print unique values and their usage stats for a column:
    # reg = TopicRegistry.load()
    # reg.df.GeoUnderTopic.value_counts()

    # Nyeste:
    # reg.df.LastChanged.sort_values()[-11:]

    # Finn antall rader som har verdier
    # reg.df.WebDeweyNr.dropna().shape[0]


    # def print_stats():
    #     for regc in [TopicRegistry, GeoRegistry]:
    #         reg = regc.load()
    #         df = reg.df
    #
    #         termer = df[pd.isnull(df.ReferenceId)].shape[0]
    #         henv = df[pd.notnull(df.ReferenceId)].shape[0]
    #         har_wd = df[pd.notnull(df.WebDeweyNr)].shape[0]
    #         har_ddk5 = df[pd.notnull(df.DeweyNr)].shape[0]
    #         print('Antall begreper: %d' % termer)
    #         print('Antall henvisninger: %d' % henv)
    #         print('Har WebDewey: %d' % har_wd)
    #         print('Har DDK5: %d' % har_ddk5)


if __name__ == '__main__':
    load_dotenv()

    # with open('logging.yml') as cfg:
    #    logging.config.dictConfig(yaml.safe_load(cfg))

    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)
    logging.getLogger('oauthlib').setLevel(logging.WARNING)
    logging.getLogger('mwtemplates').setLevel(logging.INFO)

    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    syslog = logging.StreamHandler()
    log.addHandler(syslog)
    syslog.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(relativeSecs)s] {%(mem_usage)s MB} %(name)-20s %(levelname)s : %(message)s')
    syslog.setFormatter(formatter)
    syslog.addFilter(AppFilter())

    t0 = time.time()

    main({**configs['common'], **configs['s1']})
    # main({**configs['common'], **configs['s2']})
