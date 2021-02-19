import pytest
from bibbi.label_index import LookupService

from bibbi.entity_service import Entities

from bibbi.components import Components

from bibbi.promus_service import TopicTable, GeographicTable, CorporationTable
from bibbi.constants import TYPE_GEOGRAPHIC, TYPE_TOPICAL, TYPE_QUALIFIER
from .util import make_datarow


class TestDataRow:

    component_data = [
        (
            TYPE_TOPICAL,
            {
                'label': 'Gresk språk',
                'detail': 'nygresk',
                'sub_topic': 'Grammatikk - For norskspråklige',
                'qualifier': 'normativ lingvistikk',
                'sub_topic_nn': 'Grammatikk - For norskspråklege',
            },
            [
                ('Gresk språk (nygresk)', None, TYPE_TOPICAL),
                ('Grammatikk', 'Grammatikk', TYPE_TOPICAL),
                ('For norskspråklige', 'For norskspråklege', TYPE_TOPICAL),
                ('normativ lingvistikk', None, TYPE_QUALIFIER),
            ]
        ),
        (   # For geografiske navn med generelle underavdelinger ønsker vi som hovedregel
            # komponenter for hvert ledd
            TYPE_GEOGRAPHIC,
            {
                'label': 'Norge',
                'label_nn': 'Noreg',
                'sub_topic': 'Utenrikspolitikk - USA',
            },
            [
                ('Norge', 'Noreg', TYPE_GEOGRAPHIC),
                ('Utenrikspolitikk', None, TYPE_TOPICAL),  # Kanskje type "general" hadde vært bedre?
                ('USA', None, TYPE_TOPICAL),
            ]
        ),
        (   # For geografiske underavdelinger ønsker vi ikke en egen komponent for
            # det dypeste nivået
            TYPE_GEOGRAPHIC,
            {
                'label': 'Algerie',
                'sub_geo': 'Alger',
            },
            [
                ('Alger (Algerie)', None, TYPE_GEOGRAPHIC),
            ]
        ),
        (   # ... men for eventuelle generell underinndelinger
            TYPE_GEOGRAPHIC,
            {
                'label': 'Algerie',
                'sub_geo': 'Alger',
                'sub_topic': 'Geografi og reiser'
            },
            [
                ('Alger (Algerie)', None, TYPE_GEOGRAPHIC),
                ('Geografi og reiser', None, TYPE_TOPICAL),
            ]
        ),
        (   # Kvalifikatorer for emneord viser typisk til overordnet område i Dewey,
            # f.eks. viser "Datingapper : programvarer" at <Datingapper> <er en> <programvare>
            #
            # Men <Grand Canyon> er definitivt ikke en <geologi>
            TYPE_GEOGRAPHIC,
            {'label': 'USA', 'sub_geo': 'Arizona - Grand Canyon', 'qualifier': 'geologi'},
            [
                ('Grand Canyon (Arizona, USA)', None, TYPE_GEOGRAPHIC),
                ('geologi', None, TYPE_QUALIFIER),
            ]
        ),
    ]

    @staticmethod
    @pytest.mark.skip("not implemented yet")
    @pytest.mark.parametrize("table,row,expected", component_data)
    def test_get_components(table, row, expected):
        row = make_datarow(table, **row)
        expected = [
            {'label': {'nb': x[0], 'nn': x[1] or x[0]}, 'entity_type': x[2], 'entity_id': None}
            for x in expected
        ]

        entities = Entities()
        entities.get()
        entities.load(repo)

        lookup = LookupService()
        components = Components(entities, lookup)
        components.load()


        actual = list(row.get_components())
        print('== Expected ==')
        for x in expected:
            print(x)
        print('== Actual ==')
        for x in actual:
            print(x)
        assert actual == expected

