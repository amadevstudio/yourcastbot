"""Copy for the pay menus (subscription / one-time) and plans by a Telegram Stars subscription (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'payRecurringButton': (
        '🔁 Подписка: продлевается сама',
        '🔁 Subscription: renews itself',
        '🔁 Assinatura: renova sozinha',
        '🔁 Suscripción: se renueva sola',
        '🔁 Abo: verlängert sich selbst',
        '🔁 מנוי: מתחדש לבד'),
    'payOnceButton': (
        '💳 Разовая оплата',
        '💳 One-time payment',
        '💳 Pagamento único',
        '💳 Pago único',
        '💳 Einmalzahlung',
        '💳 תשלום חד-פעמי'),
    'payRecurringBody': (
        '<b>Подписка</b>\n\nПлатёж списывается сам раз в месяц, тариф продлевается без напоминаний. '
        'Отменить можно в любой момент.',
        '<b>Subscription</b>\n\nThe payment is charged once a month by itself and your plan renews '
        'with no reminders. Cancel any time.',
        '<b>Assinatura</b>\n\nO pagamento é cobrado sozinho uma vez por mês e o plano renova '
        'sem lembretes. Cancele quando quiser.',
        '<b>Suscripción</b>\n\nEl pago se cobra solo una vez al mes y el plan se renueva '
        'sin recordatorios. Cancela cuando quieras.',
        '<b>Abo</b>\n\nDie Zahlung wird einmal im Monat selbst abgebucht, der Tarif verlängert sich '
        'ohne Erinnerungen. Jederzeit kündbar.',
        '<b>מנוי</b>\n\nהתשלום נגבה לבד פעם בחודש והתוכנית מתחדשת בלי תזכורות. אפשר לבטל בכל רגע.'),
    'payOnceBody': (
        '<b>Разовая оплата</b>\n\nПополните баланс один раз: тариф продлевается с него, пока хватает.',
        '<b>One-time payment</b>\n\nTop up your balance once: the plan renews from it while it lasts.',
        '<b>Pagamento único</b>\n\nRecarregue o saldo uma vez: o plano renova com ele enquanto durar.',
        '<b>Pago único</b>\n\nRecarga el saldo una vez: el plan se renueva con él mientras alcance.',
        '<b>Einmalzahlung</b>\n\nLade dein Guthaben einmal auf: der Tarif verlängert sich davon, solange es reicht.',
        '<b>תשלום חד-פעמי</b>\n\nטענו את היתרה פעם אחת: התוכנית מתחדשת ממנה כל עוד היא מספיקה.'),
    'starsSubPlanButton': (
        '⭐ {plan} – {stars} ⭐ в месяц',
        '⭐ {plan} – {stars} ⭐ a month',
        '⭐ {plan} – {stars} ⭐ por mês',
        '⭐ {plan} – {stars} ⭐ al mes',
        '⭐ {plan} – {stars} ⭐ pro Monat',
        '⭐ {plan} – {stars} ⭐ לחודש'),
    'starsSubActiveUntil': (
        '🔁 Ваша подписка звёздами действует, следующее списание {date}.',
        '🔁 Your Stars subscription is active, next charge on {date}.',
        '🔁 Sua assinatura com Estrelas está ativa, próxima cobrança em {date}.',
        '🔁 Tu suscripción con Estrellas está activa, próximo cobro el {date}.',
        '🔁 Dein Sterne-Abo ist aktiv, nächste Abbuchung am {date}.',
        '🔁 המנוי שלך בכוכבים פעיל, החיוב הבא ב-{date}.'),
    'starsSubButton': (
        '🔁 Оформить подписку: тариф продлевается сам',
        '🔁 Subscribe: the plan renews itself',
        '🔁 Assinar: o plano renova sozinho',
        '🔁 Suscribirse: el plan se renueva solo',
        '🔁 Abonnieren: der Tarif verlängert sich selbst',
        '🔁 להירשם למנוי: התוכנית מתחדשת לבד'),
    'starsSubOffer': (
        '<b>Подписка: {plan}</b>\n\n'
        '{stars} ⭐ раз в 30 дней, Telegram списывает их сам. Тариф продлевается без напоминаний '
        'и оплат вручную.\n\n'
        'Отменить можно в любой момент в Telegram: Настройки → Мои звёзды.',
        '<b>Subscription: {plan}</b>\n\n'
        '{stars} ⭐ every 30 days, charged by Telegram. Your plan renews with no reminders '
        'and no payments by hand.\n\n'
        'Cancel any time in Telegram: Settings → My Stars.',
        '<b>Assinatura: {plan}</b>\n\n'
        '{stars} ⭐ a cada 30 dias, cobrados pelo Telegram. O plano renova sem lembretes '
        'e sem pagamentos manuais.\n\n'
        'Cancele quando quiser no Telegram: Configurações → Minhas Estrelas.',
        '<b>Suscripción: {plan}</b>\n\n'
        '{stars} ⭐ cada 30 días, los cobra Telegram. El plan se renueva sin recordatorios '
        'ni pagos a mano.\n\n'
        'Cancela cuando quieras en Telegram: Ajustes → Mis Estrellas.',
        '<b>Abo: {plan}</b>\n\n'
        '{stars} ⭐ alle 30 Tage, Telegram bucht sie ab. Der Tarif verlängert sich ohne Erinnerungen '
        'und ohne Zahlungen von Hand.\n\n'
        'Jederzeit kündbar in Telegram: Einstellungen → Meine Sterne.',
        '<b>מנוי: {plan}</b>\n\n'
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
        'Подписка: {plan}',
        'Subscription: {plan}',
        'Assinatura: {plan}',
        'Suscripción: {plan}',
        'Abo: {plan}',
        'מנוי: {plan}'),
    'starsSubDescription': (
        '{plan} на 30 дней, продлевается каждый месяц сам. Отмена в любой момент: Настройки → Мои звёзды.',
        '{plan} for 30 days, renewed every month by itself. Cancel any time: Settings → My Stars.',
        '{plan} por 30 dias, renovado todo mês sozinho. Cancele quando quiser: Configurações → Minhas Estrelas.',
        '{plan} por 30 días, se renueva cada mes solo. Cancela cuando quieras: Ajustes → Mis Estrellas.',
        '{plan} für 30 Tage, verlängert sich jeden Monat selbst. Jederzeit kündbar: Einstellungen → Meine Sterne.',
        '{plan} ל-30 יום, מתחדש כל חודש לבד. ביטול בכל רגע: הגדרות ← הכוכבים שלי.'),
    'starsSubActive': (
        'Подписка уже действует',
        'Your subscription is already active',
        'Sua assinatura já está ativa',
        'Tu suscripción ya está activa',
        'Dein Abo ist bereits aktiv',
        'המנוי שלך כבר פעיל'),
    'starsSubNotForPlan': (
        'Подписка продлевает тариф, за который платите. Сначала перейдите на этот тариф.',
        'A subscription renews the plan you pay for. Switch to that plan first.',
        'A assinatura renova o plano que você paga. Mude para esse plano primeiro.',
        'La suscripción renueva el plan que pagas. Cambia a ese plan primero.',
        'Das Abo verlängert den Tarif, den du zahlst. Wechsle zuerst zu diesem Tarif.',
        'המנוי מחדש את התוכנית שעליה משלמים. קודם עברו לתוכנית הזו.'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
