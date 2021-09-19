import random
import codecs
import re
import logging
import json
import time
import os
import os.path
import dateutil.parser

from datetime import datetime
from urllib.request import urlopen, Request, HTTPError, URLError, URLopener
from urllib.parse import urlencode

from . import VERSION


USER_AGENT = 'TropTumps/{} (https://github.com/Frimkron/troptumps) {}'.format(
    VERSION, URLopener.version)
SPARQL_ENDPOINT = 'https://dbpedia.org/sparql'
DEFAULT_DATASET = 'http://dbpedia.org'
MAX_CAT_SIZE = 1_000_000_000
MIN_DECK_SIZE = 30
MAX_DECK_SIZE = 50
MIN_NUM_STATS = 4
MAX_NUM_STATS = 10
ERROR_PAUSE_TIME = 5
CACHE_FILE = os.path.expanduser(os.path.join('~', '.cache', 'troptumps'))
IMAGE_TYPES = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
}
NUMERIC_VAL_CLAUSE = "( isNumeric(xsd:double(str({0}))) " \
                       "|| datatype({0}) = xsd:date " \
                       "|| datatype({0}) = xsd:time " \
                       "|| datatype({0}) = xsd:datetime " \
                       "|| datatype({0}) = xsd:boolean ) "
IMPLICIT_PREFIXES = {
    'http://dbpedia.org/ontology/': 'dbo',
    'http://dbpedia.org/property/': 'dbp',
    'http://dbpedia.org/resource/': 'dbr',
}


def query(q):
    q = re.sub(r'\n\s+', '\n', q)
    url = SPARQL_ENDPOINT
    postdata = urlencode({
        'timeout': '30000',
        'default-graph-uri': DEFAULT_DATASET,
        'query': q,
        'format': 'json',    
    }).encode('utf-8')
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/x-www-form-urlencoded', 
        'Accept': 'application/json, text/json, */*', 
    }
    logging.debug('Requesting {}, [{}]'.format(url, postdata))
    data = json.load(codecs.getreader('utf-8')(urlopen(Request(url, postdata, headers))))
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
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(categories, f)

    with open(CACHE_FILE, 'r') as f:
        categories = json.load(f)

    logging.info('{} categories'.format(len(categories)))    
    if len(categories) == 0:
        return None
    
    cat = categories.pop(0)

    with open(CACHE_FILE, 'w') as f:
        json.dump(categories, f)

    return cat


def uri_to_ascii(uri):
    return re.sub(r'[^\x20-\x7E]', 
                  lambda m: ''.join(['%{:02x}'.format(b) for b in m.group().encode('utf-8')]), 
                  uri)


def shorten_uri(lookup, uri):

    # split prefix from name
    m = re.match(r'^(.*[/#])?([^/#]+)$', uri)
    prefix, name = m.group(1), m.group(2)
    
    # if name contains reserved character, can't use prefix (due to virtuoso bug)
    if re.search(r"[\x00-\x2c./\x3a-x40\x5b-\x5e`\x7b-\x7f-]", name):
        return '<{}>'.format(uri)
        
    # add prefix to lookup if not already there
    if prefix not in lookup:
        lookup[prefix] = 'pf{}'.format(len(lookup))
        
    return '{}:{}'.format(lookup[prefix], name)
    
    
def prefix_declarations(lookup):
    return '\n'.join(['PREFIX {}: <{}>'.format(n,p) for p,n in lookup.items() 
                      if p not in IMPLICIT_PREFIXES])
    
    
def first_sentence(para):
    return re.match(r""" 
        # content
        (
            ".*?"     # quote-delimited
            | \(.*?\) # round-delimited
            | \[.*?\] # square-delimited            
            | \b(     # initial / abbreviation
                [A-Z] 
                | [Aa].[Bb] | [Aa]bbr | [Aa]cad | [Aa].[Dd] | [Aa]l | [Aa]lt | [Aa].[Mm] | [Aa]ssn | [Aa]ug | [Aa]ve 
                | [Bb].[Aa] | [Bb].[Cc] | [Bb].[Pp] | [Bb].[Ss] | [Cc] | [Cc]al | [Cc]apt | [Cc]ent | [Cc]o | [Cc]ol 
                | [Cc]omdr | [Cc]orp | [Cc]pl | [Cc]u | [Dd] | [Dd].[Cc] | [Dd]ec | [Dd]ept | [Dd]ist | [Dd]iv 
                | [Dd]r | [Ee]d | [Ee].[Gg] | [Ee]st | [Ff]eb | [Ff]l | [Gg]al | [Gg]en | [Gg]ov | [Gg]rad | [Hh]on 
                | [Ii].e | [Ii]n | [Ii]nc | [Ii]nst | [Jj]an | [Jj]r | [Ll]at | [Ll]b | [Ll]ib | [Ll]ong | [Ll]t 
                | [Ll]td | [Mm].[Dd] | [Mm]r | [Mm]rs | [Mm]s | [Mm]sgr | [Mm]t | [Mm]ts | [Mm]us | [Nn]o | [Nn]ov 
                | [Oo]ct | [Oo]p | [Pp]l | [Pp]op | [Pp]seud | [Pp]t | [Pp]ub | [Rr]ev | [Rr].[Nn] | [Ss]ept | [Ss]er 
                | [Ss]gt | [Ss]r | [Ss]t | [Uu]ninc | [Uu]niv | [Uu].[Ss] | [Vv]ol | [Vv]s | [Vv] | [Ww]t
              )\.
            | .       # anything
        )*?
        # ending
        (
            # end symbols
            (
                # period, not prefixed with another period
                (?<! \. ) \.                                    
                # or one or more question/exclamation marks
                | [!?]+                  
            ) 
            # suffixed by:
            (?=(
                \s+[^a-z]  # whitespace and non-lower
                |\s*$      # or optional whitespace then EOI
            ))
            # alternatively just EOI
            | $ 
        )
        """
        , para, re.VERBOSE).group(0)
    

def pluralise(name):
    rules = [
        (('ium','tum','lum','ion'), -2, 'a'),
        (('ula','mna','nna','rva','tia'), None, 'e'),
        (('ay','ey','iy','oy','uy'), None, 's'),
        ('is', -2, 'es'),
        (('us','um'), -2, 'i'),
        (('ex','ix'), -2, 'ices'),
        ('ni', None, ''),
        ('y', -1, 'ies'),
        (('s','x','ch','sh'), None, 'es'),
    ]
    for suff,back,repl in rules:
        if name.endswith(suff):
            return name[:-back]+repl
    return name+'s'


def fetch_deck(input_dir):

    prefix_lookup = dict(IMPLICIT_PREFIXES)
        
    # Loop until we get a category that works
    while not input_dir:
        try:
        
            # Choose at random
            catname = get_category()
            if catname is None:
                raise Exception("No more categories")
            
            category = {
                'name': catname,
                'friendly': None,
                'description': None,
                'image': None,
            }
            logging.info('{} chosen'.format(category['name']))
            shorten_uri(prefix_lookup, category['name'])
            
            # Fetch top numerical properties as the statistics
            results = query("""%(prefixes)s
                               SELECT 
                                   ?p 
                                   COUNT(DISTINCT ?o) 
                                   GROUP_CONCAT(DISTINCT datatype(?v), "|") as ?t
                               WHERE
                               {
                                   ?o a %(category)s
                                   . ?o ?p ?v
                                   . FILTER( %(numeric-clause)s
                                             && ?p != dbo:wikiPageID 
                                             && ?p != dbo:wikiPageRevisionID )
                               }
                               GROUP BY ?p
                               ORDER BY DESC(COUNT(DISTINCT ?o))
                               LIMIT %(max-num-stats)d""" % {
                                    'prefixes': prefix_declarations(prefix_lookup),
                                    'category': shorten_uri(prefix_lookup, category['name']), 
                                    'max-num-stats': MAX_NUM_STATS+3, # leeway for when we de-dup
                                    'numeric-clause': NUMERIC_VAL_CLAUSE.format('?v') })
            
            statistics = []
            unqual_seen = set()
            for result in results:
                types = set(result['t'].split('|')) - {''}
                if len(types) == 0:
                    continue
                unqual = result['p'].split('/')[-1]
                if unqual in unqual_seen:
                    continue
                unqual_seen.add(unqual)
                statistics.append({
                    'name': result['p'], 
                    'type': next(iter(types)),
                    'friendly': None,
                })
            statistics = statistics[:MAX_NUM_STATS]
                
            logging.info('{} stats'.format(len(statistics)))
            for s in statistics:
                shorten_uri(prefix_lookup, s['name'])
            
            if len(statistics) < MIN_NUM_STATS:
                logging.info("Insufficient stats: {}".format(len(statistics)))
                continue
            
            # Fetch ids of top category members
            results = query("""%(prefixes)s
                               SELECT ?o COUNT(DISTINCT ?p)
                               WHERE
                               {
                                    ?o a %(category)s
                                    . ?o ?p ?v
                                    . FILTER( ( %(properties)s ) 
                                              && %(numeric-clause)s )
                                }
                                GROUP BY ?o
                                HAVING ( COUNT(DISTINCT ?p) >= %(min-num-stats)d )
                                ORDER BY DESC(COUNT(DISTINCT ?p))
                                LIMIT %(max-deck-size)d""" % {
                                   'prefixes': prefix_declarations(prefix_lookup),
                                   'category': shorten_uri(prefix_lookup, category['name']), 
                                   'properties': ' || '.join([
                                        '?p = {}'.format(shorten_uri(prefix_lookup,p['name'])) for p in statistics]),
                                   'min-num-stats': MIN_NUM_STATS,
                                   'max-deck-size': MAX_DECK_SIZE,
                                   'numeric-clause': NUMERIC_VAL_CLAUSE.format('?v') })
            
            members = [ b['o'] for b in results ]
            logging.info('{} members'.format(len(members)))
            for m in members:
                shorten_uri(prefix_lookup, m)
            
            if len(members) < MIN_DECK_SIZE:
                logging.info("Insufficient members: {}".format(len(members)))
                continue
    
            # fetch category details
            results = query("""%(prefixes)s
                               SELECT 
                                   GROUP_CONCAT(?l, "|") as ?name 
                                   GROUP_CONCAT(?c, "|") as ?description 
                                   GROUP_CONCAT(?t, "|") as ?image
                               WHERE
                               {
                                   OPTIONAL { %(category)s rdfs:label ?l }
                                   OPTIONAL { %(category)s rdfs:comment ?c }
                                   OPTIONAL { %(category)s dbo:thumbnail ?t }
                                   FILTER ( (langMatches(lang(?l), "EN") || lang(?l) = "") 
                                             && (langMatches(lang(?c), "EN") || lang(?c) = "") )
                               }""" % { 'prefixes': prefix_declarations(prefix_lookup),
                                        'category': shorten_uri(prefix_lookup, category['name'])})
            if len(results) > 0:
                result = results[0]
                category['friendly'] = pluralise(result['name'].split('|')[0].title()
                                                 if result['name'] else uri_to_friendly(category['name']))
                category['description'] = first_sentence(result['description'].split('|')[0]) \
                                            if result['description'] else None
                category['image'] = result['image'].split('|')[0] \
                                            if result['image'] else None
            else:
                category['friendly'] = pluralise(uri_to_friendly(category['name']))
            
            # fetch stat details
            results = query("""%(prefixes)s
                               SELECT ?p GROUP_CONCAT(?l, "|") as ?name
                               WHERE
                               {
                                   ?p rdfs:label ?l                               
                                   . FILTER( ( %(properties)s )
                                             && ( langMatches(lang(?l),"EN") || lang(?l) = "" ) )
                               }
                               GROUP BY ?p""" % {
                                   'prefixes': prefix_declarations(prefix_lookup),
                                   'properties': ' || '.join([
                                        '?p = {}'.format(shorten_uri(prefix_lookup, p['name'])) for p in statistics]) })
                                   
            lookup = { r['p']: r['name'].split('|')[0].title() for r in results if r['name'] }
            for s in statistics:
                s['friendly'] = lookup.get(s['name'], uri_to_friendly(s['name']))
                               
            # Fetch member details
            results = query("""%(prefixes)s
                               SELECT 
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
                                    'prefixes': prefix_declarations(prefix_lookup),
                                    'property-projections': '\n'.join([
                                        'GROUP_CONCAT(DISTINCT ?p{}, "|") as ?stat{}'.format(i, i) 
                                        for i,p in enumerate(statistics)]),
                                    'property-joins': '\n'.join([
                                        'OPTIONAL {{ ?o {} ?p{} . FILTER {} }}'.format(
                                            shorten_uri(prefix_lookup, p['name']), i, 
                                            NUMERIC_VAL_CLAUSE.format('?p{}'.format(i)))
                                        for i,p in enumerate(statistics)]), 
                                    'members': ' '.join([
                                        '{}'.format(shorten_uri(prefix_lookup, m))
                                        for m in members] )})
            
            cards = []
            for result in results:
                cards.append({
                    'name': result['name'].split('|')[0].title() if result['name'] else uri_to_friendly(result['o']),
                    'description': first_sentence(result['description'].split('|')[0])
                                   if result['description'] else None,
                    'image': result['image'].split('|')[0] if result['image'] else None,
                    'stats': [],
                })
                for k, v in result.items():        
                    if not k.startswith('stat'):
                        continue
                    idx = int(re.sub(r'[^0-9]', '', k))
                    stat = statistics[idx]
                    cards[-1]['stats'].append(format_stat(stat['type'], v.split('|')[0]))
                    
            deck = {
                'name': category['friendly'],
                'description': category['description'] if category['description'] else None,
                'stats': [s['friendly'] for s in statistics],
                'cards': cards,
            }
    
            output_name = 'deck_{}'.format(friendly_to_filename(deck['name']))
            output_dir = os.path.abspath(os.path.join('.', output_name))
            logging.info("Writing deck \"{}\" to {}".format(deck['name'], output_dir))
            os.mkdir(output_dir)
            
            for i, card in enumerate(deck['cards']):
                if card['image'] is None:
                    continue
                logging.debug('Downloading {}'.format(card['image']))
                try:
                    res = urlopen(Request(uri_to_ascii(card['image']), headers={'User-Agent': USER_AGENT}))
                except HTTPError as e:
                    if e.getcode() == 404:
                        logging.warn("404 for {}".format(card['image']))
                        card['image'] = None
                        continue
                    raise
                contenttype = res.headers['Content-Type']
                imagetype = IMAGE_TYPES.get(contenttype, None)
                if imagetype is None:
                    logging.warn("Non-image response ({}) for {}".format(contenttype, card['image']))
                    card['image'] = None
                    continue
                imagename = 'card{:02d}.{}'.format(i, imagetype)
                with open(os.path.join(output_dir, imagename), 'wb') as f:
                    while True:
                        buff = res.read(1024)
                        if not buff:
                            break
                        f.write(buff)
                card['image'] = imagename
               
            logging.debug("writing json file")         
            with open(os.path.join(output_dir, '{}.json'.format(output_name)), 'w') as f:
                json.dump(deck, f, indent=2)
            
            # exit condition - we're done
            input_dir = output_dir
            
        except (HTTPError, URLError) as e:
            logging.error(e)
            logging.debug("Pausing for {}s".format(ERROR_PAUSE_TIME))
            time.sleep(ERROR_PAUSE_TIME)
            continue

    return input_dir
