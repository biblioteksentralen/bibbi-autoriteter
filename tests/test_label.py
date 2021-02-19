import pytest

from bibbi.label import LabelService
from bibbi.constants import TYPE_GEOGRAPHIC, TYPE_TOPICAL, TYPE_CORPORATION, TYPE_PERSON
from .util import make_datarow


class TestLabel:

    # Ekstremeksempel: Verdenskrigen, 1939-1945 - Italia - Roma - Krigsoperasjoner - Spillefilmer &

    examples = [

        # Topic
        (   # Nynorsk forklaring, men ikke label
            TYPE_TOPICAL,
            {
                'label': 'Spotify',
                'detail': 'strømmetjeneste',
                'detail_nn': 'strøymeteneste',
            },
            {
                'original': {
                    'nb': 'Spotify (strømmetjeneste)',
                    'nn': 'Spotify (strøymeteneste)'
                },
                'transformed': {
                    'nb': 'Spotify (strømmetjeneste)',
                    'nn': 'Spotify (strøymeteneste)'
                },
            }
        ),
        (
            # <Fortellinger> (form/sjanger) om <filmkunst> fra <Hollywood> (sted)
            TYPE_TOPICAL,
            {
                'label': 'Filmkunst',
                'sub_topic': 'Fortellinger',
                'sub_geo': 'USA - California - Los Angeles - Hollywood',
            },
            {
                'original': {
                    'nb': 'Filmkunst - USA - California - Los Angeles - Hollywood - Fortellinger',
                    'nn': 'Filmkunst - USA - California - Los Angeles - Hollywood - Fortellinger',
                },
                'transformed': {
                    'nb': 'Filmkunst - Hollywood (Los Angeles, California, USA) - Fortellinger',
                    'nn': 'Filmkunst - Hollywood (Los Angeles, California, USA) - Fortellinger',
                },
            },
        ),
        (   # <Historie> (form/sjanger) om <sykling> i <Amsterdam> (sted)
            TYPE_TOPICAL,
            {
                'label': 'Sykling',
                'sub_topic': 'Historie',
                'sub_geo': 'Nederland - Amsterdam',
            },
            {
                'original': {
                    'nb': 'Sykling - Nederland - Amsterdam - Historie',
                    'nn': 'Sykling - Nederland - Amsterdam - Historie',
                },
                'transformed': {
                    'nb': 'Sykling - Amsterdam (Nederland) - Historie',
                    'nn': 'Sykling - Amsterdam (Nederland) - Historie',
                },
            },
        ),

        # Geographic
        (   # <Historie> (form/sjanger) om <Amsterdam> (sted)
            TYPE_GEOGRAPHIC,
            {
                'label': 'Nederland',
                'sub_topic': 'Historie',
                'sub_geo': 'Amsterdam',
            },
            {
                'original': {
                    'nb': 'Nederland - Amsterdam - Historie',
                    'nn': 'Nederland - Amsterdam - Historie',
                },
                'transformed': {
                    'nb': 'Amsterdam (Nederland) - Historie',
                    'nn': 'Amsterdam (Nederland) - Historie',
                },
            },
        ),
        (   # Om <Norge> (sted) sin <utenrikspolitikk> mot <USA> (sted)
            # Egentlig: "Norges utenrikspolitiske forhold til USA"
            TYPE_GEOGRAPHIC,
            {
                'label': 'Norge',
                'label_nn': 'Noreg',
                'sub_topic': 'Utenrikspolitikk - USA',
            },
            {
                'original': {
                    'nb': 'Norge - Utenrikspolitikk - USA',
                    'nn': 'Noreg - Utenrikspolitikk - USA'
                },
                'transformed': {
                    'nb': 'Norge - Utenrikspolitikk - USA',
                    'nn': 'Noreg - Utenrikspolitikk - USA'
                },
            },
        ),
        (   # <Historie> (form/sjanger) om <Roma> i perioden <31 f.Kr.-284 e.Kr.> (tidsperiode)
            TYPE_GEOGRAPHIC,
            {
                'label': 'Italia',
                'sub_geo': 'Roma',
                'sub_topic': 'Historie - 31 f.Kr.-284 e.Kr.',
            },
            {
                'original': {
                    'nb': 'Italia - Roma - Historie - 31 f.Kr.-284 e.Kr.',
                    'nn': 'Italia - Roma - Historie - 31 f.Kr.-284 e.Kr.',
                },
                'transformed': {
                    'nb': 'Roma (Italia) - Historie - 31 f.Kr.-284 e.Kr.',
                    'nn': 'Roma (Italia) - Historie - 31 f.Kr.-284 e.Kr.',
                },
            },
        ),
        (   # Om <Alger i Algerie>
            TYPE_GEOGRAPHIC,
            {
                'label': 'Algerie',
                'sub_geo': 'Alger',
            },
            {
                'original': {
                    'nb': 'Algerie - Alger',
                    'nn': 'Algerie - Alger',
                },
                'transformed': {
                    'nb': 'Alger (Algerie)',
                    'nn': 'Alger (Algerie)',
                },
            },
        ),
        (   # Kvalifikatorer for emneord viser typisk til overordnet område i Dewey,
            # f.eks. viser "Datingapper : programvarer" at <Datingapper> <er en> <programvare>
            #
            # Men <Grand Canyon> er definitivt ikke en <geologi>
            TYPE_GEOGRAPHIC,
            {
                'label': 'USA',
                'sub_geo': 'Arizona - Grand Canyon',
                'qualifier': 'geologi',
            },
            {
                'original': {
                    'nb': 'USA - Arizona - Grand Canyon : geologi',
                    'nn': 'USA - Arizona - Grand Canyon : geologi',
                },
                'transformed': {
                    'nb': 'Grand Canyon (Arizona, USA) : geologi',
                    'nn': 'Grand Canyon (Arizona, USA) : geologi',
                },
            },
        ),

        # Corporation
        (   # Om <Kommuneloven i Norge>
            TYPE_CORPORATION,
            {
                'label': 'Norge',
                'label_nn': 'Noreg',
                'work_title': 'Kommuneloven',
                'law': '1',
            },
            {
                'original': {
                    'nb': 'Norge - Kommuneloven',
                    'nn': 'Noreg - Kommuneloven'
                },
                'transformed': {
                    'nb': 'Kommuneloven (Norge)',
                    'nn': 'Kommuneloven (Noreg)'
                },
            },
        ),
        (   # <Dataspill> om <Titanic (skip)> sitt <forlis> (merk: underemne på nynorsk: Dataspel)
            TYPE_CORPORATION,
            {
                'label': 'Titanic',
                'detail': 'skip',
                'qualifier': 'forlis',
                'sub_topic': 'Dataspill',
                'sub_topic_nn': 'Dataspel',
            },
            {
                'original': {
                    'nb': 'Titanic (skip) - Dataspill : forlis',
                    'nn': 'Titanic (skip) - Dataspel : forlis'
                },
                'transformed': {
                    'nb': 'Titanic (skip) - Dataspill : forlis',
                    'nn': 'Titanic (skip) - Dataspel : forlis'
                },
            },
        ),

        # Person
        (
            TYPE_PERSON,
            {
                'label': 'Bartholomeus',
                'numeration': 'I',
                'title': 'økumenisk patriark av Konstantinopel',
                'date': '1940-',
                'nationality': 'tyrk.',
            },
            {
                'original': {
                    'nb': 'Bartholomeus I, tyrk. : økumenisk patriark av Konstantinopel, 1940-',
                    'nn': 'Bartholomeus I, tyrk. : økumenisk patriark av Konstantinopel, 1940-'
                },
                'transformed': {
                    'nb': 'Bartholomeus I, tyrk. : økumenisk patriark av Konstantinopel, 1940-',
                    'nn': 'Bartholomeus I, tyrk. : økumenisk patriark av Konstantinopel, 1940-'
                },
            },
        ),

        # (   # Om <Kommuneloven i Norge>
        #     CorporationTable,
        #     {'label': 'Møllebyen litteraturfestival', 'location': 'Moss', 'date': '2011'},
        #     {'nb': 'Møllebyen litteraturfestival : Moss : 2011',
        #            'nn': 'Møllebyen litteraturfestival : Moss : 2011'
        #        },
        #     {'nb': 'Møllebyen litteraturfestival (Moss, 2011)',
        #            'nn': 'Møllebyen litteraturfestival (Moss, 2011)'
        #        },
        # ),

    ]

    @staticmethod
    @pytest.mark.parametrize("row_type,row_data,expected", examples)
    def test_get_label_without_transform(row_type, row_data, expected):
        row = make_datarow(row_type, **row_data)
        label_service = LabelService()
        label = label_service.get_label(row)

        assert label.nb == expected['original']['nb']
        assert label.nn == expected['original']['nn']

    @staticmethod
    @pytest.mark.parametrize("row_type,row_data,expected", examples)
    def test_get_label_with_transform(row_type, row_data, expected):
        row = make_datarow(row_type, **row_data)
        label_service = LabelService(transform=True)
        label = label_service.get_label(row)

        assert label.nb == expected['transformed']['nb']
        assert label.nn == expected['transformed']['nn']
