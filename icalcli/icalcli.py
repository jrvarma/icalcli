#!/usr/bin/env python3

# ** The MIT License **
#
# Copyright (c) 2007 Eric Davis (aka Insanum)
#
# Copyright (c) 2019-2022 Prof. Jayanth R. Varma (jrvarma@gmail.com)
#      * Broke link with Google Calendar
#      * Now processes an event list from any source.
#      * Renamed from gcalcli to icalcli
#      * Editing of multiple events together
#      * Regular expression search
#      * Added an interactive REPL and many new command line options

# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF
# OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

# These are standard libraries and should never fail
import sys
import re
from os.path import expanduser
import textwrap
import signal
from datetime import datetime, timedelta, date
from unicodedata import east_asian_width
from collections import namedtuple
from socket import gethostname
import importlib.util
import shlex
import readline  # noqa: F401
from traceback import print_exc
from difflib import unified_diff

# Required 3rd party libraries
try:
    from icalendar import Event, Alarm, Calendar
    from icalendar.prop import TypesFactory
    from dateutil.tz import tzlocal, UTC, gettz
    import recurring_ical_events
except ImportError as exc:  # pragma: no cover
    print("ERROR: Missing module - %s" % exc.args[0])
    sys.exit(1)


# Package local imports

from icalcli import utils
from icalcli.argparsers import get_argument_parser, get_add_parser
from icalcli.utils import _u  # , days_since_epoch
from icalcli.printer import Printer

EventTitle = namedtuple('EventTitle', ['title', 'color'])
CalName = namedtuple('CalName', ['name', 'color'])
ALL_EVENTS = 0
RECURRING_EVENTS = 1
NON_RECURRING_EVENTS = 2
ORIGINAL_OF_RECURRING_EVENTS = 3


def safe_decode(x, field):
    try:
        return x.decoded(field)
    except:  # noqa: E722
        print("iCalendar error:", x.errors)
        print("iCalendar could not decode {:} field of \n{:}".format(
            field, x.to_ical().decode()))
        raise


Event.Decoded = safe_decode
Alarm.Decoded = safe_decode


class IcalendarInterface:

    cache = {}
    allCals = []
    allEvents = []

    UNIWIDTH = {'W': 2, 'F': 2, 'N': 1, 'Na': 1, 'H': 1, 'A': 1}
    backend_cache_dirty = False
    default_outputs = ['end', 'alarms', 'freebusy', 'location']
    no_past_events = 5
    no_future_events = 10

    def __init__(self, add_parser, backend_interface, printer,
                 **options):

        self.cals = []
        self.printer = printer
        self.initial_options = options
        self.set_options(options)
        self.add_parser = add_parser
        self.backend_interface = backend_interface
        self.events = self.backend_interface.events.copy()
        self.check_duplicate_uids()
        self.setup_recurring_events()
        # stored as detail, but provided as option: TODO: fix that
        self.outputs['width'] = options.get('width', 80)

    def set_options(self, options):
        r"""
        This is run at initiaization
        and also while processing each command in REPL loop

        Parameters
        ----------
        options : dict of command options
        """
        self.options = options
        self.set_now()  # set self.now
        self.outputs = options.get('outputs', {})
        for key in self.default_outputs:
            if key not in self.outputs:
                self.outputs[key] = True

    def set_now(self):
        # This command is run at initiaization, but it should also be
        # run frequently to prevent self.now from becoming stale
        self.now = datetime.now(tzlocal())

        def offset(now, years):
            d = int(365.25 * years) + (1 if years > 0 else -1)
            dt = now + timedelta(days=d)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        self.default_start = offset(
            self.now, -self.initial_options['default_past_years'])
        self.default_end = offset(
            self.now, self.initial_options['default_future_years'])

    @staticmethod
    def uid(event):
        """Return uid of event"""
        return event.Decoded('uid').decode()

    def check_duplicate_uids(self):
        # fixes https://github.com/jrvarma/icalcli/pull/8#issue-1310596831
        if len(set(self.uid(e) for e in self.events)) < len(self.events):
            # list to dict to list is a one-liner dedup
            self.events = list(
                {self.uid(e): e for e in self.events}.values())
            self.readonly = True
            self.printer.err_msg('Duplicate UIDs found. '
                                 'Calendar deduplicated and set to readonly\n')
        else:
            self.readonly = False

    def setup_recurring_events(self):
        self.recur_uids = set(self.uid(e) for e in self.events
                              if 'RRULE' in e or 'RDATE' in e)
        if self.recur_uids:
            cal = Calendar()
            ics_list = []
            for event in self.events:
                cal.add_component(event)
            ics_list += [cal.to_ical().decode()]
            self.calendar = Calendar.from_ical("".join(ics_list))
            self.recurring_events = recurring_ical_events.of(
                self.calendar, keep_recurrence_attributes=True)

    @staticmethod
    def display_timezone(dt):
        r"""Set or convert timezone to display time in local timezone

        Parameters
        ----------
        dt : date or datetime (may or may not be timezone aware)

        Returns
        -------
        datetime (timezone aware)
        """
        if not hasattr(dt, 'tzinfo'):  # skip dates
            return dt
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tzlocal())
        else:
            return dt.astimezone(tzlocal())

    @staticmethod
    def confirm(prompt):
        response = input(prompt)
        return (response and response[0].lower() == 'y')

    @staticmethod
    def calendar_timezone(dt):
        r"""Convert datetime to default timezone of calendar

        Parameters
        ----------
        dt : date or datetime
        Returns
        -------
        datetime (timezone aware)
        """
        if not hasattr(dt, 'tzinfo'):  # skip dates
            return dt
        return dt.astimezone(tz=IcalendarInterface.calendar_tz)

    @staticmethod
    def decode_dtm(event, field):
        r"""Parse dtstart or dtend field in event into datetime

        Calendar default timezone is used

        Parameters
        ----------
        event : icalendar Event
        field : string ('dtstart' or 'dtend')

        Returns
        -------
        datetime (timezone aware)
        """
        if field not in event and field == 'dtend':
            d = event.Decoded('dtstart') + event.Decoded('duration')
        else:
            d = event.Decoded(field)
        if isinstance(d, datetime):
            return IcalendarInterface.display_timezone(d)
        else:
            return IcalendarInterface.display_timezone(
                datetime.combine(
                    d, datetime.min.time()))

    def valid_title(self, event):
        r"""Return summary of event

        Parameters
        ----------
        event : icalendar Event

        Returns
        -------
        string
        """
        if 'summary' in event and (
                event.Decoded('summary').decode().strip()):
            return event.Decoded('summary').decode()
        else:
            return "(No title)"

    def isallday(self, event):
        r"""Whether event is an All Day event

        Parameters
        ----------
        event : icalendar Event

        Returns
        -------
        boolean
        """
        return (self.decode_dtm(event, 'dtstart').hour == 0 and
                self.decode_dtm(event, 'dtstart').minute == 0 and
                self.decode_dtm(event, 'dtend').hour == 0 and
                self.decode_dtm(event, 'dtend').minute == 0)

    def cal_monday(self, day_num):
        r"""Shift the day number if week should start on Monday

        Shift the day number if we're doing cal_monday,
        or cal_weekend is false, since that also means
        we're starting on day 1

        Parameters
        ----------
        day_num : int

        Returns
        -------
        int
        """
        if self.options['cal_monday'] or not self.options[
                'cal_weekend']:
            day_num -= 1
            if day_num < 0:
                day_num = 6
        return day_num

    def event_time_in_range(self, e_time, r_start, r_end):
        r"""Whether event time is within given range

        Parameters
        ----------
        e_time : datetime
        r_start : datetime
        r_end : datetime

        Returns
        -------
        boolean
        """
        return e_time >= r_start and e_time < r_end

    def event_spans_time(self, e_start, e_end, time_point):
        r"""Whether event straddles given time

        Parameters
        ----------
        e_start : datetime
        e_end : datetime
        time_point : datetime

        Returns
        -------
        boolean
        """
        return e_start < time_point and e_end >= time_point

    def format_title(self, event, allday=False):
        r"""Return event title (summary and start time)

        Parameters
        ----------
        event : icalendar event
        allday : boolean

        Returns
        -------
        string
        """
        titlestr = self.valid_title(event)
        if allday:
            return titlestr
        elif self.options['military']:
            return ' '.join(
                [self.decode_dtm(event, 'dtstart').strftime("%H:%M"),
                 titlestr])
        else:
            return ' '.join([
                self.decode_dtm(event, 'dtstart').strftime("%I:%M")
                .lstrip('0') +
                self.decode_dtm(event, 'dtstart').strftime('%p')
                .lower(), titlestr])

    def get_week_events(self, start_dt, end_dt, event_list):
        r"""Returns all events during a week (start_dt to end_dt)

        Parameters
        ----------
        start_dt : datetime
        end_dt : datetime
        event_list : list of icalendar events

        Returns
        -------
        list of list of strings
        each sublist is list of events during a day
        """
        week_events = [[] for _ in range(7)]

        to_show_now = True
        if self.now < start_dt or self.now > end_dt:
            to_show_now = False
        now_daynum = self.cal_monday(int(self.now.strftime("%w")))

        for event in event_list:
            event_daynum = self.cal_monday(int(self.decode_dtm(
                event, 'dtstart').strftime("%w")))
            event_allday = self.isallday(event)

            event_end_date = self.decode_dtm(event, 'dtend')
            event_start_date = self.decode_dtm(event, 'dtstart')
            if event_allday:
                # NOTE(slwaqo): in allDay events end date is always
                # set as day+1 and hour 0:00
                # So to not display it one day more, it's
                # necessary to lower it by one day
                event_end_date -= timedelta(days=1)

            event_is_today = self.event_time_in_range(
                event_start_date, start_dt, end_dt)

            event_continues_today = self.event_spans_time(
                event_start_date, event_end_date,
                start_dt)

            # NOTE(slawqo): it's necessary to process events which
            # starts in current period of time
            # but for all day events also to process events
            # which was started before current period of time and are
            # still continue in current period of time
            if event_is_today or (event_allday
                                  and event_continues_today):
                force_now_marker = False

                if to_show_now:
                    if(self.now >= event_start_date
                       and self.now <= event_end_date
                       and not event_allday):
                        # line marker is during event (recolor event)
                        force_now_marker = True
                        to_show_now = False
                    # elif (int(days_since_epoch(self.now)) <
                    #       int(days_since_epoch(event_start_date))):
                    #     force_now_marker = False
                    #     week_events[event_daynum - 1].append(
                    #         EventTitle(
                    #             '\n' + self.options['cal_width'] * '-',
                    #             self.options['color_now_marker']))
                    #     to_show_now = False
                    elif self.now <= event_start_date:
                        # add a line marker at end of today
                        force_now_marker = False
                        week_events[now_daynum].append(
                            EventTitle(
                                '\n' + self.options['cal_width'] * '-',
                                self.options['color_now_marker']))
                        to_show_now = False
                if force_now_marker:
                    event_color = self.options['color_now_marker']
                else:
                    event_color = 'default'
                # NOTE(slawqo): for all day events it's necessary to
                # add event to more than one day in week_events
                titlestr = self.format_title(event, allday=event_allday)
                if event_allday and event_start_date < event_end_date:
                    if event_end_date >= end_dt:
                        end_daynum = 6
                    else:
                        end_daynum = self.cal_monday(int(
                            event_end_date.strftime("%w")))
                    if event_start_date < start_dt:
                        start_daynum = 0
                    else:
                        start_daynum = event_daynum
                    # if event_daynum > end_daynum:
                    #     event_daynum = 0
                    for day in range(start_daynum, end_daynum + 1):
                        week_events[day].append(
                            EventTitle('\n' + titlestr, event_color))
                else:
                    # newline and empty string are the keys to turn off
                    # coloring
                    week_events[event_daynum].append(
                            EventTitle('\n' + titlestr, event_color))
        return week_events

    def printed_len(self, string):
        r"""Find printed length of a string

        We need to treat everything as unicode for this to give
        us the info we want.  Data string comes in as `str` type
        so we convert them to unicode and then check their size.
        Fixes the output issues around non-US locale strings

        Parameters
        ----------
        string : string

        Returns
        -------
        int : printed length
        """
        return sum(
                self.UNIWIDTH[east_asian_width(char)] for char in _u(
                    string))

    def word_cut(self, word):
        r"""Where to cut word to fit into cal_width

        Parameters
        ----------
        word : string

        Returns
        -------
        int: where to cut the word
        """
        stop = 0
        for i, char in enumerate(word):
            stop += self.printed_len(char)
            if stop >= self.options['cal_width']:
                return stop, i + 1

    def next_cut(self, string, cur_print_len):
        r"""Where to cut string to fit into cal_width

        Tries to cut between words if possible.
        If word is too long, cuts within word

        Parameters
        ----------
        string : string (will be split into list of words)
        cur_print_len : int

        Returns
        -------
        int: where to cut the word
        """
        print_len = 0

        words = _u(string).split()
        for i, word in enumerate(words):
            word_len = self.printed_len(word)
            if ((cur_print_len + word_len + print_len
                 ) >= self.options['cal_width']):
                cut_idx = len(' '.join(words[:i]))
                # if the  word is too long,
                # we cannot cut between words
                if cut_idx == 0:
                    return self.word_cut(word)
                return (print_len, cut_idx)
            print_len += word_len + i  # +i for the space between words
        return (print_len, len(' '.join(words[:i])))

    def get_cut_index(self, event_string):
        r"""Cut string at line break, between words or within word
        to cal_width

        Parameters
        ----------
        event_string : string

        Returns
        -------
        int: where to cut
        """
        print_len = self.printed_len(event_string)

        # newline in string is a special case
        idx = event_string.find('\n')
        if idx > -1 and idx <= self.options['cal_width']:
            return (self.printed_len(event_string[:idx]),
                    len(event_string[:idx]))

        if print_len <= self.options['cal_width']:
            return (print_len, len(event_string))

        else:
            # we must cut: next_cut loops until we find the right spot
            return self.next_cut(event_string, 0)

    def GraphEvents(self, cmd, startDateTime, count, eventList):
        r"""Constructs graphical display with weeks in rows,
        days of week in columns, and event strings in cells

        Parameters
        ----------
        cmd : Command ('calw' or 'calm' for week and month)
        startDateTime : datetime (start date)
        count : int (number of weeks or months)
        eventList : list of icalendar events
        """

        color_border = self.options['color_border']

        # # ignore started events (i.e. events that start
        # # previous day and end start day)
        # while (len(eventList) and
        #        self.decode_dtm(eventList[0], 'dtstart')
        #        < startDateTime):
        #     eventList = eventList[1:]

        day_width_line = self.options['cal_width'] * self.printer.art[
            'hrz']
        days = 7 if self.options['cal_weekend'] else 5
        # Get the localized day names... January 1, 2001 was a Monday
        day_names = ([date(2001, 1, i + 1).strftime('%A')
                      for i in range(days)])
        if not self.options['cal_monday'] or not self.options[
                'cal_weekend']:
            day_names = day_names[6:] + day_names[:6]

        def build_divider(left, center, right):
            return (
                self.printer.art[left] + day_width_line +
                ((days - 1) * (self.printer.art[center]
                               + day_width_line)) +
                self.printer.art[right])

        week_top = build_divider('ulc', 'ute', 'urc')
        week_divider = build_divider('lte', 'crs', 'rte')
        week_bottom = build_divider('llc', 'bte', 'lrc')
        empty_day = self.options['cal_width'] * ' '

        if cmd == 'calm':
            # month titlebar
            month_title_top = build_divider('ulc', 'hrz', 'urc')
            self.printer.msg(month_title_top + '\n', color_border)

            month_title = startDateTime.strftime('%B %Y')
            month_width = (self.options['cal_width'] * days) + (
                days - 1)
            month_title += ' ' * (month_width
                                  - self.printed_len(month_title))

            self.printer.art_msg('vrt', color_border)
            self.printer.msg(month_title, self.options['color_date'])
            self.printer.art_msg('vrt', color_border)

            month_title_bottom = build_divider('lte', 'ute', 'rte')
            self.printer.msg('\n' + month_title_bottom + '\n',
                             color_border)
        else:
            # week titlebar
            # month title bottom takes care of this when cmd='calm'
            self.printer.msg(week_top + '\n', color_border)

        # weekday labels
        self.printer.art_msg('vrt', color_border)
        for day_name in day_names:
            day_name += ' ' * (
                    self.options['cal_width'] - self.printed_len(
                        day_name))

            self.printer.msg(day_name, self.options['color_date'])
            self.printer.art_msg('vrt', color_border)

        self.printer.msg('\n' + week_divider + '\n', color_border)
        cur_month = startDateTime.strftime("%b")

        # get date range objects for the first week
        if cmd == 'calm':
            day_num = self.cal_monday(
                int(startDateTime.strftime("%w")))
            startDateTime = (startDateTime - timedelta(days=day_num))
        startWeekDateTime = startDateTime
        endWeekDateTime = (startWeekDateTime + timedelta(days=7))

        for i in range(count):
            # create and print the date line for a week
            for j in range(days):
                if cmd == 'calw':
                    d = (startWeekDateTime +
                         timedelta(days=j)).strftime("%d %b")
                else:  # (cmd == 'calm'):
                    d = (startWeekDateTime +
                         timedelta(days=j)).strftime("%d")
                    if cur_month != (startWeekDateTime +
                                     timedelta(days=j)).strftime("%b"):
                        d = ''
                tmpDateColor = self.options['color_date']

                if (self.now.strftime("%d%b%Y") == (
                        (startWeekDateTime + timedelta(days=j))
                        .strftime("%d%b%Y"))):
                    tmpDateColor = self.options['color_now_marker']
                    d += " **"

                d += ' ' * (self.options['cal_width']
                            - self.printed_len(d))

                # print dates
                self.printer.art_msg('vrt', color_border)
                self.printer.msg(d, tmpDateColor)

            self.printer.art_msg('vrt', color_border)
            self.printer.msg('\n')

            week_events = self.get_week_events(
                    startWeekDateTime, endWeekDateTime, eventList)

            # get date range objects for the next week
            startWeekDateTime = endWeekDateTime
            endWeekDateTime = (endWeekDateTime + timedelta(days=7))

            while True:
                # keep looping over events by day,
                # printing one line at a time
                # stop when everything has been printed
                done = True
                self.printer.art_msg('vrt', color_border)
                for j in range(days):
                    if not week_events[j]:
                        # no events today
                        self.printer.msg(
                                empty_day + self.printer.art['vrt'],
                                color_border)
                        continue

                    curr_event = week_events[j][0]
                    print_len, cut_idx = self.get_cut_index(
                        curr_event.title)
                    padding = ' ' * (self.options['cal_width']
                                     - print_len)

                    self.printer.msg(
                            curr_event.title[:cut_idx] + padding,
                            curr_event.color)

                    # trim what we've already printed
                    trimmed_title = curr_event.title[cut_idx:].strip()

                    if trimmed_title == '':
                        week_events[j].pop(0)
                    else:
                        week_events[j][0] = curr_event._replace(
                            title=trimmed_title)

                    done = False
                    self.printer.art_msg('vrt', color_border)

                self.printer.msg('\n')
                if done:
                    break

            if i < range(count)[len(range(count)) - 1]:
                self.printer.msg(week_divider + '\n', color_border)
            else:
                self.printer.msg(week_bottom + '\n', color_border)

    def PrintEvent(self, event, prefix, ev_type=ALL_EVENTS):
        r"""Prints one event

        Parameters
        ----------
        event : icalendar event
        prefix : string (for example, indent before event)
        """

        def formatDescr(descr, indent, box):
            wrapper = textwrap.TextWrapper()
            if box:
                wrapper.initial_indent = (indent + '  ')
                wrapper.subsequent_indent = (indent + '  ')
                wrapper.width = (self.outputs.get('width') - 2)
            else:
                wrapper.initial_indent = indent
                wrapper.subsequent_indent = indent
                wrapper.width = self.outputs.get('width')
            new_descr = ""
            for line in descr.split("\n"):
                if box:
                    tmpLine = wrapper.fill(line)
                    for singleLine in tmpLine.split("\n"):
                        singleLine = singleLine.ljust(
                                self.outputs.get('width'), ' ')
                        new_descr += (singleLine[:len(indent)] +
                                      self.printer.art['vrt'] +
                                      singleLine[
                                          (len(indent) + 1):
                                          (self.outputs.get('width')
                                           - 1)]
                                      + self.printer.art['vrt'] + '\n')
                else:
                    new_descr += wrapper.fill(line) + "\n"
            return new_descr.rstrip()

        indent = 12 * ' '
        outputsIndent = 19 * ' '

        def time_format(tm):
            if self.options['military']:
                timeFormat = '%-5s'
                tmpTimeStr = tm.strftime("%H:%M")
            else:
                timeFormat = '%-7s'
                tmpTimeStr = (
                    tm.strftime("%I:%M").lstrip('0').rjust(5) +
                    tm.strftime('%p').lower())
            return timeFormat, tmpTimeStr

        def date_format(tm):
            if self.options['military']:
                dateFormat = '%-5s'
                tmpDateStr = tm.strftime("%d-%m")
            else:
                dateFormat = '%-7s'
                tmpDateStr = tm.strftime(" %d-%b").lstrip('0')
            return dateFormat, tmpDateStr

        if not prefix:
            prefix = indent

        self.printer.msg(prefix, self.options['color_date'])

        happeningNow = (self.decode_dtm(event, 'dtstart')
                        <= self.now
                        <= self.decode_dtm(event, 'dtend'))
        allDay = self.isallday(event)
        eventColor = (self.options['color_now_marker']
                      if happeningNow and not allDay
                      else 'default')

        timeFormat, tmpTimeStr = time_format(self.decode_dtm(
            event, 'dtstart'))
        if ev_type == ORIGINAL_OF_RECURRING_EVENTS:
            if self.options['military']:
                fmt = '     %10s'  # matches ' ', ' to ', 5 char date & time
            else:
                fmt = '     %14s'  # matches ' ', ' to ', 7 char date & time
            self.printer.msg(fmt % 'Recurs', eventColor)
        elif allDay:
            fmt = ' ' + timeFormat
            self.printer.msg(fmt % '', eventColor)
            if self.outputs.get('end'):
                dateFormat, tmpDateStr = date_format(
                    self.decode_dtm(event, 'dtend'))
                fmt = ' to ' + dateFormat
                self.printer.msg(fmt % tmpDateStr, eventColor)
        else:
            fmt = ' ' + timeFormat
            self.printer.msg(fmt % tmpTimeStr, eventColor)
            if self.outputs.get('end'):
                timeFormat, tmpTimeStr = time_format(
                    self.decode_dtm(event, 'dtend'))
                fmt = ' to ' + timeFormat
                self.printer.msg(fmt % tmpTimeStr, eventColor)

        if self.outputs.get('alarms'):
            alarms = event.walk('valarm')
            if alarms:
                if isinstance(alarms[0].Decoded('trigger'), timedelta):
                    minutes = -(alarms[0].Decoded('trigger')
                                .total_seconds()/60)
                    self.printer.msg(' AL:%.0fm' % minutes)
                else:
                    self.printer.msg(' AL: ??')
            else:
                self.printer.msg(' '*7)
        if self.outputs.get('freebusy'):
            free = ('transp' in event and
                    event.Decoded('transp').decode() == 'TRANSPARENT')
            self.printer.msg(' free ' if free else ' busy ',
                             eventColor)

        self.printer.msg('  %s' % self.valid_title(event).strip(),
                         eventColor)

        if(self.outputs.get('location')
           and 'location' in event
           and event.Decoded('location').decode().strip()):
            xstr = " [%s]" % (event.Decoded('location').
                              decode().strip())
            self.printer.msg(xstr, 'default')

        if self.outputs.get('uid'):
            xstr = " <%s>" % (event.Decoded('uid').decode().strip())
            self.printer.msg(xstr, 'default')

        self.printer.msg('\n')

        if(self.outputs.get('description') and 'description' in event
           and event.Decoded('description').decode().strip()):
            descrIndent = outputsIndent + '  '
            box = True  # leave old non-box code for option later
            if box:
                topMarker = (descrIndent +
                             self.printer.art['ulc'] +
                             (self.printer.art['hrz'] *
                              ((self.outputs.get('width')
                                - len(descrIndent)) - 2)) +
                             self.printer.art['urc'])
                botMarker = (descrIndent +
                             self.printer.art['llc'] +
                             (self.printer.art['hrz'] *
                              ((self.outputs.get('width')
                                - len(descrIndent)) - 2)) +
                             self.printer.art['lrc'])
                xstr = "%s  Description:\n%s\n%s\n%s\n" % (
                    outputsIndent,
                    topMarker,
                    formatDescr(event.Decoded('description').
                                decode().strip(), descrIndent, box),
                    botMarker
                )
            else:
                marker = descrIndent + '-' * (
                    (self.outputs.get('width') - len(descrIndent)))
                xstr = "%s  Description:\n%s\n%s\n%s\n" % (
                    outputsIndent,
                    marker,
                    formatDescr(event.Decoded('description').
                                decode().strip(), descrIndent, box),
                    marker
                )
            self.printer.msg(xstr, 'default')

    def iterate_events(self, startDateTime, eventList, yearDate=True,
                       work=None, print_count=True,
                       ev_type=ALL_EVENTS):
        r"""Iterate through events and print them

        Parameters
        ----------
        startDateTime : datetime
        eventList : list of icalendar events
        yearDate : boolean
        work : function to be called for each event

        Returns
        -------
        int: number of selected events
        """

        selected = 0

        if print_count:
            if len(eventList) == 0:
                self.printer.msg('\nNo Events Found...\n', 'yellow')
                return selected
            else:
                self.printer.msg(f'\n{len(eventList)} Events Found\n',
                                 'yellow')

        # 12 chars for day & length must match 'indent' in PrintEvent
        dayFormat = '\n%a %d-%b-%y' if yearDate else '\n%a %b %d  '
        day = ''

        for event in eventList:
            if(self.options['ignore_started'] and
               (self.decode_dtm(event, 'dtstart') < self.now)):
                continue
            if self.options['ignore_declined'] and self._DeclinedEvent(
                    event):
                continue

            selected += 1
            tmpDayStr = self.decode_dtm(event, 'dtstart').strftime(
                dayFormat)
            prefix = None
            if yearDate or tmpDayStr != day:
                day = prefix = tmpDayStr

            self.PrintEvent(event, prefix, ev_type=ev_type)

            if work:
                work(event)

        return selected

    @staticmethod
    def to_datetime(d):
        r"""Convert date or datetime to timezone aware datetime

        Parameters
        ----------
        d : date or datetime (may or not be timezone aware)

        Returns
        -------
        timezone aware datetime converted to local timezone
        """
        if isinstance(d, datetime):
            return IcalendarInterface.display_timezone(d)
        else:
            return IcalendarInterface.display_timezone(
                datetime.combine(d, datetime.min.time()))

    def event_match(self, event, start=None, end=None,
                    pattern=None, field='summary', ignore_case=True):
        r"""Check whether an event matches search criteria

        Parameters
        ----------
        event : event (icalendar object) to be checked
        start : starting date (datetime object) for date searches
        end : ending date (datetime object) for date searches
        pattern : regex pattern for text based searches
        field : field to be searched for text based searches
        ignore_case : do case insensitive matching (defaults to True)

        Returns
        -------
        True if the event matches:
        a) the text based search (if pattern is not None)
        AND
        a) the date based search (unless both start & end are None)
        """
        event_start = self.to_datetime(event.Decoded('dtstart'))
        if 'dtend' in event:
            event_end = self.to_datetime(event.Decoded('dtend'))
        elif 'duration' in event:
            event_end = self.to_datetime(event.Decoded('dtstart')
                                         + event.Decoded('duration'))
        else:
            # special case where an event is punctual and has no end date
            event_end = event_start
        date_in_range = not ((start and event_end < start) or
                             (end and event_start > end))
        flags = re.I if ignore_case else 0
        if not pattern:
            pat_match = True
        elif event.decoded(field, None) is None:
            pat_match = False
        else:
            s = event[field].to_ical()
            if isinstance(s, bytes):
                s = s.decode()
            pat_match = (
                re.search(pattern, s, flags=flags) is not None)
        return date_in_range and pat_match

    def search_for_events(self, start, end, pattern, field='summary',
                          ev_type=ALL_EVENTS):
        r"""Retrieve events matching (text and/or date based) search

        Parameters
        ----------
        start : starting date (defaults to None)
        end : ending date (defaults to None)
        pattern : regex pattern for text based searches (default: None)
        field : String
                field to be searched for regex (defaults to 'summary")
        ev_type: ALL_EVENTS or RECURRING_EVENTS or NON_RECURRING_EVENTS

        Returns
        -------
        list of matching vevents
        """
        ignore_case = not ('no_ignore_case' in self.options and
                           self.options['no_ignore_case'])
        if start:
            start = self.to_datetime(start)
        else:
            start = self.default_start
        if end:
            end = self.to_datetime(end)
        else:
            end = self.default_end
        self.save_last_search_spec(start, end, pattern, field)
        if self.recur_uids and ev_type != NON_RECURRING_EVENTS:
            events = self.recurring_events.between(start, end)
        else:
            events = self.events
        event_list = [ev for ev in events if self.event_match(
            ev, start, end, pattern, field, ignore_case)]
        if ev_type == NON_RECURRING_EVENTS:
            event_list = [e for e in event_list
                          if self.uid(e) not in self.recur_uids]
        elif ev_type == RECURRING_EVENTS:
            event_list = [e for e in event_list
                          if self.uid(e) in self.recur_uids]
        elif ev_type == ORIGINAL_OF_RECURRING_EVENTS:
            uids = set(self.uid(e) for e in event_list) & self.recur_uids
            event_list = [e for e in self.events if self.uid(e) in uids]
        event_list.sort(key=lambda x: (self.decode_dtm(x, 'dtstart'),
                                       x.Decoded('summary').decode()))
        return event_list

    def save_last_search_spec(self, start, end, search=None, field='summary'):
        r"""Print search criteria for matching events

        Parameters
        ----------
        start : datetime
        end : datetime
        search : string
        field : field within event to search

        """
        spec = ""
        if search:
            spec += f'Search for {search} in {field} '
        if start:
            spec += f'From {start.strftime("%Y-%m-%d(%H:%M)")} '
        if end:
            spec += f'To {end.strftime("%Y-%m-%d(%H:%M)")}'
        self.last_search_spec = spec

    def display_queried_events(self, start, end, search=None, yearDate=True,
                               field='summary', ev_type=ALL_EVENTS):
        r"""Search for matching events and print them

        Parameters
        ----------
        start : datetime
        end : datetime
        search : string
        yearDate : boolean
        field : field within event to search
        ev_type: ALL_EVENTS or RECURRING_EVENTS or NON_RECURRING_EVENTS

        Returns
        -------
        int: number of events printed
        """
        event_list = self.search_for_events(
            start, end, pattern=search, field=field, ev_type=ev_type)
        self.printer.msg(self.last_search_spec)
        return self.iterate_events(start, event_list, yearDate=yearDate)

    def TextQuery(self, search_text='', start=None, end=None,
                  field='summary'):
        r"""Search for matching events and print them

        Parameters
        ----------
        search_text : string
        start : datetime
        end : datetime
        field : field within event to search

        Returns
        -------
        int: number of events printed
        """
        return self.display_queried_events(start, end, search_text,
                                           True, field)

    def AgendaQuery(self, start=None, end=None, days=5):
        r"""Print agenda (events within next 'days' days)

        Parameters
        ----------
        start : datetime
        end : datetime
        days : number of days

        Returns
        -------
        int: number of events printed
        """
        if not start:
            start = self.now.replace(hour=0, minute=0,
                                     second=0, microsecond=0)

        if not end:
            end = (start + timedelta(days=days)).replace(
                hour=23, minute=59, second=59, microsecond=10**6-1)

        return self.display_queried_events(start, end)

    def CalQuery(self, cmd, startText='', count=1):
        r"""Process calw and calm commands by calling GraphEvents

        Parameters
        ----------
        cmd : string (calw or calm)
        startText : string (parsed to get start date)
        count : number of weeks or months
        """
        if not startText:
            # convert now to midnight this morning and use for default
            start = self.now.replace(hour=0,
                                     minute=0,
                                     second=0,
                                     microsecond=0)
        else:
            try:
                start = utils.get_time_from_str(startText)
                start = start.replace(hour=0, minute=0, second=0,
                                      microsecond=0)
            except Exception:
                self.printer.err_msg(
                        'Error: failed to parse start time\n')
                if self.initial_options['stack_trace']:
                    print_exc()
                return

        # convert start date to the beginning of the week or month
        if cmd == 'calw':
            dayNum = self.cal_monday(int(start.strftime("%w")))
            start = (start - timedelta(days=dayNum))
            end = (start + timedelta(days=(count * 7)))
        else:  # cmd == 'calm':
            start = (start - timedelta(days=(start.day - 1)))
            endMonth = (start.month + 1)
            endYear = start.year
            if endMonth == 13:
                endMonth = 1
                endYear += 1
            end = start.replace(month=endMonth, year=endYear)
            daysInMonth = (end - start).days
            offsetDays = int(start.strftime('%w'))
            if self.options['cal_monday']:
                offsetDays -= 1
                if offsetDays < 0:
                    offsetDays = 6
            totalDays = (daysInMonth + offsetDays)
            count = int(totalDays / 7)
            if totalDays % 7:
                count += 1

        eventList = self.search_for_events(start, end, None)

        self.GraphEvents(cmd, start, count, eventList)

    def sync(self):
        r"""Sync calendar
        """
        self.printer.msg("Syncing in progress\n")
        self.backend_interface.sync(self.vtimezone)
        self.events = self.backend_interface.events.copy()
        self.backend_cache_dirty = False
        self.setup_recurring_events()
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.printer.msg(f"Sync completed at {now}\n")

    def delete(self, search_text='', start=None, end=None,
               field='summary'):
        r"""Delete matching events from calendar after prompt

        Parameters
        ----------
        search_text : string
        start : datetime
        end : datetime
        field : string (field within event to be searched)
        """
        if self.readonly:
            raise Exception("Read-only calendar cannot be modified")
        if self.recur_uids:
            ev_types = [ORIGINAL_OF_RECURRING_EVENTS, NON_RECURRING_EVENTS]
        else:
            ev_types = [ALL_EVENTS]
        msgs = {
            ALL_EVENTS: "",
            ORIGINAL_OF_RECURRING_EVENTS:
            "Processing recurrings event firsts\n",
            NON_RECURRING_EVENTS: "Processing non recurring events\n"
        }
        warn_recur = "Warning! Deleting event deletes all its occurences\n"
        for ev_type in ev_types:
            self.printer.msg(msgs[ev_type])
            event_list = self.search_for_events(
                start, end, pattern=search_text, field=field, ev_type=ev_type)
            self.printer.msg(self.last_search_spec)
            nevents = len(event_list)
            if nevents == 0:
                self.printer.msg('No events found\n'
                                 '......................................\n')
                continue
            self.iterate_events(start, event_list, ev_type=ev_type)
            self.printer.msg('......................................\n')
            if nevents > 1:
                if ev_type == ORIGINAL_OF_RECURRING_EVENTS:
                    self.printer.msg(warn_recur)
                response = input(
                    "Y (delete all), P (prompt), Anything else (cancel) ")
                if not (response and response[0] in 'YP'):
                    self.printer.msg("Action cancelled\n")
                    continue
                else:
                    prompt = not response[0] == 'Y'
            else:
                prompt = True
            deleted = 0
            for event in event_list:
                self.iterate_events(None, [event], print_count=False,
                                    ev_type=ev_type)
                if prompt:
                    if ev_type == ORIGINAL_OF_RECURRING_EVENTS:
                        self.printer.msg(warn_recur)
                    if not IcalendarInterface.confirm("Delete y/n? "):
                        self.printer.msg("Event retained\n")
                        continue
                self.backend_interface.delete_event(self.uid(event))
                self.printer.msg("Event deleted\n")
                self.backend_cache_dirty = True
                deleted += 1
            self.printer.msg(f'{deleted} events deleted\n')

    def read_edit_args(self):
        while True:
            s = input("Enter updated event details as if "
                      + "adding new event\n")
            if s == '':
                return None
            try:
                args = self.add_parser.parse_args(shlex.split(s))
                return args
                break
            except Exception as e:
                sys.stderr.write(str(e)+'\n')
                if self.initial_options['stack_trace']:
                    print_exc()
            except SystemExit:
                return None

    def edit(self, search_text='', start=None, end=None,
             field='summary'):
        r"""Edit matching events

        Parameters
        ----------
        search_text : string
        start : datetime
        end : datetime
        field : string (field within event to be searched)
        """
        if self.readonly:
            raise Exception("Read-only calendar cannot be modified")
        if self.recur_uids:
            ev_types = [ORIGINAL_OF_RECURRING_EVENTS, NON_RECURRING_EVENTS]
        else:
            ev_types = [ALL_EVENTS]
        msgs = {
            ALL_EVENTS: "",
            ORIGINAL_OF_RECURRING_EVENTS: "Processing recurrings events\n",
            NON_RECURRING_EVENTS: "Processing non recurring events\n"
        }
        warn_recur = "Warning! Editing event modifies all its recurrences\n"
        tot_events = 0
        for ev_type in ev_types:
            event_list = self.search_for_events(
                start, end, pattern=search_text, field=field, ev_type=ev_type)
            if not event_list:
                continue
            self.printer.msg(msgs[ev_type])
            self.printer.msg(self.last_search_spec)
            self.iterate_events(start, event_list, ev_type=ev_type)
            self.printer.msg('......................................\n')
            nevents = len(event_list)
            tot_events += nevents
            if nevents == 0:
                continue
            if nevents > 1:
                if ev_type == RECURRING_EVENTS:
                    all_together = False
                elif IcalendarInterface.confirm(
                        "Do you want to edit all together y/n? "):
                    all_together = True
                else:
                    all_together = False
                    if not IcalendarInterface.confirm(
                            "Do you want to edit all individually y/n? "):
                        self.printer.msg("Action cancelled\n")
                        continue
            edited = 0
            if nevents > 1 and all_together:
                if ev_type == ORIGINAL_OF_RECURRING_EVENTS:
                    self.printer.msg(warn_recur)
                args = self.read_edit_args()
                if args:
                    if args.raw_ics:
                        self.printer.msg(
                            '--raw_ics ignored: editing multiple events\n')
                        args.raw_ics = None
                    for event in event_list:
                        self.iterate_events(None, [event], print_count=False)
                        self.add(args, event)
                        edited += 1
                else:
                    self.printer.msg('Event not edited\n')
            else:
                for event in event_list:
                    self.iterate_events(None, [event], print_count=False,
                                        ev_type=ev_type)
                    self.printer.msg(event.to_ical().decode() + '\n')
                    if ev_type == ORIGINAL_OF_RECURRING_EVENTS:
                        self.printer.msg(warn_recur)
                    args = self.read_edit_args()
                    if args:
                        if self.add(args, event):
                            edited += 1
                    else:
                        self.printer.msg('Event not edited\n')
            self.printer.msg(f'{edited} events edited\n')
        if tot_events == 0:
            self.printer.msg('No events found\n')

    def preview_recurring_event(self, event):
        cal = Calendar()
        cal.add_component(event)
        recurring_events = recurring_ical_events.of(cal)
        preview = recurring_events.between(
            self.default_start, self.now)[-self.no_past_events:]
        self.printer.msg(
            f"Showing up to {self.no_past_events} recent/current events")
        self.iterate_events(None, preview, print_count=False)
        self.printer.msg(
            f"Showing up to {self.no_future_events} current/future events")
        preview = recurring_events.between(
            self.now, self.default_end)[:self.no_future_events]
        self.iterate_events(None, preview, print_count=False)

    def add(self, args, original=None):
        r"""Add new event

        New event is created from command line or REPL arguments.
        This is also called from edit in which case, fields to be
        changed are given in args and unchanged fields are taken
        from old event.

        Parameters
        ----------
        args :  dict of command line or REPL arguments
        old : None or icalendar event to be replaced
        """
        if self.readonly:
            raise Exception("Read-only calendar cannot be modified")
        if args.raw_ics:
            return self.raw_ics(original)
        default_event_duration = timedelta(minutes=30)
        old = None
        if original:
            old = original.copy()
            uid = old.Decoded('uid').decode()
            old_start = self.display_timezone(old.Decoded('dtstart'))
            old_duration = (
                ('duration' in old and old.Decoded('duration')) or
                (old.Decoded('dtend') - old.Decoded('dtstart')))
            if not args.summary:
                args.summary = old.Decoded('summary').decode()
            if(not args.time and not (args.start and 'T' in args.start)
               and self.isallday(old)):
                args.allday = True
            day = args.day or old_start.day
            month = args.month or old_start.month
            year = args.year or old_start.year
        else:
            uid = "%s (%s)" % (datetime.now().isoformat(),
                               gethostname())
            # old_start = self.now
            # old_duration = None
            if not args.summary:
                raise Exception('Summary must be specified')
            day = args.day or self.now.day
            month = args.month or self.now.month + (
                1 if day < self.now.day and not args.year else 0)
            if not args.month and month == 13:
                month = 1
            year = args.year or self.now.year + (
                1 if month < self.now.month else 0)
        if args.allday:
            if args.start:
                start = date.fromisoformat(args.start)
            else:
                start = date(year, month, day)
            if args.no_of_days:
                duration = timedelta(days=args.no_of_days)
            elif old:
                duration = old_duration
            else:
                duration = timedelta(days=1)
            end = ((args.end and date.fromisoformat(args.end))
                   or (start + duration))
        else:
            if not (old or args.time or
                    (args.start and 'T' in args.start)):
                raise Exception(
                    'Either time or allday must be specified')
            if args.start:
                start = datetime.fromisoformat(args.start)
            else:
                if args.time:
                    try:
                        hh, mm = args.time.split(':')
                        int(hh), int(mm)
                    except Exception:
                        raise Exception(
                            'Time must be entered as hh:mm')
                    if args.timezone:
                        tz = gettz(args.timezone)
                        if tz is None:
                            raise Exception(
                                'Unknown timezone ' + args.timezone)
                    else:
                        tz = tzlocal()
                    start = datetime(year, month, day, int(hh),
                                     int(mm), tzinfo=tz)
                else:  # old is not None here
                    hh, mm = old_start.hour, old_start.minute
                    start = datetime(year, month, day, int(hh),
                                     int(mm), tzinfo=tzlocal())
            if not (args.no_of_days or args.duration):
                if old:
                    duration = old_duration
                else:
                    duration = default_event_duration
            else:
                duration = timedelta(
                    days=args.no_of_days or 0,
                    minutes=args.duration or default_event_duration)
            end = ((args.end and date.fromisoformat(args.end)) or
                   (start + duration))
        dtstamp = self.calendar_timezone(
            self.display_timezone(datetime.now()))
        if not old:
            event = Event()
            event.add('uid', uid)
            event.add('created', dtstamp)
        elif not args.noalarm:
            event = old
        else:
            s = re.sub(r'BEGIN:VALARM.*END:VALARM\s*', '',
                       old.to_ical().decode(), flags=re.DOTALL)
            event = Calendar.from_ical(s)

        def add_or_change(event, field, value):
            if field in event:
                event[field] = event._encode(field, value)
            else:
                event.add(field, value)

        def add_recurrence(event, field, value):
            tf = TypesFactory()
            parsed_value = tf.from_ical(field, value)
            add_or_change(event, field, parsed_value)

        add_or_change(event, 'last-modified', dtstamp)
        add_or_change(event, 'summary', args.summary)
        add_or_change(event, 'dtstart', self.calendar_timezone(start))
        add_or_change(event, 'dtend', self.calendar_timezone(end))
        if args.free:
            add_or_change(event, 'transp', 'TRANSPARENT')
        if args.busy:
            add_or_change(event, 'transp', 'OPAQUE')
        if args.location:
            add_or_change(event, 'location', args.location)
        if args.alarm:
            if not (old and event.walk('valarm')):
                event.add_component(Alarm())
            alarm = event.walk('valarm')[0]
            add_or_change(alarm, 'action', 'DISPLAY')
            add_or_change(alarm, 'trigger',
                          timedelta(minutes=-args.alarm))
        is_recurring_event = False
        for k in "rrule rdate exrule exdate".split():
            if k in vars(args):
                v = vars(args)[k]
                if v:
                    add_recurrence(event, k, v)
                    is_recurring_event = True
        if not args.no_prompt:
            self.printer.msg("{:} Event Details\n".format(
                "Edited" if old else "New"))
            self.printer.msg(event.to_ical().decode())
            if is_recurring_event:
                self.preview_recurring_event(event)
            else:
                self.iterate_events(None, [event], print_count=False)
            if not IcalendarInterface.confirm("Proceed y/n? "):
                self.printer.msg("Action cancelled\n")
                return False
        self.printer.msg("%s event\n" % ("Updating" if old
                                         else "adding"))
        if old:
            self.backend_interface.update_event(event, self.vtimezone)
        else:
            self.backend_interface.create_event(event, self.vtimezone)
        self.printer.msg("Event %s\n" % ("updated" if old
                                         else "added"))
        self.iterate_events(None, [event], print_count=False)
        self.backend_cache_dirty = True
        return True

    def raw_ics(self, original=None):
        if original:
            uid = original.Decoded('uid').decode()
        else:
            uid = "%s (%s)" % (datetime.now().isoformat(),
                               gethostname())
        self.printer.msg("Enter raw ICS lines followed by blank line")
        ics = ''
        for line in sys.stdin:
            if not line.strip():
                break
            ics += line
        try:
            event = Event.from_ical(ics)
        except Exception:
            self.printer.err_msg("iCalendar could not parse raw ICS")
            raise
        if event.errors:
            self.printer.err_msg("iCalendar could not parse raw ICS")
            raise Exception(str(event.errors))
        out = event.to_ical().decode()

        def lines(s):
            return ("\n".join(s.splitlines())).splitlines(keepends=True)
        diff = list(unified_diff(
            lines(ics), lines(out), fromfile='Input', tofile='Parsed', n=0))
        if diff:
            self.printer.err_msg(
                "ICS generated from parsed event differs from input ICS")
            for line in diff:
                self.printer.msg(line.strip())
            if not IcalendarInterface.confirm("Proceed y/n? "):
                self.printer.msg("Action cancelled\n")
                return False
        if 'uid' in event:
            new_uid = event.decoded('uid').decode()
            if original and new_uid != uid:
                raise 'UID cannot be changed. Delete event and add new event'
            else:
                uid = new_uid
        self.events[uid] = event
        return True


def repl(ecal=None):
    r"""Read Evaluate Print Loop (REPL)

    First time, reads and executes commands from command line
    In non interactive mode, the program then exits.
    Otherwise, it repeatedly reads command from terminal
    and executes it. Stops only if user types quit (q).
    Parameters
    ----------
    ecal : IcalendarInterface

    Returns
    -------
    IcalendarInterface or None
    """
    if ecal:
        # IcalendarInterface (ecal) already exists
        # So the first run is already over
        # ecal has been created and command line has been processed
        # So read next command from the terminal
        parser = get_argument_parser(initial=False)
        s = input("Enter new command\n")
        try:
            FLAGS = parser.parse_args(shlex.split(s))
        except Exception as e:
            sys.stderr.write(str(e))
            parser.print_usage()
            return ecal
        except SystemExit:
            return ecal
        # Use existing IcalendarInterface (ecal)
        ecal.set_options(vars(FLAGS))
    else:
        # IcalendarInterface (ecal) does not exist
        # So this is the first command
        # Read command from the command line
        parser = get_argument_parser(initial=True)
        try:
            FLAGS = parser.parse_args()
        except Exception as e:
            sys.stderr.write(str(e))
            parser.print_usage()
            sys.exit(1)
        try:
            spec = importlib.util.spec_from_file_location(
                "config", expanduser(FLAGS.config))
            config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config)
            assert config.backend_interface
        except Exception as e:
            sys.stderr.write(str(e))
            print("Unable to import backend_interface")
            sys.exit(1)

        printer = Printer(conky=FLAGS.conky, use_color=FLAGS.color,
                          art_style=FLAGS.lineart)

        if FLAGS.command is None:
            # if no command given we simulate default command
            default_command = "agenda"
            parser = get_argument_parser(initial=True)
            FLAGS = parser.parse_args(sys.argv[1:] + [default_command])

        # create IcalendarInterface (ecal)
        ecal = IcalendarInterface(
            add_parser=get_add_parser(),
            backend_interface=config.backend_interface,
            printer=printer, **vars(FLAGS))
        if hasattr(config, 'timezones') and 'tz' in config.timezones:
            IcalendarInterface.calendar_tz = config.timezones['tz']
        else:
            IcalendarInterface.calendar_tz = UTC
        if hasattr(config, 'timezones') and 'vtimezone' in config.timezones:
            IcalendarInterface.vtimezone = config.timezones['vtimezone']
        else:
            IcalendarInterface.vtimezone = None
        ecal.interactive = FLAGS.interactive
        ecal.no_auto_sync = False
        if FLAGS.locale:
            try:
                utils.set_locale(FLAGS.locale)
            except ValueError as exc:
                ecal.printer.err_msg(str(exc)+'\n')
                if ecal.initial_options['stack_trace']:
                    print_exc()

    # The no_auto_sync option is available only for editing commands
    # If an edit is done with no_auto_sync and this is followed by a viewing
    # command, we must "remember" the no_auto_sync. So we store it in ecal.
    # If a quit command is given, we cannot auto-sync, but must prompt for sync
    if "no_auto_sync" in FLAGS:
        ecal.no_auto_sync = FLAGS.no_auto_sync

    try:
        if FLAGS.command in ['g', 'agenda']:
            ecal.AgendaQuery(start=FLAGS.start, end=FLAGS.end,
                             days=FLAGS.days)

        elif FLAGS.command in ['w', 'calw']:
            ecal.CalQuery(
                    'calw', count=FLAGS.weeks, startText=FLAGS.start)

        elif FLAGS.command in ['m', 'calm']:
            ecal.CalQuery('calm', startText=FLAGS.start)

        elif FLAGS.command in ['s', 'search']:
            ecal.TextQuery(FLAGS.text[0], start=FLAGS.start,
                           end=FLAGS.end,
                           # field='uid' if FLAGS.uid else 'summary')
                           field=FLAGS.property)

        elif FLAGS.command in ['a', 'add']:
            ecal.add(FLAGS)

        elif FLAGS.command in ['y', 'sync']:
            ecal.sync()

        elif FLAGS.command in ['e', 'edit']:
            ecal.edit(FLAGS.text[0], start=FLAGS.start, end=FLAGS.end,
                      # field='uid' if FLAGS.uid else 'summary')
                      field=FLAGS.property)

        elif FLAGS.command in ['d', 'delete']:
            ecal.delete(FLAGS.text[0], start=FLAGS.start,
                        # field='uid' if FLAGS.uid else 'summary')
                        field=FLAGS.property)

        elif FLAGS.command in ['q', 'quit']:
            if(ecal.backend_cache_dirty and ecal.no_auto_sync
               and not IcalendarInterface.confirm(
                   "Changes made in calendar not yet synced. Quit y/n? ")):
                pass
            else:
                ecal.interactive = False

    except Exception as exc:
        ecal.printer.err_msg(str(exc)+'\n')
        if ecal.initial_options['stack_trace']:
            print_exc()
        return ecal if ecal.interactive else None

    if ecal.backend_cache_dirty and not ecal.no_auto_sync:
        ecal.printer.msg("Syncing changes made in calendar\n")
        ecal.sync()
    if ecal.backend_cache_dirty:
        ecal.printer.msg("Changes made in calendar not yet synced\n")
    if ecal.interactive:
        return ecal  # Returning non None continues the REPL loop
    else:
        return None  # None means that REPL loop is over


def main():
    # Start Read Evaluate Print Loop (REPL)
    ecal = repl()
    # Keep running REPL until it returns None
    while ecal:
        # The REPL may keep running for many hours/days
        # The date/time stored in ecal's "now" variable may become very stale
        # So we set ecal's "now" variable before running each command.
        ecal.set_now()
        ecal = repl(ecal=ecal)


def SIGINT_handler(signum, frame):
    sys.stderr.write('Signal caught, bye!\n')
    sys.exit(1)


signal.signal(signal.SIGINT, SIGINT_handler)


if __name__ == '__main__':
    main()
