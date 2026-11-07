"""Plans given for something other than money (db/plan_grants.py): Bronze for subscribing to the owner's channels."""
LANGS = ('en', 'ru', 'pt-BR', 'es', 'de', 'he', 'fa')
_COPY = {
'chanPlanButton': (
    '🎁 Bronze for free: subscribe to channels',
    '🎁 Бронза бесплатно: подписка на каналы',
    '🎁 Bronze grátis: assine canais',
    '🎁 Bronce gratis: suscríbete a canales',
    '🎁 Bronze gratis: Kanäle abonnieren',
    '🎁 ברונזה בחינם: הרשמה לערוצים',
    '🎁 برنزی رایگان: عضویت در کانال‌ها'),
'chanPlanBody': (
    '<b>Bronze for free</b>\n\nSubscribe to the channels below and Bronze is yours while you stay subscribed: '
    'new episodes of your podcasts come as files, as on the paid Bronze. AI (summaries, transcripts, questions) '
    'is not included.\n\nSubscribed? Tap "Check".',
    '<b>Бронза бесплатно</b>\n\nПодпишитесь на каналы ниже, и Бронза ваша, пока вы на них подписаны: новые '
    'выпуски ваших подкастов приходят файлами, как на платной Бронзе. ИИ (пересказы, расшифровки, вопросы) '
    'в неё не входит.\n\nПодписались? Нажмите "Проверить".',
    '<b>Bronze grátis</b>\n\nAssine os canais abaixo e o Bronze é seu enquanto continuar inscrito: episódios '
    'novos dos seus podcasts chegam como arquivos, como no Bronze pago. A IA (resumos, transcrições, perguntas) '
    'não está incluída.\n\nAssinou? Toque em "Verificar".',
    '<b>Bronce gratis</b>\n\nSuscríbete a los canales de abajo y el Bronce es tuyo mientras sigas suscrito: los '
    'episodios nuevos de tus pódcasts llegan como archivos, como en el Bronce de pago. La IA (resúmenes, '
    'transcripciones, preguntas) no está incluida.\n\n¿Ya te suscribiste? Toca "Comprobar".',
    '<b>Bronze gratis</b>\n\nAbonniere die Kanäle unten, und Bronze gehört dir, solange du sie abonniert hast: '
    'neue Folgen deiner Podcasts kommen als Dateien, wie beim bezahlten Bronze. KI (Zusammenfassungen, '
    'Transkripte, Fragen) ist nicht dabei.\n\nAbonniert? Tippe auf "Prüfen".',
    '<b>ברונזה בחינם</b>\n\nהירשמו לערוצים שלמטה, והברונזה שלכם כל עוד אתם רשומים: פרקים חדשים של הפודקאסטים '
    'שלכם מגיעים כקבצים, כמו בברונזה בתשלום. AI (סיכומים, תמלילים, שאלות) לא כלול.\n\nנרשמתם? הקישו "בדיקה".',
    '<b>برنزی رایگان</b>\n\nعضو کانال‌های زیر شوید و تا وقتی عضو هستید برنزی مال شماست: قسمت‌های تازهٔ '
    'پادکست‌هایتان مثل برنزی پولی به‌صورت فایل می‌آیند. هوش مصنوعی (خلاصه، متن پیاده‌شده، سؤال) در آن نیست.'
    '\n\nعضو شدید؟ "بررسی" را بزنید.'),
'chanPlanActive': (
    '✅ Bronze for channels is on. It stays while you are subscribed to all of them: the bot checks every hour.',
    '✅ Бронза за каналы включена. Она действует, пока вы подписаны на все эти каналы: бот проверяет каждый час.',
    '✅ O Bronze pelos canais está ativo. Fica enquanto você assinar todos eles: o bot verifica a cada hora.',
    '✅ El Bronce por canales está activo. Sigue mientras estés suscrito a todos: el bot lo comprueba cada hora.',
    '✅ Bronze für Kanäle ist an. Es bleibt, solange du alle abonniert hast: der Bot prüft jede Stunde.',
    '✅ ברונזה בזכות הערוצים פעילה. היא נשארת כל עוד אתם רשומים לכולם: הבוט בודק כל שעה.',
    '✅ برنزیِ کانال\u200cها روشن است. تا وقتی عضو همهٔ آن\u200cها باشید می\u200cماند: ربات هر ساعت بررسی می\u200cکند.'),
'chanPlanCheck': (
    '✅ Check', '✅ Проверить', '✅ Verificar', '✅ Comprobar', '✅ Prüfen', '✅ בדיקה', '✅ بررسی'),
'chanPlanTerms': (
    'This is a promo, and we may end it at any time; you will get a message if we do.',
    'Это акция, и мы можем завершить её в любой момент; тогда пришлём сообщение.',
    'É uma promoção e podemos encerrá-la a qualquer momento; se isso acontecer, você recebe uma mensagem.',
    'Es una promoción y podemos terminarla en cualquier momento; si pasa, te enviaremos un mensaje.',
    'Das ist eine Aktion, die wir jederzeit beenden können; dann bekommst du eine Nachricht.',
    'זה מבצע, ואנחנו יכולים לסיים אותו בכל עת; אם זה יקרה, תקבלו הודעה.',
    'این یک پیشنهاد ویژه است و ممکن است هر زمان تمامش کنیم؛ در آن صورت پیام می\u200cگیرید.'),
'chanPlanOn': (
    'Bronze is on 🎉 New episodes of your podcasts will come as files. It stays while you are subscribed to the channels; a plan you pay for replaces it whenever you like.',
    'Бронза включена 🎉 Новые выпуски ваших подкастов будут приходить файлами. Она действует, пока вы подписаны на каналы; оплаченный тариф заменит её, когда захотите.',
    'Bronze ativado 🎉 Episódios novos dos seus podcasts vão chegar como arquivos. Fica enquanto você assinar os canais; um plano pago o substitui quando quiser.',
    'Bronce activado 🎉 Los episodios nuevos de tus pódcasts llegarán como archivos. Sigue mientras estés suscrito a los canales; un plan de pago lo reemplaza cuando quieras.',
    'Bronze ist an 🎉 Neue Folgen deiner Podcasts kommen als Dateien. Es bleibt, solange du die Kanäle abonniert hast; ein bezahlter Tarif ersetzt es, wann du willst.',
    'הברונזה פעילה 🎉 פרקים חדשים של הפודקאסטים שלכם יגיעו כקבצים. היא נשארת כל עוד אתם רשומים לערוצים; מסלול בתשלום מחליף אותה מתי שתרצו.',
    'برنزی روشن شد 🎉 قسمت\u200cهای تازهٔ پادکست\u200cهایتان به\u200cصورت فایل می\u200cآیند. تا وقتی عضو کانال\u200cها باشید می\u200cماند؛ هر وقت بخواهید طرح پولی جایش را می\u200cگیرد.'),
'chanPlanMissing': (
    'Not subscribed yet: {channels}. Subscribe and tap "Check" again.',
    'Пока нет подписки: {channels}. Подпишитесь и нажмите "Проверить" ещё раз.',
    'Ainda sem inscrição: {channels}. Assine e toque em "Verificar" de novo.',
    'Aún sin suscripción: {channels}. Suscríbete y toca "Comprobar" otra vez.',
    'Noch nicht abonniert: {channels}. Abonniere und tippe noch einmal auf "Prüfen".',
    'עדיין לא רשומים: {channels}. הירשמו והקישו שוב "בדיקה".',
    'هنوز عضو نیستید: {channels}. عضو شوید و دوباره "بررسی" را بزنید.'),
'chanPlanBusy': (
    'You have a plan running. Free Bronze is for when no plan runs: it will be here when yours ends.',
    'У вас уже идёт тариф. Бесплатная Бронза для тех, у кого тарифа нет: она будет ждать, когда ваш закончится.',
    'Você já tem um plano ativo. O Bronze grátis é para quem não tem plano: ele estará aqui quando o seu acabar.',
    'Ya tienes un plan activo. El Bronce gratis es para quien no tiene plan: estará aquí cuando el tuyo termine.',
    'Du hast schon einen laufenden Tarif. Gratis-Bronze ist für alle ohne Tarif: es wartet, bis deiner endet.',
    'כבר יש לכם מסלול פעיל. ברונזה בחינם היא למי שאין לו מסלול: היא תחכה כשהמסלול שלכם ייגמר.',
    'طرح شما هنوز فعال است. برنزی رایگان برای وقتی است که طرحی ندارید: وقتی طرحتان تمام شد اینجاست.'),
'chanPlanUnavailable': (
    'Free Bronze is not available now.',
    'Бесплатная Бронза сейчас недоступна.',
    'O Bronze grátis não está disponível agora.',
    'El Bronce gratis no está disponible ahora.',
    'Gratis-Bronze ist gerade nicht verfügbar.',
    'ברונזה בחינם לא זמינה כרגע.',
    'برنزی رایگان الان در دسترس نیست.'),
'chanPlanCheckFailed': (
    'Could not check the subscriptions right now. Please try again in a minute.',
    'Не получилось проверить подписки. Попробуйте через минуту.',
    'Não foi possível verificar as inscrições agora. Tente de novo em um minuto.',
    'No se pudieron comprobar las suscripciones ahora. Inténtalo de nuevo en un minuto.',
    'Die Abos konnten gerade nicht geprüft werden. Bitte versuche es in einer Minute erneut.',
    'לא הצלחנו לבדוק את ההרשמות כרגע. נסו שוב בעוד דקה.',
    'الان نشد عضویت‌ها را بررسی کنیم. یک دقیقهٔ دیگر دوباره امتحان کنید.'),
'chanPlanOff': (
    '<b>Free Bronze is off</b>: you are not subscribed to {channels}. New episodes no longer come as files. Subscribe and tap "Check" to get it back, or pick a plan below: each comes with AI summaries and questions.',
    '<b>Бесплатная Бронза выключена</b>: вы не подписаны на {channels}. Новые выпуски больше не приходят файлами. Подпишитесь и нажмите "Проверить", чтобы вернуть её, или выберите тариф ниже: в каждом есть ИИ-пересказы и вопросы.',
    '<b>O Bronze grátis foi desativado</b>: você não assina {channels}. Episódios novos não chegam mais como arquivos. Assine e toque em "Verificar" para recuperá-lo, ou escolha um plano abaixo: todos têm resumos com IA e perguntas.',
    '<b>El Bronce gratis se desactivó</b>: no estás suscrito a {channels}. Los episodios nuevos ya no llegan como archivos. Suscríbete y toca "Comprobar" para recuperarlo, o elige un plan abajo: todos tienen resúmenes con IA y preguntas.',
    '<b>Gratis-Bronze ist aus</b>: du hast {channels} nicht abonniert. Neue Folgen kommen nicht mehr als Dateien. Abonniere und tippe auf "Prüfen", um es zurückzubekommen, oder wähle unten einen Tarif: jeder hat KI-Zusammenfassungen und Fragen.',
    '<b>ברונזה בחינם כבויה</b>: אתם לא רשומים ל-{channels}. פרקים חדשים כבר לא מגיעים כקבצים. הירשמו והקישו "בדיקה" כדי להחזיר אותה, או בחרו מסלול למטה: בכל אחד יש סיכומי AI ושאלות.',
    '<b>برنزی رایگان خاموش شد</b>: عضو {channels} نیستید. قسمت\u200cهای تازه دیگر به\u200cصورت فایل نمی\u200cآیند. عضو شوید و "بررسی" را بزنید تا برگردد، یا یکی از طرح\u200cهای زیر را بگیرید: همه خلاصهٔ هوش مصنوعی و سؤال دارند.'),
'chanPlanWarn': (
    '<b>Free Bronze needs every channel</b>: you are not subscribed to {channels}. Subscribe within {hours} hours to keep it, then tap "Check".',
    '<b>Для бесплатной Бронзы нужны все каналы</b>: вы не подписаны на {channels}. Подпишитесь в течение {hours} часов, чтобы её сохранить, и нажмите "Проверить".',
    '<b>O Bronze grátis precisa de todos os canais</b>: você não assina {channels}. Assine em até {hours} horas para mantê-lo e toque em "Verificar".',
    '<b>El Bronce gratis necesita todos los canales</b>: no estás suscrito a {channels}. Suscríbete en las próximas {hours} horas para conservarlo y toca "Comprobar".',
    '<b>Gratis-Bronze braucht alle Kanäle</b>: du hast {channels} nicht abonniert. Abonniere innerhalb von {hours} Stunden, um es zu behalten, und tippe auf "Prüfen".',
    '<b>ברונזה בחינם דורשת את כל הערוצים</b>: אתם לא רשומים ל-{channels}. הירשמו בתוך {hours} שעות כדי לשמור עליה, והקישו "בדיקה".',
    '<b>برنزی رایگان همهٔ کانال\u200cها را لازم دارد</b>: عضو {channels} نیستید. تا {hours} ساعت دیگر عضو شوید تا بماند، و "بررسی" را بزنید.'),
'chanPlanStopped': (
    '<b>Free Bronze for channels has ended</b>: the offer is over. New episodes no longer come as files. To keep them coming, pick a plan below: each comes with AI summaries and questions.',
    '<b>Бесплатная Бронза за каналы закончилась</b>: акция завершена. Новые выпуски больше не приходят файлами. Чтобы они приходили, выберите тариф ниже: в каждом есть ИИ-пересказы и вопросы.',
    '<b>O Bronze grátis pelos canais acabou</b>: a promoção terminou. Episódios novos não chegam mais como arquivos. Para continuar recebendo, escolha um plano abaixo: todos têm resumos com IA e perguntas.',
    '<b>El Bronce gratis por canales terminó</b>: la promoción acabó. Los episodios nuevos ya no llegan como archivos. Para seguir recibiéndolos, elige un plan abajo: todos tienen resúmenes con IA y preguntas.',
    '<b>Gratis-Bronze für Kanäle ist vorbei</b>: die Aktion ist beendet. Neue Folgen kommen nicht mehr als Dateien. Damit sie weiter kommen, wähle unten einen Tarif: jeder hat KI-Zusammenfassungen und Fragen.',
    '<b>ברונזה בחינם בזכות ערוצים הסתיימה</b>: המבצע נגמר. פרקים חדשים כבר לא מגיעים כקבצים. כדי שימשיכו להגיע, בחרו מסלול למטה: בכל אחד יש סיכומי AI ושאלות.',
    '<b>برنزی رایگانِ کانال\u200cها تمام شد</b>: این طرح به پایان رسید. قسمت\u200cهای تازه دیگر به\u200cصورت فایل نمی\u200cآیند. برای اینکه بیایند، یکی از طرح\u200cهای زیر را بگیرید: همه خلاصهٔ هوش مصنوعی و سؤال دارند.'),
'chanPlanScreenButton': (
    '🎁 Free Bronze: the channels', '🎁 Бесплатная Бронза: каналы', '🎁 Bronze grátis: os canais',
    '🎁 Bronce gratis: los canales', '🎁 Gratis-Bronze: die Kanäle', '🎁 ברונזה בחינם: הערוצים',
    '🎁 برنزی رایگان: کانال‌ها'),
'chanPlanPayNote': (
    'You have free Bronze for channels. A plan you pay for replaces it and runs from the payment.',
    'У вас бесплатная Бронза за каналы. Оплаченный тариф заменит её и пойдёт с момента оплаты.',
    'Você tem o Bronze grátis pelos canais. Um plano pago o substitui e começa no pagamento.',
    'Tienes el Bronce gratis por canales. Un plan de pago lo reemplaza y empieza con el pago.',
    'Du hast Gratis-Bronze für Kanäle. Ein bezahlter Tarif ersetzt es und läuft ab der Zahlung.',
    'יש לכם ברונזה בחינם בזכות ערוצים. מסלול בתשלום מחליף אותה ומתחיל מרגע התשלום.',
    'برنزی رایگانِ کانال‌ها را دارید. طرح پولی جایش را می‌گیرد و از لحظهٔ پرداخت شروع می‌شود.'),
'aiGrantNoAi': (
    'Free Bronze for channels comes without AI.',
    'Бесплатная Бронза за каналы идёт без ИИ.',
    'O Bronze grátis pelos canais vem sem IA.',
    'El Bronce gratis por canales viene sin IA.',
    'Gratis-Bronze für Kanäle kommt ohne KI.',
    'ברונזה בחינם בזכות ערוצים מגיעה בלי AI.',
    'برنزی رایگانِ کانال‌ها هوش مصنوعی ندارد.'),
'grantEpisodesUsed': (
    'Free Bronze gives up to {limit} episodes a day by tap, and today’s are used up.',
    'Бесплатная Бронза даёт скачать до {limit} выпусков в сутки, на сегодня они закончились.',
    'O Bronze grátis dá até {limit} episódios por dia, e os de hoje acabaram.',
    'El Bronce gratis da hasta {limit} episodios al día, y los de hoy se acabaron.',
    'Gratis-Bronze gibt bis zu {limit} Folgen pro Tag, die von heute sind aufgebraucht.',
    'ברונזה בחינם נותנת עד {limit} פרקים ביום, ושל היום נגמרו.',
    'برنزی رایگان روزانه تا {limit} قسمت می‌دهد و سهم امروز تمام شده است.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': text} for lang, text in zip(LANGS, texts)} for key, texts in _COPY.items()}
