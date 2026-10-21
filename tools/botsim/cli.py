# -*- coding: utf-8 -*-
"""botsim from the command line: a scenario, one action per line (README.md).

    python tools/botsim/cli.py [--db COPY.db] [--offline] [--ai fake|real|off] [--user 1001] [--lang ru]
                               [-c ACTION ...] [SCENARIO_FILE | -]

Actions:
    send TEXT            a message (/start, a search, a question)
    tap TEXT             a button of the bot's latest message that has it (exact text, else a part)
    tap ROW,COL          a button of the bot's latest message with buttons, by position
    data JSON            a tap with this callback data on the latest message
    file PATH [MIME]     a document (an OPML file)
    deliver              the episodes the taps queued, sent as the send workers would
    ai                   the summaries queued (a canned one unless --ai real)
    screen [N]           the last N messages of the chat
    user ID [LANG]       act as another user from now on
    # ...                a comment
"""
import argparse
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('scenario', nargs='?', help='a file of actions, - for stdin')
    parser.add_argument('-c', dest='actions', action='append', default=[], help='an action (repeatable)')
    parser.add_argument('--db', help='a database to copy and use (the copy is deleted after); default: a fresh one')
    parser.add_argument('--in-place', action='store_true', help='use --db itself, not a copy (the bot writes to it)')
    parser.add_argument('--offline', action='store_true', help='no HTTP: catalog and feeds fail')
    parser.add_argument('--ai', default='fake', choices=('fake', 'real', 'off'))
    parser.add_argument('--user', type=int, default=1001)
    parser.add_argument('--lang', default='en')
    parser.add_argument('--verbose', action='store_true', help='print every log line as it happens')
    args = parser.parse_args(argv)

    lines = list(args.actions)
    if args.scenario == '-':
        lines += sys.stdin.read().splitlines()
    elif args.scenario:
        lines += open(args.scenario, encoding='utf-8').read().splitlines()

    copy_dir, database = None, args.db
    if args.db and not args.in_place:
        copy_dir = tempfile.mkdtemp(prefix='botsim_db_')
        database = os.path.join(copy_dir, 'sim.db')
        shutil.copyfile(args.db, database)

    from tools.botsim import sim
    try:
        sim.boot(database, network=not args.offline, ai=args.ai, quiet=not args.verbose)
        user = sim.BotSim(args.user, args.lang)
        failed = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                step = run(user, line)
            except Exception as e:
                print('!!! %s: %s: %s' % (line, type(e).__name__, e))
                failed = True
                continue
            if isinstance(step, sim.BotSim):
                user = step
                print('>>> now user %s (%s)' % (user.user_id, user.lang))
            elif isinstance(step, str):
                print(step)
            else:
                print(step)
                failed = failed or bool(step.errors)
        return 1 if failed else 0
    finally:
        sim.shutdown()
        if copy_dir:
            shutil.rmtree(copy_dir, ignore_errors=True)


def run(user, line):
    from tools.botsim import sim
    verb, _, rest = line.partition(' ')
    rest = rest.strip()
    if verb == 'send':
        return user.send(rest)
    if verb == 'tap':
        if ',' in rest and all(part.strip().isdigit() for part in rest.split(',', 1)):
            row, column = (int(part) for part in rest.split(',', 1))
            return user.tap((row, column))
        return user.tap(rest)
    if verb == 'data':
        return user.tap_data(rest)
    if verb == 'file':
        path, _, mime = rest.partition(' ')
        return user.send_file(os.path.basename(path), open(path, 'rb').read(), mime.strip() or 'application/xml')
    if verb == 'deliver':
        return user.deliver()
    if verb == 'ai':
        return user.run_ai()
    if verb == 'screen':
        return user.screen(int(rest or 3))
    if verb == 'user':
        user_id, _, lang = rest.partition(' ')
        return sim.BotSim(int(user_id), lang.strip() or user.lang)
    raise ValueError('unknown action %r (see --help)' % verb)


if __name__ == '__main__':
    sys.exit(main())
