# -*- coding: utf-8 -*-
"""The pack of episodes end to end in botsim: the free week's limit offers the pack first (every plan
still under it), its button opens a Stars invoice Telegram accepts, the payment is credited once and
said, and the next click past the week goes on the pack.

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
        stars._stars_rate_x1000 = stars.STARS_DEFAULT_WITHDRAW_RATE_X1000  # Telegram's rate is not asked here
        stars._stars_rate_updated_at = time.time()
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

        raw = json.dumps(payload, separators=(",", ":"))
        assert stars.validate_precheckout_payload(raw, USER, 'XTR', payload['s'])[0]
        step = ok(user._observe('pay', lambda: stars.process_successful_payment(USER, 'XTR', payload['s'], raw, 'sim-pack-1')),
                  "the payment")
        assert ('Left in your packs: %d' % config.click_pack_episodes) in step.new[-1].text, step.new[-1].text
        assert not stars.process_successful_payment(USER, 'XTR', payload['s'], raw, 'sim-pack-1'), "credited once"
        print("ok  credited once and said")

        assert free_limit.limit_hit(USER, 'https://cdn.example/next.mp3', ()) is None
        assert click_packs.left(USER) == config.click_pack_episodes - 1
        print("ok  the next click past the week goes on the pack")
    finally:
        sim.shutdown()
    print("all click pack walk checks passed")


if __name__ == "__main__":
    main()
