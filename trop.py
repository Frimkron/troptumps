#!/usr/bin/env python3

""" 
TODO: Properties that are basically the same with different names/prefixes
TODO: At least fix middle initials as end of sentences (test)
TODO: Can post instead of get to avoid max uri length? (it would appear not) 
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
import argparse
import dateutil.parser
import enum
import colorsys
from collections import namedtuple
from reportlab.pdfgen import canvas
from reportlab import platypus
from reportlab.lib import pagesizes
from reportlab.lib.units import mm
from reportlab.lib import styles
from reportlab.lib import colors
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics
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
DEFAULT_FONT = 'DejaVuSans'
FONT_FALLBACK_REGEX = r'[^\u0000-\u01ff]+'
FONT_FALLBACK_ORDER = ['DejaVuSans', 'Cyberbit']
FONT_B_SUFFIX = '-Bold'
FONT_I_SUFFIX = '-Oblique'
FONT_BI_SUFFIX = '-BoldOblique'

class BacksType(enum.Enum):
    LONG_FLIP = enum.auto()
    SHORT_FLIP = enum.auto()
    NONE = enum.auto()
               
GOLDEN_RATIO = 0.617
DEFAULT_PAGE_SIZE = 'a4'
DEFAULT_LOG_LEVEL = 'info'
DEFAULT_PAGE_MARGIN = 9*mm
DEFAULT_BLEED_MARGIN = 3*mm
DEFAULT_PRIMARY_S = 0.5
DEFAULT_PRIMARY_L_RANGE = 0.1, 0.8
DEFAULT_BACKS_TYPE = BacksType.LONG_FLIP.name.lower()
SECONDARY_HUE_ADJACENCY = 0.15
SECONDARY_LUM_CONTRAST = 0.35
SECONDARY_DESATURATION = 0.3
SECONDARY_ROW_LUM_VAR = 0.1
TEXT_LUM_CONTRAST = 0.7

CARD_SIZE = 63.5*mm, 88.9*mm
CARD_TEXT_SIZE = 2.25*mm
CARD_STAT_SIZE = 2.15*mm
CARD_SMALLPRINT_SIZE = 2*mm
CARD_TITLE_SIZE = 3.5*mm
CARD_MARGIN = 3*mm
CARD_LINE_SPACING = 1.1
CARD_SECTION_PROPS = 0.75, 2, 1.75, 3.5
CARD_OUTLINE_WIDTH = 0.25*mm
DECK_TITLE_SIZE = 8*mm
DECK_PRETITLE_SIZE = 6*mm
DECK_CREDITS = "Generated using data from http://wiki.dbpedia.org"
CARD_STAT_SPACING = 1.3
CARD_CORNER_RAD = 4*mm

class PdfVars(enum.Enum):
    BLEED_MARGIN = enum.auto()
    PAGE_MARGIN = enum.auto()
    PAGE_SIZE = enum.auto()
    ROUND_CORNERS = enum.auto()
    PRIMARY_HSL = enum.auto()
    SECONDARY_HSL = enum.auto()
    TEXT_HSL = enum.auto()
    BACKS_TYPE = enum.auto()


def query(q):
    q = re.sub(r'\n\s+', '\n', q)
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
            [^("\[]   # any non-bracket
            | ".*?"   # quote-delimited
            | \(.*?\) # round-delimited
            | \[.*?\] # square-delimited
        )+?
        # ending
        (
            # end symbols
            (
                (?<! (\b[A-Z] | \.) ) \. # period, not prefixed with another period or single capital
                | [!?]+                  # or one or more question/exclamation marks
            ) (?=(\s|$))   # suffixed by whitespace or EOI
            # alternatively just EOI
            | $ 
        )
        """
        , para, re.VERBOSE).group(0)
    

def pluralise(name):
    rules = [
        (('ium','tum','lum','ion'), 2, 'a'),
        (('ula','mna','nna','rva','tia'), None, 'e'),
        (('ay','ey','iy','oy','uy'), None, 's'),
        ('is', 2, 'es'),
        (('us','um'), 2, 'i'),
        (('ex','ix'), 2, 'ices'),
        ('ni', None, ''),
        ('y', 1, 'ies'),
        (('s','x','ch','sh'), None, 'es'),
    ]
    for suff,back,repl in rules:
        if name.endswith(suff):
            return name[:-back]+repl
    return name+'s'


def adjacent_h(hsl, amount):
    return (hsl[0]+amount)%1.0, hsl[1], hsl[2]
    
    
def contrasting_l(hsl, amount):
    return (hsl[0], hsl[1], 
        max(min(hsl[2]+(amount*(1 if hsl[2]<0.5 else -1)),1.0),0.0) )


def desaturated(hsl, amount):
    return hsl[0], max(min(hsl[1]-amount,1.0),0.0), hsl[2]


def lightened(hsl, amount):
    return hsl[0], hsl[1], max(min(hsl[2]+amount,1.0),0.0)


def grid_size(config):
    avail_page_w = config[PdfVars.PAGE_SIZE][0]-config[PdfVars.PAGE_MARGIN]*2
    avail_page_h = config[PdfVars.PAGE_SIZE][1]-config[PdfVars.PAGE_MARGIN]*2
    total_card_w = CARD_SIZE[0] + config[PdfVars.BLEED_MARGIN]*2
    total_card_h = CARD_SIZE[1] + config[PdfVars.BLEED_MARGIN]*2
    return int(avail_page_w / total_card_w), int(avail_page_h / total_card_h)
    
    
def card_canv_itr(c, config):
    backstype = config[PdfVars.BACKS_TYPE]
    text_hsl = contrasting_l(config[PdfVars.PRIMARY_HSL], TEXT_LUM_CONTRAST)
    facesize = CARD_SIZE[0]-CARD_MARGIN*2, CARD_SIZE[1]-CARD_MARGIN*2
    endnow = False
    while True:
        # fronts        
        cardcount = 0
        fronts_itr = card_canv_itr_page(c, config, False, False)
        for i in fronts_itr:
            cardcount += 1
            endnow = yield
            if endnow:
                halt_card_itr(fronts_itr)
        # backs
        if backstype != BacksType.NONE:
            """ 
               < L >        < S >
              +--+--+    +----+----+
            ^ |^ | ^|  ^ |^   |   ^|
            S +--+--+  L +----+----+
            v |v |     v |v   |
              +--+ Po    +----+   La
            """
            pagesize = config[PdfVars.PAGE_SIZE]
            upsidedown = (pagesize[1] > pagesize[0]) == (backstype == BacksType.SHORT_FLIP)
            backs_itr = card_canv_itr_page(c,config, True, upsidedown) 
            for i in range(cardcount):
                next(backs_itr)
                c.setFillColorRGB(*colors.hsl2rgb(*text_hsl))
                c.setFont(DEFAULT_FONT+FONT_I_SUFFIX, DECK_TITLE_SIZE)
                c.drawCentredString(facesize[0]/2, -facesize[1]*(1-GOLDEN_RATIO), "Trop Tumps")
            halt_card_itr(backs_itr)
        if endnow:
            break


def card_canv_itr_page(c, config, rtl, upsidedown):
    gridsize = grid_size(config)
    pagesize = config[PdfVars.PAGE_SIZE]
    pmargin = config[PdfVars.PAGE_MARGIN]
    bleed = config[PdfVars.BLEED_MARGIN]
    primary_hsl = config[PdfVars.PRIMARY_HSL]
    outline_hsl = contrasting_l(primary_hsl, TEXT_LUM_CONTRAST)
    rounded = config[PdfVars.ROUND_CORNERS]
    card_space = CARD_SIZE[0]+bleed*2, CARD_SIZE[1]+bleed*2
    xstart = pagesize[0]-pmargin*2-card_space[0] if rtl else 0
    xdir = -1 if rtl else 1

    c.translate(pagesize[0]/2, pagesize[1]/2)
    c.rotate(180 if upsidedown else 0)   
    c.translate(-pagesize[0]/2 + pmargin + xstart, pagesize[1]/2 - pmargin)
    endnow = False
    for j in range(gridsize[1]):
        for i in range(gridsize[0]):
            c.saveState()
            # draw background colour over whole bleed area
            c.translate(card_space[0]*i*xdir, -card_space[1]*j)
            c.setFillColorRGB(*colors.hsl2rgb(*primary_hsl))
            c.rect(0.0, 0.0, card_space[0], -card_space[1], stroke=0, fill=1)
            # draw card outline
            c.translate(bleed, -bleed)
            c.setStrokeColorRGB(*colors.hsl2rgb(*outline_hsl))
            c.setLineWidth(CARD_OUTLINE_WIDTH)
            if rounded:
                c.roundRect(0.0, -CARD_SIZE[1], CARD_SIZE[0], CARD_SIZE[1], CARD_CORNER_RAD, stroke=1, fill=0)
            else:
                c.rect(0.0, 0.0, CARD_SIZE[0], -CARD_SIZE[1], stroke=1, fill=0)
            # move to card design area
            c.translate(CARD_MARGIN, -CARD_MARGIN)
            endnow = yield
            c.restoreState()
            if endnow: 
                break
        if endnow: 
            break            
    c.showPage()


def halt_card_itr(itr):
    try:
        itr.send(True)
    except StopIteration:
        pass


def colour_string(string):
    m = re.match(r'^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$', string, re.IGNORECASE)    
    if m:
        r,g,b = [int(m.group(c+1),16)/255.0 for c in range(3)]
        h,l,s = colorsys.rgb_to_hls(r,g,b)
        return h,s,l

    m = re.match(r'^#([0-9a-f])([0-9a-f])([0-9a-f])$', string, re.IGNORECASE)
    if m:
        r,g,b = [int(m.group(c+1),16)/15.0 for c in range(3)]
        h,l,s = colorsys.rgb_to_hls(r,g,b)
        return h,s,l
        
    named_colours = { n: getattr(colors,n) for n in dir(colors) 
                      if isinstance(getattr(colors,n),colors.Color) and re.match(r'^[a-z]+$',n) }
    name = string.replace(' ','').lower()
    if name in named_colours:
        r,g,b = named_colours[name].rgb()
        h,l,s = colorsys.rgb_to_hls(r,g,b)
        return h,s,l
        
    raise ValueError()


def tag_font_fallbacks(text):
    def repl(match):
        out = ""
        prev = None
        fnum = 0
        for c in match.group(0):
            while fnum < len(FONT_FALLBACK_ORDER):
                if ord(c) in pdfmetrics.getFont(FONT_FALLBACK_ORDER[fnum]).face.charWidths:
                    if fnum != prev:
                        if prev is not None:
                            out += '</font>'
                        out += '<font face="{}">'.format(FONT_FALLBACK_ORDER[fnum])
                        prev = fnum
                    out += c
                    break
                fnum += 1
            else:
                logging.warn('No font for character {}'.format(hex(ord(c))))
                out += c
                fnum = 0
        if prev is not None:
            out += '</font>'
        logging.debug('Fallback replacement: "{}" -> "{}"'.format(match.group(0), out))
        return out
                
    return re.sub(FONT_FALLBACK_REGEX, repl, text)
    
    
ap = argparse.ArgumentParser()
ap.add_argument('-d','--datadir',
                help="Re-generate PDF from this existing directory rather than starting from scratch.")
ap.add_argument('-l','--loglevel',choices=('debug','info','warn','error','fatal'),default=DEFAULT_LOG_LEVEL,
                help="Verbosity of output. Defaults to {}.".format(DEFAULT_LOG_LEVEL))
ap.add_argument('-p','--pagesize',choices=[s.lower() for s in dir(pagesizes) if re.match(r'[A-Z]',s)], 
                default=DEFAULT_PAGE_SIZE,
                help="Paper size to output. Defaults to {}.".format(DEFAULT_PAGE_SIZE))
ap.add_argument('-m','--pagemargin',type=float,default=DEFAULT_PAGE_MARGIN,
                help="Page margin in mm. Defaults to {}.".format(DEFAULT_PAGE_MARGIN))
ap.add_argument('-b','--bleedmargin',type=float,default=DEFAULT_BLEED_MARGIN,
                help="Bleed area to leave around cards, in mm. Defaults to {}.".format(DEFAULT_BLEED_MARGIN))
ap.add_argument('-k','--backs', choices=([b.name.lower() for b in BacksType]), default=DEFAULT_BACKS_TYPE,
                help="Method to orient odd pages for card backs. Defaults to {}".format(DEFAULT_BACKS_TYPE))
ap.add_argument('-c','--color',type=colour_string,default=None,
                help="Force primary color. Takes an HTML color name or hex code.")
ap.add_argument('-s','--seccolor',type=colour_string,default=None,
                help="Force secondary color. Takes an HTML color name or hex code. Defaults to adjacent hue "
                     "of primary color.")
ap.add_argument('-q','--sqcorners',action='store_true',
                help="Print square card corners instead of round.")
                
args = ap.parse_args()
    
logging.basicConfig(level=getattr(logging,args.loglevel.upper()))
input_dir = args.datadir
prefix_lookup = dict(IMPLICIT_PREFIXES)
    
# Loop until we get a category that works
while not input_dir:
    try:
    
        # Choose at random
        category = {
            'name': get_category(),
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
                                'max-num-stats': MAX_NUM_STATS,
                                'numeric-clause': NUMERIC_VAL_CLAUSE.format('?v') })
        
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
                'description': first_sentence(result['description'].split('|')[0]) if result['description'] else None,
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
        output_dir = os.path.join(os.path.dirname(__file__), output_name)
        logging.info("Writing deck \"{}\" to {}".format(deck['name'], output_dir))
        os.mkdir(output_dir)
        
        for i, card in enumerate(deck['cards']):
            if card['image'] is None:
                continue
            logging.debug('Downloading {}'.format(card['image']))
            try:
                res = urlopen(uri_to_ascii(card['image']))
            except HTTPError as e:
                if e.getcode() == 404:
                    continue
                raise
            imagetype = IMAGE_TYPES[res.headers['Content-Type']]
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
        
# read deck data
input_name = os.path.basename(input_dir)
with open(os.path.join(input_dir, '{}.json'.format(input_name)), 'r') as f:
    deck = json.load(f)

logging.info("Generating PDF")
output_dir = input_dir
output_name = input_name
primary_hsl = args.color if args.color is not None \
                         else (random.random(),
                               DEFAULT_PRIMARY_S,
                               DEFAULT_PRIMARY_L_RANGE[0] + sum([random.random() for i in range(3)])/3.0 
                                        * (DEFAULT_PRIMARY_L_RANGE[1]-DEFAULT_PRIMARY_L_RANGE[0]))
secondary_hsl = args.seccolor if args.seccolor is not None \
                              else desaturated(
                                        contrasting_l(
                                            adjacent_h(primary_hsl,SECONDARY_HUE_ADJACENCY),
                                            SECONDARY_LUM_CONTRAST),
                                        SECONDARY_DESATURATION)
text_hsl = desaturated(contrasting_l(secondary_hsl, TEXT_LUM_CONTRAST), 1.0)

pdf_config = {
    PdfVars.PAGE_SIZE: getattr(pagesizes, args.pagesize.upper()),
    PdfVars.PAGE_MARGIN: args.pagemargin,
    PdfVars.BLEED_MARGIN: args.bleedmargin,
    PdfVars.ROUND_CORNERS: not args.sqcorners,
    PdfVars.PRIMARY_HSL: primary_hsl,
    PdfVars.SECONDARY_HSL: secondary_hsl,
    PdfVars.TEXT_HSL: text_hsl,
    PdfVars.BACKS_TYPE: getattr(BacksType, args.backs.upper()),
}

# establish if portrait or landscape better
pdf_config[PdfVars.PAGE_SIZE] = pagesizes.portrait(pdf_config[PdfVars.PAGE_SIZE])
pt_gridsize = grid_size(pdf_config)

pdf_config[PdfVars.PAGE_SIZE] = pagesizes.landscape(pdf_config[PdfVars.PAGE_SIZE])
ls_gridsize = grid_size(pdf_config)

if pt_gridsize[0]*pt_gridsize[1] > ls_gridsize[0]*ls_gridsize[1]:
    pdf_config[PdfVars.PAGE_SIZE] = pagesizes.portrait(pdf_config[PdfVars.PAGE_SIZE])
else:
    pdf_config[PdfVars.PAGE_SIZE] = pagesizes.landscape(pdf_config[PdfVars.PAGE_SIZE])

# load fonts
for fontfam in FONT_FALLBACK_ORDER:
    for fontext in ('.ttf', '.otf'):
        fargs = {}
        for fsuff,arg in [('','normal'), (FONT_B_SUFFIX,'bold'), (FONT_I_SUFFIX,'italic'), 
                          (FONT_BI_SUFFIX,'boldItalic')]:
            fname = fontfam + fsuff
            ffile = fname + fontext
            if not os.path.exists(ffile):
                continue
            pdfmetrics.registerFont(ttfonts.TTFont(fname, ffile))
            fargs[arg] = fname

        if len(fargs) > 0:
            pdfmetrics.registerFontFamily(fontfam, **fargs)
            break

prefront_style = styles.ParagraphStyle('prefront-style', fontName=DEFAULT_FONT, fontSize=DECK_PRETITLE_SIZE,
                                        alignment=styles.TA_CENTER, textColor=colors.Color(
                                            *colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])))
front_style = styles.ParagraphStyle('front-style', fontName=DEFAULT_FONT, fontSize=DECK_TITLE_SIZE,
                                    alignment=styles.TA_CENTER, leading=DECK_TITLE_SIZE*CARD_LINE_SPACING,
                                    textColor=colors.Color(*colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])))
title_style = styles.ParagraphStyle('title-style', fontName=DEFAULT_FONT, fontSize=CARD_TITLE_SIZE, 
                                    alignment=styles.TA_CENTER, textColor=colors.Color(
                                        *colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])))
desc_style = styles.ParagraphStyle('desc-style', fontName=DEFAULT_FONT, fontSize=CARD_TEXT_SIZE, 
                                   leading=CARD_TEXT_SIZE*CARD_LINE_SPACING, 
                                   textColor=colors.Color(*colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])))
creds_style = styles.ParagraphStyle('creds-style', fontName=DEFAULT_FONT, fontSize=CARD_TEXT_SIZE,
                                   leading=CARD_TEXT_SIZE*CARD_LINE_SPACING, alignment=styles.TA_CENTER,
                                   textColor=colors.Color(
                                        *colors.hsl2rgb(*contrasting_l(pdf_config[PdfVars.PRIMARY_HSL], 
                                                                       TEXT_LUM_CONTRAST))))
stat_style = styles.ParagraphStyle('stat-style', fontName=DEFAULT_FONT, fontSize=CARD_STAT_SIZE, 
                                   leading=CARD_STAT_SIZE, 
                                   textColor=colors.Color(*colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])))
                                   
front_tbl_style = platypus.TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),
                                       ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                                       ('ROWBACKGROUNDS',(0,0),(-1,2),
                                            [colors.hsl2rgb(*pdf_config[PdfVars.SECONDARY_HSL])]),
                                       ('TOPPADDING',(0,0),(-1,-1),2*mm),
                                       ('BOTTOMPADDING',(0,0),(-1,-1),2*mm),
                                       ('LEFTPADDING',(0,0),(-1,-1),2*mm),
                                       ('RIGHTPADDING',(0,0),(-1,-1),2*mm)])
tbl_style = platypus.TableStyle([('ALIGN',(0,0),(0,1),'CENTER'),
                                 ('ALIGN',(0,3),(-1,-1),'CENTER'),
                                 ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                                 ('ROWBACKGROUNDS',(0,0),(-1,-1),
                                        [colors.hsl2rgb(*pdf_config[PdfVars.SECONDARY_HSL]),None]),
                                 ('TOPPADDING',(0,0),(-1,-1),0),
                                 ('BOTTOMPADDING',(0,0),(-1,-1),0),
                                 ('LEFTPADDING',(0,0),(0,-2),3*mm),
                                 ('RIGHTPADDING',(0,0),(0,-2),3*mm),
                                 ('LEFTPADDING',(0,-1),(0,-1),0),
                                 ('RIGHTPADDING',(0,-1),(0,-1),0)])
stat_tbl_style = platypus.TableStyle([('ALIGN',(0,0),(0,-1),'LEFT'),
                                      ('ALIGN',(1,0),(1,-1),'RIGHT'),
                                      ('FONTNAME',(0,0),(-1,-1),DEFAULT_FONT),
                                      ('FONTSIZE',(0,0),(-1,-1),CARD_STAT_SIZE),
                                      ('ROWBACKGROUNDS',(0,0),(-1,-1),
                                            [colors.hsl2rgb(*lightened(pdf_config[PdfVars.SECONDARY_HSL],
                                                                       SECONDARY_ROW_LUM_VAR/2)),
                                             colors.hsl2rgb(*lightened(pdf_config[PdfVars.SECONDARY_HSL],
                                                                       -SECONDARY_ROW_LUM_VAR/2)) ]),
                                      ('TEXTCOLOR',(0,0),(-1,-1),colors.hsl2rgb(*pdf_config[PdfVars.TEXT_HSL])),
                                      ('LEFTPADDING',(0,0),(-1,-1),2*mm),
                                      ('RIGHTPADDING',(0,0),(-1,-1),2*mm),
                                      ('TOPPADDING',(0,0),(-1,-1),0),
                                      ('BOTTOMPADDING',(0,0),(-1,-1),0),
                                      ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                                      ('LEADING',(0,0),(-1,-1),CARD_STAT_SIZE)])
    
canv = canvas.Canvas(os.path.join(output_dir, '{}.pdf'.format(output_name)), pagesize=pdf_config[PdfVars.PAGE_SIZE])
canv.setTitle('Trop Tumps '+deck['name'])
canv_itr = card_canv_itr(canv, pdf_config)
facesize = CARD_SIZE[0]-CARD_MARGIN*2, CARD_SIZE[1]-CARD_MARGIN*2

# title card
next(canv_itr)
pretitle = platypus.Paragraph('<i>Trop Tumps</i>', prefront_style)
title = platypus.Paragraph(tag_font_fallbacks(deck['name']), front_style)
desc  = platypus.Paragraph(tag_font_fallbacks(deck['description']), desc_style) if deck['description'] else None
creds = platypus.Paragraph(DECK_CREDITS, creds_style)
tbl = platypus.Table([[pretitle],[title],[desc],[creds]])
tbl.setStyle(front_tbl_style)
tblsize = tbl.wrap(*facesize)
tbl.wrapOn(canv, *facesize)
tbl.drawOn(canv, 0,-facesize[1]*(1-GOLDEN_RATIO)-tblsize[1]/2)

# cards
for card_idx, card in enumerate(deck['cards']):
    next(canv_itr)
    title = platypus.Paragraph(tag_font_fallbacks(card['name']), title_style)
    img = platypus.Image(os.path.join(output_dir, card['image']), facesize[0], 
                         facesize[1]*(CARD_SECTION_PROPS[1]/sum(CARD_SECTION_PROPS)), 
                         kind='proportional') if card['image'] else None
    desc = platypus.Paragraph(tag_font_fallbacks(card['description']), desc_style) if card['description'] else None
    stattbl = platypus.Table([ [platypus.Paragraph(tag_font_fallbacks(deck['stats'][i]), stat_style), 
                                platypus.Paragraph(tag_font_fallbacks(card['stats'][i]), stat_style)]
                               for i in range(len(deck['stats'])) ], 
                             rowHeights=CARD_TEXT_SIZE*CARD_STAT_SPACING, colWidths=(None, facesize[0]/3.0),
                             spaceBefore=0, spaceAfter=0)
    stattbl.setStyle(stat_tbl_style)
    tbl = platypus.Table([[title],[img],[desc],[stattbl]], 
                         rowHeights=[facesize[1]*(p/sum(CARD_SECTION_PROPS)) for p in CARD_SECTION_PROPS])
    tbl.setStyle(tbl_style)
    tblsize = tbl.wrap(*facesize)
    tbl.wrapOn(canv, *facesize)
    tbl.drawOn(canv, 0, -tblsize[1])
    
    canv.setFillColorRGB(*colors.hsl2rgb(*contrasting_l(pdf_config[PdfVars.PRIMARY_HSL], TEXT_LUM_CONTRAST)))
    canv.setFont(DEFAULT_FONT, CARD_SMALLPRINT_SIZE)
    canv.drawRightString(facesize[0], -facesize[1], "{0} / {1}".format(card_idx+1, len(deck['cards'])))
halt_card_itr(canv_itr)
                        
canv.save()
