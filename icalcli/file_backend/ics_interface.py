from icalendar import Calendar
from tempfile import NamedTemporaryFile
from pathlib import Path


class ICSInterface:
    def __init__(self, filename, backup=False):
        r"""Initialize ICSInterface

        Parameters
        ----------
        filename : path to ics file
        backup: boolean whether to back up old file before overwriting
        """
        if isinstance(filename, list):
            self.filepaths = [Path(f).resolve() for f in filename]
            self.readonly = True
        else:
            self.filepaths = [Path(filename).resolve()]
            self.readonly = False
        self.backup = backup
        self.ics = []
        self.all_events()

    def all_events(self):
        def check_event(event):
            if event.errors:
                print("iCalendar error:\n{:} while parsing\n{:}".format(
                    event.errors, event.to_ical().decode()))
                return False
            else:
                return True
        self.events = []
        self.cache_events = {}
        filecount = 0
        for path in self.filepaths:
            with open(path, 'r') as fp:
                cal = Calendar.from_ical(fp.read())
            events = [ev for ev in cal.walk('VEVENT') if check_event(ev)]
            self.events += events
            for ev in events:
                uid = ev.decoded('uid').decode()
                if len(self.filepaths) > 1:
                    uid = f"File{filecount}:{uid}"
                self.cache_events[uid] = ev
            filecount += 1

    def create_event(self, event, vtimezone=None):
        uid = event.decoded('uid').decode()
        self.cache_events[uid] = event

    def update_event(self, event, vtimezone=None):
        uid = event.decoded('uid').decode()
        self.cache_events[uid] = event

    def delete_event(self, uid):
        del self.cache_events[uid]

    def sync(self, vtimezone=None):
        if self.readonly:
            return
        if self.backup:
            with NamedTemporaryFile(mode='w',
                                    suffix=self.filepaths[0].suffix,
                                    prefix=self.filepaths[0].name,
                                    dir=self.filepaths[0].parent,
                                    delete=False) as fp:
                fp.write(self.ics)
        cal = Calendar()
        for event in self.cache_events.values():
            cal.add_component(event)
        if vtimezone:
            cal.add_component(vtimezone)
        self.ics = cal.to_ical().decode()
        with open(self.filepaths[0], 'w') as fp:
            fp.write(self.ics)
        self.all_events()
