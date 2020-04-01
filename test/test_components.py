import pytest
from bibbi.datatable import TopicTable, GeographicTable, CorporationTable
from bibbi.entities import TYPE_GEOGRAPHIC, TYPE_TOPIC, TYPE_QUALIFIER
from .util import make_datarow


class TestDataRow:

    component_data = [
        (
            TopicTable,
            {
                'label': 'Gresk språk',
                'detail': 'nygresk',
                'sub_topic': 'Grammatikk - For norskspråklige',
                'qualifier': 'normativ lingvistikk',
                'sub_topic_nn': 'Grammatikk - For norskspråklege',
            },
            [
                ('Gresk språk (nygresk)', None, TYPE_TOPIC),
                ('Grammatikk', 'Grammatikk', TYPE_TOPIC),
                ('For norskspråklige', 'For norskspråklege', TYPE_TOPIC),
                ('normativ lingvistikk', None, TYPE_QUALIFIER),
            ]
        ),
        (   # For geografiske navn med generelle underavdelinger ønsker vi som hovedregel
            # komponenter for hvert ledd
            GeographicTable,
            {
                'label': 'Norge',
                'label_nn': 'Noreg',
                'sub_topic': 'Utenrikspolitikk - USA',
            },
            [
                ('Norge', 'Noreg', TYPE_GEOGRAPHIC),
                ('Utenrikspolitikk', None, TYPE_TOPIC),  # Kanskje type "general" hadde vært bedre?
                ('USA', None, TYPE_TOPIC),
            ]
        ),
        (   # For geografiske underavdelinger ønsker vi ikke en egen komponent for
            # det dypeste nivået
            GeographicTable,
            {
                'label': 'Algerie',
                'sub_geo': 'Alger',
            },
            [
                ('Alger (Algerie)', None, TYPE_GEOGRAPHIC),
            ]
        ),
        (   # ... men for eventuelle generell underinndelinger
            GeographicTable,
            {
                'label': 'Algerie',
                'sub_geo': 'Alger',
                'sub_topic': 'Geografi og reiser'
            },
            [
                ('Alger (Algerie)', None, TYPE_GEOGRAPHIC),
                ('Geografi og reiser', None, TYPE_TOPIC),
            ]
        ),
        (   # Kvalifikatorer for emneord viser typisk til overordnet område i Dewey,
            # f.eks. viser "Datingapper : programvarer" at <Datingapper> <er en> <programvare>
            #
            # Men <Grand Canyon> er definitivt ikke en <geologi>
            GeographicTable,
            {'label': 'USA', 'sub_geo': 'Arizona - Grand Canyon', 'qualifier': 'geologi'},
            [
                ('Grand Canyon (Arizona, USA)', None, TYPE_GEOGRAPHIC),
                ('geologi', None, TYPE_QUALIFIER),
            ]
        ),
    ]

    @staticmethod
    @pytest.mark.parametrize("table,row,expected", component_data)
    def test_get_components(table, row, expected):
        row = make_datarow(table, **row)
        expected = [
            {'label': {'nb': x[0], 'nn': x[1] or x[0]}, 'entity_type': x[2], 'entity_id': None}
            for x in expected
        ]
        actual = list(row.get_components())
        print('== Expected ==')
        for x in expected:
            print(x)
        print('== Actual ==')
        for x in actual:
            print(x)
        assert actual == expected

