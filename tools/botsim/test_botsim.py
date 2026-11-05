# -*- coding: utf-8 -*-
"""The bot end to end in botsim (README.md): a fresh database, no network, a canned AI.

A new user's /start (welcome screen, the welcome plan), the menu and its
settings, the storefront (Stars first, change-plan kept), an OPML file whose
feeds do not answer, and a summary with a question: what the user sees,
through the real handlers, dispatcher and database. Needs the bot's
requirements (skipped where they are not installed, as in CI).

Run from the repo root: python tools/botsim/test_botsim.py
"""
import json
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import telebot  # noqa: F401
    import telethon  # noqa: F401
except ImportError as e:  # CI has no bot requirements
    print("skip botsim (%s)" % e.__class__.__name__)
    sys.exit(0)

from tools.botsim import sim  # noqa: E402

USER = 1001


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    return sqlite3.connect(sim._state['database'])


def test_start(user):
    step = user.send('/start')
    _assert(step.handlers[-1] == 'processor(start)' and len(step.new) == 2 and not step.edited
            and '14 days free' in step.new[0].text and 'Welcome!' in step.new[1].text,
            "/start: the welcome plan stays, the welcome screen comes under it (it used to be edited into it)")
    _assert(not step.errors, "no error on the way")
    plan = _db().execute("SELECT ut.tariff_id, ut.time_left FROM user_tariff_cs ut JOIN users u ON u.id = ut.uid "
                         "WHERE u.telegramId = ?", (USER,)).fetchone()
    _assert(plan is not None and plan[0] == 3 and plan[1] > 0, "a new user gets the welcome Relay")
    _assert(('new_user', ) == step.analytics[0][:1],
            "a newcomer's first /start reaches Amplitude as new_user (recorded, not sent)")

    menu = user.tap('menu')
    _assert(menu.edited and any('RSS & Import' in text for text in menu.edited[0].button_texts()),
            "the menu replaces the welcome screen")
    settings = user.tap('Settings')
    _assert(settings.edited and len(settings.edited[0].buttons) >= 2, "settings: a list of sections")


def test_text_is_a_search(user):
    """A podcast's name typed on the welcome screen or the menu is searched, not ignored."""
    user.send('/start')
    step = user.send('Some podcast')
    _assert(step.handlers[-1] == 'processor(search)' and step.new, "on the welcome screen a text is a search")
    user.send('/menu')
    step = user.send('Some podcast')
    _assert(step.handlers[-1] == 'processor(search)' and step.new, "on the menu too")
    settings = user.send('/settings')
    step = user.send('Some podcast')
    _assert('processor(search)' not in step.handlers and settings.new, "other screens keep their own input")


def test_storefront(user):
    step = user.send('/subscription')
    kinds = [json.loads(button['callback_data']).get('tp')
             for row in step.new[0].buttons for button in row if button.get('callback_data')]
    _assert(kinds[:3] == ['bs_recur', 'bs_once', 'bs_trfs'],
            "/subscription: a subscription, a one-time payment, change plan")
    step = user.tap('💳')
    once = [json.loads(button['callback_data']).get('tp')
            for row in step.edited[0].buttons for button in row if button.get('callback_data')]
    _assert(once[:2] == ['bs_stars', 'bs_cryptobot'], "one-time payment: Stars first, CryptoBot kept")


def test_cryptobot(user):
    """CryptoBot bills dollars, the coin is picked there: no rate (USDC had none and every amount failed)."""
    from app.service.payment import cryptoBotPaymentModule as crypto
    invoices = []

    class Api:
        def createInvoice(self, **params):
            invoices.append(params)
            return {'pay_url': 'https://t.me/CryptoBot?start=IV%d' % len(invoices)}
    saved = crypto.cryptoBotApi, crypto.CryptoBotApi
    crypto.cryptoBotApi = Api()
    crypto.CryptoBotApi = lambda *args: Api()
    try:
        user.send('/subscription')
        user.tap('💳')
        page = user.tap('Crypto Bot')
        data = [json.loads(button['callback_data']) for row in page.edited[0].buttons for button in row
                if button.get('callback_data')]
        plans = [d for d in data if d.get('tp') == 'bs_crbot_input' and d.get('pl')]
        _assert(len(plans) >= 2 and not any('asset' in d for d in data) and 'USDC' in page.edited[0].text,
                "CryptoBot: the plans at once, no coin to pick first (CryptoBot asks for it)")
        _assert(any(text == 'Another amount' for text in page.edited[0].button_texts())
                and data[-1].get('tp') == 'bck', "another amount, and Back")
        relay = next(d for d in plans if d['pl'] == 3)
        step = user.tap_data(json.dumps(relay))
        invoice = invoices[-1]
        _assert(invoice['currency_type'] == 'fiat' and invoice['fiat'] == 'USD' and invoice['amount'] == '5.00'
                and json.loads(invoice['payload']) == {'tgid': USER, 'amount': 500, 'v': 3, 'net': 'testnet'},
                "a plan's invoice: dollars, any coin, the plan in the payload")
        sent = (step.edited or step.new)[0]
        _assert('$5' in sent.text and sent.buttons[0][0].get('url', '').endswith('IV1') and not step.errors,
                "the invoice comes as a Pay button")
        user.tap_data(json.dumps({'tp': 'bs_crbot_input'}))
        typed = user.send('3')
        _assert(invoices[-1]['amount'] == '3.00' and 'v' not in json.loads(invoices[-1]['payload'])
                and not typed.errors, "a typed amount is a top-up, no plan")
    finally:
        crypto.cryptoBotApi, crypto.CryptoBotApi = saved


def test_opml_offline(user):
    opml = (b'<opml version="2.0"><body>'
            b'<outline type="rss" text="Offline Show" xmlUrl="https://feeds.example.com/offline.xml"/>'
            b'</body></opml>')
    step = user.send_file('subs.opml', opml, 'text/x-opml')
    _assert(step.handlers == ['opml_file (stop)'], "an OPML file is read before the routes, and only there")
    _assert(any('Offline Show' in text for text in step.texts), "a feed that does not answer is named")
    _assert(any(text.endswith('1 of 1…') for text in step.texts),
            "the status line is edited to the full count (message_master's result is read right)")
    _assert(not step.errors, "and nothing breaks")
    other = user.send_file('photo.jpg', b'\xff\xd8\xff', 'image/jpeg')
    _assert('opml_file (stop)' not in other.handlers, "other documents are not taken for OPML")


def test_summary_and_question(user):
    from db import ai
    ai.remember_episode('simref0000000001', 'https://cdn.example.com/ep.mp3', None, 'Episode One', 'Sim Show',
                        1800)
    step = user.tap_data(json.dumps({'tp': 'sum', 'r': 'simref0000000001'}))
    _assert(len(step.new) == 1 and step.new[0].text == '📝 Summary: queued…',
            "Summary: a status line at once (it takes minutes)")
    status = step.new[0]
    again = user.tap_data(json.dumps({'tp': 'sum', 'r': 'simref0000000001'}))
    _assert(not again.new and not user.api.messages[(USER, status.message_id)].deleted,
            "a second tap adds no second status line")
    made = user.run_ai()
    _assert(not made.new and len(made.edited) == 1 and made.edited[0].message_id == status.message_id
            and sim.FAKE_SUMMARY.splitlines()[0] in made.edited[0].text,
            "the jobs process turns the status line into the summary")
    _assert(any(button.get('text') for button in made.edited[0].buttons[0]), "with its Ask button")
    transcript = user.tap('Transcript', message=made.edited[0])
    _assert(transcript.handlers == ['action_processor(recs, trn)'] and len(transcript.new) == 1
            and transcript.new[0].kind == 'document' and 'Episode One' in transcript.new[0].text,
            "Transcript: the text the summary was made from, as a file")
    ask = user.tap((0, 0), message=made.edited[0])
    _assert(ask.handlers == ['processor(ask)'] and ask.new, "Ask opens the question screen")
    answer = user.send('Who is the guest?')
    _assert(answer.handlers[-1] == 'processor(ask)' and any(sim.FAKE_ANSWER in text for text in answer.texts),
            "a text there is a question, answered")
    thinking = [method for method, params, _ in user.api.log if method == 'editMessageText'
                and sim.FAKE_ANSWER in str(params.get('text'))]
    _assert(len(answer.new) == 1 and thinking, "the answer is the 'Thinking…' line, edited")
    left = _db().execute("SELECT COUNT(*) FROM usage_events WHERE user_id = ? AND kind = 'ask'", (USER,)).fetchone()
    _assert(left[0] == 1, "and counted in the usage ledger")
    done = user.tap('Done')
    _assert(done.handlers == ['action_processor(ask, askDone)'] and done.new, "Done: the menu as a new message")
    again = user.send('Who is the guest?')
    _assert('processor(ask)' not in again.handlers, "after Done a text is no question")


def test_transcript_alone(user):
    """Transcript under the audio, no summary first: a status line, then only the transcript as a file
    (no summary made); Summary after it is made from that transcript."""
    from db import ai
    ai.remember_episode('simref0000000005', 'https://cdn.example.com/ep5.mp3', None, 'Episode Five', 'Sim Show',
                        1800)
    from tools.botsim.fake_telegram import Sent
    audio = Sent(user.api.next_id(), USER, 'audio', 'Episode Five')  # the audio the buttons are on
    step = user.tap_data(json.dumps({'tp': 'trn', 'r': 'simref0000000005'}), message=audio)
    _assert(step.handlers == ['action_processor(recs, trn)'] and len(step.new) == 1
            and step.new[0].text == '📥 Transcript: queued…' and step.new[0].reply_to == audio.message_id,
            "Transcript: a status line at once, under the audio")
    status = step.new[0]
    made = user.run_ai()
    files = [m for m in made.new if m.kind == 'document']
    _assert(len(files) == 1 and 'Episode Five' in files[0].text and not made.errors,
            "the jobs process sends the transcript as a file")
    _assert(user.api.messages[(USER, status.message_id)].deleted and not any(
        sim.FAKE_SUMMARY.splitlines()[0] in m.text for m in made.new + made.edited),
            "its status line goes, and no summary is made")
    _assert(ai.transcript('simref0000000005')['text'] == sim.FAKE_TRANSCRIPT, "the transcript is cached")
    again = user.tap_data(json.dumps({'tp': 'trn', 'r': 'simref0000000005'}), message=audio)
    _assert(len(again.new) == 1 and again.new[0].kind == 'document', "a second tap: the file at once")
    summary = user.tap_data(json.dumps({'tp': 'sum', 'r': 'simref0000000005'}), message=audio)
    made = user.run_ai()
    _assert(summary.new and any(sim.FAKE_SUMMARY.splitlines()[0] in m.text for m in made.edited),
            "Summary after it: made from that transcript")


def test_done_opens_podcast(user):
    """Done after questions about an episode of a known podcast: that podcast's page, Back to the menu."""
    from db import ai
    db = _db()
    channel = db.execute("INSERT INTO channels (name, rss_link) VALUES ('Sim Show', 'https://feed.example/rss')"
                         ).lastrowid
    db.commit()
    db.close()
    ai.remember_episode('simref0000000004', 'https://cdn.example.com/ep4.mp3', channel, 'Episode Four', 'Sim Show',
                        1800)
    step = user.tap_data(json.dumps({'tp': 'sum', 'r': 'simref0000000004'}))
    made = user.run_ai()
    user.tap((0, 0), message=made.edited[0])
    user.send('Who is the guest?')
    done = user.tap('Done')
    _assert(done.handlers == ['action_processor(ask, askDone)'] and done.new and not done.errors,
            "Done: the podcast page as a new message")
    from app.repository.storage import storage
    _assert(storage.get_user_states(USER)[-1] == 'podcast', "the chat is on the podcast page")
    back = user.tap('Back', message=done.new[-1])
    _assert(back.handlers == ['go_back'] and not back.errors and storage.get_user_states(USER)[-1] == 'menu',
            "Back on it: the menu")
    _assert(step.new, "the summary was asked for")


def test_show_question(user):
    """Ask about the podcast: the page's button, a question, a text answer with a download button
    per episode it names and Back (every screen has one), Back to the page."""
    import xml.etree.ElementTree as ET
    from app.controller.builders import showAskModule
    from app.repository.storage import storage
    from app.service.ai import show_ask
    feed = ET.fromstring('<rss><channel><item><title>New one</title><guid>g2</guid>'
                         '<description>About guests.</description><enclosure url="https://cdn.example.com/2.mp3"/>'
                         '</item><item><title>Old one</title><guid>g1</guid>'
                         '<enclosure url="https://cdn.example.com/1.mp3"/></item></channel></rss>').find('channel')
    saved = showAskModule._context
    showAskModule._context = lambda podcast: show_ask.build(show_ask.feed_episodes(feed), [])
    try:
        user.send('/menu')
        storage.set_user_state_data(USER, 'podcast', {
            'id': None, 'service_id': '42', 'service_name': 'itunes', 'title': 'Sim Show', 'descr': 'About.',
            'imgUrl': None, 'recCount': 2, 'lastDate': '', 'subscribed': False, 'genres': []})
        storage.add_user_state(USER, 'podcast')
        opened = user.tap_data(json.dumps({'tp': show_ask.ACTION}))
        screen = (opened.new + opened.edited)[-1]
        _assert(opened.handlers == ['processor(showAsk)'] and 'Sim Show' in screen.text
                and screen.buttons[-1][0]['text'] == 'Back', "the question screen names the show and has Back")
        answer = user.send('What does the host ask guests?')
        reply = (answer.new + answer.edited)[-1]
        _assert(answer.handlers[-1] == 'processor(showAsk)' and '[1]' in reply.text and '[E1]' not in reply.text,
                "a text there is a question about the show, its labels as numbers")
        _assert([b['text'][:8] for row in reply.buttons for b in row] == ['⬇️ 1. Ne', '⬇️ 2. Ol', 'Back']
                and json.loads(reply.buttons[0][0]['callback_data'])['tp'] == 'rec',
                "a download button per episode it names, then Back")
        back = user.tap('Back', message=reply)
        _assert(back.handlers == ['go_back'] and any('Sim Show' in text for text in back.texts),
                "Back opens the podcast page")
        _assert(not (opened.errors or answer.errors or back.errors), "and nothing breaks")
    finally:
        showAskModule._context = saved


def test_show_notes(user):
    """Show notes under a brief episode: the feed's text as a quote replying to the audio."""
    from db import ai
    ai.remember_episode('simref0000000002', 'https://cdn.example.com/ep2.mp3', None, 'Episode Two', 'Sim Show',
                        600, descr='<p>Guests &amp; links: <a href="https://example.com">site</a></p>')
    step = user.tap_data(json.dumps({'tp': 'desc', 'r': 'simref0000000002'}))
    _assert(step.handlers == ['action_processor(recs, desc)'] and len(step.new) == 1
            and step.new[0].text.startswith('<blockquote expandable>') and 'Guests &amp; links' in step.new[0].text,
            "Show notes: the description as a collapsible quote")
    _assert(step.new[0].reply_to is not None, "a reply to the message the button is on (the audio)")
    ai.remember_episode('simref0000000003', 'https://cdn.example.com/ep3.mp3', None, 'Episode Three', 'Sim Show', 600)
    empty = user.tap_data(json.dumps({'tp': 'desc', 'r': 'simref0000000003'}))
    _assert(not empty.new and empty.toasts and empty.toasts[0][0], "no text: a toast, no empty message")


def _plan_row(user_id):
    return _db().execute("SELECT ut.tariff_id, ut.balance, ut.time_left FROM user_tariff_cs ut "
                         "JOIN users u ON u.id = ut.uid WHERE u.telegramId = ?", (user_id,)).fetchone()


def _callbacks(step):
    return [json.loads(button['callback_data']) for message in step.new + step.edited
            for row in message.buttons for button in row if button.get('callback_data')]


def test_downgrade_refund():
    """A cheaper plan or off is asked first (a trial's tap on Bronze was a switch at once and cost
    $1.86 to undo, with Back the only button); the move gives back half of the days left, only
    when the chat ever paid: the welcome trial's days must not become balance."""
    db = _db()
    bronze = db.execute("SELECT id FROM tariffs WHERE level = 1").fetchone()[0]
    relay = db.execute("SELECT id FROM tariffs WHERE level = 3").fetchone()[0]
    db.close()
    trial = sim.BotSim(2001, 'en')
    trial.send('/start')
    before = _plan_row(2001)
    ask = trial.tap_data(json.dumps({'tp': 'bs_trf_v', 'v': bronze}))
    _assert(_plan_row(2001) == before and 'Change plan: ' in ask.texts[0] and 'Going back to' in ask.texts[0]
            and 'comes back' not in ask.texts[0],
            "a cheaper plan is asked first: nothing changes yet, going back's price is said, no refund to a trial")
    _assert({'tp': 'bs_trf_ok', 'v': bronze, 'c': relay} in _callbacks(ask), "the yes names the plan it was asked from")
    trial.tap_data(json.dumps({'tp': 'bs_trf_ok', 'v': bronze, 'c': bronze}))
    _assert(_plan_row(2001) == before, "a yes asked from another plan asks again, it does not switch")
    trial.tap('Yes, change plan')
    after = _plan_row(2001)
    _assert(before[1] == 0 and after[0] == bronze and after[1] == 0,
            "the welcome trial moved to Bronze: the plan changes, no money appears")
    short = trial.tap_data(json.dumps({'tp': 'bs_trf_v', 'v': relay}))
    _assert(_plan_row(2001)[0] == bronze and {'tp': 'bs_stars'} in _callbacks(short),
            "back to Relay without the money: the Stars page is a tap away, not a dead end")

    off = sim.BotSim(2003, 'en')
    off.send('/start')
    ask = off.tap_data(json.dumps({'tp': 'bs_trf_v', 'v': 0}))
    _assert(_plan_row(2003)[0] == relay and 'off?' in ask.texts[0], "turning the plan off is asked first too")

    payer = sim.BotSim(2002, 'en')
    payer.send('/start')
    db = _db()
    db.execute("INSERT INTO payment_history (user_id, service_type, invoice_id, status, amount, datetime) "
               "SELECT id, 'stars', 'sim-1', 'paid', 500, datetime('now') FROM users WHERE telegramId = 2002")
    db.commit()
    db.close()
    ask = payer.tap_data(json.dumps({'tp': 'bs_trf_v', 'v': bronze}))
    _assert('comes back to your balance' in ask.texts[0], "a chat that paid is told what comes back")
    payer.tap('Yes, change plan')
    _assert(_plan_row(2002)[1] > 0, "a chat that paid still gets half of the days left back")


def main():
    sim.boot(network=False, ai='fake')
    try:
        user = sim.BotSim(USER, 'en')
        test_start(user)
        test_text_is_a_search(user)
        test_storefront(user)
        test_cryptobot(user)
        test_opml_offline(user)
        test_summary_and_question(user)
        test_transcript_alone(user)
        test_done_opens_podcast(user)
        test_show_question(user)
        test_show_notes(user)
        test_downgrade_refund()
    finally:
        sim.shutdown()
    print("all botsim checks passed")


if __name__ == '__main__':
    main()
