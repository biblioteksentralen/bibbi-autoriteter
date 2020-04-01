# encoding=utf-8
import logging.config
import psutil
import os

from dotenv import load_dotenv

from bibbi.components import Components
from bibbi.repository import TopicTable, GeographicTable, CorporationTable, PersonTable, Repository
from bibbi.entities import Entities
from bibbi.serializers.rdf import RdfSerializers

# gnd: / gndo:
# bibs.ent, men .ent finnes ikke
# 'entities' eller 'authority' eller...


config = {
    'destination_dir': 'out/',
    'load_from_cache': True,
    'conversions': [
        {
            'name': 'bibbi',
            'delete_unused': False,
            'entity_candidates': False,
            'label_transforms': False,
            'component_extraction': False,

            'rdf': {
                'graph': {
                    'concept_scheme': 'http://id.bibbi.dev/bibbi/',
                    'entity_ns': 'http://id.bibbi.dev/bibbi/',
                    'group_ns': 'http://id.bibbi.dev/bibbi/group/',
                },
                'includes': [
                    'src/bs.ttl',
                    'src/bibbi.scheme.ttl',
                ],
                'variants': [
                    {
                        'type': 'entities+mappings',
                        'filters': [
                            'type:topic',
                        ],
                        'products': [{
                            'filename': 'bibbi-topic.nt',
                            'format': 'ntriples',
                        }]
                    },
                    {
                        'type': 'entities+mappings',
                        'filters': [
                            'type:geographic',
                        ],
                        'products': [{
                            'filename': 'bibbi-geographic.nt',
                            'format': 'ntriples',
                        }]
                    },
                    {
                        'type': 'entities+mappings',
                        'filters': [
                            'type:person',
                        ],
                        'products': [{
                            'filename': 'bibbi-person.nt',
                            'format': 'ntriples',
                        }]
                    },
                    {
                        'type': 'entities+mappings',
                        'filters': [
                            'type:corporation',
                        ],
                        'products': [{
                            'filename': 'bibbi-corporation.nt',
                            'format': 'ntriples',
                        }]
                    },
                    {
                        'type': 'reverse_mappings',
                        'products': [{
                            'filename': 'webdewey-bibbi-mappings.nt',
                            'format': 'ntriples',
                        }]
                    },
                ],
            }
        },
        # {
        #     'name': 'bibbi-ex2',
        #     'delete_unused': True,
        #     'entity_candidates': True,
        #     'label_transforms': True,
        #     'component_extraction': True,
        #     'graph_options': {
        #         'concept_scheme': 'http://id.bibbi.dev/bibbi-ex2/',
        #         'entity_ns': 'http://id.bibbi.dev/bibbi-ex2/',
        #         'group_ns': 'http://id.bibbi.dev/bibbi-ex2/group/',
        #     },
        #     'include': [
        #         'src/bs.ttl',
        #         'src/bibbi-ex2.scheme.ttl',
        #     ],
        #     'products': {
        #         'vocabulary': [{
        #             'filename': 'bibbi-ex2.nt',
        #             'format': 'ntriples',
        #         }],
        #         'forward_mappings': [{
        #             'filename': 'bibbi-webdewey-mappings-ex2.nt',
        #             'format': 'ntriples',
        #         }],
        #         'reverse_mappings': [{
        #             'filename': 'webdewey-bibbi-mappings-ex2.nt',
        #             'format': 'ntriples',
        #         }],
        #     }
        # },
    ],
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

    # ------------------------------------------------------------
    # Load everything into memory first

    log.info('===== Load =====')

    # Load DataTables
    repo = Repository([
        TopicTable,
        GeographicTable,
        CorporationTable,
        PersonTable,
    ])
    repo.load(not config['load_from_cache'])

    for conv_cfg in config['conversions']:

        # ------------------------------------------------------------
        # Build

        log.info('===== Build entities: %s =====', conv_cfg['name'])

        entities = Entities()
        entities.load(repo)

        components = Components()
        components.load_from_entities(entities)

        # return

        include_unused = True

        if include_unused is False:
            before = len(entities)
            entities = entities.filter(
                lambda entity: entity.items_as_entry > 0 or entity.items_as_subject > 0
            )
            after = len(entities)
            log.info('Removed %d unused entities' % (before - after))

        # ------------------------------------------------------------
        # Serialize

        if 'rdf' in conv_cfg:
            log.info('===== Serialize: RDF =====')
            RdfSerializers(conv_cfg['rdf']).serialize(entities, config['destination_dir'])


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

    main(config)

