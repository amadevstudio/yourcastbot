"""AI queue jobs for a frozen collection: silent transcription parts, then one combined result."""
from app.i18n.messages import get_message
from app.service.ai import paid_models, summary, transcript
from db import ai, usage, voice as batches


def charged(request):
    return 0 if ai.audio_paid(request['chat_id'], request['ref'], exclude=request['id'], done_only=True) else request['seconds']


def process(request, session, send, edit, send_file):
    from app.jobs import ai_watcher as worker
    from app.controller.builders.summaryModule import summary_message
    episode = ai.accessible_episode(request['ref'], request['chat_id'])
    if episode is None:
        raise summary.SummaryUnavailable('private recording expired')
    if request['kind'] == batches.PART:
        found, made = worker.episode_transcript(episode, session, speakers=paid_models.speakers_fit(
            request['chat_id'], request['seconds'] or episode.get('seconds')))
        worker._note_paid(request, found, made)
        usage.record_transcript(request['chat_id'], request['ref'], found.cost_usd if made else 0.0)
        return charged(request)
    rows = batches.run_items(request['id'])
    if not rows or any(row['request_status'] != 'done' for row in rows):
        # Never summarize an incomplete batch or silently omit a failed recording.
        raise summary.SummaryUnavailable('voice collection is incomplete')
    if request['kind'] == batches.FINISH:
        return 0
    sections = []
    for number, row in enumerate(rows, 1):
        member = ai.accessible_episode(row['ref'], request['chat_id'])
        found = ai.transcript(row['ref']) if member else None
        if found is None:
            raise summary.SummaryUnavailable('private recording expired')
        label = get_message('voiceNumber', request.get('ui_lang')).format(number=number)
        sections.append(label + '\n' + found['text'])
    whole = '\n\n'.join(sections)
    ai.save_transcript(request['ref'], whole, 'voice_batch', 0, sum(row['seconds'] for row in rows))
    if request['kind'] == batches.TEXT_ALL:
        if not send_file(request['chat_id'], episode, whole, 'voice_batch', request.get('ui_lang'), request.get('reply_to')):
            raise summary.SummaryUnavailable('voice transcript was not delivered')
    else:
        cached = ai.summary(request['ref'], request['lang'])
        if cached:
            text, cost = cached['text'], 0.0
        else:
            # Each recording's clock starts at zero. A combined summary cites recording numbers,
            # never a time that would misleadingly open the wrong recording.
            material = summary._MARK.sub('', whole)
            if len(material) > summary.MAX_TRANSCRIPT_CHARS:
                raise summary.SummaryUnavailable('voice collection exceeds model context')
            text, cost = summary.summarize(material, episode['title'], '', request['lang'], session=session,
                                          model=paid_models.summary_model(request['chat_id']), voice='batch')
            ai.save_summary(request['ref'], request['lang'], text, cost)
        usage.record_ai(request['chat_id'], request['ref'], cost)
        if not worker.deliver(request, summary_message(episode, text, request['ref'], request.get('reply_to'),
                                                       request.get('ui_lang')), send, edit):
            raise summary.SummaryUnavailable('voice summary was not delivered')
    return 0
