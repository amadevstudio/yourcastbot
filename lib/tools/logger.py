import sys
import os
import datetime
import queue
import re
import threading

import config


# A bot token, "<bot id>:<secret>". telebot puts it in every request URL, and a
# requests error quotes the URL: a WARN on 2026-10-26 wrote the whole token to
# the sender log, which /api/diag/errors serves.
BOT_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")


def redact(text: str) -> str:
    return BOT_TOKEN.sub("<bot token>", text)


# class Logger(metaclass=Singleton):
class Logger:
    LEVELS = {
        "log": "LOG",
        "warn": "WARN",
        "err": "ERR",
        "debug": "DEBUG"
    }

    def __init__(self, base_dir=None, file="out"):
        if base_dir is None:
            self.__bot_path = config.work_dir
        else:
            self.__bot_path = base_dir

        self.file = file
        self.__set_dated_filename()

        self.__write_queue = queue.Queue()

        write_thread = threading.Thread(target=self.__writer)
        write_thread.daemon = True
        write_thread.start()

    def __writer(self):
        while True:
            result = self.__write_queue.get()
            result = result.encode('utf-8')
            with open(f"{self.__bot_path}/log/{self.dated_file}.log", "ab") as f:  # add in binary mode
                f.write(result)

    def __set_dated_filename(self, now=None):
        if now is None:
            now = datetime.datetime.now()
        dated_filename = self.file + "_" + now.strftime("%d_%m_%Y")
        self.dated_file = dated_filename

    # [12:49:41 26.06.1998] LEVEL arg1 args2
    def __out_log(self, *args, level="log"):
        result = ""

        now = datetime.datetime.now()

        human_now = "[" + now.strftime("%H:%M:%S %d.%m.%Y") + "]"
        result += human_now + " "

        result += (self.LEVELS[level] if level in self.LEVELS else "EMLVL") + " "

        if len(args) > 0:
            for arg in args:
                result += str(arg) + " "
            result = result[0:-1]

        result = redact(result) + "\n"

        if config.server and self.file is not None:
            self.__set_dated_filename(now)
            self.__write_queue.put(result)
        else:
            print(result, flush=True)

    def log(self, *args):
        self.__out_log(*args, level="log")

    def warn(self, *args):
        self.__out_log(*args, level="warn")

    def debug(self, *args):
        if not config.server:
            self.__out_log(*args, level="debug")

    # works only in error
    # args (for self.__out_log) = [arg1, arg2, | Details:, exc_type exc_obj caught.py:N > raised.py:M]
    def err(self, *args, dont_raise: bool = True):
        if dont_raise or config.server:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            details = str(exc_type) + " " + str(exc_obj)
            if exc_tb is not None:
                details += " " + _tb_place(exc_tb)
                # Where it was raised, not only where it was caught: a handler
                # that logs a whole route's failure otherwise names only itself
                inner_tb = exc_tb
                while inner_tb.tb_next is not None:
                    inner_tb = inner_tb.tb_next
                if inner_tb is not exc_tb:
                    details += " > " + _tb_place(inner_tb)

            self.__out_log(
                *args, "| Details:", details, "\n", level="err")
        else:
            raise args[0]

    def custom_err(self, *args):
        self.__out_log(*args, level="err")



def _tb_place(tb) -> str:
    return os.path.split(tb.tb_frame.f_code.co_filename)[1] + ":" + str(tb.tb_lineno)


logger = Logger()
