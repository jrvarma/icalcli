# icalcli

### An iCalendar Command Line Interface

`icalcli` - a modification of [gcalcli](https://github.com/insanum/gcalcli) - is a Python command line front-end to your Calendar. It allows you to get your agenda, view weekly and monthly calendars (ascii text graphical calendar), search for events, add new events, delete events, and edit events. 

While [gcalcli](https://github.com/insanum/gcalcli) was designed for Google Calendar, `icalcli` is agnostic to (abstracts away from) the actual backend calendar service. It requires some backend interface which interacts with the backend calendar to perform all the CRUD (Create, Retrieve, Update and Delete) operations on the actual calendar. `icalcli` requires the calendar to be presented to it as a list of [icalendar](https://github.com/collective/icalendar) events (`VEVENT`). It is the responsibility of the backend interface to read the actual calendar and create this list of events.

The `etesync` folder contains a backend interface to the [EteSync](https://www.etesync.com/) calendar. In fact, `icalcli` was created primarily to provide a command line interface to my self hosted `EteSync` calendar.

## Requirements

* [Python](http://www.python.org) (3+)
* [dateutil](http://www.labix.org/python-dateutil)
* [parsedatetime](https://github.com/bear/parsedatetime)
* [icalendar](https://github.com/collective/icalendar)
* A love for the command line!

### Optional packages

* [pyetesync](https://github.com/etesync/pyetesync) the python client library for `EteSync` if you want to use the `EteSync` backend.

## Installation

### Install from PyPI

```sh
pip install icalcli
```

### Install from source

```sh
git clone https://github.com/jrvarma/icalcli.git
cd icalcli
python setup.py install
```
## Usage

### Command line arguments

`icalcli` provides a series of subcommands with the following functionality:

    edit (e)               edit calendar events
    agenda (g)             get an agenda for a time period
    calw (w)               get a week-based agenda in calendar format
    calm (m)               get a month agenda in calendar format
    add (a)                add a detailed event to the calendar
    search (s)             (regex) search for events 
    sync (y)               sync the backend calendar
    quit (q)               quit icalcli

By default, `icalcli` runs interactively as an REPL (Read Evaluate Print Loop). Run `icalcli --help` for more details.

#### Configuration Script

In the beginning, `icalcli` executes a configuration script (located, by default, at `~/.icalcli.py`) which must define the variable `backend_interface` representing the backend interface initialized with the right authentication credentials to access the backend calendar. 

