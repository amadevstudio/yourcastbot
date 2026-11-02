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
    # the transcript as a text file, under the audio and under a summary (summaryModule.request_transcript)
    'transcriptButton': (
        '📥 Расшифровка', '📥 Transcript', '📥 Transcrição', '📥 Transcripción', '📥 Transkript', '📥 תמליל'),
    'transcriptMachine': (
        'Расшифровка сделана автоматически, в ней возможны ошибки.',
        'Transcribed automatically: it may have mistakes.',
        'Transcrição automática: pode ter erros.',
        'Transcripción automática: puede tener errores.',
        'Automatisch transkribiert: Fehler sind möglich.',
        'תומלל אוטומטית: ייתכנו טעויות.'),
    # Transcript when the transcript must be made: the same hours and offers as a summary (offer.py)
    'transcriptQuota': (
        'Расшифровки и пересказы считаются по длине выпусков: {limit} аудио за 30 дней. '
        'Осталось {left}, а этот выпуск длится {needed}.',
        'Transcripts and summaries count by episode length: {limit} of audio in 30 days. '
        '{left} left, and this episode runs {needed}.',
        'As transcrições e os resumos contam pela duração dos episódios: {limit} de áudio em 30 dias. '
        'Restam {left}, e este episódio dura {needed}.',
        'Las transcripciones y los resúmenes cuentan por la duración de los episodios: {limit} de audio '
        'en 30 días. Quedan {left} y este episodio dura {needed}.',
        'Transkripte und Zusammenfassungen zählen nach der Länge der Folgen: {limit} Audio in 30 Tagen. '
        'Übrig: {left}, diese Folge dauert {needed}.',
        'תמלילים וסיכומים נספרים לפי אורך הפרקים: {limit} אודיו ב-30 יום. '
        'נשארו {left}, והפרק הזה נמשך {needed}.'),
    'transcriptForPlans': (
        'Расшифровки входят в тарифы вместе с пересказами и считаются по длине выпусков: Relay – {relay} ч '
        'аудио в месяц, Серебро – {silver} ч, Бронза – {bronze} ч. Бесплатны расшифровка, которую уже кто-то '
        'заказал, и текст, который публикует сам подкаст.',
        'Transcripts come with a plan, together with summaries, and count by episode length: Relay {relay} h '
        'of audio a month, Silver {silver} h, Bronze {bronze} h. A transcript someone already asked for, or one '
        'the podcast publishes, is free.',
        'As transcrições vêm com um plano, junto com os resumos, e contam pela duração dos episódios: Relay '
        '{relay} h de áudio por mês, Prata {silver} h, Bronze {bronze} h. Uma transcrição que alguém já pediu, '
        'ou que o próprio podcast publica, é grátis.',
        'Las transcripciones vienen con un plan, junto con los resúmenes, y cuentan por la duración de los '
        'episodios: Relay {relay} h de audio al mes, Plata {silver} h, Bronce {bronze} h. Una transcripción que '
        'alguien ya pidió, o que publica el propio podcast, es gratis.',
        'Transkripte gibt es mit einem Tarif, zusammen mit den Zusammenfassungen, gezählt nach der Länge der '
        'Folgen: Relay {relay} Std. Audio im Monat, Silber {silver} Std., Bronze {bronze} Std. Ein Transkript, '
        'das schon jemand angefragt hat oder das der Podcast selbst veröffentlicht, ist gratis.',
        'תמלילים מגיעים עם מסלול, יחד עם הסיכומים, ונספרים לפי אורך הפרקים: Relay {relay} שעות אודיו בחודש, '
        'כסף {silver} שעות, ארד {bronze} שעות. תמליל שמישהו כבר ביקש, או שהפודקאסט עצמו מפרסם, הוא בחינם.'),
    'transcriptFailed': (
        'Не получилось расшифровать этот выпуск.',
        'Could not transcribe this episode.',
        'Não foi possível transcrever este episódio.',
        'No se pudo transcribir este episodio.',
        'Diese Folge ließ sich nicht transkribieren.',
        'לא הצלחנו לתמלל את הפרק הזה.'),
    # its status line, deleted when the file comes
    'transcriptStatusQueued': (
        '📥 Расшифровка: в очереди…',
        '📥 Transcript: queued…',
        '📥 Transcrição: na fila…',
        '📥 Transcripción: en cola…',
        '📥 Transkript: in der Warteschlange…',
        '📥 תמליל: בתור…'),
    'transcriptStatusDownloading': (
        '📥 Расшифровка: скачиваю выпуск…',
        '📥 Transcript: downloading the episode…',
        '📥 Transcrição: baixando o episódio…',
        '📥 Transcripción: descargando el episodio…',
        '📥 Transkript: lade die Folge herunter…',
        '📥 תמליל: מוריד את הפרק…'),
    'transcriptStatusTranscribing': (
        '📥 Расшифровка: распознаю речь, часть {done} из {total}…',
        '📥 Transcript: transcribing, part {done} of {total}…',
        '📥 Transcrição: transcrevendo, parte {done} de {total}…',
        '📥 Transcripción: transcribiendo, parte {done} de {total}…',
        '📥 Transkript: transkribiere, Teil {done} von {total}…',
        '📥 תמליל: מתמלל, חלק {done} מתוך {total}…'),
    # questions about a whole podcast (app/service/ai/show_ask.py)
    'showAskButton': (
        '💬 Спросить о подкасте', '💬 Ask about the podcast', '💬 Perguntar sobre o podcast',
        '💬 Preguntar sobre el podcast', '💬 Frage zum Podcast', '💬 לשאול על הפודקאסט'),
    'showAskPrompt': (
        'Напишите вопрос о подкасте "{title}": о чём там говорили, в каком выпуске была тема, как ведущий '
        'обычно что-то делает. Отвечу по описаниям выпусков и расшифровкам, которые уже есть, и дам кнопки, '
        'чтобы скачать эти выпуски. Вопросов на сегодня: {left}.',
        'Write a question about "{title}": what they talked about, which episode covered a topic, how the host '
        'usually does something. I answer from the episode descriptions and the transcripts already made, '
        'with buttons to download those episodes. Questions left today: {left}.',
        'Escreva uma pergunta sobre "{title}": do que falaram, em que episódio um tema apareceu, como o '
        'apresentador costuma fazer algo. Respondo pelas descrições dos episódios e pelas transcrições já '
        'feitas, com botões para baixar esses episódios. Perguntas restantes hoje: {left}.',
        'Escribe una pregunta sobre "{title}": de qué hablaron, en qué episodio salió un tema, cómo suele '
        'hacer algo el presentador. Respondo con las descripciones de los episodios y las transcripciones ya '
        'hechas, con botones para descargar esos episodios. Preguntas que quedan hoy: {left}.',
        'Schreib eine Frage zu "{title}": worüber gesprochen wurde, in welcher Folge ein Thema vorkam, wie der '
        'Host etwas meistens macht. Ich antworte anhand der Folgenbeschreibungen und der vorhandenen '
        'Transkripte, mit Buttons zum Herunterladen dieser Folgen. Fragen heute übrig: {left}.',
        'כתבו שאלה על "{title}": על מה דיברו, באיזה פרק עלה נושא, איך המגיש בדרך כלל עושה משהו. אענה לפי '
        'תיאורי הפרקים והתמלילים שכבר קיימים, עם כפתורים להורדת הפרקים האלה. שאלות שנותרו היום: {left}.'),
    'showAskBasis': (
        'По расшифровкам: {transcripts}, по описаниям выпусков: {descriptions}.',
        'Based on {transcripts} transcripts and {descriptions} episode descriptions.',
        'Com base em {transcripts} transcrições e {descriptions} descrições de episódios.',
        'Basado en {transcripts} transcripciones y {descriptions} descripciones de episodios.',
        'Grundlage: {transcripts} Transkripte und {descriptions} Folgenbeschreibungen.',
        'מבוסס על {transcripts} תמלילים ו-{descriptions} תיאורי פרקים.'),
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
        'Нажмите на время – запись перемотается туда. А потом можно задать вопросы по выпуску. '
        'Рядом "Расшифровка": весь текст выпуска файлом.',
        '📝 The "Summary" button under the episode: AI tells you what it is about, point by point with times. '
        'Tap a time and the audio jumps there. Then you can ask questions about the episode. '
        'Next to it, "Transcript": the whole episode as a text file.',
        '📝 O botão "Resumo" sob o episódio: a IA conta do que se trata, ponto a ponto, com os horários. '
        'Toque em um horário e o áudio pula para lá. Depois dá para fazer perguntas sobre o episódio. '
        'Ao lado, "Transcrição": o episódio inteiro em um arquivo de texto.',
        '📝 El botón "Resumen" bajo el episodio: la IA te cuenta de qué trata, punto por punto con los tiempos. '
        'Toca un tiempo y el audio salta ahí. Después puedes hacer preguntas sobre el episodio. '
        'Al lado, "Transcripción": el episodio entero en un archivo de texto.',
        '📝 Der Button "Zusammenfassung" unter der Folge: Die KI sagt dir Punkt für Punkt mit Zeitangaben, '
        'worum es geht. Tippe auf eine Zeit, und das Audio springt dorthin. Danach kannst du Fragen zur Folge stellen. '
        'Daneben "Transkript": die ganze Folge als Textdatei.',
        '📝 הכפתור "סיכום" מתחת לפרק: ה-AI מספר על מה הפרק, נקודה אחר נקודה עם זמנים. '
        'הקשה על זמן מעבירה את ההקלטה לשם. אחר כך אפשר לשאול שאלות על הפרק. '
        'לידו, "תמליל": כל הפרק כקובץ טקסט.'),
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
    # better models for chats that paid (app/service/ai/paid_models.py): what they give, as configured,
    # a phrase that follows a colon in the lines below
    'paidModelsWhatBoth': (
        'расшифровки с разметкой, кто говорит, и более сильная модель для пересказов и ответов на вопросы',
        'transcripts that show who is speaking, and a stronger model for summaries and answers to questions',
        'transcrições que mostram quem está falando e um modelo mais forte para resumos e respostas às perguntas',
        'transcripciones que muestran quién habla y un modelo más potente para resúmenes y respuestas a preguntas',
        'Transkripte, die zeigen, wer spricht, und ein stärkeres Modell für Zusammenfassungen und Antworten '
        'auf Fragen',
        'תמלילים שמראים מי מדבר, ומודל חזק יותר לסיכומים ולתשובות על שאלות'),
    'paidModelsWhatTranscript': (
        'расшифровки с разметкой, кто говорит',
        'transcripts that show who is speaking',
        'transcrições que mostram quem está falando',
        'transcripciones que muestran quién habla',
        'Transkripte, die zeigen, wer spricht',
        'תמלילים שמראים מי מדבר'),
    'paidModelsWhatSummary': (
        'более сильная модель для пересказов и ответов на вопросы',
        'a stronger model for summaries and answers to questions',
        'um modelo mais forte para resumos e respostas às perguntas',
        'un modelo más potente para resúmenes y respuestas a preguntas',
        'ein stärkeres Modell für Zusammenfassungen und Antworten auf Fragen',
        'מודל חזק יותר לסיכומים ולתשובות על שאלות'),
    # a plan nobody paid for (the trial): the summary note, D-3
    'paidModelsTrial': (
        '✨ После оплаты тарифа подключаются модели получше: {what}.',
        '✨ Once your plan is paid, better models come on: {what}.',
        '✨ Com o plano pago, entram modelos melhores: {what}.',
        '✨ Con el plan pagado se activan modelos mejores: {what}.',
        '✨ Mit einem bezahlten Tarif kommen bessere Modelle dazu: {what}.',
        '✨ אחרי תשלום על המסלול נכנסים לפעולה מודלים טובים יותר: {what}.'),
    # paid before, no plan running now: the plan-off notice
    'paidModelsLapsed': (
        '✨ Продлите тариф – и вернутся модели получше: {what}.',
        '✨ Renew your plan and the better models come back: {what}.',
        '✨ Renove o plano e os modelos melhores voltam: {what}.',
        '✨ Renueva tu plan y vuelven los modelos mejores: {what}.',
        '✨ Verlängere deinen Tarif, dann sind die besseren Modelle zurück: {what}.',
        '✨ חדשו את המסלול והמודלים הטובים יותר יחזרו: {what}.'),
    # never paid, no plan running (a trial that just ended): the plan-off notice
    'paidModelsNoPlan': (
        '✨ С оплаченным тарифом – модели получше: {what}.',
        '✨ A paid plan brings better models: {what}.',
        '✨ Um plano pago traz modelos melhores: {what}.',
        '✨ Un plan de pago trae modelos mejores: {what}.',
        '✨ Ein bezahlter Tarif bringt bessere Modelle: {what}.',
        '✨ מסלול בתשלום מביא מודלים טובים יותר: {what}.'),
    # D-3 of a chat that has them
    'paidModelsEnding': (
        '✨ Вместе с тарифом выключатся модели получше: {what}.',
        '✨ The better models stop with the plan: {what}.',
        '✨ Os modelos melhores param junto com o plano: {what}.',
        '✨ Los modelos mejores se apagan junto con el plan: {what}.',
        '✨ Mit dem Tarif enden auch die besseren Modelle: {what}.',
        '✨ המודלים הטובים יותר ייכבו יחד עם המסלול: {what}.'),
    # the change-plan page
    'paidModelsPlans': (
        '✨ С любым оплаченным тарифом – модели получше: {what}.',
        '✨ Any paid plan comes with better models: {what}.',
        '✨ Qualquer plano pago vem com modelos melhores: {what}.',
        '✨ Cualquier plan de pago incluye modelos mejores: {what}.',
        '✨ Jeder bezahlte Tarif hat bessere Modelle: {what}.',
        '✨ כל מסלול בתשלום כולל מודלים טובים יותר: {what}.'),
    # /settings, AI summaries: only a chat that paid and has a plan running sees it
    'paidModelsSettingsHelp': (
        '✨ Ваш оплаченный тариф даёт модели получше: {what}. Включить или выключить – кнопкой ниже.',
        '✨ Your paid plan includes better models: {what}. Turn them on or off with the button below.',
        '✨ Seu plano pago inclui modelos melhores: {what}. Ligue ou desligue no botão abaixo.',
        '✨ Tu plan de pago incluye modelos mejores: {what}. Actívalos o desactívalos con el botón de abajo.',
        '✨ Dein bezahlter Tarif enthält bessere Modelle: {what}. Ein- oder ausschalten mit dem Button unten.',
        '✨ המסלול ששילמתם עליו כולל מודלים טובים יותר: {what}. אפשר להפעיל או לכבות בכפתור למטה.'),
    'paidModelsFeedNote': (
        'Если подкаст сам публикует расшифровку, приходит она, как есть.',
        'When a podcast publishes its own transcript, you get that one as it is.',
        'Quando o podcast publica a própria transcrição, você recebe essa, como está.',
        'Cuando el podcast publica su propia transcripción, recibes esa, tal cual.',
        'Veröffentlicht ein Podcast sein eigenes Transkript, bekommst du dieses, so wie es ist.',
        'כשהפודקאסט מפרסם תמליל משלו, תקבלו אותו כמו שהוא.'),
    'paidModelsCachedNote': (
        'Пересказ, который уже кто-то заказал, приходит готовым, как был сделан.',
        'A summary someone already asked for comes as it was made.',
        'Um resumo que alguém já pediu vem como foi feito.',
        'Un resumen que alguien ya pidió llega tal como se hizo.',
        'Eine Zusammenfassung, die schon jemand angefordert hat, kommt so, wie sie gemacht wurde.',
        'סיכום שמישהו כבר ביקש מגיע כמו שנעשה.'),
    'paidModelsOn': (
        '✨ Модели получше: вкл', '✨ Better models: on', '✨ Modelos melhores: sim', '✨ Modelos mejores: sí',
        '✨ Bessere Modelle: an', '✨ מודלים טובים יותר: פעיל'),
    'paidModelsOff': (
        '✨ Модели получше: выкл', '✨ Better models: off', '✨ Modelos melhores: não', '✨ Modelos mejores: no',
        '✨ Bessere Modelle: aus', '✨ מודלים טובים יותר: כבוי'),
    # once, when a payment turns them on and the plan is running (app/jobs/payment_effects.py)
    'paidModelsOnNotice': (
        '✨ Тариф оплачен – подключили модели получше: {what}. Выключить можно в /settings, '
        'раздел "ИИ-пересказы".',
        '✨ Your plan is paid, so better models are on: {what}. You can turn them off in /settings, '
        'under "AI summaries".',
        '✨ Seu plano está pago, então os modelos melhores estão ligados: {what}. Dá para desligar em /settings, '
        'em "Resumos com IA".',
        '✨ Tu plan está pagado, así que los modelos mejores están activados: {what}. Puedes desactivarlos en '
        '/settings, en "Resúmenes con IA".',
        '✨ Dein Tarif ist bezahlt, die besseren Modelle sind an: {what}. Ausschalten kannst du sie in /settings '
        'unter "KI-Zusammenfassungen".',
        '✨ המסלול שולם, אז המודלים הטובים יותר פעילים: {what}. אפשר לכבות אותם ב-/settings, בקטע "סיכומי AI".'),
    # under a transcript file Whisper made (paid_models.transcript_note)
    'paidTranscriptTrial': (
        '✨ После оплаты тарифа расшифровки, которые делает бот, показывают, кто говорит.',
        '✨ Once your plan is paid, the transcripts the bot makes show who is speaking.',
        '✨ Com o plano pago, as transcrições que o bot faz mostram quem está falando.',
        '✨ Con el plan pagado, las transcripciones que hace el bot muestran quién habla.',
        '✨ Mit einem bezahlten Tarif zeigen die Transkripte des Bots, wer spricht.',
        '✨ אחרי תשלום על המסלול, התמלילים שהבוט מכין מראים מי מדבר.'),
    'paidTranscriptLapsed': (
        '✨ Продлите тариф – и расшифровки, которые делает бот, будут показывать, кто говорит.',
        '✨ Renew your plan and the transcripts the bot makes will show who is speaking.',
        '✨ Renove o plano e as transcrições que o bot faz vão mostrar quem está falando.',
        '✨ Renueva tu plan y las transcripciones que hace el bot mostrarán quién habla.',
        '✨ Verlängere deinen Tarif, dann zeigen die Transkripte des Bots, wer spricht.',
        '✨ חדשו את המסלול והתמלילים שהבוט מכין יראו מי מדבר.'),
    'paidTranscriptNoPlan': (
        '✨ С оплаченным тарифом расшифровки, которые делает бот, показывают, кто говорит.',
        '✨ With a paid plan, the transcripts the bot makes show who is speaking.',
        '✨ Com um plano pago, as transcrições que o bot faz mostram quem está falando.',
        '✨ Con un plan de pago, las transcripciones que hace el bot muestran quién habla.',
        '✨ Mit einem bezahlten Tarif zeigen die Transkripte des Bots, wer spricht.',
        '✨ עם מסלול בתשלום, התמלילים שהבוט מכין מראים מי מדבר.'),
    # a chat with the better models over its hours: the transcript made before comes, without speakers
    'paidTranscriptOverQuota': (
        '✨ Расшифровка с разметкой, кто говорит, не уместилась в оставшиеся часы тарифа, поэтому пришла обычная.',
        '✨ A transcript that shows who is speaking did not fit in the hours left on your plan, so here is the '
        'regular one.',
        '✨ Uma transcrição que mostra quem está falando não coube nas horas que restam no seu plano, então aqui '
        'está a comum.',
        '✨ Una transcripción que muestra quién habla no cabía en las horas que le quedan a tu plan, así que aquí '
        'tienes la normal.',
        '✨ Ein Transkript, das zeigt, wer spricht, passte nicht mehr in die restlichen Stunden deines Tarifs, '
        'deshalb kommt das normale.',
        '✨ תמליל שמראה מי מדבר לא נכנס בשעות שנשארו במסלול שלכם, אז הנה התמליל הרגיל.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
