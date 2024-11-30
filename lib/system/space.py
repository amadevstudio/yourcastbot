import subprocess


def top(by='mem'):
    bash_command = "ps -eo pid,ppid,cmd,%mem,%cpu"
    if by is not None:
        if by == 'mem':
            bash_command += " --sort=-%mem"
    bash_command += " | head"
    process = subprocess.Popen([bash_command], stdout=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    return output


def memory_stat():
    bash_command = "free -h"
    process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    return output


def storage_stat():
    bash_command = "df -h /dev/vda2"
    process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    return output
