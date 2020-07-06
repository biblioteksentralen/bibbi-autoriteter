import logging
from textwrap import dedent
from typing import Dict, List

from SPARQLWrapper import SPARQLWrapper2

log = logging.getLogger(__name__)


class WikidataService:

    standardPrefixes = dedent("""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX p: <http://www.wikidata.org/prop/>
    PREFIX ps: <http://www.wikidata.org/prop/statement/>
    PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX bd: <http://www.bigdata.com/rdf#>
    """)

    def select(self, query: str):
        client = SPARQLWrapper2('https://query.wikidata.org/sparql')
        client.setQuery(self.standardPrefixes + query)
        for result in client.query().bindings:
            yield result

    def select_values(self, query: str):
        for result in self.select(query):
            yield {
                key: value.value
                for key, value in result.items()
            }

    def get_country_map(self) -> Dict[str, str]:
        country_map = {
            item['countryCode']: item['item']
            for item in self.select_values(
                """
                SELECT ?item ?countryCode WHERE {
                    ?item wdt:P297 ?countryCode .
                }
                """
            )
        }
        log.info('Fetched Wikidata country map for %d countries', len(country_map))
        return country_map
