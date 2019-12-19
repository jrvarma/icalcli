#!/usr/bin/env python
from setuptools import setup

setup(name='icalcli',
      version='0.9',
      maintainer='Jayanth R. Varma',
      maintainer_email='jrvarma@gmail.com',
      description='Icalendar Calendar Command Line Interface',
      long_description='',
      packages=['icalcli'],
      install_requires=[
          'python-dateutil',
          'parsedatetime',
          'icalendar'
      ],
      extras_require={
          'vobject': ["vobject"],
          'parsedatetime': ["parsedatetime"],
      },
      entry_points={
          'console_scripts':
              ['icalcli=icalcli.icalcli:main'],
      },
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Environment :: Console",
          "Intended Audience :: End Users/Desktop",
          "License :: OSI Approved :: MIT License",
          "Programming Language :: Python :: 3",
      ])
