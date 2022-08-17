__program__ = 'icalcli'
__version__ = 'v1.0.2'
__author__ = 'Jayanth Varma (modified gcalcli by Eric Davis et al.)'
from icalcli.icalcli import IcalendarInterface  # noqa F401
try:
    from icalcli.etesync_backend.etesync_crud import EtesyncCRUD  # noqa F401
    from icalcli.etesync_backend.etesync_interface import EtesyncInterface  # noqa F401
except ImportError:
    pass

from icalcli.file_backend.ics_interface import ICSInterface  # noqa F401
