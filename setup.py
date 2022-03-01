#!/usr/bin/env python
from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(name='icalcli',
      version='0.9.8.1',
      maintainer='Jayanth R. Varma',
      maintainer_email='jrvarma@gmail.com',
      description='Icalendar Calendar Command Line Interface',
      long_description=long_description,
      long_description_content_type="text/markdown",
      url="https://github.com/jrvarma/icalcli",
      packages=['icalcli', 'icalcli.etesync_backend', 'icalcli.file_backend'],
      install_requires=[
          'python-dateutil',
          'parsedatetime',
          'icalendar'
      ],
      extras_require={
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
      ],
      python_requires='>=3.6',
)  # noqa E124
