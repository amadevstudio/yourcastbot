"""Copy for the brief episode format and its show-notes button (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'episodeFormatBrief': (
        'Кратко: заголовок и кнопки',
        'Brief: title and buttons',
        'Resumido: título e botões',
        'Breve: título y botones',
        'Kurz: Titel und Buttons',
        'קצר: כותרת וכפתורים'),
    'descriptionButton': (
        '📄 Встроенный текст',
        '📄 Show notes',
        '📄 Notas do episódio',
        '📄 Notas del episodio',
        '📄 Shownotes',
        '📄 תיאור הפרק'),
    'descriptionMissing': (
        'У этого выпуска нет текста',
        'This episode has no text',
        'Este episódio não tem texto',
        'Este episodio no tiene texto',
        'Diese Folge hat keinen Text',
        'לפרק הזה אין טקסט'),
    # replaces the four-format help (messages.py): the brief format comes first, as the default
    'episodeFormatHelp': (
        'Как приходит описание эпизода:\n\n'
        '• <b>Кратко</b> (по умолчанию): название и дата, под ними кнопки "Пересказ" и "Встроенный текст"\n'
        '• <b>Одно сообщение</b>: плеер и всё описание, без обрезки\n'
        '• <b>Отдельное</b>: аудио, а описание следом в сворачиваемой цитате\n'
        '• <b>Подпись</b>: как раньше, описание обрезается под лимит подписи\n'
        '• <b>Только заголовок</b>: название, дата и ссылка',
        'How the episode text arrives:\n\n'
        '• <b>Brief</b> (default): the title and date, with "Summary" and "Show notes" buttons under them\n'
        '• <b>One message</b>: the player and the whole description, without cutting\n'
        '• <b>Separate</b>: the audio, then the description in a collapsible quote\n'
        '• <b>Caption</b>: the old way, the description is cut to fit a caption\n'
        '• <b>Title only</b>: the show, title, date and link',
        'Como o texto do episódio chega:\n\n'
        '• <b>Resumido</b> (padrão): título e data, com os botões "Resumo" e "Notas do episódio"\n'
        '• <b>Uma mensagem</b>: o player e a descrição inteira, sem cortes\n'
        '• <b>Separado</b>: o áudio e depois a descrição em uma citação recolhível\n'
        '• <b>Legenda</b>: o jeito antigo, a descrição é cortada para caber\n'
        '• <b>Só o título</b>: programa, título, data e link',
        'Cómo llega el texto del episodio:\n\n'
        '• <b>Breve</b> (por defecto): título y fecha, con los botones "Resumen" y "Notas del episodio"\n'
        '• <b>Un mensaje</b>: el reproductor y toda la descripción, sin recortes\n'
        '• <b>Aparte</b>: el audio y luego la descripción en una cita plegable\n'
        '• <b>Pie</b>: la forma antigua, la descripción se recorta para caber\n'
        '• <b>Solo el título</b>: programa, título, fecha y enlace',
        'Wie der Text der Folge ankommt:\n\n'
        '• <b>Kurz</b> (Standard): Titel und Datum, darunter die Buttons "Zusammenfassung" und "Shownotes"\n'
        '• <b>Eine Nachricht</b>: Player und ganze Beschreibung, ungekürzt\n'
        '• <b>Getrennt</b>: das Audio, danach die Beschreibung in einem einklappbaren Zitat\n'
        '• <b>Beschriftung</b>: die alte Art, die Beschreibung wird gekürzt\n'
        '• <b>Nur Titel</b>: Sendung, Titel, Datum und Link',
        'איך מגיע טקסט הפרק:\n\n'
        '• <b>קצר</b> (ברירת מחדל): כותרת ותאריך, ומתחתם הכפתורים "סיכום" ו"תיאור הפרק"\n'
        '• <b>הודעה אחת</b>: הנגן וכל התיאור, בלי קיצוץ\n'
        '• <b>נפרד</b>: האודיו ואחריו התיאור בציטוט מתקפל\n'
        '• <b>כיתוב</b>: הדרך הישנה, התיאור נחתך\n'
        '• <b>רק כותרת</b>: התוכנית, הכותרת, התאריך והקישור'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
