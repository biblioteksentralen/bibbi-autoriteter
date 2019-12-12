#!/usr/bin/env python

from distutils.core import setup

setup(
    name='Bibsent',
    version='0.1',
    packages=['bibsent'],
    description='Conversion scripts for Biblioteksentralen',
    license='GPLv3+',
    author='Dan Michael O. Heggø',
    author_email='danmichaelo@gmail.com',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)'
        'Programming Language :: Python :: 3',
    ],
    install_requires=[
        'openpyxl',
        'pandas',
        'pyyaml',
        'rdflib',
        'pyodbc',
        'feather-format',
        'skosify',
    ]
)


