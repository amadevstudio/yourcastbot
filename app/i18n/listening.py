"""Copy for feed health and the personal listening list (all supported languages)."""
LANGUAGES = ('ru', 'en', 'pt-BR', 'es', 'de', 'he')
ROWS = {
    'deliveryStatus': ('Состояние доставки', 'Delivery status', 'Status de entrega', 'Estado de entrega', 'Zustellstatus', 'מצב המסירה'),
    'feedPausedNotice': (
        'Источник временно недоступен. Мы автоматически проверяем его и повторяем попытку ежедневно. Настройка уведомлений сохранена.',
        'The feed is temporarily unavailable. We check it automatically and retry daily. Your notification preference is saved.',
        'O feed está temporariamente indisponível. Nós o verificamos automaticamente e tentamos diariamente. Sua preferência de notificações foi mantida.',
        'El feed no está disponible temporalmente. Lo comprobamos automáticamente y lo intentamos a diario. Tu preferencia de notificaciones se conserva.',
        'Der Feed ist vorübergehend nicht verfügbar. Wir prüfen ihn automatisch und versuchen es täglich erneut. Deine Benachrichtigungseinstellung bleibt erhalten.',
        'הפיד אינו זמין זמנית. אנחנו בודקים אותו אוטומטית ומנסים שוב מדי יום. העדפת ההתראות שלך נשמרה.'),
    'feedStatusHelp': (
        'Здесь доступность источника и ваша настройка уведомлений. Для бесплатного тарифа новые выпуски попадают в еженедельный дайджест; с подпиской — доставляются автоматически.',
        'Feed availability and your notification preference. On the free plan, new episodes appear in the weekly digest; paid plans deliver them automatically.',
        'Disponibilidade do feed e sua preferência de notificações. No plano grátis, os episódios aparecem no resumo semanal; nos planos pagos, são enviados automaticamente.',
        'Disponibilidad del feed y tu preferencia de notificaciones. En el plan gratis, los episodios aparecen en el resumen semanal; los planes de pago los envían automáticamente.',
        'Feed-Verfügbarkeit und deine Benachrichtigungseinstellung. Im kostenlosen Tarif erscheinen neue Folgen in der Wochenübersicht; bezahlte Tarife liefern sie automatisch.',
        'זמינות הפיד והעדפת ההתראות שלך. במסלול החינמי פרקים חדשים מופיעים בתקציר השבועי; במסלולים בתשלום הם נשלחים אוטומטית.'),
    'feedPaused': ('Источник недоступен · проверяем', 'Feed unavailable · checking', 'Feed indisponível · verificando', 'Feed no disponible · comprobando', 'Feed nicht verfügbar · Prüfung läuft', 'הפיד לא זמין · בבדיקה'),
    'feedChecking': ('Проверка запланирована', 'Check scheduled', 'Verificação agendada', 'Comprobación programada', 'Prüfung geplant', 'בדיקה מתוזמנת'),
    'feedAvailable': ('Последняя проверка успешна', 'Last check succeeded', 'Última verificação bem-sucedida', 'Última comprobación correcta', 'Letzte Prüfung erfolgreich', 'הבדיקה האחרונה הצליחה'),
    'feedUnchecked': ('Отдельная проверка ещё не проводилась', 'No separate check yet', 'Ainda sem verificação específica', 'Aún sin comprobación específica', 'Noch keine gesonderte Prüfung', 'טרם בוצעה בדיקה נפרדת'),
    'feedCheck': ('Проверить источник', 'Check feed', 'Verificar feed', 'Comprobar feed', 'Feed prüfen', 'בדיקת הפיד'),
    'feedCheckQueued': ('Проверка в очереди. Повторные нажатия не ускоряют её.', 'Check queued. Repeated taps do not speed it up.', 'Verificação na fila. Toques repetidos não a aceleram.', 'Comprobación en cola. Pulsar de nuevo no la acelera.', 'Prüfung vorgemerkt. Erneutes Tippen beschleunigt sie nicht.', 'הבדיקה בתור. לחיצות חוזרות אינן מזרזות אותה.'),
    'listenLater': ('Послушать позже', 'Listen later', 'Ouvir depois', 'Escuchar después', 'Später hören', 'להאזנה בהמשך'),
    'saveLater': ('Сохранить', 'Save', 'Salvar', 'Guardar', 'Speichern', 'שמירה'),
    'savedLater': ('Сохранено в «Послушать позже»', 'Saved to Listen later', 'Salvo em Ouvir depois', 'Guardado en Escuchar después', 'In Später hören gespeichert', 'נשמר להאזנה בהמשך'),
    'savedLimit': ('Список полон: удалите один из 200 сохранённых выпусков.', 'List full: remove one of your 200 saved episodes.', 'Lista cheia: remova um dos 200 episódios salvos.', 'Lista llena: elimina uno de los 200 episodios guardados.', 'Liste voll: Entferne eine der 200 gespeicherten Folgen.', 'הרשימה מלאה: יש להסיר אחד מ-200 הפרקים השמורים.'),
    'savedEmpty': ('Здесь будут сохранённые выпуски. Нажмите «Сохранить» рядом с выпуском в списке подкаста.', 'Your saved episodes will appear here. Tap Save next to an episode in a podcast’s episode list.', 'Seus episódios salvos aparecerão aqui. Toque em Salvar ao lado de um episódio na lista do podcast.', 'Aquí aparecerán los episodios guardados. Pulsa Guardar junto a un episodio en la lista del pódcast.', 'Hier erscheinen gespeicherte Folgen. Tippe neben einer Folge in der Podcast-Liste auf Speichern.', 'פרקים שמורים יופיעו כאן. לחצו על שמירה ליד פרק ברשימת הפרקים של פודקאסט.'),
    'removeLater': ('Убрать', 'Remove', 'Remover', 'Eliminar', 'Entfernen', 'הסרה'),
    'playLater': ('Слушать', 'Listen', 'Ouvir', 'Escuchar', 'Anhören', 'האזנה'),
    'digestEpisodes': ('Новые выпуски в ваших подписках', 'New episodes in your subscriptions', 'Novos episódios nas suas assinaturas', 'Nuevos episodios en tus suscripciones', 'Neue Folgen in deinen Abos', 'פרקים חדשים במינויים שלך'),
}
TRANSLATIONS = {key: {lang: {'ro_msg': value} for lang, value in zip(LANGUAGES, row)}
                for key, row in ROWS.items()}
