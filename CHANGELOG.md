# 1.0.0 released 2022-08-17

## Added

* Added support for recurring events using [python-recurring-ical-events ](https://github.com/niccokunzmann/python-recurring-ical-events). 
* It is also possible to create and edit recurring events The recurrence rule has to be given as a string using the `--rrule` option to the `add` and `edit` commands (for example `--rrule FREQ=DAILY;COUNT=5`). Editing/deleting modifies/deletes all occurrences of the event. To delete a single occurrence, use `--exdate`.
* Added support for creating/editing events using raw ICS text. This is mainly for properties (like `attendee` and `comment`) that are not available as command line options.
* If duplicate UIDs are found, they are de-duplicated and the calendar is opened in read only mode. Editing a file with multiple UIDs is dangerous.

## Changed

* Searching for events without any start or end parameters now returns event occurrences only within the last 5 years and next 5 years (this number can be changed with the option `--default_past_years` and `--default_future_years`). More events can be obtained using explicit start and end parameters. For example, `s home '-10 y' 15y` will go back 10 years and forward 15 years. This change was necessitated because a single recurring event (without any `COUNT` or `UNTIL` restrictions) can generate an infinite number of occurrences.
* The `-u` or `--uid` option has been removed and replaced by a more general `-p` or `--property` option that allows any property of the event to be searched. For example, `s -p rrule DAILY` will display all events with a recurrence rule that has a daily frequency.
* Many Bug fixes.
* Several method names were changed (the leading underscore was dropped from all method names), but these were intended to be used only internally. 

# 0.9.9 released 2022-07-12

## Added

* Check for errors while parsing `iCalendar` events
* Added option to provide stack trace for errors. By default, most errors are caught using try blocks and only a cryptic summary is provided. With this option, the stack trace is printed, but the program continues to run.

## Changed

* A few bug fixes

