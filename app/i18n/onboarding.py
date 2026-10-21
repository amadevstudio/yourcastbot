"""Copy for the welcome screen's podcast picker (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'welcomePickHint': (
        'Отметьте подкасты и подпишитесь на все сразу:',
        'Tick the podcasts you like and subscribe to all of them at once:',
        'Marque os podcasts que você curte e assine todos de uma vez:',
        'Marca los pódcasts que te gusten y suscríbete a todos a la vez:',
        'Markiere die Podcasts, die dir gefallen, und abonniere alle auf einmal:',
        'סמנו את הפודקאסטים שאתם אוהבים והירשמו לכולם בבת אחת:'),
    'welcomeSubscribePicked': (
        '✅ Подписаться на отмеченные ({count})',
        '✅ Subscribe to the ticked ones ({count})',
        '✅ Assinar os marcados ({count})',
        '✅ Suscribirme a los marcados ({count})',
        '✅ Markierte abonnieren ({count})',
        '✅ להירשם למסומנים ({count})'),
    'welcomePickNothing': (
        'Сначала отметьте хотя бы один подкаст',
        'Tick at least one podcast first',
        'Marque pelo menos um podcast primeiro',
        'Marca al menos un pódcast primero',
        'Markiere zuerst mindestens einen Podcast',
        'סמנו קודם לפחות פודקאסט אחד'),
    'welcomeSubscribing': (
        'Подписываю…',
        'Subscribing…',
        'Assinando…',
        'Suscribiendo…',
        'Abonniere…',
        'נרשם…'),
    'welcomeSubscribed': (
        '✅ Вы подписаны: {names}. Новые выпуски придут сюда.',
        '✅ Subscribed: {names}. New episodes will arrive here.',
        '✅ Assinado: {names}. Os episódios novos vão chegar aqui.',
        '✅ Suscrito: {names}. Los episodios nuevos llegarán aquí.',
        '✅ Abonniert: {names}. Neue Folgen kommen hier an.',
        '✅ נרשמתם: {names}. פרקים חדשים יגיעו לכאן.'),
    'welcomeSubscribeFailed': (
        'Не удалось подписаться: {names}. Попробуйте найти их через поиск.',
        'Could not subscribe to: {names}. Try finding them with search.',
        'Não foi possível assinar: {names}. Tente encontrá-los pela busca.',
        'No se pudo suscribir a: {names}. Prueba a buscarlos.',
        'Abonnieren fehlgeschlagen: {names}. Versuche, sie über die Suche zu finden.',
        'לא הצלחנו להירשם ל: {names}. נסו למצוא אותם בחיפוש.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
