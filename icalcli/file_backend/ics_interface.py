from icalendar import Calendar
from tempfile import NamedTemporaryFile
from pathlib import Path


class ICSInterface:
    def __init__(self, filename, backup=False):
        r"""Initialize EtesyncInterface

        Parameters
        ----------
        filename : path to ics file
        backup: boolean whether to back up old file before overwriting
        """
        self.filepath = Path(filename).resolve()
        self.backup = backup
        with open(self.filepath, 'r') as fp:
            self.ics = fp.read()
        self.all_events()

    def all_events(self):
        self.ical = Calendar.from_ical(self.ics)
        self.events = self.ical.walk('VEVENT')
        self.cache_events = {}
        for ev in self.events:
            uid = ev.decoded('uid').decode()
            self.cache_events[uid] = ev

    def create_event(self, event, vtimezone=None):
        uid = event.decoded('uid').decode()
        self.cache_events[uid] = event

    def update_event(self, event, vtimezone=None):
        uid = event.decoded('uid').decode()
        self.cache_events[uid] = event

    def delete_event(self, uid):
        del self.cache_events[uid]

    def sync(self, vtimezone=None):
        if self.backup:
            with NamedTemporaryFile(mode='w',
                                    suffix=self.filepath.suffix,
                                    prefix=self.filepath.name,
                                    dir=self.filepath.parent,
                                    delete=False) as fp:
                fp.write(self.ics)
        cal = Calendar()
        for event in self.cache_events.values():
            cal.add_component(event)
        if vtimezone:
            cal.add_component(vtimezone)
        self.ics = cal.to_ical().decode()
        with open(self.filepath, 'w') as fp:
            fp.write(self.ics)
        self.all_events()
