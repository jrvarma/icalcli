#!/usr/bin/env python

# this is part of the etesync 2.0 backend
# for etesync 1.0 backend see etesync_crud.py

from etebase import Client, Account, FetchOptions, Base64Url
from time import sleep, time
import json

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

    def __init__(self, user, server_url, password, calendar_uid,
                 cache_file=None, silent=True):
        """Initialize

        Parameters
        ----------
        user : etebase username
        password : etebase password
        server_url : url of etebase server
        calendar_uid : uid of calendar
        cache_file: path to the cache file or None
        """
        client = Client(user, server_url)
        etebase = Account.login(client, user, password)
        col_mgr = etebase.get_collection_manager()
        collection = col_mgr.fetch(calendar_uid)
        self.item_mgr = col_mgr.get_item_manager(collection)
        self.items = {}
        self.stoken = None
        self.raw_events = []
        self.cache_file = cache_file
        self.load_cache()
        self.sync(silent)
        print("Reading all events")
        self.get_all_events()

    def create_event(self, event, event_uid):
        """Create event

        Parameters
        ----------
        event : iCalendar file as bytes
        (calendar containing one event to be added)
        event_uid : uid of event to be updated
        """
        item = self.item_mgr.create(
            {
                "name": event_uid,
                "mtime": int(round(time() * 1000))
            },
            event
        )
        self.item_mgr.batch([item])

    def update_event(self, event, event_uid):
        """Edit event

        Parameters
        ----------
        event : iCalendar file as bytes
        (calendar containing one event to be updated)
        event_uid : uid of event to be updated
        """
        item = self.item_mgr.fetch(self.event_uid_to_item_uid[event_uid])
        assert item.meta['name'] == event_uid
        item.content = event
        # item.meta["mtime"] = int(round(time() * 1000))
        self.item_mgr.batch([item])

    def retrieve_event(self, event_uid):
        r"""Retrieve event by uid

        Parameters
        ----------
        event_uid : uid of event to be retrieved

        Returns
        -------
        iCalendar file (as a string)
        """
        item = self.item_mgr.fetch(self.event_uid_to_item_uid[event_uid])
        assert item.meta['name'] == event_uid
        return item.content.decode()

    def delete_event(self, event_uid):
        """Delete event and sync calendar

        Parameters
        ----------
        uid : uid of event to be deleted
        """
        item = self.item_mgr.fetch(self.event_uid_to_item_uid[event_uid])
        assert item.meta['name'] == event_uid
        item.meta["mtime"] = int(round(time() * 1000))
        item.delete()
        self.item_mgr.batch([item])

    def get_all_events(self):
        """Retrieve all events in calendar

        Returns
        -------
        List of iCalendar files (as strings)
        """
        self.event_uid_to_item_uid = {
            e.meta['name']: e.uid for e in self.items.values()}
        self.raw_events = [e.content.decode()
                           for e in self.items.values() if not e.deleted]

    def sync(self, silent=False):
        """Initialize

        Parameters
        ----------
        silent : boolean whether to report sync attempt and success
        """
        silent or print("Syncing with server. Please wait")
        msg = "etebase fetch attempt {:} failed. Will retry after {:} seconds"
        delay = 5
        done = False
        chunk = 100
        for i in range(5):
            try:
                while not done:
                    items = self.item_mgr.list(
                        FetchOptions().stoken(self.stoken).limit(chunk))
                    self.items.update(
                        {item.uid: item for item in items.data})
                    self.stoken = items.stoken
                    done = items.done
                    # silent or print(".", end='')
                break
            except Exception:
                silent or print(msg.format(i+1, delay))
                sleep(delay)
        if done:
            silent or print("Syncing completed.")
            self.save_cache()
        else:
            print("Syncing with server failed after 5 attempts")
        return

    def load_cache(self):
        if self.cache_file:
            d = json.load(open(self.cache_file))
            if 'stoken' in d:
                self.stoken = d['stoken']
            if 'blobs' in d:
                for cache_blob in d['blobs']:
                    item = self.item_mgr.cache_load(
                        Base64Url.from_base64(cache_blob))
                    self.items[item.uid] = item

    def save_cache(self):
        if self.cache_file:
            cache = dict(
                stoken=self.stoken,
                blobs=[Base64Url.to_base64(self.item_mgr.cache_save(item))
                       for item in self.items.values()])
            json.dump(cache, open(self.cache_file, 'w'))
