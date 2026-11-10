from datetime import date

from icalendar import Calendar, Event

from icalcli.file_backend.ics_interface import ICSInterface


def test_missing_single_file_starts_empty(tmp_path):
    missing = tmp_path / "calendar.ics"
    backend = ICSInterface(str(missing))
    assert backend.events == []
    assert backend.cache_events == {}


def test_missing_single_file_sync_creates_it(tmp_path):
    missing = tmp_path / "calendar.ics"
    backend = ICSInterface(str(missing))
    cal = Calendar()
    event = Event()
    event.add("uid", "test-uid-1")
    event.add("summary", "Test event")
    event.add("dtstart", date(2026, 1, 1))
    backend.create_event(event)
    backend.sync()
    assert missing.is_file()
    assert "Test event" in missing.read_text()


def test_missing_file_with_missing_parent_dir_raises(tmp_path):
    missing = tmp_path / "no-such-dir" / "calendar.ics"
    try:
        ICSInterface(str(missing))
    except FileNotFoundError as exc:
        assert "calendar.ics" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
