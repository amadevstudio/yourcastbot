from operator import itemgetter
# import tracemalloc

from pympler import tracker


def memory_usage(engine='tracemalloc'):
    if engine == 'pympler':
        mem = tracker.SummaryTracker()
        return sorted(mem.create_summary(), reverse=True, key=itemgetter(2))[:10]
    # elif engine == 'tracemalloc':
    #     snapshot = tracemalloc.take_snapshot()
    #     return snapshot.statistics('lineno')[:10]