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
    'starsBundleButton': (
        '📅 Relay на {months} мес. · −{discount}% · {stars} ⭐',
        '📅 Relay for {months} mo · −{discount}% · {stars} ⭐',
        '📅 Relay por {months} meses · −{discount}% · {stars} ⭐',
        '📅 Relay por {months} meses · −{discount}% · {stars} ⭐',
        '📅 Relay für {months} Monate · −{discount}% · {stars} ⭐',
        '📅 Relay ל-{months} חודשים · −{discount}% · {stars} ⭐'),
    'telegram_stars_bundle_description': (
        'Relay на {months} мес. со скидкой {discount}%: на баланс {balance}$ за {stars} ⭐. Продление каждый месяц с баланса. Курс: 1000 ⭐ ≈ {rate}$.',
        'Relay for {months} months, {discount}% off: ${balance} to your balance for {stars} ⭐. Renews monthly from the balance. Rate: 1000 ⭐ ≈ ${rate}.',
        'Relay por {months} meses com {discount}% de desconto: US${balance} no saldo por {stars} ⭐. Renova todo mês pelo saldo. Câmbio: 1000 ⭐ ≈ US${rate}.',
        'Relay por {months} meses con {discount}% de descuento: {balance} US$ al saldo por {stars} ⭐. Se renueva cada mes desde el saldo. Cambio: 1000 ⭐ ≈ {rate} US$.',
        'Relay für {months} Monate mit {discount}% Rabatt: {balance} $ Guthaben für {stars} ⭐. Verlängert sich monatlich aus dem Guthaben. Kurs: 1000 ⭐ ≈ {rate} $.',
        'Relay ל-{months} חודשים בהנחה של {discount}%: ‎${balance} ליתרה תמורת {stars} ⭐. מתחדש כל חודש מהיתרה. שער: 1000 ⭐ ≈ ‎${rate}.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
