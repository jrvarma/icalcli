from __future__ import absolute_import
import argparse
import icalcli
from icalcli import utils
from icalcli.printer import valid_color_name
import copy as _copy
from os.path import expanduser
from sys import stdout

OUTPUTS = {'l': 'location', 'e': 'end', 'a': 'alarms',
           'd': 'description', 'f': 'freebusy', 'u': 'uid'}
NO_OUTPUTS = ['no' + s[0] for s in OUTPUTS.keys()]


class OutputsAction(argparse._AppendAction):

    def __call__(self, parser, namespace, value, option_string=None):
        outputs = _copy.copy(getattr(namespace, self.dest, {}))

        if value == 'A':
            outputs = {d: True for d in OUTPUTS.keys()}
        elif value in OUTPUTS.keys():
            outputs[OUTPUTS[value]] = True
        elif value in NO_OUTPUTS:
            outputs[OUTPUTS[value[2]]] = False

        setattr(namespace, self.dest, outputs)


def validwidth(value):
    ival = int(value)
    if ival < 10:
        raise argparse.ArgumentTypeError("Width must be a number >= 10")
    return ival


def validreminder(value):
    if not utils.parse_reminder(value):
        raise argparse.ArgumentTypeError(
                "Not a valid reminder string: %s" % value)
    else:
        return value


def get_outputs_parser():
    outputs_parser = argparse.ArgumentParser(add_help=False)
    outputs_parser.add_argument(
        "-o", "--outputs", default={}, action=OutputsAction,
        choices=list(OUTPUTS.keys())+NO_OUTPUTS,
        help="Which parts to display, can be: "
        + ", ".join([k+'/no'+k+': '+v for k, v in OUTPUTS.items()]))
    return outputs_parser


def get_output_parser(parents=[]):
    output_parser = argparse.ArgumentParser(add_help=False, parents=parents)
    output_parser.add_argument(
            "--nostarted", action="store_true", dest="ignore_started",
            default=False, help="Hide events that have started")
    output_parser.add_argument(
            "--nodeclined", action="store_true", dest="ignore_declined",
            default=False, help="Hide events that have been declined")
    output_parser.add_argument(
            "--width", "-w", default=10, dest='cal_width', type=validwidth,
            help="Set output width")
    output_parser.add_argument(
            "--military", action="store_true", default=False,
            help="Use 24 hour display")
    output_parser.add_argument(
            "--override-color", action="store_true", default=False,
            help="Use overridden color for event")
    return output_parser


def get_color_parser():
    color_parser = argparse.ArgumentParser(add_help=False)
    color_parser.add_argument(
            "--color_date", default="yellow", type=valid_color_name,
            help="Color for the date")
    color_parser.add_argument(
            "--color_now_marker", default="brightred", type=valid_color_name,
            help="Color for the now marker")
    color_parser.add_argument(
            "--color_border", default="white", type=valid_color_name,
            help="Color of line borders")
    color_parser.add_argument(
            "--color_title", default="brightyellow", type=valid_color_name,
            help="Color of the agenda column titles")
    return color_parser


def get_cal_query_parser():
    cal_query_parser = argparse.ArgumentParser(add_help=False)
    cal_query_parser.add_argument("start", type=str, nargs="?")
    cal_query_parser.add_argument(
            "--monday", action="store_true", dest='cal_monday', default=False,
            help="Start the week on Monday")
    cal_query_parser.add_argument(
            "--noweekend", action="store_false", dest='cal_weekend',
            default=True,  help="Hide Saturday and Sunday")
    return cal_query_parser


def get_start_end_parser():
    se_parser = argparse.ArgumentParser(add_help=False)
    se_parser.add_argument(
        "start", type=utils.get_start_time_from_str, nargs="?")
    se_parser.add_argument(
        "end", type=utils.get_end_time_from_str, nargs="?")
    return se_parser


def get_search_parser():
    # requires search text, optional start and end filters
    search_parser = argparse.ArgumentParser(add_help=False)
    search_parser.add_argument("text", nargs=1, type=utils._u)
    search_parser.add_argument(
            "start", type=utils.get_start_time_from_str, nargs="?")
    search_parser.add_argument(
        "end", type=utils.get_end_time_from_str, nargs="?")
    search_parser.add_argument(
        "-n", "--no-ignore-case", action="store_true", default=False)
    search_parser.add_argument("-u", "--uid", action="store_true",
                               default=False, help='Search by UID')
    return search_parser


def fill_add_parser(add):
    add.add_argument('-y', '--year', type=int, help='Event year')
    add.add_argument('-m', '--month', type=int, help='Event month')
    add.add_argument('-d', '--day', type=int, help='Event day')
    add.add_argument('-t', '--time', help='Event time hh:mm')
    add.add_argument('-D', '--duration', type=int,
                     help='Event duration (minutes)')
    add.add_argument('-A', '--allday', action='store_true',
                     help='All day event')
    add.add_argument('-N', '--no-of-days', type=int,
                     help='Event duration (days)')
    alarms = add.add_mutually_exclusive_group()
    alarms.add_argument('-a', '--alarm', type=int,
                        help='Alarm (minutes before event)')
    alarms.add_argument('-q', '--noalarm', action='store_true',
                        help='Remove all alarms')
    add.add_argument('-f', '--free', action='store_true',
                     help='Show as free')
    add.add_argument('-b', '--busy', action='store_true',
                     help='Show as busy')
    add.add_argument('-s', '--start', help='Start date/time (ISO format)')
    add.add_argument('-e', '--end', help='End date/time (ISO format)')
    add.add_argument('-z', '--timezone', help='Specify Timezone')
    add.add_argument('-S', '--summary', help='Event Summary')
    add.add_argument('-L', '--location', help='Location')
    add.add_argument("--no-auto-sync", action="store_true", default=False,
                     help="Automatically sync when calendar changed")
    add.add_argument("--no-prompt", action="store_true", default=False,
                     help="Add event without prompting")
    return add


def get_argument_parser():
    parser = argparse.ArgumentParser(
        description='Icalendar Calendar Command Line Interface',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        fromfile_prefix_chars="@")

    parser.add_argument(
        "--version", action="version", version="%%(prog)s %s (%s)" %
        (icalcli.__version__, icalcli.__author__))

    parser.add_argument(
        "-i", "--interactive", action="store_true", default=False,
        help="Interactively execute commands")
    parser.add_argument(
        "-c", "--config", default=expanduser('~/.icalcli.py'),
        type=str, help="Config script to be executed")
    parser.add_argument(
        "--locale", default='', type=str, help="System locale")
    parser.add_argument(
        "--conky", action="store_true", default=False,
        help="Use Conky color codes")
    parser.add_argument(
        "--nocolor", action="store_false",
        default=stdout.isatty(), dest="color",
        help="Enable/Disable all color output")
    parser.add_argument(
        "--lineart", default="unicode",
        choices=["fancy", "unicode", "ascii"],
        help="Choose line art style for calendars: \"fancy\": for" +
        "VTcodes, \"unicode\" for Unicode box drawing characters," +
        "\"ascii\" for old-school plusses, hyphens and pipes.")

    # parent parser types used for subcommands
    outputs_parser = get_outputs_parser()
    color_parser = get_color_parser()

    # Output parser should imply color parser
    output_parser = get_output_parser(parents=[color_parser])

    # remind_parser = get_remind_parser()
    cal_query_parser = get_cal_query_parser()

    # parsed start and end times
    start_end_parser = get_start_end_parser()

    # tacks on search text
    search_parser = get_search_parser()

    sub = parser.add_subparsers(
        help="Invoking a subcommand with --help prints subcommand usage.",
        dest="command")
    # sub.required = True

    sub.add_parser("sync", aliases=['y'])
    sub.add_parser("quit", aliases=['q'])
    # sub.add_parser("recent", aliases=['r'],
    #                parents=[outputs_parser, output_parser])

    sub.add_parser(
        "search", aliases=['s'],
        parents=[outputs_parser, output_parser, search_parser])
    edit = sub.add_parser("edit", aliases=['e'], parents=[
        outputs_parser, output_parser, search_parser])
    edit.add_argument(
        "--no-auto-sync", action="store_true", default=False,
        help="Do not automatically sync when calendar changed")

    delete = sub.add_parser(
        "delete", aliases=['d'],
        parents=[outputs_parser, output_parser, search_parser])
    # delete.add_argument("--no-prompt", action="store_true", default=False,
    #                     help="Delete without prompting")
    delete.add_argument("--no-auto-sync", action="store_true", default=False,
                        help="Automatically sync when calendar changed")

    agenda = sub.add_parser(
        "agenda", aliases=['g'],
        parents=[outputs_parser, output_parser, start_end_parser])
    agenda.add_argument('-n', "--days", type=int, default=5, nargs="?")

    calw = sub.add_parser(
        "calw", aliases=['w'],
        parents=[outputs_parser, output_parser, cal_query_parser])
    calw.add_argument('-n', "--weeks", type=int, default=2, nargs="?")

    sub.add_parser(
        "calm", aliases=['m'],
        parents=[outputs_parser, output_parser, cal_query_parser])

    # sub.add_parser("interactive", aliases=['i'])

    add = sub.add_parser("add", aliases=['a'],
                         parents=[outputs_parser, output_parser])
    fill_add_parser(add)
    return parser


def get_add_parser():
    return fill_add_parser(argparse.ArgumentParser(prog=''))
