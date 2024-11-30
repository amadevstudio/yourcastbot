import datetime
import subprocess
from config import work_dir


def restart():
    records_dir = work_dir
    bash_command = "supervisorctl restart yourcast"
    print("!!!!!RESTARTED!!!!!\n\n\n", datetime.datetime.now(), flush=True)
    process = subprocess.Popen(
        bash_command.split(), stdout=subprocess.PIPE, cwd=records_dir)
    output, error = process.communicate()
    print(output, error, flush=True)


def print_top_memory():
    bash_command = "top -b -o +%MEM"
    head_bash_command = "head -20"
    process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)
    result_process = subprocess.Popen(
        head_bash_command.split(), stdin=process.stdout, stdout=subprocess.PIPE)
    # process.stdout.close()
    output, error = result_process.communicate()
    print('TOP MEMORY USAGE', flush=True)
    print(output.decode(), "\nError:", error, flush=True)
