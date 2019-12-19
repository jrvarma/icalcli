from etesync_crud import EtesyncCRUD
from icalendar import Calendar


# The EtesyncInterface class is basically a wrapper around the
# EtesyncCRUD class from which it is derived
# The CRUD operations (Create, Retrieve, Update and Delete)
# work with icalendar events (VEVENT). These are converted to
# ics calendar strings and EtesyncCRUD methods are called with
# these strings as argument.

# The class is initialized with user details, authToken and
# EITHER the encryption password OR the cipher key.

# Intended usage is that a calling program obtains user credentials
# from terminal input or some secure storage (like a key ring)
# and then creates an instance of EtesyncCRUD as follows:

# # call with cipher key
# etes = EtesyncInterface(email, None, remoteUrl, uid, authToken, cipher_key)
# # call with encryption password
# etes = EtesyncInterface(email, userPassword, remoteUrl, uid, authToken, None)

# The calling program can then perform CRUD operations by calling
# etes.create_event, etes.retrieve_event,
# etes.update_event and etes.delete_event

# The calling program must explicitly call etes.sync when needed. For example:
# (a) if the server has been updated from another device
# (b) after any CRUD operation other than Retrieve

# No exception handling is done. That is left to the calling program.


class EtesyncInterface (EtesyncCRUD):
    def __init__(self, email, userPassword, remoteUrl, uid, authToken,
                 cipher_key=None):
        r"""Initialize EtesyncInterface

        Parameters
        ----------
        email : etesync username(email)
        userPassword : etesync encryption password
        remoteUrl : url of etesync server
        uid : uid of calendar (currently only one calendar is supported)
        authToken : authentication token for etesync server
        """
        super(EtesyncInterface, self).__init__(
            email, userPassword, remoteUrl,
            uid, authToken, cipher_key)
        self.all_events()

    def all_events(self):
        self.events = [Calendar.from_ical(ev).walk('VEVENT')[0]
                       for ev in EtesyncCRUD.all_events(self)]

    def create_event(self, event):
        r"""Create event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        ics = self.event_to_ics(event)
        EtesyncCRUD.create_event(self, ics)

    def update_event(self, event):
        r"""Update event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        uid = event.decoded('uid').decode()
        ics = self.event_to_ics(event)
        EtesyncCRUD.update_event(self, ics, uid)

    def event_to_ics(self, event):
        r"""Make calendar string (ics) from event

        Parameters
        ----------
        event : event to be added (iCalendar object)
        """
        cal = Calendar()
        cal.add_component(event)
        try:
            cal.add_component(timezones['vtimezone'])
        except NameError:
            pass
        ics = cal.to_ical().decode()
        return ics

    def sync(self):
        r"""Sync with server and rebuild vevent list
        """
        EtesyncCRUD.sync(self)
        self.all_events()

