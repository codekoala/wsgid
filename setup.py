#!/usr/bin/env python
# encoding: utf-8
from setuptools import setup
import sys
from wsgid import __progname__, __version__, __description__


PROG_NAME = __progname__

if 'upload' in sys.argv:
    PROG_NAME = 'm2wsgid'

setup(
    name=PROG_NAME,
    version=__version__,
    url="https://github.com/daltonmatos/wsgid",
    license="3-BSD",
    description=__description__,
    author="Dalton Barreto",
    author_email="daltonmatos@gmail.com",
    long_description=open('README.rst').read(),
    packages=['wsgid', 'wsgid/core', 'wsgid/commands', 'wsgid.loaders', 'wsgid/interfaces'],
    scripts=['scripts/wsgid'],
    install_requires=['plugnplay==0.5.1', 'pyzmq==2.1.10', 'python-daemon==1.6', 'simplejson==2.3.0', 'argparse==1.2.1'],
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Application Frameworks"
    ])
