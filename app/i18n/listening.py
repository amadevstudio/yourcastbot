"""Copy for the feed pause notice and the episode digest (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'feedPausedNotice': (
        'Источник временно недоступен. Мы автоматически проверяем его и повторяем попытку ежедневно. Настройка уведомлений сохранена.',
        'The feed is temporarily unavailable. We check it automatically and retry daily. Your notification preference is saved.',
        'O feed está temporariamente indisponível. Nós o verificamos automaticamente e tentamos diariamente. Sua preferência de notificações foi mantida.',
        'El feed no está disponible temporalmente. Lo comprobamos automáticamente y lo intentamos a diario. Tu preferencia de notificaciones se conserva.',
        'Der Feed ist vorübergehend nicht verfügbar. Wir prüfen ihn automatisch und versuchen es täglich erneut. Deine Benachrichtigungseinstellung bleibt erhalten.',
        'הפיד אינו זמין זמנית. אנחנו בודקים אותו אוטומטית ומנסים שוב מדי יום. העדפת ההתראות שלך נשמרה.'),
    'playLater': ('Слушать', 'Listen', 'Ouvir', 'Escuchar', 'Anhören', 'האזנה'),
    'digestRelayLine': (
        '📨 С Relay новые выпуски ваших подкастов приходят сюда файлом: $5 в месяц, оплата звёздами Telegram.',
        '📨 With Relay, new episodes of your podcasts arrive here as files: $5/mo, paid with Stars.',
        '📨 Com o Relay, os episódios novos dos seus podcasts chegam aqui como arquivo: US$ 5 por mês, pago com Stars.',
        '📨 Con Relay, los episodios nuevos de tus pódcasts llegan aquí como archivo: $5 al mes, con Stars.',
        '📨 Mit Relay kommen neue Folgen deiner Podcasts hier als Datei an: 5 $ im Monat, bezahlt mit Stars.',
        '📨 עם Relay, פרקים חדשים של הפודקאסטים שלך מגיעים לכאן כקובץ: \u200e$5 לחודש, בתשלום ב-Stars.'),
    'digestEpisodes': ('Новые выпуски в ваших подписках', 'New episodes in your subscriptions', 'Novos episódios nas suas assinaturas', 'Nuevos episodios en tus suscripciones', 'Neue Folgen in deinen Abos', 'פרקים חדשים במינויים שלך'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
