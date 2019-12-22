__program__ = 'icalcli'
__version__ = 'v0.9'
__author__ = 'Jayanth Varma (modified gcalcli by Eric Davis, Brian Hartvigsen, Joshua Crowgey)'
from icalcli.icalcli import IcalendarInterface
from icalcli.etesync_backend.etesync_crud import EtesyncCRUD
from icalcli.etesync_backend.etesync_interface import EtesyncInterface
from icalcli.file_backend.ics_interface import ICSInterface
