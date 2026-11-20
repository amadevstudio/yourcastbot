# -*- coding: utf-8 -*-
"""The pack of episodes end to end in botsim: the free week's limit offers the pack first (every plan
still under it), its button opens a Stars invoice Telegram accepts, paying it goes through the bot's
own pre-checkout and payment handlers (botsim's `pay`), the payment is credited once and said, the
next click past the week goes on the pack, and an invoice whose pack changed is refused before the money.

Needs the bot's and botsim's requirements. Run from the repo root: python tools/botsim/test_click_pack.py
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

USER = 8201


def ok(step, label):
    assert not step.errors, step.errors
    print("ok  %s" % label)
    return step


def main():
    try:
        from tools.botsim import sim
    except Exception as e:  # CI has no bot requirements
        print("skip click pack walk (%s)" % e.__class__.__name__)
        return
    sim.boot(network=False, ai='fake')
    try:
        from app.service.payment import starsPaymentModule as stars
        import config
        from app.service.record import free_limit
        from db import click_packs, usage
        from lib.telegram.general.message_master import render_messages

        user = sim.BotSim(user_id=USER, lang='en')
        ok(user.send('/start'), "a new user")
        week = ['https://cdn.example/w%d.mp3' % i for i in range(config.free_rec_per_week)]
        for link in week:
            usage.record_deliveries([USER], 'rec', link, at=time.time() - 3600)
        from db.sqliteAdapter import SQLighter
        db = SQLighter(config.db_path)
        try:
            db.subscribeUserToTariffByTg(USER, 0, 0, 0, 0)  # the welcome plan off: the free week applies
        finally:
            db.close()
        hit = free_limit.limit_hit(USER, 'https://cdn.example/next.mp3', ())
        assert hit is not None and hit.limit == 'week', hit
        step = ok(user._observe('limit', lambda: render_messages(USER, [free_limit.hit_message(hit, 'en')])),
                  "the week's limit is shown")
        message = user.last(with_buttons=True)
        texts = message.button_texts()
        assert texts[0].startswith('📦 +%d episodes' % config.click_pack_episodes), texts
        assert any('Relay' in t for t in texts[1:]) and any('Bronze' in t for t in texts[1:]), texts
        print("ok  the pack first, every plan still under it")

        step = ok(user.tap('📦'), "the pack's button")
        invoice = step.new[-1]
        assert invoice.kind == 'invoice' and not step.unanswered_tap, invoice
        payload = json.loads(invoice.media['invoice']['payload'])
        assert payload['k'] == config.click_pack_episodes and payload['b'] == config.click_pack_cents, payload
        print("ok  a Stars invoice for the pack, the tap answered")

        step = ok(user.pay(), "paid through the bot's pre-checkout and payment handlers")
        assert not step.notes, step.notes
        assert ('Left in your packs: %d' % config.click_pack_episodes) in step.new[-1].text, step.new[-1].text
        charge = sim._state['tg'].payments[-1]['telegram_payment_charge_id']
        raw = json.dumps(payload, separators=(",", ":"))
        assert not stars.process_successful_payment(USER, 'XTR', payload['s'], raw, charge), "credited once"
        print("ok  credited once and said")

        assert free_limit.limit_hit(USER, 'https://cdn.example/next.mp3', ()) is None
        assert click_packs.left(USER) == config.click_pack_episodes - 1
        print("ok  the next click past the week goes on the pack")

        ok(user.tap('📦', message), "another pack's invoice")
        saved = config.click_pack_episodes
        config.click_pack_episodes = saved + 10  # the pack changed between the invoice and the payment
        try:
            step = user.pay()
        finally:
            config.click_pack_episodes = saved
        assert any('refused the payment: Invalid payment offer' in note for note in step.notes), step.notes
        assert click_packs.left(USER) == config.click_pack_episodes - 1, "nothing credited"
        print("ok  an invoice whose pack changed is refused at the pre-checkout, before the money")
    finally:
        sim.shutdown()
    print("all click pack walk checks passed")


if __name__ == "__main__":
    main()
