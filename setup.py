import os.path
import setuptools
from troptumps import VERSION

here = os.path.abspath(os.path.dirname(__file__))

setuptools.setup(
    name='troptumps',
    version=VERSION,
    description='A statistics-duelling deck generator using data from wikipedia',
    long_description=open(os.path.join(here, 'README.md'), encoding='utf-8').read(),
    author='Mark Frimston',
    author_email='mark@markfrimston.co.uk',
    url='https://github.com/frimkron/troptumps',
    license='GPL',
    
    packages=['troptumps'],
    package_data={
        'troptumps': [ 
            os.path.join('fonts', '*'),
        ],
    },
    install_requires=[
        'python-dateutil>=2.6.0',
        'reportlab>=3.4.0',
        'pillow>=1.1.7',
    ],
    python_requires='>=3.6',
    entry_points={ 
        'console_scripts': [ 
            'troptumps = troptumps.__main__:main' 
        ],
    },
)
    
