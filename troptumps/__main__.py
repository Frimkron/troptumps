#!/usr/bin/env python3


import re
import sys
import logging
import argparse
import colorsys

from reportlab.lib import pagesizes

from . import pdf
from . import fetch
from . import VERSION


DEFAULT_LOG_LEVEL = 'info'


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

               
def main():    
    
    ap = argparse.ArgumentParser(description='Finds a suitable category from wikipedia and generates a PDF of playing '
                                             'cards from it, in the current directory.')
    ap.add_argument('-d','--datadir',
                    help="Re-generate PDF from this existing directory rather than starting from scratch.")
    ap.add_argument('-l','--loglevel',choices=('debug','info','warn','error','fatal'),default=DEFAULT_LOG_LEVEL,
                    help="Verbosity of output. Defaults to {}.".format(DEFAULT_LOG_LEVEL))
    ap.add_argument('-p','--pagesize',choices=[s.lower() for s in dir(pagesizes) if re.match(r'[A-Z]',s)], 
                    default=pdf.DEFAULT_PAGE_SIZE,
                    help="Paper size to output. Defaults to {}.".format(pdf.DEFAULT_PAGE_SIZE))
    ap.add_argument('-m','--pagemargin',type=float,default=pdf.DEFAULT_PAGE_MARGIN_MM,
                    help="Page margin in mm. Defaults to {}.".format(pdf.DEFAULT_PAGE_MARGIN_MM))
    ap.add_argument('-b','--bleedmargin',type=float,default=pdf.DEFAULT_BLEED_MARGIN_MM,
                    help="Bleed area to leave around cards, in mm. Defaults to {}.".format(pdf.DEFAULT_BLEED_MARGIN_MM))
    ap.add_argument('-k','--backs', choices=([b.name.lower() for b in pdf.BacksType]), default=pdf.DEFAULT_BACKS_TYPE,
                    help="Method to orient odd pages for card backs. Defaults to {}".format(pdf.DEFAULT_BACKS_TYPE))
    ap.add_argument('-c','--color',type=colour_string,default=None,
                    help="Force primary color. Takes an HTML color name or hex code.")
    ap.add_argument('-s','--seccolor',type=colour_string,default=None,
                    help="Force secondary color. Takes an HTML color name or hex code. Defaults to adjacent hue "
                         "of primary color.")
    ap.add_argument('-q','--sqcorners',action='store_true',
                    help="Print square card corners instead of round.")
    ap.add_argument('-v','--version',action='store_true',
                    help="Output version number and exit")
                    
    args = ap.parse_args()
    
    if args.version:
        sys.exit("Trop Tumps v{} by Mark Frimston".format(VERSION))
        
    logging.basicConfig(level=getattr(logging,args.loglevel.upper()))

    # fetch deck data if necessary
    input_dir = fetch.fetch_deck(args.datadir)

    # create pdf
    pdf.create_pdf(args, input_dir)
    

if __name__ == "__main__":
    main()
