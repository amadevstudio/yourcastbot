# -*- coding: utf-8 -*-
"""Translations for `messages` that the main table lacked (pt-BR, es, de, he).

Merged by `messages.py` with setdefault, so a text written there wins. English
is the source; every %s, {name} and HTML tag stays as it is in English
(`test_translations_complete.py` checks it).
"""

EXTRA_TRANSLATIONS = {
    "privacy": {
        "pt-BR": "Armazenamos alguns dos seus dados para prestar o serviço: id do Telegram, seu nome, apelido, idioma e todos os dados informados no bot, por exemplo, a lista de podcasts que você assina, avaliações de podcasts, identificadores de canais e assim por diante.\n\nNão compartilhamos esses dados com ninguém, exceto quando são usados na interface do bot.",
        "es": "Guardamos algunos de sus datos para prestar el servicio: id de Telegram, su nombre, apodo, idioma y todos los datos indicados en el bot, por ejemplo, la lista de podcasts a los que se ha suscrito, las valoraciones de podcasts, los identificadores de canales, etc.\n\nNo compartimos estos datos con nadie, salvo cuando se usan en la interfaz del bot.",
        "de": "Wir speichern einige deiner Daten, um den Dienst bereitzustellen: Telegram-ID, deinen Namen, Nicknamen, die Sprache sowie alle im Bot angegebenen Daten, zum Beispiel die Liste der abonnierten Podcasts, Podcast-Bewertungen, Kanalkennungen und so weiter.\n\nWir geben diese Daten an niemanden weiter, außer wenn sie in der Bot-Oberfläche verwendet werden.",
        "he": "אנו שומרים חלק מהנתונים שלך כדי לספק את השירות: מזהה טלגרם, שמך, כינוי, שפה, וכן כל הנתונים שצוינו בבוט, למשל רשימת הפודקאסטים שנרשמת אליהם, דירוגי פודקאסטים, מזהי ערוצים וכן הלאה.\n\nאיננו משתפים נתונים אלה עם איש, מלבד המקרים שבהם הם משמשים בממשק הבוט.",
    },
    "or": {"es": "o", "de": "oder", "he": "או"},
    "weAlsoSignedYouOnPodcastName": {
        "es": "También le suscribimos a <a href='http://t.me/%s?start=podcast_%s'>%s</a>",
        "de": "Wir haben dich außerdem für <a href='http://t.me/%s?start=podcast_%s'>%s</a> angemeldet",
        "he": "רשמנו אותך גם ל-<a href='http://t.me/%s?start=podcast_%s'>%s</a>",
    },
    "dontForgetToVisitStart": {
        "es": "No olvide visitar la página de inicio /start",
        "de": "Vergiss nicht, die Startseite /start zu besuchen",
        "he": "אל תשכח לבקר בעמוד הפתיחה /start",
    },
    "showFileSizes": {
        "pt-BR": "Tamanhos dos arquivos",
        "es": "Tamaños de archivo",
        "de": "Dateigrößen",
        "he": "גדלי קבצים",
    },
    "amountTooSmall": {
        "es": "El importe es demasiado pequeño",
        "de": "Der Betrag ist zu klein",
        "he": "הסכום קטן מדי",
    },
    "notFoundOrFuture": {
        "es": "No se encontró el episodio (se eliminó o cambió) o ya llegó a la última publicación.",
        "de": "Die Folge wurde nicht gefunden (gelöscht oder geändert) oder du hast die neueste Veröffentlichung erreicht.",
        "he": "הפרק לא נמצא (נמחק או השתנה), או שהגעת לפרסום האחרון.",
    },
    "taskAddedToQueue": {
        "pt-BR": "Tarefa adicionada à fila",
        "es": "Tarea añadida a la cola",
        "de": "Aufgabe zur Warteschlange hinzugefügt",
        "he": "המשימה נוספה לתור",
    },
    "updateInProgress": {
        "es": "Actualización en curso, espere, por favor",
        "de": "Aktualisierung läuft, bitte warten",
        "he": "העדכון מתבצע, נא להמתין",
    },
    "exitSearchMode": {
        "pt-BR": "🆑 Limpar busca",
        "es": "🆑 Borrar búsqueda",
        "de": "🆑 Suche zurücksetzen",
        "he": "🆑 נקה חיפוש",
    },
    "channelConnect": {
        "es": "🔌 Canales conectados",
        "de": "🔌 Verbundene Kanäle",
        "he": "🔌 ערוצים מחוברים",
    },
    "wrongUrl": {
        "pt-BR": "O link não corresponde ao formato",
        "es": "El enlace no tiene el formato correcto",
        "de": "Der Link entspricht nicht dem Format",
        "he": "הקישור אינו תואם לפורמט",
    },
    "loadNextRecord": {
        "es": "Siguiente episodio",
        "de": "Nächste Folge",
        "he": "הפרק הבא",
    },
    "podcastTop": {
        "es": "👑 Top de podcasts 🌍",
        "de": "👑 Top-Podcasts 🌍",
        "he": "👑 הפודקאסטים המובילים 🌍",
    },
    "podcastTopLang": {
        "es": "👑 Top local",
        "de": "👑 Lokale Top-Liste",
        "he": "👑 המובילים המקומיים",
    },
    "generalTop": {
        "es": "🔝 Top general",
        "de": "🔝 Allgemeine Top-Liste",
        "he": "🔝 המובילים הכלליים",
    },
    "advertisingQuestions": {
        "pt-BR": "Para questões de publicidade, escreva para %s",
        "es": "Para consultas de publicidad, escriba a %s",
        "de": "Bei Werbeanfragen schreibe an %s",
        "he": "לשאלות פרסום יש לכתוב אל %s",
    },
    "searchResultsNotFound": {
        "pt-BR": "Nada encontrado, tente outra pesquisa",
        "es": "No se encontró nada, pruebe con otra búsqueda",
        "de": "Nichts gefunden, versuche eine andere Suchanfrage",
        "he": "לא נמצא דבר, נסה חיפוש אחר",
    },
    "proTipSendPageNumToGo": {
        "es": "Consejo: envíe el número de página para ir a ella",
        "de": "Profi-Tipp: Sende die Seitenzahl, um direkt dorthin zu springen",
        "he": "טיפ: שלח את מספר העמוד כדי לעבור אליו",
    },
    "proTipSendPageNumToGoWithSearch": {
        "es": "Consejo: envíe el número de página para ir a ella\n🔍 Envíe un texto para empezar a buscar",
        "de": "Profi-Tipp: Sende die Seitenzahl, um direkt dorthin zu springen\n🔍 Sende einen Text, um die Suche zu starten",
        "he": "טיפ: שלח את מספר העמוד כדי לעבור אליו\n🔍 שלח טקסט כדי להתחיל בחיפוש",
    },
    "sendTextToRestartSearch": {
        "pt-BR": "🔍 Envie um texto para iniciar uma nova busca",
        "es": "🔍 Envíe un texto para iniciar una nueva búsqueda",
        "de": "🔍 Sende einen Text, um eine neue Suche zu starten",
        "he": "🔍 שלח טקסט כדי להתחיל חיפוש חדש",
    },
    "youHaveNewEpisodesShort": {
        "es": "<b>¡Tiene episodios nuevos!</b>",
        "de": "<b>Du hast neue Folgen!</b>",
        "he": "<b>יש לך פרקים חדשים!</b>",
    },
    "withoutTariffUpdateLimited": {
        "es": "Sin Relay, la actualización manual está limitada a 15 podcasts. Relay: /subscription\n\nTambién puede apoyar este bot: /donate o [Patreon.com](https://example.invalid/donate)",
        "de": "Ohne Relay ist die manuelle Aktualisierung auf 15 Podcasts begrenzt. Relay: /subscription\n\nDu kannst diesen Bot auch unterstützen: /donate oder [Patreon.com](https://example.invalid/donate)",
        "he": "ללא Relay העדכון הידני מוגבל ל-15 פודקאסטים. Relay: /subscription\n\nאפשר גם לתמוך בבוט הזה: /donate או [Patreon.com](https://example.invalid/donate)",
    },
    "withoutTariffCantChooseBitrate": {
        "pt-BR": "É necessária uma assinatura do bot para alterar a taxa de bits. Mais informações: /subscription",
        "es": "Se necesita una suscripción al bot para cambiar la tasa de bits. Más información: /subscription",
        "de": "Für die Änderung der Bitrate ist ein Bot-Abonnement erforderlich. Mehr Infos: /subscription",
        "he": "נדרש מינוי לבוט כדי לשנות את קצב הסיביות. מידע נוסף: /subscription",
    },
    "youAlreadySubscribedOnTariff": {"es": "Ya está suscrito a este plan"},
    "tariffActivatedNotEnoughMoney": {
        "es": "Ya se suscribió a este plan, pero aún no está activado. \nPara activarlo, debe añadir %s a su saldo💲(dólares).",
    },
    "notEnoughMoneyToActivate": {
        "es": "Fondos insuficientes para activar el plan.\nPara activarlo por completo, debe añadir %s a su saldo💲(dólares).",
        "he": "אין מספיק כספים להפעלת המסלול.\nכדי להפעיל אותו במלואו יש להוסיף %s ליתרה שלך💲(דולרים).",
    },
    "tariffSuccessChanged": {"es": "¡El plan se aplicó correctamente!"},
    "tariffNotActive": {"es": "¡El plan no está activado! Para activarlo, recargue su saldo"},
    "bot_subscription": {"es": "💳 Suscripción"},
    "pay": {
        "es": "💸 Pagar",
        "de": "💸 Bezahlen",
        "he": "💸 לתשלום",
    },
    "donate_page_body": {
        "es": "La suscripción le da acceso a todas las funciones\n\nHay varios planes. Véalos pulsando el botón \"Elegir plan\".\n\n<b>¡Atención! Cualquier recarga de la cuenta se considera una donación.</b> Los dólares del sistema son puntos virtuales que se otorgan por donaciones; no se consideran dinero, su cambio equivale al dólar estadounidense y pertenecen al propietario del bot, no a los usuarios.",
        "de": "Mit dem Abonnement erhältst du Zugriff auf alle Funktionen\n\nEs gibt mehrere Tarife. Sieh sie dir über die Schaltfläche \"Tarif wählen\" an.\n\n<b>Achtung! Jede Aufladung des Kontos gilt als Spende!</b> Dollar im System sind virtuelle Punkte, die für Spenden vergeben werden. Sie gelten nicht als Geld, ihr Kurs entspricht dem US-Dollar, und sie gehören dem Bot-Betreiber, nicht den Nutzern.",
        "he": "המינוי נותן גישה לכל התכונות\n\nיש כמה מסלולים. אפשר לעיין בהם בלחיצה על הכפתור \"בחירת מסלול\".\n\n<b>שימו לב! כל הטענת חשבון נחשבת לתרומה!</b> דולרים במערכת הם נקודות וירטואליות שמוענקות בעבור תרומות, הן אינן נחשבות לכסף, שערן שווה לדולר האמריקאי, והן שייכות לבעל הבוט ולא למשתמשים.",
    },
    "payViaCryptoBot": {
        "es": "Recargar saldo con Crypto Bot",
        "de": "Guthaben über Crypto Bot aufladen",
        "he": "טעינת יתרה דרך Crypto Bot",
    },
    "telegram_stars_invoice_error": {
        "es": "No se pudo crear la factura de Telegram Stars. Inténtelo de nuevo más tarde.",
        "de": "Die Telegram-Stars-Rechnung konnte nicht erstellt werden. Bitte versuche es später erneut.",
        "he": "לא ניתן היה ליצור חשבונית Telegram Stars. נסה שוב מאוחר יותר.",
    },
    "bot_sub_cryptobot_page_body": {
        "pt-BR": "Selecione a criptomoeda que você tem na sua conta do Crypto Bot\n\nMais detalhes: @cryptobot",
        "es": "Seleccione la criptomoneda que tiene en su cuenta de Crypto Bot\n\nMás detalles: @cryptobot",
        "de": "Wähle die Kryptowährung, die du auf deinem Crypto-Bot-Konto hast\n\nMehr Details: @cryptobot",
        "he": "בחר את המטבע הדיגיטלי שיש לך בחשבון Crypto Bot\n\nפרטים נוספים: @cryptobot",
    },
    "bot_sub_cryptobot_amount_input": {
        "es": "Introduzca el importe con el que desea recargar el saldo del bot en USD 💲(dólares)",
        "de": "Gib den Betrag ein, um den du dein Bot-Guthaben in USD aufladen möchtest 💲(Dollar)",
        "he": "הזן את הסכום שברצונך להטעין ליתרת הבוט ב-USD 💲(דולרים)",
    },
    "cryptobot_generated_link_page": {
        "es": "Va a recargar el saldo del bot con {summa}💲(dólares) usando {assetAmount} {asset}\n\nTipo de cambio: 1 {asset} = {exchangeRateUSD}$ (dólares)\n\nPulse el enlace para realizar el pago: {paymentLink}",
        "de": "Du lädst das Bot-Guthaben um {summa}💲(Dollar) mit {assetAmount} {asset} auf\n\nWechselkurs: 1 {asset} = {exchangeRateUSD}$ (Dollar)\n\nKlicke auf den Link, um zu bezahlen: {paymentLink}",
        "he": "אתה עומד להטעין את יתרת הבוט ב-{summa}💲(דולרים) באמצעות {assetAmount} {asset}\n\nשער חליפין: 1 {asset} = {exchangeRateUSD}$ (דולרים)\n\nלחץ על הקישור כדי לשלם: {paymentLink}",
    },
    "payViaPatreon": {
        "pt-BR": "Assinar pelo Patreon",
        "es": "Suscribirse mediante Patreon",
        "de": "Über Patreon abonnieren",
        "he": "מינוי דרך Patreon",
    },
    "patreon_page_body": {
        "es": "Regístrese en Patreon.com para activar su suscripción. Después, en el menú de este bot, pulse el botón \"Indicar correo de Patreon\" y envíe al bot el correo que usó al registrarse en Patreon. A continuación vaya a <a href='https://example.invalid/donate'>https://example.invalid/donate</a> y done el importe necesario.\n\nLa verificación de la suscripción se realizará automáticamente, pero también puede pulsar el botón \"Comprobar Patreon\" para hacerlo sin esperar en la cola.",
        "de": "Registriere dich auf Patreon.com, um dein Abonnement zu aktivieren. Tippe dann im Menü dieses Bots auf die Schaltfläche \"Patreon-E-Mail angeben\" und sende dem Bot die E-Mail-Adresse, mit der du dich bei Patreon registriert hast. Gehe danach auf <a href='https://example.invalid/donate'>https://example.invalid/donate</a> und spende den erforderlichen Betrag.\n\nDie Prüfung des Abonnements erfolgt automatisch, du kannst aber auch auf die Schaltfläche \"Patreon prüfen\" tippen, um sie außerhalb der Warteschlange auszulösen.",
        "he": "הירשם ב-Patreon.com כדי להפעיל את המינוי. לאחר מכן, בתפריט הבוט הזה, לחץ על הכפתור \"ציון מייל Patreon\" ושלח לבוט את כתובת המייל שבה השתמשת בהרשמה ל-Patreon. אחר כך היכנס אל <a href='https://example.invalid/donate'>https://example.invalid/donate</a> ותרום את הסכום הנדרש.\n\nאימות המינוי יתבצע אוטומטית, אבל אפשר גם ללחוץ על הכפתור \"בדיקת Patreon\" כדי לבצע אותו מחוץ לתור.",
    },
    "thisMonthHasAlreadyBeenReplenished": {
        "es": "El saldo ya se recargó este mes",
        "de": "Das Guthaben wurde in diesem Monat bereits aufgeladen",
        "he": "היתרה כבר הוטענה החודש",
    },
    "noDataUpdatePatreon": {
        "es": "No hay datos nuevos, revise su correo e inténtelo de nuevo más tarde",
        "de": "Keine neuen Daten, prüfe deine E-Mail und versuche es später erneut",
        "he": "אין נתונים חדשים, בדוק את כתובת המייל ונסה שוב מאוחר יותר",
    },
    "balanceFromPatreonAdded": {
        "es": "¡Se le ha abonado saldo como agradecimiento por suscribirse a Patreon! Elija un plan con el comando /subscription. Condiciones actuales:",
        "de": "Dir wurde als Dank für dein Patreon-Abonnement Guthaben gutgeschrieben! Wähle einen Tarif mit dem Befehl /subscription. Aktuelle Konditionen:",
        "he": "נזקפה לזכותך יתרה כתודה על המינוי ב-Patreon! בחר מסלול באמצעות הפקודה /subscription. התנאים הנוכחיים:",
    },
    "tellPatreonEmail": {
        "es": "📧 Indicar correo de Patreon",
        "de": "📧 Patreon-E-Mail angeben",
        "he": "📧 ציון מייל Patreon",
    },
    "checkPatreonStatus": {
        "es": "📥 Comprobar Patreon",
        "de": "📥 Patreon prüfen",
        "he": "📥 בדיקת Patreon",
    },
    "donate_page_email_input": {
        "es": "📧 Envíe su correo electrónico",
        "de": "📧 Sende deine E-Mail-Adresse",
        "he": "📧 שלח את כתובת המייל שלך",
    },
    "current_email": {
        "es": "Correo actual",
        "de": "Aktuelle E-Mail",
        "he": "כתובת המייל הנוכחית",
    },
    "email_saved": {
        "es": "Correo guardado",
        "de": "E-Mail gespeichert",
        "he": "כתובת המייל נשמרה",
    },
    "save_error": {
        "es": "Error al guardar",
        "de": "Fehler beim Speichern",
        "he": "שגיאה בשמירה",
    },
    "donate_page_referral": {
        "es": "¡Traiga amigos y obtenga bonos! Si una persona entra con su enlace, recibirá 5 días y 20 notificaciones adicionales en el plan actual o, si no está suscrito, 3 días de suscripción al plan mínimo. Si una persona recarga el saldo con su enlace, su plan pasará al máximo y su duración aumentará en 15 días.",
    },
    "you_cant_recieve_notifications": {
        "es": "Con las condiciones actuales no recibirá notificaciones de nuevos episodios.\nMás información: /subscription",
    },
    "tariff_lvl1": {"es": "🥉 Bronce", "he": "🥉 ברונזה"},
    "tariff_lvl2": {"es": "🥈 Plata", "he": "🥈 כסף"},
    "days_left": {"es": "Días restantes: %s", "he": "ימים שנותרו: %s"},
    "curr_balance": {"es": "Saldo actual: %s💲", "he": "יתרה נוכחית: %s💲"},
    "not_enough_for_renewal": {
        "es": "(no alcanza para la renovación: %s💲)",
        "he": "(אין מספיק לחידוש: %s💲)",
    },
    "payViaRobokassa": {
        "es": "💸 Recargar saldo con Robokassa",
        "he": "💸 טעינת יתרה דרך Robokassa",
    },
    "bot_sub_pmnt_page": {
        "es": "<b>💸 Depósito</b>\n\nAquí puede recargar su saldo. Para obtener un enlace pulse el botón o <b>introduzca el importe manualmente</b>.\n\n<b>¡Atención! La recarga de la cuenta también se considera una donación.</b> Los dólares del sistema son puntos virtuales otorgados por donaciones, cuyo cambio equivale al dólar estadounidense, y pertenecen al propietario del bot. La administración y el propietario del bot no se responsabilizan del dinero donado, del saldo en el sistema ni de los puntos virtuales. El plan elegido por el usuario puede cancelarse y el saldo anularse en cualquier momento sin necesidad de indicar el motivo.\nAl mismo tiempo, la administración se pondrá en contacto y resolverá las disputas siempre que sea posible y según la situación.",
        "he": "<b>💸 הפקדה</b>\n\nכאן אפשר להטעין את היתרה. לקבלת קישור לחץ על הכפתור או <b>הזן את הסכום ידנית</b>.\n\n<b>שימו לב! הטענת חשבון נחשבת גם היא לתרומה!</b> דולרים במערכת הם נקודות וירטואליות שמוענקות בעבור תרומות, שערן שווה לדולר האמריקאי, והן בבעלות בעל הבוט. ההנהלה ובעל הבוט אינם אחראים לכסף שנתרם, ליתרה במערכת ולנקודות הווירטואליות. המסלול שבחר המשתמש ניתן לביטול והיתרה ניתנת לאיפוס בכל עת וללא מתן סיבה.\nבמקביל, ההנהלה תיצור קשר ותפתור מחלוקות ככל האפשר ובהתאם למצב.",
    },
    "money_came": {"es": "¡Su pago ha sido acreditado!", "he": "התשלום שלך נזקף לזכותך!"},
    "subscribe_now": {
        "es": "Vaya a la página de planes y elija el que desee.",
        "he": "עבור לעמוד המסלולים ובחר את המסלול הרצוי.",
    },
    "enough_to_prolongation": {
        "es": "Tiene fondos suficientes para renovar.",
        "he": "יש לך מספיק כספים לחידוש.",
    },
    "not_enough_to_prolongation": {
        "es": "No tiene fondos suficientes para renovar.",
        "he": "אין לך מספיק כספים לחידוש.",
    },
    "tariff_prolonged": {
        "es": "El plan actual se ha ampliado.",
        "he": "המסלול הנוכחי הוארך.",
    },
    "tariff_prolonged_by_daemon": {
        "es": "¡Su plan se ha ampliado! Condiciones actuales:",
        "he": "המסלול שלך הוארך! התנאים הנוכחיים:",
    },
    "your_tariff_description": {
        "es": "Descripción de su plan",
        "he": "תיאור המסלול שלך",
    },
    "notificationsEnded": {
        "es": "Se alcanzó el límite de notificaciones dentro de este plazo.\nEspere al nuevo plazo o cambie a un plan con un límite mayor.",
        "he": "הגעת למגבלת ההתראות בתוך תקופת התוקף הזו.\nהמתן לתקופה חדשה או עבור למסלול עם מגבלה גבוהה יותר.",
    },
    "award_without_s_new_user": {
        "es": "¡Un nuevo usuario se registró con su enlace y quedó suscrito al plan! Condiciones actuales:",
        "he": "משתמש חדש נרשם דרך הקישור שלך, ונרשמת למסלול! התנאים הנוכחיים:",
    },
    "award_with_s_new_user": {
        "es": "¡Un nuevo usuario se registró con su enlace, su plan ha mejorado!",
        "he": "משתמש חדש נרשם דרך הקישור שלך, המסלול שלך השתפר!",
    },
    "award_without_s_subscribed": {
        "es": "El usuario invitado recargó el saldo por primera vez, ¡quedó suscrito al plan! Condiciones actuales:",
        "he": "המשתמש שהזמנת הטעין יתרה בפעם הראשונה, ונרשמת למסלול! התנאים הנוכחיים:",
    },
    "award_with_s_subscribed": {
        "es": "El usuario invitado recargó el saldo por primera vez, ¡su plan ha mejorado! Condiciones actuales:",
        "he": "המשתמש שהזמנת הטעין יתרה בפעם הראשונה, המסלול שלך השתפר! התנאים הנוכחיים:",
    },
    "openThePodcast": {
        "es": "Abrir el podcast",
        "de": "Podcast öffnen",
        "he": "פתח את הפודקאסט",
    },
    "downloadEpisode": {
        "pt-BR": "Baixar o episódio",
        "es": "Descargar el episodio",
        "de": "Folge herunterladen",
        "he": "הורד את הפרק",
    },
    "linkInTheBotByPodcastId": {
        "es": "[Abrir el podcast](t.me/{botName}?start={mode}_{id})",
        "de": "[Podcast öffnen](t.me/{botName}?start={mode}_{id})",
        "he": "[פתח את הפודקאסט](t.me/{botName}?start={mode}_{id})",
    },
    "linkInTheBotByPodcastId_HTML": {
        "es": "<a href=\"t.me/{botName}?start={mode}_{id}\">Abrir el podcast</a>",
        "de": "<a href=\"t.me/{botName}?start={mode}_{id}\">Podcast öffnen</a>",
        "he": "<a href=\"t.me/{botName}?start={mode}_{id}\">פתח את הפודקאסט</a>",
    },
    "in_the_bot": {
        "es": "con @{botName}",
        "de": "mit @{botName}",
        "he": "עם @{botName}",
    },
    "cover_image": {
        "pt-BR": "Capa",
        "es": "Portada",
        "de": "Cover",
        "he": "עטיפה",
    },
    "genresMessage": {
        "es": "%s\nElija un género",
        "de": "%s\nWähle ein Genre",
        "he": "%s\nבחר ז'אנר",
    },
    "topMessage": {
        "es": "👑\nTop de géneros",
        "de": "👑\nGenre-Top",
        "he": "👑\nהמובילים לפי ז'אנר",
    },
    "connectTgChannelMessage": {
        "es": "🔌<b>Canales conectados</b>\n\nPuede añadir un canal de Telegram, elegir podcasts y ¡el bot enviará allí los episodios nuevos automáticamente!\n\n¡Deje que el bot gestione el canal de podcasts por usted!",
        "de": "🔌<b>Verbundene Kanäle</b>\n\nDu kannst einen Telegram-Kanal hinzufügen und Podcasts auswählen, und der Bot sendet neue Folgen automatisch dorthin!\n\nLass den Bot den Podcast-Kanal für dich verwalten!",
        "he": "🔌<b>ערוצים מחוברים</b>\n\nאפשר להוסיף ערוץ טלגרם, לבחור פודקאסטים, והבוט ישלח אליו פרקים חדשים באופן אוטומטי!\n\nתן לבוט לנהל בשבילך את ערוץ הפודקאסטים!",
    },
    "cantConnectTgChannelMessage": {
        "es": "<b>Para añadir un canal, su plan debe ser de nivel %s.</b>\nSu plan actual: %s.\n\nMás información: /subscription",
        "de": "<b>Um einen Kanal hinzuzufügen, muss dein Tarif Stufe %s haben.</b>\nDein aktueller Tarif: %s.\n\nMehr Infos: /subscription",
        "he": "<b>כדי להוסיף ערוץ, המסלול שלך חייב להיות ברמה %s.</b>\nהמסלול הנוכחי שלך: %s.\n\nמידע נוסף: /subscription",
    },
    "myTgChannels": {"es": "Mis canales", "de": "Meine Kanäle", "he": "הערוצים שלי"},
    "addTgChannel": {"es": "Añadir canal", "de": "Kanal hinzufügen", "he": "הוסף ערוץ"},
    "addTgChannelInput": {
        "es": "Haga que este bot sea administrador de su canal. Luego introduzca el id del canal, que empieza con un signo menos, o envíe al bot cualquier mensaje del canal",
        "de": "Mache diesen Bot zum Administrator deines Kanals. Gib dann die Kanal-ID ein, sie beginnt mit einem Minus, oder sende dem Bot eine beliebige Nachricht aus dem Kanal",
        "he": "הפוך את הבוט הזה למנהל של הערוץ שלך. לאחר מכן הזן את מזהה הערוץ, שמתחיל במינוס, או שלח לבוט הודעה כלשהי מהערוץ",
    },
    "tgChannelNotFoundEnsureBotAdmin": {
        "es": "Canal no encontrado. Asegúrese de haber añadido el bot como administrador",
        "de": "Kanal nicht gefunden. Stelle sicher, dass du den Bot als Administrator hinzugefügt hast",
        "he": "הערוץ לא נמצא. ודא שהוספת את הבוט כמנהל",
    },
    "tgChannelNotFoundEnsureBotAdminWithName": {
        "es": "Canal <b>%s</b> no encontrado. Asegúrese de haber añadido el bot como administrador.\n\nMás información: /my_tg_channels",
        "de": "Kanal <b>%s</b> nicht gefunden. Stelle sicher, dass du den Bot als Administrator hinzugefügt hast.\n\nMehr Infos: /my_tg_channels",
        "he": "הערוץ <b>%s</b> לא נמצא. ודא שהוספת את הבוט כמנהל.\n\nמידע נוסף: /my_tg_channels",
    },
    "tgChannelAlreadyAdded": {
        "es": "El canal ya está añadido",
        "de": "Der Kanal wurde bereits hinzugefügt",
        "he": "הערוץ כבר נוסף",
    },
    "maxTgChannelsForNow": {
        "pt-BR": "Você atingiu o número máximo de canais",
        "es": "Ha alcanzado el número máximo de canales",
        "de": "Du hast die maximale Anzahl an Kanälen erreicht",
        "he": "הגעת למספר הערוצים המרבי",
    },
    "tgChannelAdded": {
        "es": "El canal se añadió correctamente",
        "de": "Der Kanal wurde erfolgreich hinzugefügt",
        "he": "הערוץ נוסף בהצלחה",
    },
    "yourTgChannelList": {
        "es": "🔌\nLista de canales que ha añadido",
        "de": "🔌\nListe der Kanäle, die du hinzugefügt hast",
        "he": "🔌\nרשימת הערוצים שהוספת",
    },
    "yourTgChannelsEmpty": {
        "pt-BR": "Você ainda não tem canais",
        "es": "Todavía no tiene canales",
        "de": "Du hast noch keine Kanäle",
        "he": "עדיין אין לך ערוצים",
    },
    "yourTgChannel": {
        "es": "Gestionar el canal añadido",
        "de": "Hinzugefügten Kanal verwalten",
        "he": "ניהול הערוץ שנוסף",
    },
    "tgChannelStatus": {"es": "Estado", "de": "Status", "he": "סטטוס"},
    "tgChannelSubs": {"es": "Podcasts", "de": "Podcasts", "he": "פודקאסטים"},
    "tgChannelDelete": {"es": "Eliminar canal", "de": "Kanal löschen", "he": "מחק ערוץ"},
    "tapAgainToDeleteTgChannel": {
        "es": "Pulse de nuevo para confirmar la eliminación",
        "de": "Tippe erneut, um das Löschen zu bestätigen",
        "he": "לחץ שוב כדי לאשר את המחיקה",
    },
    "yourTgChannelSubList": {
        "es": "🔌\nPulse un podcast para que el bot empiece a seguir sus nuevos episodios y a enviarlos al canal. Pulse de nuevo para cancelar. Tenga en cuenta que si se da de baja de un podcast abriéndolo, por ejemplo, con el comando /subscriptions, también desaparecerá su conexión con el canal de Telegram.",
        "de": "🔌\nTippe auf einen Podcast, damit der Bot seine neuen Folgen verfolgt und in den Kanal sendet. Tippe erneut, um abzubrechen. Beachte: Wenn du einen Podcast abbestellst, indem du ihn öffnest, zum Beispiel über den Befehl /subscriptions, verschwindet auch seine Verbindung zum Telegram-Kanal.",
        "he": "🔌\nלחץ על פודקאסט כדי שהבוט יתחיל לעקוב אחר הפרקים החדשים שלו וישלח אותם לערוץ. לחץ שוב כדי לבטל. שים לב: אם תבטל מינוי לפודקאסט על ידי פתיחתו, למשל דרך הפקודה /subscriptions, גם החיבור שלו לערוץ הטלגרם יימחק.",
    },
    "maintenance": {
        "es": "¡El bot está en mantenimiento! Espere un momento, por favor.",
    },
}
