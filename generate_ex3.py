#!/usr/bin/env python
# encoding=utf-8
from itertools import combinations
from rdflib import Graph
from rdflib.namespace import RDF, SKOS, Namespace, URIRef
import logging
import re
import sys

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()


BS = Namespace('http://schema.bibbi.dev/')
BIBBI = Namespace('http://id.bibbi.dev/')


def load_bibbi():
    logger.info('Loading bibbi')
    bibbi = Graph()
    bibbi.load('data/bibbi-aut-3.nt', format='nt')
    bibbi.load('data/bibbi-manual-topconcepts.nt', format='nt')
    return bibbi


def load_wd():
    logger.info('Loading webdewey')
    wd = Graph()
    wd.load('data/webdewey-nb.nt', format='nt')
    return wd


def normalize_ddc(uri):
    m = re.match(r'http://dewey.info/class/([ABC\d.-]+)/e23/', uri)
    value = m.group(1)
    if len(value) == 2:
        return value + '0'
    if len(value) == 1:
        return value + '00'
    return value


def normalize_ddc_uri(uri):
    return uri
    return 'http://dewey.info/class/' + normalize_ddc(uri) + '/e23/'


def norm_ddc_2(ddc):
    # "Termodynamikk : fysikk" <-> 536.7 -> 536 -> 53,
    # men Bibbi-emnet fysikk ligger på 530, ikke 53,
    # så vi normaliserer det til "53" så de matcher.
    m = re.match('^([0-9])00$', ddc)
    if m:
        print(':: ' + m.group(1))
        return m.group(1)
    m = re.match('^([0-9]{2})0$', ddc)
    if m:
        print(':::: ' + m.group(1))
        return m.group(1)
    return ddc


def norm_ddc_2_uri(uri):
    m = re.match(r'http://dewey.info/class/([ABC\d.-]+)/e23/', uri)
    return 'http://dewey.info/class/' + norm_ddc_2(m.group(1)) + '/e23/'


def generate_broader_links(bibbi, wd, out_filename='bibbi_broader.nt'):
    logger.info('Generating broader links')

    out = Graph()

    # Collect broader relations in WebDewey
    wd_broader = {}
    for tr in wd.triples((None, SKOS.broader, None)):
        sub = normalize_ddc_uri(str(tr[0]))
        obj = normalize_ddc_uri(str(tr[2]))

        if sub != obj:
            wd_broader[sub] = obj
    logger.info('%d broader relations in WebDewey', len(wd_broader))

    # Collect mappings to WebDewey
    n = 0
    bibbi_wd_mappings = {}  # [bibbi] -> wd
    wd_bibbi_mappings = {}  # [wd] -> bibbi
    for tr in bibbi.triples((None, SKOS.closeMatch, None)):
        sub = str(tr[0])
        obj = str(tr[2])
        if sub.startswith('http://id.bibbi.dev/') and obj.startswith('http://dewey.info/class/'):
            obj = norm_ddc_2_uri(obj)
            n += 1
            # 1 to 1
            bibbi_wd_mappings[sub] = obj
            # 1 to many
            wd_bibbi_mappings[obj] = wd_bibbi_mappings.get(obj, []) + [sub]
    print('%d mappings from Bibbi to WebDewey' % n)

    # Generate related relations for Bibbi
    bibbi_related = {}
    for wc_c, bibbi_cs in wd_bibbi_mappings.items():
        for a, b in combinations(bibbi_cs, 2):
            bibbi_related[a] = bibbi_related.get(a, []) + [b]
    print(
        'Generated related links for %d Bibbi concepts'
        % (len(bibbi_related))
    )

    # Generate broader relations for Bibbi
    bibbi_broader = {}
    skipped = set()
    failed = set()
    for bibbi_c, wd_c in bibbi_wd_mappings.items():
        # Skip numbers that are not valid wd numbers
        if wd_c not in wd_broader:
            skipped.add(bibbi_c)
            continue
        wd_p = wd_c
        while True:
            if wd_p not in wd_broader:
                print('ERR: No route for %s' % wd_c)
                failed.add(bibbi_c)
                break
            wd_p = wd_broader[wd_p]
            rev_mappings = wd_bibbi_mappings.get(wd_p, [])
            if len(rev_mappings):
                for bibbi_p in rev_mappings:
                    bibbi_broader[bibbi_c] = bibbi_broader.get(bibbi_c, []) + [bibbi_p]
                break
    print(
        'Generated broader links for %d Bibbi concepts, failed for %d, skipped %d'
        % (len(bibbi_broader), len(failed), len(skipped))
    )

    for sub, objs in bibbi_related.items():
        for obj in objs:
            out.add((URIRef(sub), SKOS.related, URIRef(obj)))
            out.add((URIRef(obj), SKOS.related, URIRef(sub)))

    for sub, objs in bibbi_broader.items():
        for obj in objs:
            out.add((URIRef(sub), SKOS.broader, URIRef(obj)))
            out.add((URIRef(obj), SKOS.narrower, URIRef(sub)))

    # tc = 0
    # for bibbi_c, bibbi_ps in bibbi_broader.items():
    #     for bibbi_p in bibbi_ps:
    #         if bibbi_p not in bibbi_broader:
    #             tc += 1
    #             print('Top concept? ', bibbi_p)
    #             out.add((URIRef(bibbi_p), SKOS.topConceptOf, BIBBI['']))
    # print('%d top concepts' % tc)

    out.serialize(out_filename, format='nt')
    print('Wrote %s' % out_filename)


def stats(bibbi):
    logger.info('Generating stats')

    # Bin URIs by type
    bins = {}
    for tr in bibbi.triples((None, RDF.type, None)):
        uri = str(tr[2])
        if uri not in bins:
            bins[uri] = set()
        bins[uri].add(str(tr[0]))

    # for k, v in bins.items():
    #     print('%s: %d' % (k.split('/')[-1], len(v)))

    for k, v in bins.items():
        if k.startswith('http://schema.bibbi.dev/'):
            print('%s: %d' % (k.split('/')[-1], len(v)))

    for a, b in combinations(bins.keys(), 2):  # 2 for pairs, 3 for triplets, etc
        if a.startswith('http://schema.bibbi.dev/') and b.startswith('http://schema.bibbi.dev/'):
            len_a = len(bins[a])  #e
            len_b = len(bins[b])
            isec = len(bins[a].intersection(bins[b]))  # Finnes i <a> OG <b>
            isec_a = isec / len_a * 100
            isec_b = isec / len_b * 100
            if isec_a > 0:
                print('%d %% of "%s" is also "%s" (%d of %d)' % (
                    isec_a, a.split('/')[-1], b.split('/')[-1], isec, len_a)
                )
            if isec_b > 0:
                print('%d %% of "%s" is also "%s" (%d of %d)' % (
                    isec_b, b.split('/')[-1], a.split('/')[-1], isec, len_b)
                )

    print('Number of entities: %d' % (
        len(bins['http://schema.bibbi.dev/Entity']) + len(bins.get('http://schema.bibbi.dev/EntityCandidate', []))
    ))


if __name__ == '__main__':
    if len(sys.argv) > 0 and sys.argv[1] == 'hierarchy':
        generate_broader_links(load_bibbi(), load_wd(), 'data/bibbi-broader.nt')
    elif len(sys.argv) > 0 and sys.argv[1] == 'stats':
        stats(load_bibbi())
    else:
        print('Usage: hierarchy || stats')
