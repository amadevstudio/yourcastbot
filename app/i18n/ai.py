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
    'summaryQuota': (
        'Пересказы считаются по длине выпусков: {limit} аудио за 30 дней. '
        'Осталось {left}, а этот выпуск длится {needed}.',
        'Summaries count by episode length: {limit} of audio in 30 days. '
        '{left} left, and this episode runs {needed}.',
        'Os resumos contam pela duração dos episódios: {limit} de áudio em 30 dias. '
        'Restam {left}, e este episódio dura {needed}.',
        'Los resúmenes cuentan por la duración de los episodios: {limit} de audio en 30 días. '
        'Quedan {left} y este episodio dura {needed}.',
        'Zusammenfassungen zählen nach der Länge der Folgen: {limit} Audio in 30 Tagen. '
        'Übrig: {left}, diese Folge dauert {needed}.',
        'סיכומים נספרים לפי אורך הפרקים: {limit} אודיו ב-30 יום. '
        'נשארו {left}, והפרק הזה נמשך {needed}.'),
    'summaryBiggerPlan': (
        'Тариф выше даёт больше:',
        'A bigger plan gives more:',
        'Um plano maior dá mais:',
        'Un plan mayor da más:',
        'Ein größerer Tarif gibt mehr:',
        'מסלול גדול יותר נותן יותר:'),
    'summaryForPlans': (
        'ИИ-пересказы входят в тарифы и считаются по длине выпусков: Relay – {relay} ч аудио в месяц, '
        'Серебро – {silver} ч, Бронза – {bronze} ч. Пересказ, который уже кто-то заказал, бесплатен.',
        'AI summaries come with a plan and count by episode length: Relay {relay} h of audio a month, '
        'Silver {silver} h, Bronze {bronze} h. A summary someone already asked for is free.',
        'Resumos com IA vêm com um plano e contam pela duração dos episódios: Relay {relay} h de áudio '
        'por mês, Prata {silver} h, Bronze {bronze} h. Um resumo que alguém já pediu é grátis.',
        'Los resúmenes con IA vienen con un plan y cuentan por la duración de los episodios: Relay '
        '{relay} h de audio al mes, Plata {silver} h, Bronce {bronze} h. Un resumen que alguien ya pidió es gratis.',
        'KI-Zusammenfassungen gibt es mit einem Tarif, gezählt nach der Länge der Folgen: Relay {relay} Std. '
        'Audio im Monat, Silber {silver} Std., Bronze {bronze} Std. Eine Zusammenfassung, die schon jemand '
        'angefragt hat, ist gratis.',
        'סיכומי AI מגיעים עם מסלול ונספרים לפי אורך הפרקים: Relay {relay} שעות אודיו בחודש, '
        'כסף {silver} שעות, ארד {bronze} שעות. סיכום שמישהו כבר ביקש הוא בחינם.'),
    'settingsSummaryTitle': (
        'ИИ-пересказы', 'AI summaries', 'Resumos com IA', 'Resúmenes con IA', 'KI-Zusammenfassungen',
        'סיכומי AI'),
    'summaryLanguageOriginal': (
        'На языке выпуска', "In the episode's language", 'No idioma do episódio', 'En el idioma del episodio',
        'In der Sprache der Folge', 'בשפת הפרק'),
    'summaryLanguageMine': (
        'На языке моего Telegram', 'In my Telegram language', 'No idioma do meu Telegram',
        'En el idioma de mi Telegram', 'In meiner Telegram-Sprache', 'בשפת הטלגרם שלי'),
    'summaryLanguageHelp': (
        'На каком языке присылать пересказ: на языке, на котором говорят в выпуске, '
        'или на языке вашего Telegram.',
        'Which language summaries come in: the one spoken in the episode, or your Telegram language.',
        'Em que idioma enviar os resumos: o falado no episódio ou o idioma do seu Telegram.',
        'En qué idioma enviar los resúmenes: el que se habla en el episodio o el idioma de tu Telegram.',
        'In welcher Sprache Zusammenfassungen kommen: in der Sprache der Folge oder in deiner Telegram-Sprache.',
        'באיזו שפה לשלוח סיכומים: בשפה שמדברים בה בפרק או בשפת הטלגרם שלך.'),
    'summaryHours': ('{h} ч', '{h} h', '{h} h', '{h} h', '{h} Std.', '{h} ש׳'),
    'summaryMinutes': ('{m} мин', '{m} min', '{m} min', '{m} min', '{m} Min.', '{m} דק׳'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
