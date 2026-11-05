"""Copy for referrals, the paywall at a limit, prepaid months and win-back (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'award_welcome_invited': (
        '🎁 Вас пригласил друг: +{days} дней Relay к пробному периоду.',
        '🎁 A friend invited you: +{days} days of Relay on top of the free trial.',
        '🎁 Um amigo convidou você: +{days} dias de Relay além do teste grátis.',
        '🎁 Te invitó un amigo: +{days} días de Relay además de la prueba gratis.',
        '🎁 Ein Freund hat dich eingeladen: +{days} Tage Relay zusätzlich zum Gratis-Test.',
        '🎁 חבר הזמין אותך: עוד {days} ימי Relay מעבר לתקופת הניסיון.'),
    'referralInviteButton': (
        '🎁 Позвать друга: +{days} дней',
        '🎁 Invite a friend: +{days} days',
        '🎁 Convidar um amigo: +{days} dias',
        '🎁 Invitar a un amigo: +{days} días',
        '🎁 Freund einladen: +{days} Tage',
        '🎁 להזמין חבר: עוד {days} ימים'),
    'referralShareText': (
        'Слушаю подкасты в Telegram: новые выпуски приходят файлом прямо в чат. По этой ссылке {days} дней бесплатно.',
        'I listen to podcasts in Telegram: new episodes arrive as files right in the chat. This link gives you {days} days free.',
        'Ouço podcasts no Telegram: os episódios novos chegam como arquivo direto no chat. Com este link são {days} dias grátis.',
        'Escucho pódcasts en Telegram: los episodios nuevos llegan como archivo directo al chat. Con este enlace tienes {days} días gratis.',
        'Ich höre Podcasts in Telegram: neue Folgen kommen als Datei direkt in den Chat. Mit diesem Link hast du {days} Tage gratis.',
        'אני מאזין לפודקאסטים בטלגרם: פרקים חדשים מגיעים כקובץ ישר לצ׳אט. עם הקישור הזה מקבלים {days} ימים בחינם.'),
    'freeLimitReached': (
        'Лимит бесплатного плана: {limit} подкастов',
        'Free plan limit: {limit} podcasts',
        'Limite do plano grátis: {limit} podcasts',
        'Límite del plan gratis: {limit} pódcasts',
        'Limit des Gratis-Tarifs: {limit} Podcasts',
        'מגבלת המסלול החינמי: {limit} פודקאסטים'),
    'freeEpisodesUsed': (
        'Бесплатные выпуски на этой неделе закончились: {limit} из {limit}.',
        'Free episodes for this week are used up: {limit} of {limit}.',
        'Os episódios grátis desta semana acabaram: {limit} de {limit}.',
        'Los episodios gratis de esta semana se acabaron: {limit} de {limit}.',
        'Die Gratis-Folgen für diese Woche sind aufgebraucht: {limit} von {limit}.',
        'הפרקים החינמיים של השבוע נגמרו: {limit} מתוך {limit}.'),
    'freeEpisodesNextHours': (
        'Следующий бесплатный – через {hours} ч.',
        'The next free one in {hours} h.',
        'O próximo grátis em {hours} h.',
        'El próximo gratis en {hours} h.',
        'Die nächste Gratis-Folge in {hours} Std.',
        'הפרק החינמי הבא בעוד {hours} שעות.'),
    'freeEpisodesNextDays': (
        'Следующий бесплатный – через {days} дн.',
        'The next free one in {days} d.',
        'O próximo grátis em {days} d.',
        'El próximo gratis en {days} d.',
        'Die nächste Gratis-Folge in {days} Tg.',
        'הפרק החינמי הבא בעוד {days} ימים.'),
    'freeEpisodesAnyPlan': (
        'Любой тариф снимает лимит:',
        'Any plan removes the limit:',
        'Qualquer plano remove o limite:',
        'Cualquier plan quita el límite:',
        'Jeder Tarif hebt das Limit auf:',
        'כל מסלול מסיר את המגבלה:'),
    'trialEpisodesUsed': (
        'На пробном периоде можно скачать до {limit} выпусков в сутки, на сегодня они закончились.',
        'The trial gives up to {limit} episodes a day by tap, and today’s are used up.',
        'No período de teste são até {limit} episódios por dia, e os de hoje acabaram.',
        'En la prueba puedes descargar hasta {limit} episodios al día, y los de hoy se acabaron.',
        'Im Testzeitraum gibt es bis zu {limit} Folgen pro Tag, die von heute sind aufgebraucht.',
        'בתקופת הניסיון אפשר לקבל עד {limit} פרקים ביום, ושל היום נגמרו.'),
    'trialEpisodesNext': (
        'Следующий – через {hours} ч. Оплата Relay сразу снимает лимит, а новые выпуски ваших подкастов приходят как обычно.',
        'The next one in {hours} h. Paying for Relay lifts the limit at once; new episodes of your podcasts keep arriving as usual.',
        'O próximo em {hours} h. Pagar o Relay remove o limite na hora; os episódios novos dos seus podcasts continuam chegando.',
        'El siguiente en {hours} h. Pagar Relay quita el límite al instante; los episodios nuevos de tus pódcasts siguen llegando.',
        'Die nächste in {hours} Std. Mit Relay fällt das Limit sofort weg; neue Folgen deiner Podcasts kommen weiter wie gewohnt.',
        'הבא בעוד {hours} שעות. תשלום על Relay מסיר את המגבלה מיד, ופרקים חדשים של הפודקאסטים שלך ממשיכים להגיע כרגיל.'),
    'starsBundleButton': (
        '📅 Relay на {months} мес. · −{discount}% · {stars} ⭐',
        '📅 Relay for {months} mo · −{discount}% · {stars} ⭐',
        '📅 Relay por {months} meses · −{discount}% · {stars} ⭐',
        '📅 Relay por {months} meses · −{discount}% · {stars} ⭐',
        '📅 Relay für {months} Monate · −{discount}% · {stars} ⭐',
        '📅 Relay ל-{months} חודשים · −{discount}% · {stars} ⭐'),
    'prepayLongestButton': (
        '📅 Relay на {months} мес. со скидкой {discount}%',
        '📅 Relay for {months} months, {discount}% off',
        '📅 Relay por {months} meses com {discount}% de desconto',
        '📅 Relay por {months} meses con {discount}% de descuento',
        '📅 Relay für {months} Monate mit {discount}% Rabatt',
        '📅 Relay ל-{months} חודשים בהנחה של {discount}%'),
    'telegram_stars_bundle_description': (
        'Relay на {months} мес. со скидкой {discount}%: на баланс {balance}$ за {stars} ⭐. Продление каждый месяц с баланса. Курс: 1000 ⭐ ≈ {rate}$.',
        'Relay for {months} months, {discount}% off: ${balance} to your balance for {stars} ⭐. Renews monthly from the balance. Rate: 1000 ⭐ ≈ ${rate}.',
        'Relay por {months} meses com {discount}% de desconto: US${balance} no saldo por {stars} ⭐. Renova todo mês pelo saldo. Câmbio: 1000 ⭐ ≈ US${rate}.',
        'Relay por {months} meses con {discount}% de descuento: {balance} US$ al saldo por {stars} ⭐. Se renueva cada mes desde el saldo. Cambio: 1000 ⭐ ≈ {rate} US$.',
        'Relay für {months} Monate mit {discount}% Rabatt: {balance} $ Guthaben für {stars} ⭐. Verlängert sich monatlich aus dem Guthaben. Kurs: 1000 ⭐ ≈ {rate} $.',
        'Relay ל-{months} חודשים בהנחה של {discount}%: ‎${balance} ליתרה תמורת {stars} ⭐. מתחדש כל חודש מהיתרה. שער: 1000 ⭐ ≈ ‎${rate}.'),
    'winbackOffer': (
        'Relay выключен уже неделю, и новые выпуски ваших подкастов не приходят файлом.\n\nВернуть автодоставку: первый месяц со скидкой {discount}%.',
        'Relay has been off for a week, and new episodes of your podcasts no longer arrive as files.\n\nBring auto-delivery back: the first month is {discount}% off.',
        'O Relay está desligado há uma semana, e os episódios novos dos seus podcasts não chegam mais como arquivo.\n\nVolte a receber: o primeiro mês sai com {discount}% de desconto.',
        'Relay lleva una semana apagado y los episodios nuevos de tus pódcasts ya no llegan como archivo.\n\nRecupera la entrega automática: el primer mes con {discount}% de descuento.',
        'Relay ist seit einer Woche aus, und neue Folgen deiner Podcasts kommen nicht mehr als Datei.\n\nHol dir die automatische Zustellung zurück: der erste Monat mit {discount}% Rabatt.',
        'Relay כבוי כבר שבוע, ופרקים חדשים של הפודקאסטים שלך כבר לא מגיעים כקובץ.\n\nלהחזיר את המשלוח האוטומטי: החודש הראשון בהנחה של {discount}%.'),
    'winbackOfferLast': (
        'Скидка {discount}% на первый месяц Relay ещё ждёт вас.\n\nНовые выпуски снова будут приходить файлом прямо в чат и постом в ваш канал.',
        'The {discount}% off your first month of Relay is still waiting.\n\nNew episodes will again arrive as files right here and as posts in your channel.',
        'O desconto de {discount}% no primeiro mês do Relay ainda está esperando por você.\n\nOs episódios novos voltarão a chegar como arquivo aqui e como post no seu canal.',
        'El descuento del {discount}% en tu primer mes de Relay aún te espera.\n\nLos episodios nuevos volverán a llegar como archivo aquí y como publicación en tu canal.',
        'Die {discount}% Rabatt auf deinen ersten Relay-Monat warten noch.\n\nNeue Folgen kommen dann wieder als Datei hierher und als Beitrag in deinen Kanal.',
        'ההנחה של {discount}% על החודש הראשון של Relay עדיין מחכה לך.\n\nפרקים חדשים יחזרו להגיע כקובץ לכאן וכפוסט בערוץ שלך.'),
    'winbackOfferButton': (
        '⭐ Вернуть Relay −{discount}%',
        '⭐ Bring Relay back −{discount}%',
        '⭐ Voltar ao Relay −{discount}%',
        '⭐ Recuperar Relay −{discount}%',
        '⭐ Relay zurückholen −{discount}%',
        '⭐ להחזיר את Relay ‎−{discount}%'),
    'winbackPlain': (
        'Relay выключен, и новые выпуски ваших подкастов не приходят файлом.\n\nВернуть автодоставку можно в одно нажатие.',
        'Relay is off, and new episodes of your podcasts no longer arrive as files.\n\nBring auto-delivery back in one tap.',
        'O Relay está desligado, e os episódios novos dos seus podcasts não chegam mais como arquivo.\n\nReative a entrega automática com um toque.',
        'Relay está apagado y los episodios nuevos de tus pódcasts ya no llegan como archivo.\n\nRecupera la entrega automática con un toque.',
        'Relay ist aus, und neue Folgen deiner Podcasts kommen nicht mehr als Datei.\n\nHol dir die automatische Zustellung mit einem Tipp zurück.',
        'Relay כבוי, ופרקים חדשים של הפודקאסטים שלך כבר לא מגיעים כקובץ.\n\nאפשר להחזיר את המשלוח האוטומטי בלחיצה אחת.'),
    # D-3: what the plan brought, under its text (app/jobs/relay_remind.recap_text)
    'planRecap': (
        'Что вы уже получили с ботом:',
        'What the bot has brought you so far:',
        'O que o bot já trouxe para você:',
        'Lo que el bot ya te trajo:',
        'Was der Bot dir bisher gebracht hat:',
        'מה הבוט כבר הביא לך:'),
    'planRecapEpisodes': (
        '🎧 выпусков в чате: {n}',
        '🎧 episodes delivered: {n}',
        '🎧 episódios entregues: {n}',
        '🎧 episodios entregados: {n}',
        '🎧 zugestellte Folgen: {n}',
        '🎧 פרקים שנשלחו: {n}'),
    'planRecapShows': (
        '🎙 подкастов на автодоставке: {n}',
        '🎙 podcasts on auto-delivery: {n}',
        '🎙 podcasts com entrega automática: {n}',
        '🎙 pódcasts con entrega automática: {n}',
        '🎙 Podcasts mit automatischer Zustellung: {n}',
        '🎙 פודקאסטים במשלוח אוטומטי: {n}'),
    'planRecapSummaries': (
        '📝 ИИ-пересказов: {n}',
        '📝 AI summaries: {n}',
        '📝 resumos de IA: {n}',
        '📝 resúmenes con IA: {n}',
        '📝 KI-Zusammenfassungen: {n}',
        '📝 סיכומי AI: {n}'),
    # Under the plan's text at the end of a plan (app/service/payment/plan_end.py):
    # the user's podcasts that stop arriving as files, on {date} (D-3) or now (plan-off);
    # Muted: the weekly digest is off, so no text reminder either
    'planLossAt': (
        '🎙 С {date} новые выпуски {shows} будут приходить текстом раз в неделю, а не файлом.',
        '🎙 From {date}, new episodes of {shows} will come as a weekly text reminder, not as files.',
        '🎙 A partir de {date}, os episódios novos de {shows} chegarão como um lembrete semanal em texto, não como arquivo.',
        '🎙 Desde el {date}, los episodios nuevos de {shows} llegarán como un recordatorio semanal de texto, no como archivo.',
        '🎙 Ab dem {date} kommen neue Folgen von {shows} nur noch als wöchentliche Text-Erinnerung, nicht als Datei.',
        '🎙 החל מ-{date} פרקים חדשים של {shows} יגיעו כתזכורת טקסט שבועית ולא כקובץ.'),
    'planLossAtMuted': (
        '🎙 С {date} новые выпуски {shows} перестанут приходить файлом.',
        '🎙 From {date}, new episodes of {shows} will stop arriving as files.',
        '🎙 A partir de {date}, os episódios novos de {shows} deixarão de chegar como arquivo.',
        '🎙 Desde el {date}, los episodios nuevos de {shows} dejarán de llegar como archivo.',
        '🎙 Ab dem {date} kommen neue Folgen von {shows} nicht mehr als Datei.',
        '🎙 החל מ-{date} פרקים חדשים של {shows} יפסיקו להגיע כקובץ.'),
    'planLossNow': (
        '🎙 Теперь новые выпуски {shows} приходят текстом раз в неделю, а не файлом.',
        '🎙 New episodes of {shows} now come as a weekly text reminder, not as files.',
        '🎙 Agora os episódios novos de {shows} chegam como um lembrete semanal em texto, não como arquivo.',
        '🎙 Ahora los episodios nuevos de {shows} llegan como un recordatorio semanal de texto, no como archivo.',
        '🎙 Neue Folgen von {shows} kommen jetzt nur als wöchentliche Text-Erinnerung, nicht als Datei.',
        '🎙 מעכשיו פרקים חדשים של {shows} מגיעים כתזכורת טקסט שבועית ולא כקובץ.'),
    'planLossNowMuted': (
        '🎙 Новые выпуски {shows} больше не приходят файлом.',
        '🎙 New episodes of {shows} no longer arrive as files.',
        '🎙 Os episódios novos de {shows} não chegam mais como arquivo.',
        '🎙 Los episodios nuevos de {shows} ya no llegan como archivo.',
        '🎙 Neue Folgen von {shows} kommen nicht mehr als Datei.',
        '🎙 פרקים חדשים של {shows} כבר לא מגיעים כקובץ.'),
    'planLossShowsTwo': (
        '{a} и {b}',
        '{a} and {b}',
        '{a} e {b}',
        '{a} y {b}',
        '{a} und {b}',
        '{a} ו{b}'),
    'planLossShowsMore': (
        '{shows} и ещё {n}',
        '{shows} and {n} more',
        '{shows} e mais {n}',
        '{shows} y {n} más',
        '{shows} und {n} weiteren',
        '{shows} ועוד {n}'),
    'planLossMonths': (
        'января,февраля,марта,апреля,мая,июня,июля,августа,сентября,октября,ноября,декабря',
        'Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec',
        'janeiro,fevereiro,março,abril,maio,junho,julho,agosto,setembro,outubro,novembro,dezembro',
        'enero,febrero,marzo,abril,mayo,junio,julio,agosto,septiembre,octubre,noviembre,diciembre',
        'Januar,Februar,März,April,Mai,Juni,Juli,August,September,Oktober,November,Dezember',
        'ינואר,פברואר,מרץ,אפריל,מאי,יוני,יולי,אוגוסט,ספטמבר,אוקטובר,נובמבר,דצמבר'),
    'planLossDate': (
        '{d} {m}',
        '{m} {d}',
        '{d} de {m}',
        '{d} de {m}',
        '{d}. {m}',
        '{d} ב{m}'),
    # The end of a Relay trial: the win-back discount at once (plan_end.trial_offer)
    'trialOfferLine': (
        '🎁 Первый месяц Relay со скидкой {discount}%: {price} вместо {full}.',
        '🎁 Your first month of Relay is {discount}% off: {price} instead of {full}.',
        '🎁 O primeiro mês do Relay com {discount}% de desconto: {price} em vez de {full}.',
        '🎁 Tu primer mes de Relay con {discount}% de descuento: {price} en lugar de {full}.',
        '🎁 Dein erster Relay-Monat mit {discount}% Rabatt: {price} statt {full}.',
        '🎁 החודש הראשון של Relay בהנחה של {discount}%: ‎{price} במקום ‎{full}.'),
    'trialOfferButton': (
        '⭐ Relay −{discount}%: первый месяц за {price}',
        '⭐ Relay −{discount}%: first month for {price}',
        '⭐ Relay −{discount}%: primeiro mês por {price}',
        '⭐ Relay −{discount}%: primer mes por {price}',
        '⭐ Relay −{discount}%: erster Monat für {price}',
        '⭐ Relay ‎−{discount}%: חודש ראשון ב-‎{price}'),
    'offerNotAvailable': (
        'Это предложение уже недоступно.',
        'This offer is no longer available.',
        'Esta oferta não está mais disponível.',
        'Esta oferta ya no está disponible.',
        'Dieses Angebot ist nicht mehr verfügbar.',
        'ההצעה הזו כבר לא זמינה.'),
    # The Stars page: what a payment does, without a plan running and with one (it tops that plan up)
    'bot_sub_stars_page_body': (
        'Оплата Stars – в два тапа, не выходя из Telegram. Выбранный план включится сразу и дальше будет '
        'продлеваться с баланса каждые 30 дней, пока на нём хватает денег.\n1000 ⭐ ≈ ${rate}.',
        'Pay with Stars in two taps without leaving Telegram. The plan you pick turns on at once and then renews '
        'from your balance every 30 days while the balance covers it.\n1000 ⭐ ≈ ${rate}.',
        'Pague com Stars em dois toques, sem sair do Telegram. O plano escolhido é ativado na hora e depois renova '
        'pelo saldo a cada 30 dias, enquanto o saldo cobrir.\n1000 ⭐ ≈ US${rate}.',
        'Paga con Stars en dos toques, sin salir de Telegram. El plan que elijas se activa al momento y luego se '
        'renueva con el saldo cada 30 días mientras alcance.\n1000 ⭐ ≈ ${rate}.',
        'Mit Stars in zwei Taps zahlen, ohne Telegram zu verlassen. Der gewählte Tarif startet sofort und verlängert '
        'sich dann alle 30 Tage aus dem Guthaben, solange es reicht.\n1000 ⭐ ≈ ${rate}.',
        'תשלום ב-Stars בשתי הקשות, בלי לצאת מטלגרם. המסלול שתבחרו יופעל מיד ויתחדש מהיתרה כל 30 יום, כל עוד '
        'היא מספיקה.\n1000 ⭐ ≈ ${rate}.'),
    'bot_sub_stars_page_running': (
        'Оплата Stars – в два тапа, не выходя из Telegram. Деньги идут на баланс, с него {plan} продлевается '
        'каждые 30 дней. Другой план включается кнопкой "Сменить план".\n1000 ⭐ ≈ ${rate}.',
        'Pay with Stars in two taps without leaving Telegram. The money goes to your balance, and {plan} renews '
        'from it every 30 days. Another plan is switched on with "Change plan".\n1000 ⭐ ≈ ${rate}.',
        'Pague com Stars em dois toques, sem sair do Telegram. O dinheiro vai para o saldo, e o {plan} renova por '
        'ele a cada 30 dias. Outro plano se ativa em "Mudar de plano".\n1000 ⭐ ≈ US${rate}.',
        'Paga con Stars en dos toques, sin salir de Telegram. El dinero va al saldo y {plan} se renueva con él cada '
        '30 días. Otro plan se activa con "Cambiar plan".\n1000 ⭐ ≈ ${rate}.',
        'Mit Stars in zwei Taps zahlen, ohne Telegram zu verlassen. Das Geld geht aufs Guthaben, daraus verlängert '
        'sich {plan} alle 30 Tage. Einen anderen Tarif startest du mit "Tarif wechseln".\n1000 ⭐ ≈ ${rate}.',
        'תשלום ב-Stars בשתי הקשות, בלי לצאת מטלגרם. הכסף נכנס ליתרה, וממנה {plan} מתחדש כל 30 יום. מסלול אחר '
        'מפעילים דרך "שנה מסלול".\n1000 ⭐ ≈ ${rate}.'),
    # Under "not enough on the balance" (the change-plan page): to the Stars page
    'topUpStarsButton': (
        '⭐ Пополнить баланс – Telegram Stars',
        '⭐ Top up with Telegram Stars',
        '⭐ Recarregar com Telegram Stars',
        '⭐ Recargar con Telegram Stars',
        '⭐ Mit Telegram Stars aufladen',
        '⭐ הטענה ב-Telegram Stars'),
    # The change-plan page asks before a cheaper plan or off (paymentModule.downgrade_text)
    'planDowngradeAsk': (
        '<b>Сменить план: {current} → {plan}?</b>',
        '<b>Change plan: {current} → {plan}?</b>',
        '<b>Mudar de plano: {current} → {plan}?</b>',
        '<b>¿Cambiar de plan: {current} → {plan}?</b>',
        '<b>Tarif wechseln: {current} → {plan}?</b>',
        '<b>לעבור מ-{current} ל-{plan}?</b>'),
    'planDowngradeDays': (
        'Осталось дней: {days}, они сохранятся на новом плане.',
        'Days left: {days}, they stay on the new plan.',
        'Dias restantes: {days}, eles ficam no novo plano.',
        'Días restantes: {days}, se quedan en el nuevo plan.',
        'Verbleibende Tage: {days}, sie bleiben im neuen Tarif.',
        'ימים שנותרו: {days}, הם נשארים במסלול החדש.'),
    'planOffAsk': (
        '<b>Отключить план {current}?</b>',
        '<b>Turn {current} off?</b>',
        '<b>Desativar {current}?</b>',
        '<b>¿Desactivar {current}?</b>',
        '<b>{current} deaktivieren?</b>',
        '<b>להשבית את {current}?</b>'),
    'planOffWhat': (
        'Новые выпуски перестанут приходить файлами сами: без плана – раз в неделю список новых.',
        'New episodes stop arriving as files on their own: without a plan you get a weekly list of new ones.',
        'Os episódios novos deixam de chegar como arquivo sozinhos: sem plano, uma lista semanal dos novos.',
        'Los episodios nuevos dejan de llegar solos como archivo: sin plan, una lista semanal de los nuevos.',
        'Neue Folgen kommen nicht mehr von selbst als Datei: ohne Tarif gibt es wöchentlich eine Liste der neuen.',
        'פרקים חדשים יפסיקו להגיע לבד כקובץ: בלי מסלול תקבלו פעם בשבוע רשימה של החדשים.'),
    'planDowngradeRefund': (
        'На баланс вернётся ${refund} – половина разницы в цене за эти дни.',
        '${refund} comes back to your balance: half of the price difference for these days.',
        'US${refund} voltam para o saldo: metade da diferença de preço por esses dias.',
        'Vuelven al saldo ${refund}: la mitad de la diferencia de precio por estos días.',
        '${refund} gehen zurück aufs Guthaben: die Hälfte des Preisunterschieds für diese Tage.',
        '‎${refund} יחזרו ליתרה: חצי מהפרש המחיר על הימים האלה.'),
    'starsRefunded': (
        'Telegram вернул ваш платёж в Stars: с баланса списано ${amount}.',
        'Telegram returned your Stars payment: ${amount} is taken off your balance.',
        'O Telegram devolveu seu pagamento em Stars: US${amount} saíram do saldo.',
        'Telegram devolvió tu pago en Stars: se descontaron ${amount} de tu saldo.',
        'Telegram hat deine Stars-Zahlung zurückerstattet: ${amount} wurden vom Guthaben abgezogen.',
        'Telegram החזיר את התשלום שלכם ב-Stars: ‎${amount} ירדו מהיתרה.'),
    'starsRefundDays': (
        'План теряет дни, оплаченные этим платежом. Дней осталось: {days}.',
        'Your plan loses the days that payment bought. Days left: {days}.',
        'Seu plano perde os dias que esse pagamento comprou. Dias restantes: {days}.',
        'Tu plan pierde los días que compró ese pago. Días restantes: {days}.',
        'Dein Tarif verliert die Tage, die diese Zahlung bezahlt hat. Verbleibende Tage: {days}.',
        'המסלול מאבד את הימים שהתשלום הזה קנה. ימים שנותרו: {days}.'),
    'starsRefundPlanOff': (
        'План закончился: он был оплачен этим платежом.',
        'Your plan has ended: that payment paid for it.',
        'Seu plano terminou: era esse pagamento que o cobria.',
        'Tu plan terminó: era ese pago el que lo cubría.',
        'Dein Tarif ist beendet: Er war mit dieser Zahlung bezahlt.',
        'המסלול הסתיים: התשלום הזה הוא ששילם עליו.'),
    'starsRefundDebt': (
        'Баланс: −${debt}. Следующий платёж сначала покроет его.',
        'Balance: −${debt}. The next payment covers this first.',
        'Saldo: −US${debt}. O próximo pagamento cobre isso primeiro.',
        'Saldo: −${debt}. El próximo pago cubre esto primero.',
        'Guthaben: −${debt}. Die nächste Zahlung deckt das zuerst.',
        'יתרה: ‎−${debt}. התשלום הבא יכסה את זה קודם.'),
    'planDowngradeBack': (
        'Вернуться на план {current} до конца срока будет стоить ${back}.',
        'Going back to {current} before the period ends will cost ${back}.',
        'Voltar para {current} antes do fim do período custará US${back}.',
        'Volver a {current} antes de que acabe el periodo costará ${back}.',
        'Zurück zu {current} vor Ende des Zeitraums kostet ${back}.',
        'חזרה ל-{current} לפני סוף התקופה תעלה ‎${back}.'),
    'planDowngradeStarsSub': (
        'Подписка Stars на план {current} отменится.',
        'Your Stars subscription to {current} will be canceled.',
        'Sua assinatura em Stars do {current} será cancelada.',
        'Tu suscripción con Stars a {current} se cancelará.',
        'Dein Stars-Abo für {current} wird gekündigt.',
        'המנוי ב-Stars ל-{current} יבוטל.'),
    'planDowngradeYes': (
        '✓ Да, сменить план',
        '✓ Yes, change plan',
        '✓ Sim, mudar de plano',
        '✓ Sí, cambiar de plan',
        '✓ Ja, Tarif wechseln',
        '✓ כן, לשנות מסלול'),
    'planOffYes': (
        '✓ Отключить',
        '✓ Turn off',
        '✓ Desativar',
        '✓ Desactivar',
        '✓ Deaktivieren',
        '✓ להשבית'),
    # Not enough on the balance for the plan tapped on the change-plan page (a Stars button under it)
    'notEnoughMoneyToActivate': (
        'На балансе не хватает ${missing}, чтобы перейти на этот план до конца срока. Пополните баланс и нажмите '
        'план ещё раз.',
        'Your balance is ${missing} short of this plan for the rest of the period. Top up, then tap the plan again.',
        'Faltam US${missing} no saldo para este plano até o fim do período. Recarregue e toque no plano de novo.',
        'Faltan ${missing} en el saldo para este plan hasta el final del periodo. Recarga y vuelve a tocar el plan.',
        'Dem Guthaben fehlen ${missing} für diesen Tarif bis zum Ende des Zeitraums. Lade auf und tippe den Tarif '
        'noch einmal an.',
        'חסרים ביתרה ‎${missing} למסלול הזה עד סוף התקופה. הטעינו ולחצו על המסלול שוב.'),
    'tariffActivatedNotEnoughMoney': (
        'Этот план выбран, но не включён: на балансе не хватает ${missing}. Пополните баланс – и план включится.',
        'This plan is chosen but not on: your balance is ${missing} short. Top up and the plan turns on.',
        'Este plano está escolhido, mas não ativo: faltam US${missing} no saldo. Recarregue e o plano será ativado.',
        'Este plan está elegido, pero no activo: faltan ${missing} en el saldo. Recarga y el plan se activa.',
        'Dieser Tarif ist gewählt, aber nicht aktiv: dem Guthaben fehlen ${missing}. Lade auf, dann startet er.',
        'המסלול הזה נבחר אבל לא פעיל: חסרים ביתרה ‎${missing}. הטעינו והמסלול יופעל.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
