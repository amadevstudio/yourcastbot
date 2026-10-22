"""Copy for Relay by a Telegram Stars subscription (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'starsSubButton': (
        '🔁 Relay по подписке: продлевается сам',
        '🔁 Relay by subscription: renews itself',
        '🔁 Relay por assinatura: renova sozinho',
        '🔁 Relay por suscripción: se renueva solo',
        '🔁 Relay im Abo: verlängert sich selbst',
        '🔁 Relay במנוי: מתחדש לבד'),
    'starsSubPriceButton': (
        '🔁 Relay по подписке – {stars} ⭐ в месяц',
        '🔁 Relay by subscription – {stars} ⭐ a month',
        '🔁 Relay por assinatura – {stars} ⭐ por mês',
        '🔁 Relay por suscripción – {stars} ⭐ al mes',
        '🔁 Relay im Abo – {stars} ⭐ pro Monat',
        '🔁 Relay במנוי – {stars} ⭐ לחודש'),
    'starsSubOffer': (
        '<b>Relay по подписке</b>\n\n'
        '{stars} ⭐ раз в 30 дней, Telegram списывает их сам. Тариф продлевается без напоминаний '
        'и оплат вручную.\n\n'
        'Отменить можно в любой момент в Telegram: Настройки → Мои звёзды.',
        '<b>Relay by subscription</b>\n\n'
        '{stars} ⭐ every 30 days, charged by Telegram. Your plan renews with no reminders '
        'and no payments by hand.\n\n'
        'Cancel any time in Telegram: Settings → My Stars.',
        '<b>Relay por assinatura</b>\n\n'
        '{stars} ⭐ a cada 30 dias, cobrados pelo Telegram. O plano renova sem lembretes '
        'e sem pagamentos manuais.\n\n'
        'Cancele quando quiser no Telegram: Configurações → Minhas Estrelas.',
        '<b>Relay por suscripción</b>\n\n'
        '{stars} ⭐ cada 30 días, los cobra Telegram. El plan se renueva sin recordatorios '
        'ni pagos a mano.\n\n'
        'Cancela cuando quieras en Telegram: Ajustes → Mis Estrellas.',
        '<b>Relay im Abo</b>\n\n'
        '{stars} ⭐ alle 30 Tage, Telegram bucht sie ab. Der Tarif verlängert sich ohne Erinnerungen '
        'und ohne Zahlungen von Hand.\n\n'
        'Jederzeit kündbar in Telegram: Einstellungen → Meine Sterne.',
        '<b>Relay במנוי</b>\n\n'
        '{stars} ⭐ כל 30 יום, טלגרם גובה אותם. התוכנית מתחדשת בלי תזכורות ובלי תשלומים ידניים.\n\n'
        'אפשר לבטל בכל רגע בטלגרם: הגדרות ← הכוכבים שלי.'),
    'starsSubPayButton': (
        '⭐ Подписаться – {stars} ⭐ в месяц',
        '⭐ Subscribe – {stars} ⭐ a month',
        '⭐ Assinar – {stars} ⭐ por mês',
        '⭐ Suscribirse – {stars} ⭐ al mes',
        '⭐ Abonnieren – {stars} ⭐ pro Monat',
        '⭐ להירשם – {stars} ⭐ לחודש'),
    'starsSubTitle': (
        'Relay: подписка на месяц',
        'Relay: monthly subscription',
        'Relay: assinatura mensal',
        'Relay: suscripción mensual',
        'Relay: Monatsabo',
        'Relay: מנוי חודשי'),
    'starsSubDescription': (
        'Relay на 30 дней, продлевается каждый месяц сам. Отмена в любой момент: Настройки → Мои звёзды.',
        'Relay for 30 days, renewed every month by itself. Cancel any time: Settings → My Stars.',
        'Relay por 30 dias, renovado todo mês sozinho. Cancele quando quiser: Configurações → Minhas Estrelas.',
        'Relay por 30 días, se renueva cada mes solo. Cancela cuando quieras: Ajustes → Mis Estrellas.',
        'Relay für 30 Tage, verlängert sich jeden Monat selbst. Jederzeit kündbar: Einstellungen → Meine Sterne.',
        'Relay ל-30 יום, מתחדש כל חודש לבד. ביטול בכל רגע: הגדרות ← הכוכבים שלי.'),
    'starsSubActive': (
        'Подписка на Relay уже действует',
        'Your Relay subscription is already active',
        'Sua assinatura do Relay já está ativa',
        'Tu suscripción a Relay ya está activa',
        'Dein Relay-Abo ist bereits aktiv',
        'המנוי שלך ל-Relay כבר פעיל'),
    'starsSubNotForPlan': (
        'Подписка продлевает Relay. Сначала смените тариф на Relay.',
        'A subscription renews Relay. Switch your plan to Relay first.',
        'A assinatura renova o Relay. Mude seu plano para Relay primeiro.',
        'La suscripción renueva Relay. Cambia tu plan a Relay primero.',
        'Das Abo verlängert Relay. Wechsle zuerst zu Relay.',
        'המנוי מחדש את Relay. קודם עברו לתוכנית Relay.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
