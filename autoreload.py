#!/usr/bin/env python
import os
import signal
import sys
import subprocess
import time


def file_filter(name):
    return (
            not name.startswith(".")
            and not name.endswith(".swp")
            and not name.endswith("logs")
            and not name.endswith("journal")
            and not name.endswith(".db")
            and not name.endswith(".session")
    )


def folder_filter(name):
    return (
        not name == '.git'
        and not name == '.idea'
        and not name == '__pycache__'
        and not name == '.mypy_cache'

        and not name == 'records'
    )


def print_stdout(process):
    stdout = process.stdout
    if stdout is not None:
        print(stdout)


def file_times_and_names(path, initial=False):
    for root, dirs, files in os.walk(path):

        dirs[:] = [d for d in dirs if folder_filter(d)]
        if not folder_filter(root):
            continue

        for file in filter(file_filter, files):
            try:
                yield [os.stat(os.path.join(root, file)).st_mtime, f"{root}/{file}"]
            except Exception as e:
                if initial:
                    print(f"Can't watch for os.path.join(root, file), {e}")


def find_max_time(args):
    max_value = next(args)
    for arg in args:
        if arg[0] > max_value[0]:
            max_value = arg
    return max_value


# We concatenate all the arguments together, and treat that as the command to run
command = " ".join(sys.argv[1:])
print(f"AR: Launching `{command}`", flush=True)

# The path to watch
watch_path = "."

# How often we check the filesystem for changes (in seconds)
wait = 1

# The process to autoreload
watch_process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid)

# The current maximum file modified time under the watched directory
last_value = find_max_time(file_times_and_names(watch_path, initial=True))


while True:
    max_value = find_max_time(file_times_and_names(watch_path))
    if max_value[0] > last_value[0]:
        last_value = max_value
        print(f"AR: Restarting process, file {last_value[1]} changed at {last_value[0]}", flush=True)
        time.sleep(1)
        os.killpg(os.getpgid(watch_process.pid), signal.SIGTERM)

        watch_process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid)
    time.sleep(wait)
