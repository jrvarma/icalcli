#!/usr/bin/env python

# this is part of the etesync 2.0 backend
# for etesync 1.0 backend see etesync_interface.py

from icalcli.etesync_backend.etebase_crud import EtebaseCRUD
from icalendar import Calendar


# The EtebaseInterface class is basically a wrapper around the
# EtebaseCRUD class from which it is derived
# The CRUD operations (Create, Retrieve, Update and Delete)
# work with icalendar events (VEVENT). While calling EtebaseCRUD methods,
# both inputs and return values are converted to/from
# ics calendar bytes/strings

# The class is initialized with user details and credentials.

# Intended usage is that a calling program obtains user credentials
# from terminal input or some secure storage (like a key ring)
# and then creates an instance of EtebaseCRUD as follows:

# etes = EtebaseInterface(user, server_url, password, calendar_uid)

# The calling program can then perform CRUD operations by calling
# etes.create_event, etes.retrieve_event,
# etes.update_event and etes.delete_event

# The calling program must explicitly call sync() when the server
# has been updated from another device
# sync() is not needed after any CRUD operation

# No exception handling is done. That is left to the calling program.


class EtebaseInterface (EtebaseCRUD):
    def __init__(self, user, server_url, password, calendar_uid,
                 cache_file=None, silent=True):
        r"""Initialize EtebaseInterface

        Parameters
        ----------
        user : etebase username
        password : etebase password
        server_url : url of etebase server
        calendar_uid : uid of calendar
        """
        super(EtebaseInterface, self).__init__(
            user=user, server_url=server_url, password=password,
            calendar_uid=calendar_uid, cache_file=cache_file, silent=silent)
        print("Parsing all events")
        self.all_events()

    def all_events(self):
        self.events = [Calendar.from_ical(ev).walk('VEVENT')[0]
                       for ev in self.raw_events]

    def create_event(self, event, vtimezone=None):
        r"""Create event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        ics = self.event_to_ics(event, vtimezone)
        uid = event.decoded('uid').decode()
        EtebaseCRUD.create_event(self, ics, uid)

    def update_event(self, event, vtimezone=None):
        r"""Update event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        uid = event.decoded('uid').decode()
        ics = self.event_to_ics(event, vtimezone)
        EtebaseCRUD.update_event(self, ics, uid)

    def event_to_ics(self, event, vtimezone=None):
        r"""Make calendar byte array (ics) from event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        cal = Calendar()
        cal.add_component(event)
        if vtimezone:
            cal.add_component(vtimezone)
        ics = cal.to_ical()
        return ics

    def sync(self, vtimezone=None):
        r"""Sync with server and rebuild vevent list
        """
        EtebaseCRUD.sync(self)
        self.all_events()
