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
'chanPlanBodyAll': (
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
'chanPlanBodySome': (
    '<b>Bronze for free</b>\n\nSubscribe to {need} of the {total} channels below and Bronze is yours while you '
    'stay subscribed: new episodes of your podcasts come as files, as on the paid Bronze. AI (summaries, '
    'transcripts, questions) is not included.\n\nSubscribed? Tap "Check".',
    '<b>Бронза бесплатно</b>\n\nПодпишитесь на {need} из {total} каналов ниже, и Бронза ваша, пока вы на них '
    'подписаны: новые выпуски ваших подкастов приходят файлами, как на платной Бронзе. ИИ (пересказы, '
    'расшифровки, вопросы) в неё не входит.\n\nПодписались? Нажмите "Проверить".',
    '<b>Bronze grátis</b>\n\nAssine {need} dos {total} canais abaixo e o Bronze é seu enquanto continuar '
    'inscrito: episódios novos dos seus podcasts chegam como arquivos, como no Bronze pago. A IA (resumos, '
    'transcrições, perguntas) não está incluída.\n\nAssinou? Toque em "Verificar".',
    '<b>Bronce gratis</b>\n\nSuscríbete a {need} de los {total} canales de abajo y el Bronce es tuyo mientras '
    'sigas suscrito: los episodios nuevos de tus pódcasts llegan como archivos, como en el Bronce de pago. La IA '
    '(resúmenes, transcripciones, preguntas) no está incluida.\n\n¿Ya te suscribiste? Toca "Comprobar".',
    '<b>Bronze gratis</b>\n\nAbonniere {need} der {total} Kanäle unten, und Bronze gehört dir, solange du sie '
    'abonniert hast: neue Folgen deiner Podcasts kommen als Dateien, wie beim bezahlten Bronze. KI '
    '(Zusammenfassungen, Transkripte, Fragen) ist nicht dabei.\n\nAbonniert? Tippe auf "Prüfen".',
    '<b>ברונזה בחינם</b>\n\nהירשמו ל-{need} מתוך {total} הערוצים שלמטה, והברונזה שלכם כל עוד אתם רשומים: פרקים '
    'חדשים של הפודקאסטים שלכם מגיעים כקבצים, כמו בברונזה בתשלום. AI (סיכומים, תמלילים, שאלות) לא כלול.'
    '\n\nנרשמתם? הקישו "בדיקה".',
    '<b>برنزی رایگان</b>\n\nعضو {need} کانال از {total} کانال زیر شوید و تا وقتی عضو هستید برنزی مال شماست: '
    'قسمت‌های تازهٔ پادکست‌هایتان مثل برنزی پولی به‌صورت فایل می‌آیند. هوش مصنوعی (خلاصه، متن پیاده‌شده، '
    'سؤال) در آن نیست.\n\nعضو شدید؟ "بررسی" را بزنید.'),
'chanPlanActive': (
    '✅ Bronze for channels is on. It stays while you are subscribed to {need} of them: the bot checks every hour.',
    '✅ Бронза за каналы включена. Она действует, пока вы подписаны на {need} из них: бот проверяет каждый час.',
    '✅ O Bronze pelos canais está ativo. Fica enquanto você assinar {need} deles: o bot verifica a cada hora.',
    '✅ El Bronce por canales está activo. Sigue mientras estés suscrito a {need} de ellos: el bot lo comprueba cada hora.',
    '✅ Bronze für Kanäle ist an. Es bleibt, solange du {need} davon abonniert hast: der Bot prüft jede Stunde.',
    '✅ ברונזה בזכות הערוצים פעילה. היא נשארת כל עוד אתם רשומים ל-{need} מהם: הבוט בודק כל שעה.',
    '✅ برنزیِ کانال‌ها روشن است. تا وقتی عضو {need} کانال از آن‌ها باشید می‌ماند: ربات هر ساعت بررسی می‌کند.'),
'chanPlanCheck': (
    '✅ Check', '✅ Проверить', '✅ Verificar', '✅ Comprobar', '✅ Prüfen', '✅ בדיקה', '✅ بررسی'),
'chanPlanOn': (
    'Bronze is on 🎉 New episodes of your podcasts will come as files. It stays while you are subscribed to '
    '{need} of the channels; a plan you pay for replaces it whenever you like.',
    'Бронза включена 🎉 Новые выпуски ваших подкастов будут приходить файлами. Она действует, пока вы подписаны '
    'на {need} из каналов; оплаченный тариф заменит её, когда захотите.',
    'Bronze ativado 🎉 Episódios novos dos seus podcasts vão chegar como arquivos. Fica enquanto você assinar '
    '{need} dos canais; um plano pago o substitui quando quiser.',
    'Bronce activado 🎉 Los episodios nuevos de tus pódcasts llegarán como archivos. Sigue mientras estés '
    'suscrito a {need} de los canales; un plan de pago lo reemplaza cuando quieras.',
    'Bronze ist an 🎉 Neue Folgen deiner Podcasts kommen als Dateien. Es bleibt, solange du {need} der Kanäle '
    'abonniert hast; ein bezahlter Tarif ersetzt es, wann du willst.',
    'הברונזה פעילה 🎉 פרקים חדשים של הפודקאסטים שלכם יגיעו כקבצים. היא נשארת כל עוד אתם רשומים ל-{need} '
    'מהערוצים; מסלול בתשלום מחליף אותה מתי שתרצו.',
    'برنزی روشن شد 🎉 قسمت‌های تازهٔ پادکست‌هایتان به‌صورت فایل می‌آیند. تا وقتی عضو {need} کانال باشید می‌ماند؛ '
    'هر وقت بخواهید طرح پولی جایش را می‌گیرد.'),
'chanPlanMissing': (
    'Subscribed to {count} of the {need} needed. Subscribe and tap "Check" again.',
    'Подписок: {count} из {need} нужных. Подпишитесь и нажмите "Проверить" ещё раз.',
    'Inscrito em {count} dos {need} necessários. Assine e toque em "Verificar" de novo.',
    'Suscrito a {count} de los {need} necesarios. Suscríbete y toca "Comprobar" otra vez.',
    '{count} von {need} nötigen abonniert. Abonniere und tippe noch einmal auf "Prüfen".',
    'רשומים ל-{count} מתוך {need} הנדרשים. הירשמו והקישו שוב "בדיקה".',
    'عضو {count} کانال از {need} کانال لازم هستید. عضو شوید و دوباره "بررسی" را بزنید.'),
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
    '<b>Free Bronze is off</b>: you are subscribed to {count} of the {need} channels it needs. New episodes no '
    'longer come as files. Subscribe again and tap "Check", or take Relay: files, AI summaries and questions.',
    '<b>Бесплатная Бронза выключена</b>: вы подписаны на {count} из {need} нужных каналов. Новые выпуски '
    'больше не приходят файлами. Подпишитесь снова и нажмите "Проверить" или возьмите Relay: файлы, '
    'ИИ-пересказы и вопросы.',
    '<b>O Bronze grátis foi desativado</b>: você assina {count} dos {need} canais necessários. Episódios novos '
    'não chegam mais como arquivos. Assine de novo e toque em "Verificar", ou pegue o Relay: arquivos, resumos '
    'com IA e perguntas.',
    '<b>El Bronce gratis se desactivó</b>: estás suscrito a {count} de los {need} canales necesarios. Los '
    'episodios nuevos ya no llegan como archivos. Vuelve a suscribirte y toca "Comprobar", o toma Relay: '
    'archivos, resúmenes con IA y preguntas.',
    '<b>Gratis-Bronze ist aus</b>: du hast {count} der {need} nötigen Kanäle abonniert. Neue Folgen kommen '
    'nicht mehr als Dateien. Abonniere wieder und tippe auf "Prüfen", oder nimm Relay: Dateien, '
    'KI-Zusammenfassungen und Fragen.',
    '<b>ברונזה בחינם כבויה</b>: אתם רשומים ל-{count} מתוך {need} הערוצים הנדרשים. פרקים חדשים כבר לא מגיעים '
    'כקבצים. הירשמו שוב והקישו "בדיקה", או קחו את Relay: קבצים, סיכומי AI ושאלות.',
    '<b>برنزی رایگان خاموش شد</b>: عضو {count} کانال از {need} کانال لازم هستید. قسمت‌های تازه دیگر '
    'به‌صورت فایل نمی‌آیند. دوباره عضو شوید و "بررسی" را بزنید، یا Relay بگیرید: فایل، خلاصهٔ هوش مصنوعی و سؤال.'),
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
