import unittest

import troptumps.fetch as fetch


class FirstSentenceTests(unittest.TestCase):

    CASES = [
        ("Simple sentence. Second sentence.", "Simple sentence."), 
        ("", ""),
        (" ", " "),
        (".", "."),
        ("..", ".."),
        ("Ends at end of input", "Ends at end of input"),
        
        ("Ends with exclamation! Second sentence.", "Ends with exclamation!"),
        ("Ends with question? Second sentence.", "Ends with question?"),
        ("Multiple end symbols?!? Second sentence.", "Multiple end symbols?!?"),
        ("Second uncapitalised. second sentence.", "Second uncapitalised. second sentence."),
        ("Second number start. 2nd sentence.", "Second number start."),
        ("Dot.in.word. Second sentence.", "Dot.in.word."),
        ("Exclamation!in!word! Second sentence.", "Exclamation!in!word!"),
        ("Question?in?word? Second sentence.", "Question?in?word?"),
        
        ("Ellipsis... and end. Second sentence.", "Ellipsis... and end."),
        ("Long ellipsis............ and end. Second sentence.", "Long ellipsis............ and end."),
        ("Short ellipsis.. and end. Second sentence.", "Short ellipsis.. and end."),
        ("Ellipsis at EOI...", "Ellipsis at EOI..."),
        ("...Ellipsis at start. Second sentence.", "...Ellipsis at start."),
        
        ("A.C.R.O.N.Y.M. at start. Second sentence.", "A.C.R.O.N.Y.M. at start."),
        ("At end A.C.R.O.N.Y.M. Second sentence.", "At end A.C.R.O.N.Y.M. Second sentence."), #
        ("Middle I. Nitial. Second sentence.", "Middle I. Nitial."),
        ("One capital end, I. Second sentence.", "One capital end, I. Second sentence."), #
        ("One lower end, a. Second sentence.", "One lower end, a."),
        ("One number end, 0. Second sentence.", "One number end, 0."),
        ("Two capital end, YO. Second sentence.", "Two capital end, YO."),
        ("Two lower end, ja. Second sentence.", "Two lower end, ja."),
        ("Two number end, 12. Second sentence.", "Two number end, 12."),
        ("Capitalised vs. Capitalised. Second sentence.", "Capitalised vs. Capitalised."),
        ("Capitalised v. Capitalised. Second sentence.", "Capitalised v. Capitalised."),
        ("lower vs. lower. Second sentence.", "lower vs. lower."),
        ("lower v. lower. Second sentence.", "lower v. lower."),
        
        ("(Period in. Bracket). Second sentence.", "(Period in. Bracket)."),
        ('"Period in. Quote". Second sentence.', '"Period in. Quote".'),
        ('[Period in. Squares]. Second sentence.', '[Period in. Squares].'),
        ("(Period in (nested.) Brackets). Second sentence.", "(Period in (nested.) Brackets)."),
        ("(Period near (nested). Brackets). Second sentence.", "(Period near (nested)."),
        ('(Period in "mixed." Delimiters). Second sentence.', '(Period in "mixed." Delimiters).'),
        ("(End in bracket.) Second sentence.", "(End in bracket.) Second sentence."), #
        ("Lone closing ) bracket. Second sentence.", "Lone closing ) bracket."),
        ("Lone opening ( bracket. Second sentence.", "Lone opening ( bracket."),
        
        ("An abbr. Mr Bond. Second sentence.", "An abbr. Mr Bond."),
        ("In Aug. Mr Bond. Second sentence.", "In Aug. Mr Bond."),
        ("In aug. Mr Bond. Second sentence.", "In aug. Mr Bond."),
        ("An e.g. Mr Bond. Second sentence.", "An e.g. Mr Bond."),
        ("A t.e.s.t. Mr Bond. Second sentence.", "A t.e.s.t."), #
        ("A p.e.g. Mr Bond. Second sentence.", "A p.e.g. Mr Bond."), #
    ]
    
    def test_first_sentence(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(expected, fetch.first_sentence(text))
            
