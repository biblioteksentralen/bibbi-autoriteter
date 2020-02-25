import pytest
from bibbi.datatable import TopicTable, GeographicTable, CorporationTable
from bibbi.entities import TYPE_GEOGRAPHIC, TYPE_TOPIC, TYPE_QUALIFIER
from .util import make_datarow


class TestDataRow:

    # Ekstremeksempel: Verdenskrigen, 1939-1945 - Italia - Roma - Krigsoperasjoner - Spillefilmer &
    label_data = [
        # Topic
        (   # Nynorsk forklaring, men ikke label
            TopicTable,
            {'label': 'Spotify', 'detail': 'strømmetjeneste', 'detail_nn': 'strøymeteneste'},
            ('Spotify (strømmetjeneste)', 'Spotify (strøymeteneste)'),
            ('Spotify (strømmetjeneste)', 'Spotify (strøymeteneste)'),
        ),
        (
            # <Fortellinger> (form/sjanger) om <filmkunst> fra <Hollywood> (sted)
            TopicTable,
            {'label': 'Filmkunst', 'sub_topic': 'Fortellinger', 'sub_geo': 'USA - California - Los Angeles - Hollywood'},
            ('Filmkunst - USA - California - Los Angeles - Hollywood - Fortellinger', None),
            ('Filmkunst - Hollywood (Los Angeles, California, USA) - Fortellinger', None),
        ),
        (   # <Historie> (form/sjanger) om <sykling> i <Amsterdam> (sted)
            TopicTable,
            {'label': 'Sykling', 'sub_topic': 'Historie', 'sub_geo': 'Nederland - Amsterdam'},
            ('Sykling - Nederland - Amsterdam - Historie', None),
            ('Sykling - Amsterdam (Nederland) - Historie', None),
        ),
        # Geographic
        (   # <Historie> (form/sjanger) om <Amsterdam> (sted)
            GeographicTable,
            {'label': 'Nederland', 'sub_topic': 'Historie', 'sub_geo': 'Amsterdam'},
            ('Nederland - Amsterdam - Historie', None),
            ('Amsterdam (Nederland) - Historie', None),
        ),
        (   # Om <Norge> (sted) sin <utenrikspolitikk> mot <USA> (sted)
            # Egentlig: "Norges utenrikspolitiske forhold til USA"
            GeographicTable,
            {'label': 'Norge', 'label_nn': 'Noreg', 'sub_topic': 'Utenrikspolitikk - USA'},
            ('Norge - Utenrikspolitikk - USA', 'Noreg - Utenrikspolitikk - USA'),
            ('Norge - Utenrikspolitikk - USA', 'Noreg - Utenrikspolitikk - USA'),
        ),
        (   # <Historie> (form/sjanger) om <Roma> i perioden <31 f.Kr.-284 e.Kr.> (tidsperiode)
            GeographicTable,
            {'label': 'Italia', 'sub_geo': 'Roma', 'sub_topic': 'Historie - 31 f.Kr.-284 e.Kr.'},
            ('Italia - Roma - Historie - 31 f.Kr.-284 e.Kr.', None),
            ('Roma (Italia) - Historie - 31 f.Kr.-284 e.Kr.', None),
        ),
        (   # Om <Alger i Algerie>
            GeographicTable,
            {'label': 'Algerie', 'sub_geo': 'Alger'},
            ('Algerie - Alger', None),
            ('Alger (Algerie)', None),
        ),
        (   # Kvalifikatorer for emneord viser typisk til overordnet område i Dewey,
            # f.eks. viser "Datingapper : programvarer" at <Datingapper> <er en> <programvare>
            #
            # Men <Grand Canyon> er definitivt ikke en <geologi>
            GeographicTable,
            {'label': 'USA', 'sub_geo': 'Arizona - Grand Canyon', 'qualifier': 'geologi'},
            ('USA - Arizona - Grand Canyon : geologi', None),
            ('Grand Canyon (Arizona, USA) : geologi', None),
        ),
        # Corporation
        (   # Om <Kommuneloven i Norge>
            CorporationTable,
            {'label': 'Norge', 'label_nn': 'Noreg', 'title': 'Kommuneloven', 'law': '1'},
            ('Norge - Kommuneloven', 'Noreg - Kommuneloven'),
            ('Kommuneloven (Norge)', 'Kommuneloven (Noreg)'),
        ),
        (   # <Dataspill> om <Titanic (skip)> sitt <forlis> (merk: underemne på nynorsk: Dataspel)
            CorporationTable,
            {'label': 'Titanic', 'detail': 'skip', 'qualifier': 'forlis', 'sub_topic': 'Dataspill', 'sub_topic_nn': 'Dataspel'},
            ('Titanic (skip) - Dataspill : forlis', 'Titanic (skip) - Dataspel : forlis'),
            ('Titanic (skip) - Dataspill : forlis', 'Titanic (skip) - Dataspel : forlis'),
        ),
        # (   # Om <Kommuneloven i Norge>
        #     CorporationTable,
        #     {'label': 'Møllebyen litteraturfestival', 'location': 'Moss', 'date': '2011'},
        #     ('Møllebyen litteraturfestival : Moss : 2011', 'Møllebyen litteraturfestival : Moss : 2011'),
        #     ('Møllebyen litteraturfestival (Moss, 2011)', 'Møllebyen litteraturfestival (Moss, 2011)'),
        # ),

    ]

    @staticmethod
    @pytest.mark.parametrize("table,row,expected_without_transforms,expected_with_transforms", label_data)
    def test_get_label_with_label_transforms(table, row, expected_without_transforms, expected_with_transforms):
        row = make_datarow(table, **row)
        assert row.get_label(label_transforms=False) == {'nb': expected_without_transforms[0], 'nn': expected_without_transforms[1] or expected_without_transforms[0]}
        assert row.get_label(label_transforms=True) == {'nb': expected_with_transforms[0], 'nn': expected_with_transforms[1] or expected_with_transforms[0]}

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

