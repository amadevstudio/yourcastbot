"""Expose library errors and uncaught exceptions to the dated diagnostics logs."""
import logging
import sys
import threading
import traceback

from lib.tools.logger import Logger


class RuntimeHandler(logging.Handler):
    def __init__(self, target):
        super().__init__(logging.WARNING)
        self.target = target

    def emit(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += ' ' + ''.join(traceback.format_exception(*record.exc_info))
        # Diagnostics groups log records by line. Keep exception context on it.
        message = ' | '.join(message.splitlines())
        write = self.target.custom_err if record.levelno >= logging.ERROR else self.target.warn
        write(record.name + ':', message)


def install_runtime_logging(role):
    root = logging.getLogger()
    if any(isinstance(h, RuntimeHandler) for h in root.handlers):
        return
    target = Logger(file='runtime_' + role)
    root.addHandler(RuntimeHandler(target))
    previous_sys = sys.excepthook
    previous_thread = threading.excepthook

    def uncaught(kind, error, tb):
        if not issubclass(kind, (KeyboardInterrupt, SystemExit)):
            target.custom_err('uncaught:', ' | '.join(
                ''.join(traceback.format_exception(kind, error, tb)).splitlines()))
        previous_sys(kind, error, tb)

    def thread_uncaught(args):
        if args.exc_type is not SystemExit:
            target.custom_err('thread', args.thread.name, ':', ' | '.join(
                ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).splitlines()))
        previous_thread(args)

    sys.excepthook = uncaught
    threading.excepthook = thread_uncaught
