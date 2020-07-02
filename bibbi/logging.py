import logging
import os

import psutil
from colorama import Fore, Style

DEBUG = "DEBG"
INFO = "INFO"
WARNING = "WARN"
ERROR = "ERR."
CRITICAL = "CRIT"

COLORS = {
    DEBUG: Fore.LIGHTCYAN_EX,
    INFO: Fore.LIGHTWHITE_EX,
    WARNING: Fore.LIGHTYELLOW_EX,
    ERROR: Fore.LIGHTRED_EX,
    CRITICAL: Fore.RED,
}

NAMES = {
    logging.DEBUG: DEBUG,
    logging.INFO: INFO,
    logging.WARNING: WARNING,
    logging.ERROR: ERROR,
    logging.CRITICAL: CRITICAL,
}


class AppFilter(logging.Filter):

    def __init__(self, name=''):
        super().__init__(name)
        self.process = psutil.Process(os.getpid())

    def get_mem_usage(self):
        """ Returns memory usage in MBs """
        return self.process.memory_info().rss / 1024. ** 2

    @staticmethod
    def format_as_mins_and_secs(msecs):
        secs = msecs / 1000.
        mins = secs / 60.
        secs = secs % 60.
        return '%3.f:%02.f' % (mins, secs)

    def filter(self, record):
        super().filter(record)
        record.mem_usage = '%4.0f' % (self.get_mem_usage(),)
        record.relativeSecs = AppFilter.format_as_mins_and_secs(record.relativeCreated)
        return True


class ColorFilter(logging.Filter):
    def filter(self, record):
        super().filter(record)
        record.color = COLORS.get(record.levelname, Fore.LIGHTWHITE_EX)
        return True


def configure_logging():
    for _level, _name in NAMES.items():
        logging.addLevelName(_level, _name)

    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)
    logging.getLogger('oauthlib').setLevel(logging.WARNING)
    logging.getLogger('mwtemplates').setLevel(logging.INFO)

    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    syslog = logging.StreamHandler()
    log.addHandler(syslog)
    syslog.setLevel(logging.INFO)
    formatter = logging.Formatter('%(color)s%(levelname)s' + Style.RESET_ALL + Fore.LIGHTYELLOW_EX + '%(relativeSecs)s %(mem_usage)s MB %(name)-20s:'  + Style.RESET_ALL + ' %(message)s')
    syslog.setFormatter(formatter)
    syslog.addFilter(AppFilter())
    syslog.addFilter(ColorFilter())

