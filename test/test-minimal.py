from rdflib import Graph

graph = Graph()
graph.load('test/minimal-complex.ttl', format='turtle')

query = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX bs: <http://schema.bibbi.dev/>

CONSTRUCT {
    ?c ?p1 ?o1 .
    ?c2 ?p2 ?c .
}
WHERE {
    ?c a bs:Entity ;
        bs:itemCount 0 ;
        ?p1 ?o1 .
    OPTIONAL { ?c2 ?p2 ?c . }
    FILTER NOT EXISTS {
        ?c skos:narrower ?c3 .
        # ?c skos:narrower+ ?c3 ; ?c3 bs:itemCount ?i3 . FILTER(?i3 != 0)
    }
}
"""
graph2 = Graph()

for tr in graph.query(query):
    graph2.add(tr)

graph2.serialize()
print(graph2.serialize(format='turtle').decode('utf-8'))
