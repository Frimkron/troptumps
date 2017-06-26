#!/usr/bin/env python3

""" 
TODO: Why so many non-numeric property values?
TODO: Propertise that are basically the same with different names/prefixes
TODO: Download thumbnails
TODO: Make pdf
"""

import os
import os.path
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
CACHE_FILE = os.path.join(os.path.dirname(__file__), '.cache')
IMAGE_TYPES = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
}


def query(q):
    url = '{}?{}'.format(SPARQL_ENDPOINT, urlencode({
            'timeout': '30000',
            'default-graph-uri': DEFAULT_DATASET,
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
    
    
def friendly_to_filename(name):
    lcase = name.lower()
    unspaced = re.sub(r' ', '_', lcase)
    safe = re.sub(r'[^0-9a-z_-]', '', unspaced)
    return safe
    
    
def format_stat(datatype, value):
    if value is None or value == "":
        return "Unknown"
    try:
        if datatype == 'http://www.w3.org/2001/XMLSchema#date':
            return dateutil.parser.parse(value).strftime('%d %b, %Y')
        elif datatype == 'http://www.w3.org/2001/XMLSchema#time':
            return dateutil.parser.parse(value).strftime('%I:%M%p')
        elif datatype == 'http://www.w3.org/2001/XMLSchema#datetime':
            return dateutil.parser.parse(value).strftime('%I:%M%p on %d %b, %Y')
        elif datatype == 'http://www.w3.org/2001/XMLSchema#boolean':
            return 'Yes' if bool(value) else 'No'
        else:
            return format(float(value), 'n')
    except ValueError as e:
        logging.warn("Failed to parse \"{}\" as {}".format(value, datatype))
        return str(value)
    
                
def get_category():
    if not os.path.exists(CACHE_FILE):
        # Fetch possible categories
        logging.info('Fetching categories')
        results = query("""SELECT ?c COUNT(?o)
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
        categories = [r['c'] for r in results]
        random.shuffle(categories)
        with open(CACHE_FILE, 'w') as f:
            json.dump(categories, f)

    with open(CACHE_FILE, 'r') as f:
        categories = json.load(f)

    logging.info('{} categories'.format(len(categories)))    
    cat = categories.pop(0)
    
    with open(CACHE_FILE, 'w') as f:
        json.dump(categories, f)

    return cat


def uri_to_ascii(uri):
    return re.sub(r'[^\x20-\x7E]', 
                  lambda m: ''.join(['%{:02x}'.format(b) for b in m.group().encode('utf-8')]), 
                  uri)
    

logging.basicConfig(level=logging.DEBUG)

# Loop until we get a category that works
while True:
    try:
    
        # Choose at random
        category = {
            'name': get_category(),
            'friendly': None,
            'description': None,
            'image': None,
        }
        logging.info('{} chosen'.format(category['name']))
        
        # Fetch top numerical properties as the statistics
        results = query("""SELECT 
                               ?p 
                               COUNT(DISTINCT ?o) 
                               GROUP_CONCAT(DISTINCT datatype(?v), "|") as ?t
                           WHERE
                           {
                               ?o a <%(category)s>
                               . ?o ?p ?v
                               . FILTER( ( isNumeric(xsd:double(str(?v))) 
                                            || datatype(?v) = xsd:date 
                                            || datatype(?v) = xsd:time 
                                            || datatype(?v) = xsd:datetime
                                            || datatype(?v) = xsd:boolean )
                                         && ?p != dbo:wikiPageID 
                                         && ?p != dbo:wikiPageRevisionID )
                           }
                           GROUP BY ?p
                           ORDER BY DESC(COUNT(DISTINCT ?o))
                           LIMIT %(max-num-stats)d""" % {
                                'category': category['name'], 
                                'max-num-stats': MAX_NUM_STATS })
        
        statistics = []
        for result in results:
            types = set(result['t'].split('|')) - {''}
            if len(types) == 0:
                continue
            statistics.append({
                'name': result['p'], 
                'type': next(iter(types)),
                'friendly': None,
            })
            
        logging.info('{} stats'.format(len(statistics)))
        
        if len(statistics) < MIN_NUM_STATS:
            logging.info("Insufficient stats: {}".format(len(statistics)))
            continue
        
        # Fetch ids of top category members
        results = query("""SELECT ?o COUNT(DISTINCT ?p)
                           WHERE
                           {
                                ?o a <%(category)s>
                                . ?o ?p ?v
                                . FILTER( %(properties)s )
                            }
                            GROUP BY ?o
                            HAVING ( COUNT(DISTINCT ?p) >= %(min-num-stats)d )
                            ORDER BY DESC(COUNT(DISTINCT ?p))
                            LIMIT %(max-deck-size)d""" % {
                               'category': category['name'], 
                               'properties': ' || '.join(['?p = <{}>'.format(p['name']) for p in statistics]),
                               'min-num-stats': MIN_NUM_STATS,
                               'max-deck-size': MAX_DECK_SIZE })
        
        members = [ b['o'] for b in results ]
        logging.info('{} members'.format(len(members)))
        
        if len(members) < MIN_DECK_SIZE:
            logging.info("Insufficient members: {}".format(len(members)))
            continue

        # fetch category details
        results = query("""SELECT 
                               GROUP_CONCAT(?l, "|") as ?name 
                               GROUP_CONCAT(?c, "|") as ?description 
                               GROUP_CONCAT(?t, "|") as ?image
                           WHERE
                           {
                               OPTIONAL { <%(category)s> rdfs:label ?l }
                               OPTIONAL { <%(category)s> rdfs:comment ?c }
                               OPTIONAL { <%(category)s> dbo:thumbnail ?t }
                               FILTER ( (langMatches(lang(?l), "EN") || lang(?l) = "") 
                                         && (langMatches(lang(?c), "EN") || lang(?c) = "") )
                           }""" % {'category': category['name']})
        if len(results) > 0:
            result = results[0]
            category['friendly'] = result['name'].split('|')[0].title() if result['name'] \
                                        else uri_to_friendly(category['name'])
            category['description'] = result['description'].split('|')[0] if result['description'] else None
            category['image'] = result['image'].split('|')[0] if result['image'] else None
        else:
            category['friendly'] = uri_to_friendly(category['name'])
        
        # fetch stat details
        results = query("""SELECT ?p GROUP_CONCAT(?l, "|") as ?name
                           WHERE
                           {
                               ?p rdfs:label ?l                               
                               . FILTER( ( %(properties)s )
                                         && ( langMatches(lang(?l),"EN") || lang(?l) = "" ) )
                           }
                           GROUP BY ?p""" % {
                               'properties': ' || '.join(['?p = <{}>'.format(p['name']) for p in statistics]) })
                               
        lookup = { r['p']: r['name'].split('|')[0].title() for r in results if r['name'] }
        for s in statistics:
            s['friendly'] = lookup.get(s['name'], uri_to_friendly(s['name']))
                           
        # Fetch member details
        results = query("""SELECT 
                               ?o 
                               GROUP_CONCAT(DISTINCT ?label,"|") as ?name
                               GROUP_CONCAT(DISTINCT ?comment,"|") as ?description
                               GROUP_CONCAT(DISTINCT ?thumbnail,"|") as ?image
                               %(property-projections)s
                           WHERE
                          {
                               VALUES ?o { %(members)s }
                               OPTIONAL { ?o rdfs:label ?label }
                               OPTIONAL { ?o rdfs:comment ?comment }
                               OPTIONAL { ?o dbo:thumbnail ?thumbnail }
                               %(property-joins)s
                               FILTER( ( langMatches(lang(?label), "EN") || lang(?label) = "" )
                                        && ( langMatches(lang(?comment), "EN") || lang(?comment) = "" ) )
                           }
                           GROUP BY ?o""" % {
                                'property-projections': '\n'.join([
                                    'GROUP_CONCAT(DISTINCT ?p{}, "|") as ?stat{}'.format(i, i) 
                                    for i,p in enumerate(statistics)]),
                                'property-joins': '\n'.join([
                                    'OPTIONAL {{ ?o <{}> ?p{} }}'.format(p['name'], i)
                                    for i,p in enumerate(statistics)]), 
                                'members': ' '.join([
                                    '<{}>'.format(m)
                                    for m in members] )})
        
        cards = []
        for result in results:
            cards.append({
                'name': result['name'].split('|')[0].title() if result['name'] else uri_to_friendly(result['o']),
                'description': result['description'].split('|')[0] if result['description'] else None,
                'image': result['image'].split('|')[0] if result['image'] else None,
                'stats': [],
            })
            for k, v in result.items():        
                if not k.startswith('stat'):
                    continue
                idx = int(re.sub(r'[^0-9]', '', k))
                stat = statistics[idx]
                cards[-1]['stats'].append((stat['friendly'], format_stat(stat['type'], v.split('|')[0])))
                
        deck = {
            'name': category['friendly'],
            'description': category['description'] if category['description'] else None,
            'cards': cards,
        }

        output_name = 'deck_{}'.format(friendly_to_filename(deck['name']))
        output_dir = os.path.join(os.path.dirname(__file__), output_name)
        logging.info("Writing deck \"{}\" to {}".format(deck['name'], output_dir))
        os.mkdir(output_dir)
        
        for i, card in enumerate(deck['cards']):
            if card['image'] is None:
                continue
            logging.debug('Downloading {}'.format(card['image']))
            res = urlopen(uri_to_ascii(card['image']))
            imagetype = IMAGE_TYPES[res.headers['Content-Type']]
            imagename = 'card{:02d}.{}'.format(i, imagetype)
            with open(os.path.join(output_dir, imagename), 'wb') as f:
                while True:
                    buff = res.read(1024)
                    if not buff:
                        break
                    f.write(buff)
            card['image'] = imagename
                    
        with open(os.path.join(output_dir, '{}.json'.format(output_name)), 'w') as f:
            json.dump(deck, f, indent=2)        
        break
        
    except (HTTPError, URLError) as e:
        logging.error(e)
        logging.debug("Pausing for {}s".format(ERROR_PAUSE_TIME))
        time.sleep(ERROR_PAUSE_TIME)
        continue
