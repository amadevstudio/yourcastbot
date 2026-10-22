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
    'summaryTrialMore': (
        'С оплаченным тарифом больше: Relay – {relay} ч в месяц.',
        'A paid plan gives more: Relay {relay} h a month.',
        'Um plano pago dá mais: Relay {relay} h por mês.',
        'Un plan de pago da más: Relay {relay} h al mes.',
        'Ein bezahlter Tarif gibt mehr: Relay {relay} Std. im Monat.',
        'מסלול בתשלום נותן יותר: Relay {relay} שעות בחודש.'),
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
    'summaryAutoOn': (
        '🔁 Пересказ новых выпусков: вкл', '🔁 Summaries of new episodes: on', '🔁 Resumo dos novos episódios: sim',
        '🔁 Resumen de episodios nuevos: sí', '🔁 Zusammenfassung neuer Folgen: an', '🔁 סיכום פרקים חדשים: פעיל'),
    'summaryAutoOff': (
        '🔁 Пересказ новых выпусков: выкл', '🔁 Summaries of new episodes: off', '🔁 Resumo dos novos episódios: não',
        '🔁 Resumen de episodios nuevos: no', '🔁 Zusammenfassung neuer Folgen: aus', '🔁 סיכום פרקים חדשים: כבוי'),
    'summaryAutoHelp': (
        'С подпиской пересказ нового выпуска может приходить сам, сразу после файла. Он считается в часы '
        'пересказов плана, как по кнопке.',
        'With a plan, the summary of a new episode can come by itself, right after the file. It counts toward '
        "the plan's summary hours, as a tap does.",
        'Com um plano, o resumo de um episódio novo pode chegar sozinho, logo depois do arquivo. Ele conta nas '
        'horas de resumos do plano, como um toque.',
        'Con un plan, el resumen de un episodio nuevo puede llegar solo, justo después del archivo. Cuenta en '
        'las horas de resúmenes del plan, como un toque.',
        'Mit einem Tarif kann die Zusammenfassung einer neuen Folge von selbst kommen, direkt nach der Datei. '
        'Sie zählt zu den Stunden des Tarifs, wie ein Tippen.',
        'עם מסלול, הסיכום של פרק חדש יכול להגיע לבד, מיד אחרי הקובץ. הוא נספר בשעות הסיכומים של המסלול, '
        'כמו לחיצה.'),
    'askButton': (
        '❓ Спросить о выпуске', '❓ Ask about it', '❓ Perguntar sobre o episódio', '❓ Preguntar sobre el episodio',
        '❓ Frage zur Folge', '❓ לשאול על הפרק'),
    'askPrompt': (
        'Напишите вопрос о выпуске "{title}". Отвечу по его расшифровке и подскажу, на какой минуте об этом '
        'говорят. Вопросов на сегодня: {left}.',
        'Write a question about "{title}". I answer from its transcript and tell you the minute where it '
        'comes up. Questions left today: {left}.',
        'Escreva uma pergunta sobre "{title}". Respondo pela transcrição e digo em que minuto isso aparece. '
        'Perguntas restantes hoje: {left}.',
        'Escribe una pregunta sobre "{title}". Respondo con su transcripción y te digo en qué minuto se habla '
        'de ello. Preguntas que quedan hoy: {left}.',
        'Schreib eine Frage zu "{title}". Ich antworte anhand des Transkripts und sage dir, in welcher Minute '
        'es darum geht. Fragen heute übrig: {left}.',
        'כתבו שאלה על "{title}". אענה לפי התמליל ואגיד באיזו דקה מדברים על זה. שאלות שנותרו היום: {left}.'),
    'askDone': ('Готово', 'Done', 'Pronto', 'Listo', 'Fertig', 'סיום'),
    'askTextOnly': (
        'Напишите вопрос текстом.', 'Please type the question.', 'Escreva a pergunta em texto.',
        'Escribe la pregunta en texto.', 'Bitte schreib die Frage als Text.', 'כתבו את השאלה בטקסט.'),
    'summaryAutoNeedsPlan': (
        'Включено. Пересказы новых выпусков приходят с подпиской: без неё они ждут, пока она появится.',
        'On. Summaries of new episodes come with a plan: without one they wait until you have one.',
        'Ativado. Resumos de episódios novos vêm com um plano: sem ele, esperam até você ter um.',
        'Activado. Los resúmenes de episodios nuevos llegan con un plan: sin él, esperan hasta que tengas uno.',
        'An. Zusammenfassungen neuer Folgen kommen mit einem Tarif: ohne ihn warten sie, bis du einen hast.',
        'פעיל. סיכומי פרקים חדשים מגיעים עם מסלול: בלעדיו הם מחכים עד שיהיה לך.'),
    'askNeedsSummary': (
        'Сначала получите пересказ: вопросы задаются по расшифровке выпуска.',
        'Get the summary first: questions are answered from the episode\'s transcript.',
        'Peça o resumo primeiro: as perguntas são respondidas pela transcrição do episódio.',
        'Pide primero el resumen: las preguntas se responden con la transcripción del episodio.',
        'Hol dir zuerst die Zusammenfassung: Fragen werden anhand des Transkripts beantwortet.',
        'קודם בקשו את הסיכום: התשובות מבוססות על התמליל של הפרק.'),
    'askLimit': (
        'На сегодня вопросы закончились: {limit} в сутки. Скоро можно будет снова.',
        'No questions left for today: {limit} a day. You can ask again soon.',
        'As perguntas de hoje acabaram: {limit} por dia. Logo você poderá perguntar de novo.',
        'Se acabaron las preguntas de hoy: {limit} al día. Pronto podrás volver a preguntar.',
        'Für heute sind keine Fragen mehr übrig: {limit} am Tag. Bald geht es wieder.',
        'נגמרו השאלות להיום: {limit} ביום. בקרוב אפשר לשאול שוב.'),
    'askTrialMore': (
        'С оплаченным тарифом – {limit} вопросов в сутки.',
        'A paid plan gives {limit} questions a day.',
        'Um plano pago dá {limit} perguntas por dia.',
        'Un plan de pago da {limit} preguntas al día.',
        'Ein bezahlter Tarif gibt {limit} Fragen am Tag.',
        'מסלול בתשלום נותן {limit} שאלות ביום.'),
    'askForPlans': (
        'Вопросы к выпускам доступны с подпиской: до {limit} в день.',
        'Questions about episodes come with a plan: up to {limit} a day.',
        'Perguntas sobre episódios vêm com um plano: até {limit} por dia.',
        'Las preguntas sobre episodios vienen con un plan: hasta {limit} al día.',
        'Fragen zu Folgen gibt es mit einem Tarif: bis zu {limit} am Tag.',
        'שאלות על פרקים מגיעות עם מסלול: עד {limit} ביום.'),
    'askFailed': (
        'Не получилось ответить. Попробуйте ещё раз.',
        'Could not answer. Please try again.',
        'Não foi possível responder. Tente de novo.',
        'No se pudo responder. Inténtalo de nuevo.',
        'Das hat nicht geklappt. Bitte versuch es noch einmal.',
        'לא הצלחנו לענות. נסו שוב.'),
    # a new episode without its automatic summary: the plan's hours ran out (once in 30 days)
    'summaryAutoSkipped': (
        '🔁 Этот выпуск пришёл без пересказа: часов пересказов не хватает.',
        '🔁 This episode came without its summary: not enough summary hours left.',
        '🔁 Este episódio chegou sem resumo: não há horas de resumo suficientes.',
        '🔁 Este episodio llegó sin resumen: no quedan horas de resumen suficientes.',
        '🔁 Diese Folge kam ohne Zusammenfassung: Es sind nicht genug Stunden übrig.',
        '🔁 הפרק הזה הגיע בלי סיכום: לא נשארו מספיק שעות סיכום.'),
    # once, after the first episode with the Summary button (app/service/ai/hint.py)
    'summaryHint': (
        '📝 Под выпуском кнопка "Пересказ": ИИ расскажет, о чём он, по пунктам со временем. '
        'Нажмите на время – запись перемотается туда. А потом можно задать вопросы по выпуску.',
        '📝 The "Summary" button under the episode: AI tells you what it is about, point by point with times. '
        'Tap a time and the audio jumps there. Then you can ask questions about the episode.',
        '📝 O botão "Resumo" sob o episódio: a IA conta do que se trata, ponto a ponto, com os horários. '
        'Toque em um horário e o áudio pula para lá. Depois dá para fazer perguntas sobre o episódio.',
        '📝 El botón "Resumen" bajo el episodio: la IA te cuenta de qué trata, punto por punto con los tiempos. '
        'Toca un tiempo y el audio salta ahí. Después puedes hacer preguntas sobre el episodio.',
        '📝 Der Button "Zusammenfassung" unter der Folge: Die KI sagt dir Punkt für Punkt mit Zeitangaben, '
        'worum es geht. Tippe auf eine Zeit, und das Audio springt dorthin. Danach kannst du Fragen zur Folge stellen.',
        '📝 הכפתור "סיכום" מתחת לפרק: ה-AI מספר על מה הפרק, נקודה אחר נקודה עם זמנים. '
        'הקשה על זמן מעבירה את ההקלטה לשם. אחר כך אפשר לשאול שאלות על הפרק.'),
    # status lines while a summary is made or a question answered, edited into the result
    'summaryStatusQueued': (
        '📝 Пересказ: в очереди…',
        '📝 Summary: queued…',
        '📝 Resumo: na fila…',
        '📝 Resumen: en cola…',
        '📝 Zusammenfassung: in der Warteschlange…',
        '📝 סיכום: בתור…'),
    'summaryStatusDownloading': (
        '📝 Пересказ: скачиваю выпуск…',
        '📝 Summary: downloading the episode…',
        '📝 Resumo: baixando o episódio…',
        '📝 Resumen: descargando el episodio…',
        '📝 Zusammenfassung: lade die Folge herunter…',
        '📝 סיכום: מוריד את הפרק…'),
    'summaryStatusTranscribing': (
        '📝 Пересказ: расшифровываю, часть {done} из {total}…',
        '📝 Summary: transcribing, part {done} of {total}…',
        '📝 Resumo: transcrevendo, parte {done} de {total}…',
        '📝 Resumen: transcribiendo, parte {done} de {total}…',
        '📝 Zusammenfassung: transkribiere, Teil {done} von {total}…',
        '📝 סיכום: מתמלל, חלק {done} מתוך {total}…'),
    'summaryStatusWriting': (
        '📝 Пересказ: пишу…',
        '📝 Summary: writing…',
        '📝 Resumo: escrevendo…',
        '📝 Resumen: escribiendo…',
        '📝 Zusammenfassung: schreibe…',
        '📝 סיכום: כותב…'),
    'askThinking': (
        '🤔 Думаю…',
        '🤔 Thinking…',
        '🤔 Pensando…',
        '🤔 Pensando…',
        '🤔 Ich denke nach…',
        '🤔 חושב…'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
