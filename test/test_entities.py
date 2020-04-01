import pytest

from bibbi.constants import TYPE_TOPIC, TYPE_PERSON, TYPE_PERSON_TOPIC, TYPE_COMPLEX, TYPE_CORPORATION, TYPE_LAW
from bibbi.entities import Entities, Entity
from .util import make_datarow


class TestEntities:

    entity_type_data = [
        (
            # By default, the entity type equals the source table type
            TYPE_TOPIC,
            {
                'label': 'Alger',
                'bibsent_id': '1110267',
            },
            TYPE_TOPIC
        ),
        (
            # Strikking - Danmark - Historie : tekstilkunst
            # Should complex topical concepts still be considered topics?
            TYPE_TOPIC,
            {
                'label': 'Strikking',
                'sub_topic': 'Historie',
                'sub_geo': 'Danmark',
                'qualifier': 'tekstilkunst',
                'bibsent_id': '1179204',
            },
            TYPE_COMPLEX
        ),
        (
            # Hovedautoriteter er person
            TYPE_PERSON,
            {
                'label': 'Thunberg, Greta',
                'bibsent_id': '1175823',
                'felles_id': '1175823',
            },
            TYPE_PERSON
        ),
        (
            # Biautoriteter er ikke
            TYPE_PERSON,
            {
                'label': 'Thunberg, Greta',
                'bibsent_id': '1175824',
                'felles_id': '1175823',
            },
            TYPE_PERSON_TOPIC
        ),
        (
            # Lover
            TYPE_CORPORATION,
            {
                'label': 'Norge',
                'label_nn': 'Noreg',
                'work_title': 'Kommuneloven',
                'law': '1',
            },
            TYPE_LAW
        ),
    ]

    @pytest.mark.parametrize("row_type,row_data,expected_entity_type", entity_type_data)
    def test_entity_type(self, row_type, row_data, expected_entity_type):
        row = make_datarow(row_type, **row_data)
        entity = Entity(row.bibsent_id)
        entity.from_row(row, Entities())

        assert entity.source_type == row_type
        assert entity.type == expected_entity_type


    #
    # relation_data = [
    #     (
    #         [ # Input
    #             (TopicTable, {
    #                 'label': 'Alger',
    #                 'bibsent_id': '1110267',
    #             }),
    #             (GeographicTable, {
    #                 'label': 'Algerie',
    #                 'sub_geo': 'Alger',
    #                 'bibsent_id': '1163253',
    #             }),
    #             (GeographicTable, {
    #                 'label': 'Algerie',
    #                 'sub_geo': 'Alger',
    #                 'sub_topic': 'Geografi og reiser',
    #                 'bibsent_id': '1164999',
    #             }),
    #         ],
    #         [ # Expected output
    #             ('topic', 'alger', '1110267'),
    #             ('geographic', 'alger (algerie)', '1163253'),
    #             ('topic', 'geografi og reiser', None),    # UUID
    #         ]
    #     ),
    #     (
    #         [ # Input
    #             (TopicTable, {
    #                 'label': 'Impresjonisme',
    #                 'qualifier': 'malerkunst',
    #                 'bibsent_id': '1115090',
    #             }),
    #             (TopicTable, {
    #                 'label': 'Impresjonisme',
    #                 'qualifier': 'kunst',
    #                 'bibsent_id': '1115089',
    #             }),
    #         ],
    #         [ # Expected output
    #             ('topic', 'impresjonisme', None),
    #             ('qualifier', 'malerkunst', None),
    #             ('qualifier', 'kunst', None),
    #         ]
    #     ),
    #     (
    #         [ # Input
    #             (GeographicTable, {
    #                 'label': 'Norge',
    #                 'sub_topic': 'Utenrikspolitikk - Tyskland (BRD)',
    #                 'bibsent_id': '1148505',
    #             }),
    #             (GeographicTable, {
    #                 'label': 'Norge',
    #                 'bibsent_id': '1162625',
    #             }),
    #         ],
    #         [ # Expected output
    #             ('geographic', 'norge', '1162625'),
    #             ('topic', 'utenrikspolitikk', None),    # UUID
    #             ('topic', 'tyskland (brd)', None),  # This should really be geo though
    #         ]
    #     ),
    #     (
    #         [  # Input
    #             (CorporationTable, {
    #                 'label': 'Universitetet i Oslo',
    #                 'sub_unit': 'Oldsaksamlingen',
    #                 'bibsent_id': '1148505',
    #             }),
    #             (CorporationTable, {
    #                 'label': 'Universitetet i Oslo',
    #                 'bibsent_id': '1162625',
    #             }),
    #         ],
    #         [  # Expected output
    #             ('corporation', 'universitetet i oslo', '1162625'),
    #             ('corporation', 'oldsaksamlingen (universitetet i oslo)', '1148505'),
    #         ]
    #     ),
    # ]
    #
    # @staticmethod
    # def assert_component_in(components, entity_type, label, entity_id):
    #     entity_id = entity_id or '<UUID>'
    #     serialized = components.serialize(include_non_uuids=True)
    #     items = serialized[entity_type].items()
    #
    #     # Replace UUIDs with a constant
    #     items = [
    #         (item[0], '<UUID>' if '-' in item[1] else item[1])
    #         for item in items
    #     ]
    #     assert (label, entity_id) in items
    #
    # @pytest.mark.parametrize("rows,expected", relation_data)
    # def test_make_component_entities(self, rows, expected):
    #     entities = Entities()
    #     for row in rows:
    #         drow = make_datarow(row[0], **row[1])
    #         entities.import_row(drow)
    #
    #     component_count_before = len([exp for exp in expected if exp[2] is not None])
    #     component_count_after = len(expected)
    #     print('== Expected ==')
    #     for exp in expected:
    #         print(exp)
    #
    #     assert len(entities.components) == component_count_before
    #
    #     entities.make_component_entities()
    #
    #     c = entities.components
    #     assert len(c) == component_count_after
    #     for exp in expected:
    #         self.assert_component_in(c, *exp)


# ------------------

# def test_geo_row():
#     row = make_datarow(
#         GeographicTable,
#         bibsent_id='1',
#         label='Norge',
#         sub_topic='Utenrikspolitikk - USA'         # Merk: sub_topic inneholder både emne (Utenrikspolitikk) og stedsnavn (USA)
#     )
#     components = row.get_components()
#     assert sorted([c['label'] for c in components]) == sorted(['Norge', 'Utenrikspolitikk', 'USA'])
#     assert sorted([c['entity_type'] for c in components]) == sorted([TYPE_GEOGRAPHIC, TYPE_TOPIC, TYPE_TOPIC])

#     entities = Entities()
#     entities.import_row(row)
#     assert len(entities) == 1
#     entities.make_component_entities()
#     assert len(entities) == 4
#     # print([x.data for x in entities])
#     graph = Graph()
#     for entity in entities:
#         graph.add_entity(entity)


#     for tr in graph.triples():
#         print(str(tr[0]), str(tr[1]), str(tr[2]))

#     # print(list(graph.triples()))

#     assert len(list(graph.triples())) == 16


# def test_geo_row2():
#     row = make_datarow(
#         GeographicTable,
#         bibsent_id='2',
#         label='Nederland',
#         sub_topic='Reisehåndbøker',
#         sub_geo='Amsterdam',
#     )
#     components = row.get_components()
#     assert set([c['label'] for c in components]) == set(['Reisehåndbøker', 'Amsterdam'])


# def test_component():
#     entities = Entities()
#     entity = entities.get('1')
#     assert entity.id == '1'
