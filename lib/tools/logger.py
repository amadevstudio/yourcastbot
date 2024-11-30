import sys
import os
import datetime
import queue
import threading

import config


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

        result += "\n"

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
    # args (for self.__out_log) = [arg1, arg2, | Details:, exc_type, exc_obj, fename, :, exc_tb.tb_lineno]
    def err(self, *args, dont_raise: bool = True):
        if dont_raise or config.server:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            details = str(exc_type) + " " + str(exc_obj)
            if exc_tb is not None:
                fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                details += " " + str(fename) + ":" + str(exc_tb.tb_lineno)

            self.__out_log(
                *args, "| Details:", details, "\n", level="err")
        else:
            raise args[0]

    def custom_err(self, *args):
        self.__out_log(*args, level="err")


logger = Logger()
