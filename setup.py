import os
import re
import sys
from setuptools import setup

base_package = 'toxdog'

# Get the version (borrowed from SQLAlchemy)
base_path = os.path.dirname(__file__)
with open(os.path.join(base_path, 'toxdog.py')) as f:
    module_content = f.read()
    VERSION = re.compile(r'.*__version__ = \'(.*?)\'', re.S).match(module_content).group(1)
    LICENSE = re.compile(r'.*__license__ = \'(.*?)\'', re.S).match(module_content).group(1)


with open('README.rst') as f:
    readme = f.read()

with open('CHANGELOG.rst') as f:
    changes = f.read()


install_requires = ['colorama', 'tox', 'watchdog']
if sys.version_info < (3, 0):
    install_requires.append('subprocess32')


if __name__ == '__main__':
    setup(
        name='toxdog',
        description='Automatically run tox jobs for real-time feedback on changes.',
        long_description='\n\n'.join([readme, changes]),
        license=LICENSE,
        url='http://toxdog.readthedocs.io',
        version=VERSION,
        author='Seth Michael Larson',
        author_email='sethmichaellarson@protonmail.com',
        maintainer='Seth Michael Larson',
        maintainer_email='sethmichaellarson@protonmail.com',
        entry_points={
            'console_scripts': [
                'toxdog = toxdog:main'
            ]
        },
        install_requires=install_requires,
        keywords=['toxdog'],
        py_modules=['toxdog'],
        zip_safe=False,
        classifiers=['Intended Audience :: Developers',
                     'License :: OSI Approved :: Apache Software License',
                     'Natural Language :: English',
                     'Operating System :: OS Independent',
                     'Programming Language :: Python :: 2',
                     'Programming Language :: Python :: 2.7',
                     'Programming Language :: Python :: 3',
                     'Programming Language :: Python :: 3.3',
                     'Programming Language :: Python :: 3.4',
                     'Programming Language :: Python :: 3.5',
                     'Programming Language :: Python :: 3.6',
                     'Topic :: Software Development :: Build Tools',
                     'Topic :: Software Development :: Testing',
                     'Topic :: Utilities']
    )
