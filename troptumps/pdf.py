import os
import os.path
import json
import logging
import colorsys
import enum
import re
import random
from reportlab.pdfgen import canvas
from reportlab import platypus
from reportlab.lib import pagesizes
from reportlab.lib.units import mm
from reportlab.lib import styles
from reportlab.lib import colors
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics


class PdfVars(enum.Enum):
    BLEED_MARGIN = enum.auto()
    PAGE_MARGIN = enum.auto()
    PAGE_SIZE = enum.auto()
    ROUND_CORNERS = enum.auto()
    PRIMARY_HSL = enum.auto()
    SECONDARY_HSL = enum.auto()
    TEXT_HSL = enum.auto()
    BACKS_TYPE = enum.auto()


class BacksType(enum.Enum):
    LONG_FLIP = enum.auto()
    SHORT_FLIP = enum.auto()
    NONE = enum.auto()


FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
DEFAULT_FONT = 'DejaVuSans'
FONT_FALLBACK_REGEX = r'[^\u0000-\u01ff]+'
FONT_FALLBACK_ORDER = ['DejaVuSans', 'FreeSerif', 'KaiGenGothicCN']
FONT_B_SUFFIX = '-Bold'
FONT_I_SUFFIX = '-Oblique'
FONT_BI_SUFFIX = '-BoldOblique'

GOLDEN_RATIO = 0.617
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

DEFAULT_PAGE_SIZE = 'a4'
DEFAULT_PAGE_MARGIN_MM = 9
DEFAULT_BLEED_MARGIN_MM = 3
DEFAULT_PRIMARY_S = 0.5
DEFAULT_PRIMARY_L_RANGE = 0.1, 0.8
DEFAULT_BACKS_TYPE = BacksType.LONG_FLIP.name.lower()    


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


def create_pdf(args, input_dir):

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
        PdfVars.PAGE_MARGIN: args.pagemargin*mm,
        PdfVars.BLEED_MARGIN: args.bleedmargin*mm,
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
                ffile = os.path.join(FONT_DIR, fname + fontext)
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
        img = platypus.Image(os.path.join(output_dir, card['image']), facesize[0]-6*mm, 
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
