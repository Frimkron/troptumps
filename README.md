Trop Tumps
==========

A statistics-duelling deck generator using data from wikipedia.

Trop Tumps chooses random categories from _dbpedia.org_ and turns them into 
(mostly-useless) printable decks of cards representing things from that
category, complete with exciting statistics.


Installation
------------

Note: Trop Tumps requires Python 3.6+

The simplest way to install Trop Tumps is using [pip]. With Python and pip 
installed, Trop Tumps can be installed from the Python Package Index with:

    pip install troptumps

or directly from the source repository with:

    pip install git+https://github.com/Frimkron/troptumps#egg=troptumps

Alternatively you can download the source and install it with the `setup.py` 
script.
 

[pip]: https://pip.pypa.io/en/stable/installing/


Usage
-----

If you have installed Trop Trumps, it can be run using the `troptumps` 
executable (`troptumps.exe` on Windows), otherwise the package can be run 
directly with `python -m troptumps`.

The script will connect to _dbpedia.org_ and keep trying to find a suitable
category of things to turn into a card deck. Eventually, with a bit of luck, a 
directory named `deck_`(something) will be written to the current working 
directory, containing a printable .pdf file.

To re-generate the PDF for an existing deck (e.g. to change the paper size),
use the `--datadir` option to indicate the path of a `deck_` directory. The PDF 
will be overwritten.

Use the `--help` flag to see the full list of options.


Licence
-------

Trop Tumps is released under the _GPL 3 licence_. For the full text of this 
licence see `LICENCE.txt`. 


Credits
-------

Created by Mark Frimston

Github: <https://github.com/Frimkron>  
Website: <http://markrimston.co.uk>  
Email: <mark@markfrimston.co.uk>  
Twitter: [@frimkron](https://twitter.com/frimkron)  
Mastodon: [frimkron@mastodon.social](https://mastodon.social/@frimkron)  

