#!/usr/bin/env python3

""" 
TODO: Check that pipe-joined values are being separated properly
TODO: Have final query's values be parsed as their correct types using lookup
TODO: Format values appropriately
TODO: Dates not being parsed properly
TODO: Ignore values that don't parse as intended type
TODO: Properties with same name and different type
TODO: Properties that are basically the same with different names
"""

import time
import re
import sys
import logging
import codecs
import json
import random
import pprint
import dateutil.parser
from datetime import datetime
from urllib.request import urlopen, Request, HTTPError, URLError
from urllib.parse import urlencode


SPARQL_ENDPOINT = 'http://dbpedia.org/sparql'
DEFAULT_DATASET = 'http://dbpedia.org'
MAX_CAT_SIZE = 1_000_000_000
MIN_DECK_SIZE = 30
MAX_DECK_SIZE = 50
MIN_NUM_STATS = 4
MAX_NUM_STATS = 10
ERROR_PAUSE_TIME = 5
OUTPUT_FILE = 'tumps.json'


def query(q):
    url = '{}?{}'.format(SPARQL_ENDPOINT, urlencode({
            'timeout': '30000',
            'default-dataset-uri': DEFAULT_DATASET,
            'query': q,
            'format': 'json',    
        }))
    logging.debug('Requesting {}'.format(url))
    data = json.load(codecs.getreader('utf-8')(urlopen(Request(url))))
    results = []
    for binding in data['results']['bindings']:
        results.append({})
        for name, info in binding.items():
            val = info['value']
            results[-1][name] = val
    return results


def uri_to_friendly(uri):
    endpart = re.match(r'^.*?([^/#]+)$', uri).group(1).strip()
    spaced = re.sub('('
            r'_'
            r'|(?<=[a-z0-9])(?=[A-Z])'
            r'|(?<=[a-z])(?=[A-Z0-9])'
            r'|(?<=[A-Z])(?=[A-Z][a-z])'
        ')', ' ', endpart)
    titled = spaced.title()
    return titled
    
    
def format_stat(datatype, value):
    if datatype == 'http://www.w3.org/2001/XMLSchema#date':
        return dateutil.parser.parse(value).strftime('%d %b, %Y')
    elif datatype == 'http://www.w3.org/2001/XMLSchema#time':
        return dateutil.parser.parse(value).strftime('%I:%M%p')
    elif datatype == 'http://www.w3.org/2001/XMLSchema#datetime':
        return dateutil.parser.parse(value).strftime('%I:%M%p on %d %b, %Y')
    elif datatype == 'http://www.w3.org/2001/XMLSchema#boolean':
        return 'Yes' if bool(value) else 'No'
    else:
        return format(value, 'n')
    

logging.basicConfig(level=logging.DEBUG)


# Fetch possible categories
logging.info('Fetching categories')
results = query("""PREFIX owl: <http://www.w3.org/2002/07/owl#>
                   SELECT ?c COUNT(?o)
                   WHERE
                   {
                       ?c a owl:Class
                       . ?o a ?c
                   }
                   GROUP BY ?c
                   HAVING ( COUNT(?o) >= %(min-deck-size)d 
                            && COUNT(?o) < %(max-cat-size)d )""" % {
                        'min-deck-size': MIN_DECK_SIZE,
                        'max-cat-size': MAX_CAT_SIZE })

logging.info('{} categories'.format(len(results)))
categories = [r['c'] for r in results]

# Loop until we get a category that works
while True:
    try:
    
        # Choose at random
        category = random.choice(categories)
        logging.info('{} chosen'.format(category))
        
        # Fetch top numerical properties as the statistics
        results = query("""PREFIX owl: <http://www.w3.org/2002/07/owl#>
                           PREFIX ont: <http://dbpedia.org/ontology/>
        
                           SELECT ?p COUNT(DISTINCT ?o) GROUP_CONCAT(DISTINCT datatype(?v), "|") as ?t
                           WHERE
                           {
                               ?o a <%(category)s>
                               . ?o ?p ?v
                               . FILTER( ( isNumeric(xsd:double(str(?v))) || datatype(?v) = xsd:date 
                                            || datatype(?v) = xsd:time || datatype(?v) = xsd:datetime
                                            || datatype(?v) = xsd:boolean )
                                         && ?p != ont:wikiPageID 
                                         && ?p != ont:wikiPageRevisionID )
                           }
                           GROUP BY ?p
                           ORDER BY DESC(COUNT(DISTINCT ?o))
                           LIMIT %(max-num-stats)d""" % {
                                'category': category, 
                                'max-num-stats': MAX_NUM_STATS })
        
        statistics = []
        for result in results:
            types = set(result['t'].split('|')) - {''}
            if len(types) == 0:
                continue
            statistics.append({
                'name': result['p'], 
                'type': next(iter(types)),
                'friendly': uri_to_friendly(result['p']),
            })
            
        logging.info('{} stats'.format(len(statistics)))
        
        if len(statistics) < MIN_NUM_STATS:
            logging.info("Insufficient stats: {}".format(len(statistics)))
            continue
        
        # Fetch ids of top category members
        results = query("""PREFIX owl: <http://www.w3.org/2002/07/owl#>
                           PREFIX ont: <http://dbpedia.org/ontology/>
                           PREFIX prop: <http://dbpedia.org/property/>
        
                           SELECT ?o COUNT(DISTINCT ?p)
                           WHERE
                           {
                                ?o a <%(category)s>
                                . ?o ?p ?v
                                . ?o rdfs:label ?label
                                . ?o rdfs:comment ?comment
                                . ?o ont:thumbnail ?thumbnail
                                . FILTER( %(properties)s )
                            }
                            GROUP BY ?o
                            HAVING ( COUNT(DISTINCT ?p) >= %(min-num-stats)d )
                            ORDER BY DESC(COUNT(DISTINCT ?p))
                            LIMIT %(max-deck-size)d""" % {
                               'category': category, 
                               'properties': ' || '.join(['?p = <{}>'.format(p['name']) for p in statistics]),
                               'min-num-stats': MIN_NUM_STATS,
                               'max-deck-size': MAX_DECK_SIZE })
        
        members = [ b['o'] for b in results ]
        logging.info('{} members'.format(len(members)))
        
        if len(members) < MIN_DECK_SIZE:
            logging.info("Insufficient members: {}".format(len(members)))
            continue
        
        # Fetch member details
        results = query("""PREFIX owl: <http://www.w3.org/2002/07/owl#>
                           PREFIX ont: <http://dbpedia.org/ontology/>
                           PREFIX prop: <http://dbpedia.org/property/>
        
                           SELECT 
                               ?o 
                               GROUP_CONCAT(DISTINCT ?label,",") as ?name
                               GROUP_CONCAT(DISTINCT ?comment,",") as ?description
                               GROUP_CONCAT(DISTINCT ?thumbnail,",") as ?image
                               %(property-projections)s
                           WHERE
                           {
                               ?o rdfs:label ?label
                               . ?o rdfs:comment ?comment
                               . ?o ont:thumbnail ?thumbnail
                               %(property-joins)s
                               FILTER( ( %(members)s )
                                        && (langMatches(lang(?label), "EN") 
                                           || lang(?label) = "")
                                        && (langMatches(lang(?comment), "EN") 
                                           || lang(?comment) = "") )
                           }
                           GROUP BY ?o""" % {
                                'property-projections': '\n'.join([
                                    'GROUP_CONCAT(DISTINCT ?p{}, "|") as ?stat{}'.format(i, i) 
                                    for i,p in enumerate(statistics)]),
                                'property-joins': '\n'.join([
                                    'OPTIONAL {{ ?o <{}> ?p{} }}'.format(p['name'], i)
                                    for i,p in enumerate(statistics)]), 
                                'members': ' || '.join([
                                    '?o = <{}>'.format(m)
                                    for m in members] )})
        
        cards = []
        for result in results:
            cards.append({
                'name': result['name'],
                'description': result['description'],
                'images': result['image'],
                'stats': {},
            })
            for k, v in result.items():        
                if not k.startswith('stat'):
                    continue
                idx = int(re.sub(r'[^0-9]', '', k))
                stat = statistics[idx]
                cards[-1]['stats'][stat['friendly']] = format_stat(stat['type'], v)
                
        deckname = uri_to_friendly(category)
        deck = {
            'name': deckname,
            'cards': cards,
        }
        
        logging.info("Writing deck \"{}\" to {}".format(deckname, OUTPUT_FILE))        
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(deck, f, indent=2)
        break
        
    except (HTTPError, URLError) as e:
        logging.error(e)
        logging.debug("Pausing for {}s".format(ERROR_PAUSE_TIME))
        time.sleep(ERROR_PAUSE_TIME)
        continue
