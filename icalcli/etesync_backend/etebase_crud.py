#!/usr/bin/env python

# this is part of the etesync 2.0 backend
# for etesync 1.0 backend see etesync_crud.py

from etebase import Client, Account, FetchOptions
from time import sleep, time

# The EtesyncCRUD class exposes methods for each of the CRUD operations
# (Create, Retrieve, Update and Delete) and for sync with the server.
# It handles only one calendar

# The class is initialized with user details, authToken and
# EITHER the encryption password OR the cipher key.

# Intended usage is that a calling program (a CLI) obtains user credentials
# from terminal input or some secure storage (like a key ring)
# and then creates an instance of EtesyncCRUD as follows:

# crud = EtebaseCRUD(user, server_url, password, calendar_uid)

# The CLI program can then perform CRUD operations by calling
# crud.create_event, crud.retrieve_event,
# crud.update_event and crud.delete_event

# The CLI must explicitly call crud.sync when needed. For example:
# (a) if the server has been updated from another device
# (b) after any CRUD operation other than Retrieve

# No exception handling is done. That is left to the CLI.


class EtebaseCRUD:
    def __init__(self, user, server_url, password, calendar_uid, silent=True):
        """Initialize

        Parameters
        ----------
        user : etebase username
        password : etebase password
        server_url : url of etebase server
        calendar_uid : uid of calendar
        """
        client = Client(user, server_url)
        etebase = Account.login(client, user, password)
        col_mgr = etebase.get_collection_manager()
        collection = col_mgr.fetch(calendar_uid)
        self.item_mgr = col_mgr.get_item_manager(collection)
        self.sync(silent)

    def create_event(self, event, uid):
        """Create event

        Parameters
        ----------
        event : iCalendar file as bytes
        (calendar containing one event to be added)
        """
        item = self.item_mgr.create(
            {
                "name": uid,
                "mtime": int(round(time() * 1000))
            },
            event
        )
        self.item_mgr.batch([item])

    def update_event(self, event, uid):
        """Edit event

        Parameters
        ----------
        event : iCalendar file as bytes
        (calendar containing one event to be updated)
        uid : uid of event to be updated
        """
        item = self.item_mgr.fetch(uid)
        item.content = event
        self.item_mgr.batch([item])

    def retrieve_event(self, uid):
        r"""Retrieve event by uid

        Parameters
        ----------
        uid : uid of event to be retrieved

        Returns
        -------
        iCalendar file (as a string)
        """
        return self.item_mgr.fetch(uid).content.decode()

    def all_events(self):
        """Retrieve all events in calendar

        Returns
        -------
        List of iCalendar files (as strings)
        """
        return [e.content.decode() for e in self.items.data if not e.deleted]

    def delete_event(self, uid):
        """Delete event and sync calendar

        Parameters
        ----------
        uid : uid of event to be deleted
        """
        item = self.item_mgr.fetch(uid)
        item.delete()
        self.item_mgr.batch([item])

    def sync(self, silent=False):
        """Initialize

        Parameters
        ----------
        silent : boolean whether to report sync attempt and success
        """
        silent or print("Syncing with server. Please wait")
        msg = "etebase fetch attempt {:} failed. Will retry after {:} seconds"
        delay = 5
        synced = False
        for i in range(5):
            try:
                self.items = self.item_mgr.list(FetchOptions().limit(10**6))
                synced = True
                break
            except Exception:
                silent or print(msg.format(i+1, delay))
                sleep(delay)
        if synced:
            silent or print("Syncing completed.")
            self.all_events()
        else:
            print("Syncing with server failed after 5 attempts")
