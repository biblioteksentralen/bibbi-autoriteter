from __future__ import annotations
from typing import TYPE_CHECKING
from .constants import SUB_DELIM, TYPE_CORPORATION, QUA_DELIM, TYPE_GEOGRAPHIC, TYPE_PERSON, INNER_DELIM, TYPE_EVENT, \
    TYPE_EVENT_SUBJECT, TYPE_PERSON_SUBJECT, TYPE_CORPORATION_SUBJECT, TYPE_TITLE_SUBJECT, TYPE_WORK
from .util import LanguageMap

if TYPE_CHECKING:
    from .promus_service import DataRow


class LabelFactory:
    """
    A service that can format labels in different ways.
    """

    def __init__(self, transform: bool = False,
                 #include_subdivisions: bool = True,
                 #include_qualifier: bool = True
                 ):
        """

        :param transform: If set to true, a set of transformations will be carried out to create
            a label where the most specific part comes first.
            - Geografiske termer og underavdelinger: "Norge - Oslo" → "Oslo (Norge)"
            - Verksanalytter reverseres: "Navn - Verk" → "Verk (Navn)"
            - "Organisasjon – Avdeling" → "Avdeling (Organisasjon)"
        """
        self.transform = transform
        #self.include_subdivisions = include_subdivisions
        #self.include_qualifier = include_qualifier

    @staticmethod
    def get_label_and_detail(row: DataRow) -> LanguageMap:
        # 1. Navn ($a)
        label = row.get_lang_map('label')

        # 2. Forklarende tilføyelse i parentes
        if detail := row.get_lang_map('detail'):
            label.nb += ' (%s)' % detail.nb
            label.nn += ' (%s)' % detail.nn

        return label

    def get_base_label(self, row: DataRow, include_subdivisions: bool) -> LanguageMap:
        """
        Get the "$a ($q)" part of the label only
        """

        if row.type == TYPE_GEOGRAPHIC:
            # Geografiske emneord (655): $a og $z kombineres
            return self.get_geographic_label(row, include_subdivisions)

        elif row.type in [TYPE_PERSON, TYPE_PERSON_SUBJECT]:
            # Personer (X00): $a, $b, $t kombineres
            return self.get_person_label(row)

        elif row.type in [TYPE_CORPORATION, TYPE_CORPORATION_SUBJECT]:
            return self.get_corporation_label(row)

        elif row.type in [TYPE_EVENT, TYPE_EVENT_SUBJECT]:
            return self.get_event_label(row)

        elif row.type in [TYPE_WORK]:
            return self.get_work_label(row)

        return self.get_label_and_detail(row)

    def make(self, row: DataRow, include_subdivisions: bool = True,
             include_qualifier: bool = True) -> LanguageMap:

        label = self.get_base_label(row, include_subdivisions)

        if include_subdivisions:

            # Geografisk underavdeling ($z)
            if row.type != TYPE_GEOGRAPHIC and row.has('sub_geo'):
                label += SUB_DELIM
                label += self.get_geographic_label(row, include_subdivisions)

            # Generell underavdeling ($x)
            for subdivison in row.get_subdivisions('sub_topic'):
                label.nb += SUB_DELIM + subdivison.nb
                label.nn += SUB_DELIM + subdivison.nn

        # Tittel på analytter for personer og korporasjoner (lover, musikkalbum, verk)
        if work_title := row.get_lang_map('work_title'):
            if self.transform:
                label.nb = '%s (%s)' % (work_title.nb, label.nb)
                label.nn = '%s (%s)' % (work_title.nn, label.nn)
            else:
                label.nb += SUB_DELIM + work_title.nb
                label.nn += SUB_DELIM + work_title.nn

        if include_qualifier:
            # Kolon-kvalifikator (Blir litt gæren av disse!)
            if qualifier := row.get_lang_map('qualifier'):
                label.nb += QUA_DELIM + qualifier.nb
                label.nn += QUA_DELIM + qualifier.nn

        if row.type == TYPE_TITLE_SUBJECT or row.type == TYPE_PERSON_SUBJECT:
            label.nb += ' (emne)'
            label.nn += ' (emne)'

        return label

    def get_geographic_label(self, row: DataRow, include_subdivisions) -> LanguageMap:
        """
        Returns the geographic parts (655 $a and 6XX $z) of this subject heading
        combined into a single component, or None if there is no geographic part.
        """
        parts: list = []

        if row.type == TYPE_GEOGRAPHIC:
            parts.append(self.get_label_and_detail(row))

        if include_subdivisions:
            for label in row.get_subdivisions('sub_geo'):
                parts.append(label)

        if self.transform:
            label = parts.pop()
            if len(parts) > 0:
                label.nb += ' (%s)' % ', '.join([part.nb for part in parts[::-1]])
                label.nn += ' (%s)' % ', '.join([part.nn for part in parts[::-1]])
        else:
            label = LanguageMap(
                nb=SUB_DELIM.join([part.nb for part in parts]),
                nn=SUB_DELIM.join([part.nn for part in parts])
            )

        return label

    def get_corporation_label(self, row: DataRow) -> LanguageMap:
        """
        Returns the corporate name components (X10 $a, $b) of this subject heading
        combined into a single string.
        """

        label = self.get_label_and_detail(row)

        if sub_unit := row.get_lang_map('sub_unit'):
            if self.transform:
                label.nb = sub_unit.nb + ' (%s)' % label.nb
                label.nn = sub_unit.nn + ' (%s)' % label.nn
            else:
                label.nb += SUB_DELIM + sub_unit.nb
                label.nn += SUB_DELIM + sub_unit.nn

        # if pd.notnull(self.work_title):
        #     # Tittel på lover og musikkalbum (nynorsk-variant finnes ikke)
        #     label.extend('{title} ({label})', nb=self.work_title)
        #
        #     label['nb'] = '%s (%s)' % (self.work_title, label['nb'])
        #     label['nn'] = '%s (%s)' % (self.work_title, label['nn'])

        return label

    def get_person_label(self, row: DataRow) -> LanguageMap:
        """
        Returns the person name components (X00 $a, $b or $t) of this subject heading
        combined into a single string.
        """
        label = self.get_label_and_detail(row)

        if numeration := row.get('numeration'):
            label.nb += ' ' + numeration
            label.nn += ' ' + numeration

        if nationality := row.get('nationality'):
            label.nb += INNER_DELIM + nationality
            label.nn += INNER_DELIM + nationality

        if title := row.get('title'):
            label.nb += QUA_DELIM + title
            label.nn += QUA_DELIM + title

        if date := row.get('date'):
            label.nb += INNER_DELIM + date
            label.nn += INNER_DELIM + date

        # OBS, OBS: Ikke bare enkeltpersoner. Typ "slekten", "familien"

        # if title_nb := self.get('title'):
        #     label['nb'] += ' ' + title_nb
        #     label['nn'] += ' ' + self.get('title_nn', 'title')

        # 'PersonYear': 'date',  # $d Dates associated with name
        # 'PersonNation': 'nationality',

        # TODO: ....

        # for lab in self.get_subdivisions('sub_unit'):
        #     label['nb'] = '%s (%s)' % (lab['nb'], label['nb'])
        #     label['nn'] = '%s (%s)' % (lab['nn'], label['nn'])

        # if pd.notnull(self.work_title):
        #     # Tittel på lover og musikkalbum (nynorsk-variant finnes ikke)
        #     label['nb'] = '%s (%s)' % (self.work_title, label['nb'])
        #     label['nn'] = '%s (%s)' % (self.work_title, label['nn'])

        return label

    def get_event_label(self, row: DataRow) -> LanguageMap:
        """
        Returns the event name components (X11 $a, $n $d) of this subject heading
        combined into a single string. Not quite sure if we should also include $c
        """
        # 1. Navn ($a)
        label = row.get_lang_map('label')

        # Nummer for arrangement (X11 $n)
        if event_no := row.get('event_no'):
            label.nb += ' ' + event_no
            label.nn += ' ' + event_no

        # Dato for arrangement (X11 $d)
        if event_date := row.get('event_date'):
            label.nb += INNER_DELIM + event_date
            label.nn += INNER_DELIM + event_date

        # 2. Forklarende tilføyelse i parentes
        if detail := row.get_lang_map('detail'):
            label.nb += ' (%s)' % detail.nb
            label.nn += ' (%s)' % detail.nn

        # Lokasjon for arrangement (X11 $c)
        # if event_location := row.get('event_location'):
        #     label.nb += QUA_DELIM + event_location
        #     label.nn += QUA_DELIM + event_location

        return label

    def get_work_label(self, row: DataRow) -> LanguageMap:
        """
        Returns the work label components of this subject heading
        combined into a single string.
        """
        label = row.get_lang_map('label')

        if language := row.get('language'):
            label.nb += f" ({language})"
            label.nn += f" ({language})"

        if creator_name := row.get('creator_name'):
            label.nb += f" ({creator_name})"
            label.nn += f" ({creator_name})"

        return label
