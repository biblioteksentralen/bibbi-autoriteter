# Bibbi autoriteter

- Biblioteksentralens emneord finnes på nynorsk og bokmål.
- Prekoordinerte emneord (dvs. sammensatte emner) uttrykkes i strenger, og rekkefølgen angir hvilket aspekt ved emnet som er viktigst.
- Utviklet siden 1970-tallet.
- Følger Ellen Hjortsæters Emneordskatalogisering (Hjortsæter, 2010).
- Rundt 35 000 emnestrenger, 6500 geografiske emnestrenger, 155 000 personautoriteter
- Emneordspraksisen har sprunget ut fra *Sears List of Subject Headings*. Termene er knyttet opp mot Deweys desimalklassifikasjonssystem, 5. norske utgave.<ref> ABM Skrift #60, s. 74</ref>
- Kvalifikator (satt med kolon) brukes for å vise emnets plassering i Dewey-tabellen.
- Biautoriteter har samme `Felles_ID`, men ulik `Bibsent_ID`

### URI-er

Inspirasjon: https://wiki.dnb.de/display/DINIAGKIM/URI-Design-Empfehlungen
Naming Things: http://linkeddatabook.com/editions/1.0/#htoc10

- HTTP-URI-er brukes for å identifisere ting. For eksempel identifiserer http://data.bibsent.no/bibbi/1181096 emneordet "Hamløpere"

- URI-en http://data.bibsent.no/bibbi/1181096 er sammensatt av navnerommet http://data.bibsent.no/bibbi/ og Biblioteksentralens lokale ID 1181096, som er en naturlig nøkkel (http://patterns.dataincubator.org/book/natural-keys.html). Til sammen utgjør de en globalt unik URI.

- I noen situasjoner kan det være behov for å skille mellom entiteten vi beskriver og autoritetsposten *om* entiteten. URI-en http://data.bibsent.no/bibbi/1181096 viser til selve entiteten, mens http://data.bibsent.no/bibbi/1181096/about viser til posten om den. Sistnevnte kan inneholde informasjon som opprettelses- og endringsdato for posten.


## Personer

- schema:Person / foaf:Person
- void:inDataset ?=



### Biblioteksentralen Terms RDF schema

We also defined our own classes and properties, documented in the British Library Terms
RDF schema, 11 where necessary. There were two circumstances in which we decided it
would be appropriate to define our own terms. Firstly, if we were unable to find a property of
sufficient granularity to record a piece of data we needed. An example of this is blt:bnb to
record the BNB number, which we preferred to the less specific dcterms:identifier. The other
circumstance was if the class/property was required by a specific feature of the model. An
example of this is our modelling of the publication statement as an event.


We also created some classes and properties in order to facilitate searching: for example, we
created the classes blt:TopicLCSH and blt:TopicDDC as sub-classes of skos:Concept. These
enable users to request a more refined search based on a particular LCSH subject or DDC
number. We also created inverse properties to facilitate navigating from one resource to the
other: for example blt:hasCreated as inverse property of dcterms:creator as well as
blt:hasContributedTo as an inverse of dcterms:contributor. This makes it easier to query the
data and facilitates the retrieval of all resources created or contributed to by a particular entity.
Overall, we created relatively few classes and properties; our priority was to re-use existing
ontologies. Re-using metadata facilitates interoperability and minimizes the burden of
maintaining our own metadata.


### Interactive

```
from bibbi.repository import TopicTable, GeographicTable, GenreTable, CorporationTable, PersonTable, Repository

from bibbi.entities import Entities

repo = Repository([
	TopicTable,
	GeographicTable,
	GenreTable,
	CorporationTable,
	PersonTable,
])
repo.load()

entities = Entities()
entities.load(repo)

entity = entities.get('1102795')
entity.data

```


### Konverteringsscript

- Steg 1.1: Last inn data fra SQL inn i pandas DataFrames og normaliser kolonnenavn mest mulig på tvers av tabeller.
- Steg 1.2: Gjør enkel validering og vasking,  som å fjerne luft fra verdier
- Steg 1.3: Cache DataFrames som Feather-filer, for raskere oppslag senere.

- Steg 2.1: Bygg oversikter/indekser over referanser og komponenter (underinndelinger o.l.)
- Steg 2.2 Bygg objekter fra DataFrames-tabellene
- Steg 2.3: Tilordne ID-er til komponenter som ikke eksisterer som egne autoriteter fra før og lagre disse til disk

- Steg 3.1: Bygg RDF-graf fra objektene
- Steg 3.2: Kjør kvalitetssjekk og slutning på grafen med Skosify
- Steg 3.3: Lagre


## Installasjon

### Databasedriver for Microsoft SQL

For tilkobling til Microsft SQL Server bruker vi PyODBC-driveren FreeTDS på Linux og Mac.

#### Mac:

	brew install unixodbc freetds

Create a template file `odbcinst.ini` at `/usr/local/etc/odbcinst.ini`

	[FreeTDS]
	Description=FreeTDS
	Driver=/usr/local/lib/libtdsodbc.0.so
	Setup=/usr/local/lib/libtdsodbc.0.so
	UsageCount=1

And install it:

	sudo odbcinst -i -d -f /usr/local/etc/odbcinst.ini

#### Debian/Ubuntu:

Install dependencies:

	sudo apt install python3-dev tdsodbc freetds-bin freetds-dev unixodbc-dev

Create `/etc/odbcinst.ini`:

	[FreeTDS]
	Description=FreeTDS
	Driver=/usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so
	Setup=/usr/lib/x86_64-linux-gnu/odbc/libtdsS.so
	UsageCount=1

And install it:

	sudo odbcinst -i -d -f /etc/odbcinst.ini

#### Testing the connection

If `pyodbc` fails to connect, we don't get much information to help diagnose the problem.
The command line utility `tsql` provides more information.
See https://linux.die.net/man/1/tsql

		tsql -H wg-sxd0e-010.i04.local -p 1435 -U promus

### Other dependencies

Finally install Python dependencies using Poetry:

	poetry install
