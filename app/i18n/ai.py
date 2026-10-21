"""Copy for AI episode summaries (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'summaryButton': (
        '📝 Пересказ',
        '📝 Summary',
        '📝 Resumo',
        '📝 Resumen',
        '📝 Zusammenfassung',
        '📝 סיכום'),
    'summaryPreparing': (
        'Готовлю пересказ: 1–2 минуты',
        'Preparing the summary: 1–2 minutes',
        'Preparando o resumo: 1–2 minutos',
        'Preparando el resumen: 1–2 minutos',
        'Die Zusammenfassung kommt in 1–2 Minuten',
        'מכין את הסיכום: 1–2 דקות'),
    'summaryUnavailable': (
        'Пересказы сейчас недоступны',
        'Summaries are not available right now',
        'Os resumos não estão disponíveis agora',
        'Los resúmenes no están disponibles ahora',
        'Zusammenfassungen sind gerade nicht verfügbar',
        'סיכומים לא זמינים כרגע'),
    'summaryFailed': (
        'Не получилось сделать пересказ этого выпуска.',
        'Could not make a summary of this episode.',
        'Não foi possível resumir este episódio.',
        'No se pudo resumir este episodio.',
        'Diese Folge ließ sich nicht zusammenfassen.',
        'לא הצלחנו לסכם את הפרק הזה.'),
    'summaryQuotaUsed': (
        'Новые ИИ-пересказы в этом месяце: {used} из {limit}. Тариф выше даёт больше:',
        'New AI summaries this month: {used} of {limit}. A bigger plan gives more:',
        'Novos resumos com IA este mês: {used} de {limit}. Um plano maior dá mais:',
        'Resúmenes nuevos con IA este mes: {used} de {limit}. Un plan mayor da más:',
        'Neue KI-Zusammenfassungen diesen Monat: {used} von {limit}. Ein größerer Tarif gibt mehr:',
        'סיכומי AI חדשים החודש: {used} מתוך {limit}. מסלול גדול יותר נותן יותר:'),
    'summaryForPlans': (
        'ИИ-пересказы входят в тарифы: Relay – {relay} в месяц, Серебро – {silver}, Бронза – {bronze}. '
        'Пересказ, который уже кто-то заказал, бесплатен.',
        'AI summaries come with a plan: Relay {relay} a month, Silver {silver}, Bronze {bronze}. '
        'A summary someone already asked for is free.',
        'Resumos com IA vêm com um plano: Relay {relay} por mês, Prata {silver}, Bronze {bronze}. '
        'Um resumo que alguém já pediu é grátis.',
        'Los resúmenes con IA vienen con un plan: Relay {relay} al mes, Plata {silver}, Bronce {bronze}. '
        'Un resumen que alguien ya pidió es gratis.',
        'KI-Zusammenfassungen gibt es mit einem Tarif: Relay {relay} im Monat, Silber {silver}, Bronze {bronze}. '
        'Eine Zusammenfassung, die schon jemand angefragt hat, ist gratis.',
        'סיכומי AI מגיעים עם מסלול: Relay {relay} בחודש, כסף {silver}, ארד {bronze}. '
        'סיכום שמישהו כבר ביקש הוא בחינם.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
