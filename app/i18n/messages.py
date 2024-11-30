from config import (
    tariff_ref_period, tariff_ref_no_subscription_period,
    tariff_ref_notifies, tariff_ref_sub_period, max_subscriptions_without_tariff,
    donate_link, botName)


def get_language(lang_code):
    # Иногда language_code может быть None
    if not lang_code:
        return "en"
    if "-" in lang_code:
        lang_code = lang_code.split("-")[0]
    if lang_code == "ru":
        return "ru"
    elif lang_code == "pt":
        return "pt-BR"  # Бразильский вариант португальского языка
    elif lang_code == "es":
        return "es"
    elif lang_code == "de":
        return "de"
    elif lang_code == "he":
        return "he"
    else:
        return "en"


def get_message(message, lang_code, param=""):
    lang_code = get_language(lang_code)
    if param == "":
        param = "ro_msg"
    try:
        try:
            return messages.get(message).get(get_language(lang_code)).get(param)
        except Exception:
            return messages.get(message).get(get_language(lang_code)).get("ro_msg")
    except Exception:
        try:
            return messages.get(message).get("en").get("ro_msg")
        except Exception:
            return message


def get_message_rtd(message_route, lang_code):
    lang_code = get_language(lang_code)
    curr_route = None
    msg = None
    if len(message_route) > 0:
        try:
            for r in message_route:
                if curr_route is None:
                    curr_route = routed_messages.get(r.lower())
                else:
                    curr_route = curr_route.get(r.lower())
            try:
                msg = curr_route.get(lang_code)
            except Exception:
                msg = curr_route.get("en")
        except AttributeError:
            msg = str(message_route.pop())

    if msg is None:
        msg = ""

    return msg


emojiCodes = {
    'magnifier': '\U0001F50D',
    'microphone': '\U0001F3A4',
    'disk': '\U0001F4C0',
    'floppyDisk': '\U0001F4BE',
    'information': '\U00002139',
    'crown': '\U0001F451',
    'inboxTray': '\U0001F4E5',
    'soundEnabled': '\U0001F514',
    'soundDisabled': '\U0001F515',
    'creditCard': '\U0001F4B3',
    'dollar': '\U0001F4B2',
    'dollarBag': '\U0001F4B0',
    'moneyWithWings': '\U0001F4B8',
    'clipboard': '\U0001F4CB',
    'bronze': '\U0001F949',
    'silver': '\U0001F948',
    'gold': '\U0001F947',
    'gear': '\U00002699',
    'link': '\U0001F517',
    'goldenHeart': '\U0001F49B',
    'brokenHeart': '\U0001F494',
    'shootingStar': '\U0001F320',
    'dizzy': '\U0001F4AB',
    'star': '\U00002B50',
    'glowingStar': '\U0001F31F',
    'trophy': '\U0001F3C6',
    'globeEuropeAfrica': '\U0001F30D',
    'tongue': '\U0001F445',
    'endArrow': '\U0001F51A',
    'generalTop': '\U0001F51D',
    'email': '\U0001F4E7',
    'whiteHeavyCheckMark': '\U00002705',
    'crossMark': '\U0000274C',
    'warning': '\U000026A0',
    'exclamationMark': '\U00002757',
    'electricPlug': '\U0001F50C',
    'new': '\U0001F195',
    # 'redCircle': '\U0001F534',
    'rewindToNext': '\U000023ED',
    'CL': '🆑',
}

standartSymbols = {
    "newItem": emojiCodes.get("new", "New")
}

messages = {
    "privacy": {
        "ru": {
            "ro_msg": "Мы храним некоторые ваши данные для предоставления сервиса: telegram id, ваше имя, никнейм, "
                      "язык, а также все указанные в боте данные, например, список подкастов, на которые вы "
                      "подписались, оценки подкастов, идентификаторы каналов и так далее.\n\n"
                      "Мы ни с кем не делимся этими данными кроме случаев, когда это используется в интерфейсе бота."
        },
        "en": {
            "ro_msg": "We store some of your data to provide the service: telegram id, your name, nickname, language, "
                      "as well as all the data specified in the bot, for example, a list of podcasts that you have "
                      "subscribed to, podcast ratings, channel identifiers, and so on.\n\n"
                      "We do not share this data with anyone except when it is used in the bot interface."
        }
    },
    "or": {
        "ru": {
            "ro_msg": "или"
        },
        "en": {
            "ro_msg": "or"
        },
        "pt-BR": {
            "ro_msg": "ou"
        },
    },
    "welcomeMessage": {
        "ru": {
            "ro_msg": "<b>Добро пожаловать!</b>\n"
                      "Вы можете начать с этих популярных каналов:"
        },
        "en": {
            "ro_msg": "<b>Welcome!</b>\n"
                      "You can start with these popular channels:"
        },
        "pt-BR": {
            "ro_msg": "<b>Olá!</b>\n"
                      "Que tal começar com estes podcasts populares?"
        },
        "es": {
            "ro_msg": "<b>Bienvenido!</b>\n"
                      "Usted puede comenzar con estos canales populares"
        },
        "de": {
            "ro_msg": "<b>Herzlich Willkommen!</b>\n"
                      "Du kannst mit einem dieser beliebten Podcasts beginnen:"
        },
        "he": {
            "ro_msg": "ברוכים הבאים!"
                      "אתם יכולים להרשם לערוצים הפופולריים הללו:"
        }
    },
    "welcome": {
        "ru": {
            "ro_msg": "<b>Добро пожаловать!</b>"
        },
        "en": {
            "ro_msg": "<b>Welcome!</b>"
        },
        "pt-BR": {
            "ro_msg": "<b>Olá!</b>"
        },
        "es": {
            "ro_msg": "<b>Bienvenido!</b>"
        },
        "de": {
            "ro_msg": "<b>Herzlich Willkommen!</b>"
        },
        "he": {
            "ro_msg": "ברוכים הבאים!"
        }

    },
    "offerMessage": {
        "ru": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "Популярные каналы:"
        },
        "en": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "Popular channels:"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "Podcastas populares:"
        },
        "es": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "Canales populares:"
        },
        "de": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "Beliebte Podcasts:"
        },
        "he": {
            "ro_msg": emojiCodes.get('crown') + "\n" + "ערוצים פופולריים:"
        }

    },
    "weAlsoSignedYouOnPodcastName": {
        "ru": {
            "ro_msg": "Мы также подписали вас на <a href='http://t.me/%s?start=podcast_%s'>%s</a>"
        },
        "en": {
            "ro_msg": "We also signed you up to <a href='http://t.me/%s?start=podcast_%s'>%s</a>"
        },
        "pt-BR": {
            "ro_msg": "Também inscrevemos você em <a href='http://t.me/%s?start=podcast_%s'>%s</a>"
        },
    },
    "dontForgetToVisitStart": {
        "ru": {
            "ro_msg": "Не забудьте посетить начальную страницу /start"
        },
        "en": {
            "ro_msg": "Don't forget to visit the start page /start"
        },
        "pt-BR": {
            "ro_msg": "Não se esqueça de visitar a página inicial em /start"
        }
    },
    "pressMe": {
        "ru": {
            "ro_msg": "Нажми на меня"
        },
        "en": {
            "ro_msg": "Press me"
        },
        "pt-BR": {
            "ro_msg": "Toque aqui"
        },
        "es": {
            "ro_msg": "Toque aqui"
        },
        "de": {
            "ro_msg": "Drück mich!"
        },
        "he": {
            "ro_msg": "לחצו כאן"
        }
    },
    "subscribe": {
        "ru": {
            "ro_msg": "Подписаться"
        },
        "en": {
            "ro_msg": "Subscribe"
        },
        "pt-BR": {
            "ro_msg": "Assinar"
        },
        "es": {
            "ro_msg": "Suscribirse"
        },
        "de": {
            "ro_msg": "Abonnieren"
        },
        "he": {
            "ro_msg": "הרשמו כמנוי"
        }
    },
    "unsubscribe": {
        "ru": {
            "ro_msg": "Отписаться"
        },
        "en": {
            "ro_msg": "Unsubscribe"
        },
        "pt-BR": {
            "ro_msg": "Desinscrever"
        },
        "es": {
            "ro_msg": "Desuscribirse"
        },
        "de": {
            "ro_msg": "Abo beenden"
        },
        "he": {
            "ro_msg": "ביטול הרשמה כמנוי"
        }

    },
    "notifyon": {
        "ru": {
            # "ro_msg": "Присылать новые эпизоды"
            "ro_msg": "Новые эпизоды " + emojiCodes.get('soundDisabled')
        },
        "en": {
            # "ro_msg": "Send new episodes"
            "ro_msg": "New episodes " + emojiCodes.get('soundDisabled')
        },
        "pt-BR": {
            # "ro_msg": "Enviar novos episódios"
            "ro_msg": "Novos episódios " + emojiCodes.get('soundDisabled')
        },
        "es": {
            "ro_msg": "Nuevos episodios " + emojiCodes.get('soundDisabled')
            # "ro_msg": "Enviar episodios nuevos"
        },
        "de": {
            "ro_msg": "Neue Folgen " + emojiCodes.get('soundDisabled')
            # "ro_msg": "Neue Folgen empfangen"
        },
        "he": {
            # "ro_msg": "Send new episodes"
            "ro_msg": "פרקים חדשים " + emojiCodes.get('soundDisabled')
        }

    },
    "notifyoff": {
        "ru": {
            # "ro_msg": "Не присылать новые эпизоды"
            "ro_msg": "Новые эпизоды " + emojiCodes.get('soundEnabled')
        },
        "en": {
            # "ro_msg": "Do not send new episodes"
            "ro_msg": "New episodes " + emojiCodes.get('soundEnabled')
        },
        "pt-BR": {
            # "ro_msg": "Não enviar novos episódios"
            "ro_msg": "Novos episódios " + emojiCodes.get('soundEnabled')
        },
        "es": {
            "ro_msg": "Nuevos episodios " + emojiCodes.get('soundEnabled')
            # "ro_msg": "No enviar nuevos episodios"
        },
        "de": {
            "ro_msg": "Neue Folgen " + emojiCodes.get('soundEnabled')
            # "ro_msg": "Keine neuen Folgen empfangen"
        },
        "he": {
            # "ro_msg": "Do not send new episodes"
            "ro_msg": "פרקים חדשים " + emojiCodes.get('soundEnabled')
        }

    },
    "notifyoned": {
        "ru": {
            "ro_msg": "Теперь вы будете получать новые эпизоды этого канала!"
        },
        "en": {
            "ro_msg": "You will now receive new episodes from this channel!"
        },
        "pt-BR": {
            "ro_msg": "Agora você irá receber novos episódios deste podcast!"
        },
        "es": {
            "ro_msg": "Ahora usted recibirá nuevos episodios de este canal!"
        },
        "de": {
            "ro_msg": "In Zukunft werden wir Dir neue Folgen dieses Podcasts zusenden."
        },
        "he": {
            "ro_msg": "כעת תקבלו פרקים חדשים מערוץ זה!"
        }

    },
    "notifyoffed": {
        "ru": {
            "ro_msg": "Вы больше не будете получать новые эпизоды этого канала!"
        },
        "en": {
            "ro_msg": "You will no longer receive new episodes from this channel!"
        },
        "pt-BR": {
            "ro_msg": "Você não irá receber mais novos episódios deste podcast!"
        },
        "es": {
            "ro_msg": "Usted ya no recibirá nuevos episodios de este canal!"
        },
        "de": {
            "ro_msg": "Du wirst keine neuen Folgen dieses Podcasts mehr erhalten."
        },
        "he": {
            "ro_msg": "לא תקבלו פרקים חדשים מערוץ זה!"
        }

    },
    "yousubscribedto": {
        "ru": {
            "ro_msg": "Вы подписались на %s"
        },
        "en": {
            "ro_msg": "You subscribed to %s"
        },
        "pt-BR": {
            "ro_msg": "Vocẽ assinou %s"
        },
        "es": {
            "ro_msg": "Usted se suscribió a %s"
        },
        "de": {
            "ro_msg": "Du hast %s abonniert."
            # "ro_msg": "Du hast abonniert:"
            # "ideally": "Du hast %s abonniert."
        },
        "he": {
            "ro_msg": "נרשמתם לערוץ %s"
        }
    },
    "youunsubscribedto": {
        "ru": {
            "ro_msg": "Вы отписались от %s"
        },
        "en": {
            "ro_msg": "You unsubscribed from %s"
        },
        "pt-BR": {
            "ro_msg": "Você cancelou a assinatura de %s"
        },
        "es": {
            "ro_msg": "Usted se desuscribió de %s"
        },
        "de": {
            "ro_msg": "Du hast Dein Abo für %s beendet."
        },
        "he": {
            "ro_msg": "ביטלתם את הרישום מערוץ %s"
        }

    },
    "listen": {
        "ru": {
            "ro_msg": "Слушать"
        },
        "en": {
            "ro_msg": "Listen"
        },
        "pt-BR": {
            "ro_msg": "Ouvir"
        },
        "es": {
            "ro_msg": "Escuchar"
        },
        "de": {
            "ro_msg": "Anhören"
        },
        "he": {
            "ro_msg": "האזן"
        }
    },
    "showFileSizes": {
        "ru": {
            "ro_msg": "Размеры файлов"
        },
        "en": {
            "ro_msg": "File sizes"
        },
    },
    "goBack": {
        "ru": {
            "ro_msg": "❮❮ Назад"
        },
        "en": {
            "ro_msg": "❮❮ Go back"
        },
        "pt-BR": {
            "ro_msg": "❮❮ Voltar"
        },
        "es": {
            "ro_msg": "❮❮ Regresar"
        },
        "de": {
            "ro_msg": "❮❮ Zurück"
        },
        "he": {
            "ro_msg": "❮❮ חזור"
        }

    },
    "goBackMenu": {
        "ru": {
            "ro_msg": "❮❮ Назад в меню"
        },
        "en": {
            "ro_msg": "❮❮ Go back to menu"
        },
        "pt-BR": {
            "ro_msg": "❮❮ Voltar ao menu"
        },
        "es": {
            "ro_msg": "❮❮ Regresar al menú"
        },
        "de": {
            # "ro_msg": "❮❮ Zurück zum Hauptmenü"
            "ro_msg": "❮❮ Hauptmenü"
        },
        "he": {
            "ro_msg": "❮❮ חזור לתפריט"
        }

    },
    "skipWelcome": {
        "ru": {
            "ro_msg": emojiCodes["rewindToNext"] + " Пропустить и открыть меню"
        },
        "en": {
            "ro_msg": emojiCodes["rewindToNext"] + " Skip and open menu"
        },
        "pt-BR": {
            "ro_msg": emojiCodes["rewindToNext"] + " Pular e abrir o menu"
        },
        "es": {
            "ro_msg": emojiCodes["rewindToNext"] + " Saltar y abrir menú"
        },
        "de": {
            "ro_msg": emojiCodes["rewindToNext"] + " Menü überspringen und öffnen"
        },
        "he": {
            "ro_msg": emojiCodes["rewindToNext"] + " דלג ופתח את התפריט"
        }

    },
    "backToCHannel": {
        "ru": {
            "ro_msg": "Вернуться к каналу"
        },
        "en": {
            "ro_msg": "Go back to channel"
        },
        "pt-BR": {
            "ro_msg": "Voltar ao canal"
        },
        "es": {
            "ro_msg": "Regresar al canal"
        },
        "de": {
            "ro_msg": "Zurück zur Übersicht"
        },
        "he": {
            "ro_msg": "חזור לערוץ"
        }

    },
    "thereis": {
        "ru": {
            "ro_msg": "Всего"
        },
        "en": {
            "ro_msg": "There are"
        },
        "pt-BR": {
            "ro_msg": "Foram encontrados"
        },
        "es": {
            "ro_msg": "Se encontraron"
        },
        "de": {
            "ro_msg": "Es gibt"
        },
        "he": {
            "ro_msg": "קיים"
        }

    },
    "records": {
        "ru": {
            "ro_msg": "Записей",
            "1": "Запись",
            "2": "Записи"
        },
        "en": {
            "ro_msg": "Episodes"
        },
        "pt-BR": {
            "ro_msg": "Registros"
        },
        "es": {
            "ro_msg": "Registros"
        },
        "de": {
            "ro_msg": "Folgen",
        },
        "he": {
            "ro_msg": "רשומות"
        }

    },
    "page": {
        "ru": {
            "ro_msg": "Страница"
        },
        "en": {
            "ro_msg": "Page"
        },
        "pt-BR": {
            "ro_msg": "Página"
        },
        "es": {
            "ro_msg": "Página"
        },
        "de": {
            "ro_msg": "Seite"
        },
        "he": {
            "ro_msg": "עמוד"
        }

    },
    "of": {
        "ru": {
            "ro_msg": "Из"
        },
        "en": {
            "ro_msg": "Of"
        },
        "pt-BR": {
            "ro_msg": "De"
        },
        "es": {
            "ro_msg": "De"
        },
        "de": {
            "ro_msg": "Von"
        },
        "he": {
            "ro_msg": "של"
        }

    },
    "alreadyOnThisPage": {
        "ru": {
            "ro_msg": "Вы уже на этой странице"
        },
        "en": {
            "ro_msg": "You are already on this page"
        },
        "pt-BR": {
            "ro_msg": "Você já está nessa página"
        },
        "es": {
            "ro_msg": "Ya usted está en esta página"
        },
        "de": {
            "ro_msg": "Du befindest Dich bereits auf dieser Seite."
        },
        "he": {
            "ro_msg": "אתה כבר בעמוד זה"
        }

    },
    "pageDoesnotExist": {
        "ru": {
            "ro_msg": "Запрашиваемой страницы не существует"
        },
        "en": {
            "ro_msg": "Requested page doesn’t exist"
        },
        "pt-BR": {
            "ro_msg": "A página solicitada não existe"
        },
        "es": {
            "ro_msg": "La página solicitada no existe"
        },
        "de": {
            "ro_msg": "Die angefragte Seite gibt es nicht."
        },
        "he": {
            "ro_msg": "העמוד המבוקש איננו קיים"
        }

    },
    "original": {
        "ru": {
            "ro_msg": "Оригинальный"
        },
        "en": {
            "ro_msg": "Original"
        },
        "pt-BR": {
            "ro_msg": "Original"
        },
        "es": {
            "ro_msg": "Original"
        },
        "de": {
            "ro_msg": "Original"
        },
        "he": {
            "ro_msg": "מְקוֹרִי"
        }
    },
    "error": {
        "ru": {
            "ro_msg": "Ошибка! Попробуйте позже или свяжитесь с разработчиком"
        },
        "en": {
            "ro_msg": "Error! Try again later or contact the developer"
        },
        "pt-BR": {
            "ro_msg": "Erro! "
                      "Tente novamente mais tarde ou entre em contato com o desenvolvedor"
        },
        "es": {
            "ro_msg": "¡error! "
                      "Vuelve a intentarlo más tarde o comunícate con el desarrollador."
        },
        "de": {
            "ro_msg": "Ein Fehler ist aufgetreten! Versuche es später erneut oder "
                      "setze Dich mit dem Entwickler in Verbindung!"
        },
        "he": {
            "ro_msg": "שְׁגִיאָה! נסה שוב מאוחר יותר או פנה למפתח"
        }
    },
    "parsingError": {
        "ru": {
            "ro_msg": "Ошибка в получении информации."
        },
        "en": {
            "ro_msg": "Sorry, an error occured when receiving info."
        },
        "pt-BR": {
            "ro_msg": "Desculpe. Encontramos erro no recebimento das"
                      " informações."
        },
        "es": {
            "ro_msg": "Lo sentinos, ocurrieron errores al recibir la"
                      " información."
        },
        "de": {
            "ro_msg": "Fehler beim Abrufen der Informationen."
                      " Bitte entschuldige!"
        },
        "he": {
            "ro_msg": "מצטערים, אירעו שגיאות בקבלת המידע."
        }
    },
    "amountTooSmall": {
        "ru": {
            "ro_msg": "Значение слишком маленькое"
        },
        "en": {
            "ro_msg": "The amount is too small"
        },
        "pt-BR": {
            "ro_msg": "O montante é muito pequeno"
        }
    },
    "notFoundOrFuture": {
        "ru": {
            "ro_msg": "Запись не найдена (удалена или изменена), "
                      "или вы достигли последнего выпуска."
        },
        "en": {
            "ro_msg": "The record was not found (deleted or changed), "
                      "or you have reached the latest release."
        },
        "pt-BR": {
            "ro_msg": "O registro não foi encontrado (excluído ou alterado), "
                      "ou você já chegou no lançamento mais recente."
        }
    },
    "gettingStateError": {
        "ru": {
            "ro_msg": "Ошибка в получении вашего состояния, сброс..."
        },
        "en": {
            "ro_msg": "Error in getting your status, resetting..."
        },
        "pt-BR": {
            "ro_msg": "Erro ao obter seu status, redefinindo..."
        },
        "es": {
            "ro_msg": "Error al obtener su estado, restableciendo..."
        },
        "de": {
            "ro_msg": "Fehler beim Abrufen Deines Statusses,"
                      " Vorgang wird rückabgewickelt…"
        },
        "he": {
            "ro_msg": "אירעה שגיאה בקבלת הסטטוס שלך, מאפס..."
        }
    },
    "somethingWentWrong": {
        "ru": {
            "ro_msg": "Что-то пошло не так, попытайтесь позже"
        },
        "en": {
            "ro_msg": "Something went wrong, try again later"
        },
        "pt-BR": {
            "ro_msg": "Ocorreu um erro. Tente novamente mais tarde"
        },
        "es": {
            "ro_msg": "Algo salió mal, intente nuevamente más tarde"
        },
        "de": {
            "ro_msg": "Es ist ein Fehler aufgetreten. Versuche es später erneut!"
        },
        "he": {
            "ro_msg": "משהו השתבש, נסה שוב מאוחר יותר"
        }
    },
    "taskAddedToQueue": {
        "ru": {
            "ro_msg": "Задание помещено в очередь"
        },
        "en": {
            "ro_msg": "Task added to queue"
        }
    },
    "needTimeToLoad": {
        "ru": {
            "ro_msg": "Для загрузки необходимо время"
        },
        "en": {
            "ro_msg": "Your download will take some time"
        },
        "pt-BR": {
            "ro_msg": "O download pode demorar um pouco"
        },
        "es": {
            "ro_msg": "La descarga puede demorar un poco"
        },
        "de": {
            "ro_msg": "Das Herunterladen wird einige Zeit in Anspruch nehmen."
        },
        "he": {
            "ro_msg": "לוקח זמן להוריד, אנא המתן"
        }
    },
    "updateInProgress": {
        "ru": {
            "ro_msg": "Обновление, пожалуйста, подождите"
        },
        "en": {
            "ro_msg": "Update in progress, plese wait"
        },
        "pt-BR": {
            "ro_msg": "Atualização em andamento, por favor aguarde"
        }
    },
    "tooBigRecord": {
        "ru": {
            "ro_msg": "К сожалению, объём файла подкаста слишком большой"
                      " Однако, вы можете прослушать <a href=\"%s\">по ссылке</a>"
        },
        "en": {
            "ro_msg": "Unfortunately, the podcast file too big."
                      " But you still can listen to it <a href=\"%s\">via link</a>"
        },
        "pt-BR": {
            "ro_msg": "Infelizmente, o arquivo do podcast é muito grande."
                      " Você ainda poderá ouvir através deste <a href=\"%s\">link</a>"
        },
        "es": {
            "ro_msg": "Lamentablemente el tamaño del podcast es demasiado grande."
                      " Usted puede escucharlo <a href=\"%s\">via link</a>"
        },
        "de": {
            "ro_msg": "Leider ist die Datei der Folge zu groß."
                      " Du kannst sie aber <a href=\"%s\">über den Link</a> anhören"
        },
        "he": {
            "ro_msg": "לצערינו, גודל הפודקאסט מידי גדול."
                      " אבל אתם עדיין יכולים להאזין לו <a href=\"%s\">ע''י קישור</a>"
        }

    },
    "tooBigRecord2": {
        "ru": {
            "ro_msg": "В <a href=\"%s\">itunes</a>"
        },
        "en": {
            "ro_msg": "In <a href=\"%s\">itunes</a>"
        },
        "pt-BR": {
            "ro_msg": "No <a href=\"%s\">itunes</a>"
        },
        "es": {
            "ro_msg": "En <a href=\"%s\">itunes</a>"
        },
        "de": {
            "ro_msg": "Bei <a href=\"%s\">itunes</a>"
        },
        "he": {
            "ro_msg": "ב <a href=\"%s\">itunes</a>"
        }

    },
    "tooBigRecord3": {
        "ru": {
            "ro_msg": "Или на <a href=\"%s\">сайте подкаста</a>"
        },
        "en": {
            "ro_msg": "Or on <a href=\"%s\">the podcast web site</a>"
        },
        "pt-BR": {
            "ro_msg": "Ou no <a href=\"%s\">site do podcast</a>"
        },
        "es": {
            "ro_msg": "O en el <a href=\"%s\">sitio web del podcast</a>"
        },
        "de": {
            "ro_msg": "Oder auf <a href=\"%s\">der Webseite des Podcasts</a>"
        },
        "he": {
            "ro_msg": "או ב <a href=\"%s\">אתר הפודקאסט</a>"
        }

    },
    "recordUnavaliable": {
        "ru": {
            "ro_msg": "К сожалению, файл подкаста недоступен."
                      " Попробуйте открыть его на <a href=\"%s\">официальном сайте</a>"
        },
        "en": {
            "ro_msg": "Unfortunately, the podcast file is unavaliable."
                      " Try to open it’s <a href=\"%s\">official site</a>"
        },
        "pt-BR": {
            "ro_msg": "Infelizmente, o arquivo do podcast não está disponível."
                      " Tente abrir o <a href=\"%s\">site oficial</a>"
        },
        "es": {
            "ro_msg": "Lamentablemente el fichero del podcast no está disponoble."
                      " Intenta abrir su <a href=\"%s\">sitio oficial</a>"
        },
        "de": {
            "ro_msg": "Leider ist die Datei der Episode nicht verfügbar."
                      " Versuche es auf der <a href=\"%s\">offiziellen Webseite</a>"
        },
        "he": {
            "ro_msg": "לצערינו, קובץ הפודקאסט לא ניתן לבחירה."
                      " נסה לפתוח את <a href=\"%s\">האתר הרשמי</a>"
        }
    },
    "recordUnavaliable2": {
        "ru": {
            "ro_msg": "Или по <a href=\"%s\">прямой ссылке на файл</a>"
        },
        "en": {
            "ro_msg": "Or by <a href=\"%s\">direct link to the file</a>"
        },
        "pt-BR": {
            "ro_msg": "Ou pelo <a href=\"%s\">link direto para o arquivo</a>"
        },
        "es": {
            "ro_msg": "O por <a href=\"%s\">enlace directo al archivo</a>"
        },
        "de": {
            "ro_msg": "Oder mit dem <a href=\"%s\">Link zur Datei</a>"
        },
        "he": {
            "ro_msg": "או ע''י <a href=\"%s\">קישור ישיר לקובץ</a>"
        }
    },
    "search": {
        "ru": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Поиск"
        },
        "en": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Search"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Pesquisar"
        },
        "es": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Buscar"
        },
        "de": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Suche"
        },
        "he": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "חפש"
        }
    },
    "goToSearch": {
        "ru": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Перейти в поиск"
        },
        "en": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Go to search"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Ir para pesquisar"
        },
        "es": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Ir a buscar"
        },
        "de": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "Gehen Sie zur Suche"
        },
        "he": {
            "ro_msg": emojiCodes.get('magnifier') + " " + "עבור לחיפוש"
        }
    },
    "exitSearchMode": {
        "ru": {
            "ro_msg": emojiCodes.get('CL') + " " + "Очистить поиск"
        },
        "en": {
            "ro_msg": emojiCodes.get('CL') + " " + "Clear search"
        },
    },
    "channelConnect": {
        "ru": {
            "ro_msg": emojiCodes.get('electricPlug') + " " + "Подключённые каналы"
        },
        "en": {
            "ro_msg": emojiCodes.get('electricPlug') + " " + "Connected channels"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('electricPlug') + " " + "Canais conectados"
        }
    },
    "add_by_rss": {
        "ru": {
            "ro_msg": emojiCodes.get('link') + " " + "Добавить по RSS"
        },
        "en": {
            "ro_msg": emojiCodes.get('link') + " " + "Add by RSS"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('link') + " " + "Adicionar por RSS"
        },
        "es": {
            "ro_msg": emojiCodes.get('link') + " " + "Agregar por RSS"
        },
        "de": {
            "ro_msg": emojiCodes.get('link') + " " + "Per RSS hinzufügen"
        },
        "he": {
            "ro_msg": emojiCodes.get('link') + " " + "הוסף באמצעות RSS"
        }
    },
    "addingByRssMessage": {
        "ru": {
            "ro_msg": emojiCodes.get('link') + " " + "Чтобы добавить подкаст, пришлите"
                                                     " ссылку на RSS в формате https://host/url-path?params"
                                                     "\n\nСервисы, которые поддерживает бот:"
        },
        "en": {
            "ro_msg": emojiCodes.get('link') + " " + "To add a podcast, please send"
                                                     " an RSS link in the format https://host/url-path?params"
                                                     "\n\nServices that the bot supports:"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('link') + " " + "Para adicionar um podcast, envie "
                                                     "um link RSS no formato https://host/url-path?params"
                                                     "\n\nServiços que o bot suporta:"
        },
        "es": {
            "ro_msg": emojiCodes.get('link') + " " + "Para agregar un podcast, envíe un"
                                                     " enlace RSS en el formato https://host/url-path?params"
                                                     "\n\nServicios que admite el bot:"
        },
        "de": {
            "ro_msg": emojiCodes.get('link') + " " + "Um einen Podcast hinzuzufügen, "
                                                     "senden Sie bitte einen RSS-Link im Format https://host/url-path?params"
                                                     "\n\nVom Bot unterstützte Dienste:"
        },
        "he": {
            "ro_msg": emojiCodes.get('link') + " " + "כדי להוסיף פודקאסט,"
                                                     " אנא שלח קישור RSS בפורמט https://host/url-path?params"
                                                     "\n\nשירותים שהבוט תומך בהם:"
        }
    },
    'wrongUrl': {
        'ru': {
            'ro_msg': 'Ссылка не соответствует формату'
        },
        'en': {
            'ro_msg': 'Link does not match format'
        }
    },
    "subscriptions": {
        "ru": {
            "ro_msg": emojiCodes.get('microphone') + " " + "Подписки"
        },
        "en": {
            "ro_msg": emojiCodes.get('microphone') + " " + "Subscriptions"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('microphone') + " " + "Assinaturas"
        },
        "es": {
            "ro_msg": emojiCodes.get('microphone') + " " + "Suscripciones"
        },
        "de": {
            "ro_msg": emojiCodes.get('microphone') + " " + "Abos"
        },
        "he": {
            "ro_msg": emojiCodes.get('microphone') + " " + "מינויים"
        }

    },
    "update": {
        "ru": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "Обновить"
        },
        "en": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "Update"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "Atualizar"
        },
        "es": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "Actualizar"
        },
        "de": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "Aktualisieren"
        },
        "he": {
            "ro_msg": emojiCodes.get('inboxTray') + " " + "עדכון"
        }
    },
    "lastUpdate": {
        "ru": {
            "ro_msg": "Последний выпуск"
        },
        "en": {
            "ro_msg": "Latest release"
        },
        "pt-BR": {
            "ro_msg": "Último lançamento"
        },
        "es": {
            "ro_msg": "Último lanzamiento"
        },
        "de": {
            "ro_msg": "Neueste Erscheinung"
        },
        "he": {
            "ro_msg": "המהדורה האחרונה"
        }
    },
    "uploaded": {
        "ru": {
            "ro_msg": "Загружено"
        },
        "en": {
            "ro_msg": "Uploaded"
        },
        "pt-BR": {
            "ro_msg": "Carregado"
        },
        "es": {
            "ro_msg": "Subido"
        },
        "de": {
            "ro_msg": "Hochgeladen"
        },
        "he": {
            "ro_msg": "הועלה"
        }

    },
    "loadNextRecord": {
        "ru": {
            "ro_msg": "Следующий выпуск"
        },
        "en": {
            "ro_msg": "Next episode"
        },
        "pt-BR": {
            "ro_msg": "Próximo episódio"
        }
    },
    "settings": {
        "ru": {
            "ro_msg": emojiCodes.get('gear') + " Настройки"
        },
        "en": {
            "ro_msg": emojiCodes.get('gear') + " Settings"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('gear') + " Configurações"
        },
        "es": {
            "ro_msg": emojiCodes.get('gear') + " Configuración"
        },
        "de": {
            "ro_msg": emojiCodes.get('gear') + " Einstellungen"
        },
        "he": {
            "ro_msg": emojiCodes.get('gear') + "הגדרות"
        }

    },
    "bot_settings": {
        "ru": {
            "ro_msg": emojiCodes.get('gear') + " Глобальные настройки бота"
        },
        "en": {
            "ro_msg": emojiCodes.get('gear') + " Global bot settings"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('gear') + " Configurações globais do bot"
        },
        "es": {
            "ro_msg": emojiCodes.get('gear') + " Configuración global de bot"
        },
        "de": {
            "ro_msg": emojiCodes.get('gear') + " Globale Bot-Einstellungen"
        },
        "he": {
            "ro_msg": emojiCodes.get('gear') + " הגדרות בוט גלובליות"
        }
    },
    "bitrate": {
        "ru": {
            "ro_msg": "Битрейт"
        },
        "en": {
            "ro_msg": "Bitrate"
        },
        "pt-BR": {
            "ro_msg": "Taxa de bits"
        },
        "es": {
            "ro_msg": "Bitrate"
        },
        "de": {
            "ro_msg": "Bitrate"
        },
        "he": {
            "ro_msg": "קצב סיביות (איכות)"
        }
    },
    "bitrate_settings_description": {
        "ru": {
            "ro_msg":
                emojiCodes.get('gear') + " *Выберите битрейт*\n\n"
                                         "Например, если битрейт составляет"
                                         " 64 kbit/s, то запись длиной 10 минут будет занимать около 4.6 мегабайт."
                                         "\nВ то же время, если битрейт будет в 2 раза больше, то и размер файла"
                                         " увеличится в 2 раза.\nДанный параметр влияет на качество записи.\n\n"
                                         "Текущий битрейт: "
        },
        "en": {
            "ro_msg": emojiCodes.get('gear') + " *Select bitrate *\n\n"
                                               "For example, if the bitrate is"
                                               " 64 kbit/s, then a 10 minute recording will take about 4.6 megabytes."
                                               "\nAt the same time, if the bitrate is 2 times higher, then the file size"
                                               " will double.\nThis parameter affects the recording quality.\n\n"
                                               "Current bitrate:"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('gear') + "*Selecione taxa de bits*\n\n"
                                               "Por exemplo, se a taxa for"
                                               " 64 kbit/s, uma gravação de 10 minutos levará cerca de 4,6 megabytes."
                                               "\nSendo assim, se a taxa de bits for 2 vezes maior, o tamanho do"
                                               " arquivo dobrará.\nEste parâmetro afeta a qualidade da gravação.\n\n"
                                               "Taxa de bits atual:"
        },
        "es": {
            "ro_msg": emojiCodes.get('gear') + "*Seleccionar bitrate*\n\n"
                                               "Por ejemplo, si la tasa de bits es"
                                               " 64 kbit/s, luego una grabación de 10 minutos tomará alrededor de 4,6 "
                                               "megabytes.\nl mismo tiempo, si la tasa de bits es 2 veces mayor, entonces"
                                               "el tamaño del archivo se duplicará.\nEste parámetro afecta la calidad de "
                                               "grabación.\n\nVelocidad de bits actual:"
        },
        "de": {
            "ro_msg": emojiCodes.get('gear') + "*Bitrate auswählen*\n\n"
                                               "Wenn die Bitrate beispielsweise"
                                               " 64 kbit/s beträgt, dann belegt eine 10-minütige Aufnahme etwa 4,6 "
                                               "Megabyte.\nAnalog verdoppelt sich bei doppelter Bitrate auch die "
                                               "Dateigröße.\nDieser Parameter wirkt sich auf die "
                                               "Aufnahmequalität aus.\n\nAktuelle Bitrate:"
        },
        "he": {
            "ro_msg": emojiCodes.get('gear') + " *בחר איכות *\n\n"
                                               "לדוגמה, אם האיכות כעת היא"
                                               " 64 kbit/s, נפח הקלטה של 10 דקות יהיה 4.6 מ\"ב."
                                               "\nלעומת זאת, אם האיכות תהיה פי 2 - גודל הקובץ יהיה"
                                               " כפול.\nהפרמטר הזה משפיע על איכות ההקלטה.\n\n"
                                               "איכות נוכחית:"
        }
    },
    "do_not_change_bitrate": {
        "ru": {
            "ro_msg": "Не изменять битрейт"
        },
        "en": {
            "ro_msg": "Don't change bitrate"
        },
        "pt-BR": {
            "ro_msg": "Não alterar a taxa de bits"
        },
        "es": {
            "ro_msg": "No cambie la tasa de bits"
        },
        "de": {
            "ro_msg": "Bitrate nicht ändern"
        },
        "he": {
            "ro_msg": "אל תשנה את האיכות"
        }
    },
    "bitrate_changed": {
        "ru": {
            "ro_msg": "Битрейт изменён, новое значение: "
        },
        "en": {
            "ro_msg": "Bitrate changed, new value: "
        },
        "pt-BR": {
            "ro_msg": "Taxa de bits alterada, novo valor: "
        },
        "es": {
            "ro_msg": "Bitrate cambiado, nuevo valor: "
        },
        "de": {
            "ro_msg": "Bitrate geändert, neuer Wert: "
        },
        "he": {
            "ro_msg": "האיכות שונתה. הערך החדש הוא: "
        }
    },
    "podcastOffer": {
        "ru": {
            "ro_msg": emojiCodes.get('crown') + " " + "Интересные подкасты"
        },
        "en": {
            "ro_msg": emojiCodes.get('crown') + " " + "Recommendations"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('crown') + " " + "Sugestões"
        },
        "es": {
            "ro_msg": emojiCodes.get('crown') + " " + "Le puede gustar"
        },
        "de": {
            "ro_msg": emojiCodes.get('crown') + " " + "Empfehlungen"
        },
        "he": {
            "ro_msg": emojiCodes.get('crown') + " " + "אולי תאהב את זה"
        }
    },
    "podcastTop": {
        "ru": {
            "ro_msg": emojiCodes.get('crown') + " " + "Топ подкастов" + \
                      " " + emojiCodes.get('globeEuropeAfrica')
        },
        "en": {
            "ro_msg": emojiCodes.get('crown') + " " + "Top podcasts" + \
                      " " + emojiCodes.get('globeEuropeAfrica')
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('crown') + " " + "Top podcasts" + \
                      " " + emojiCodes.get('globeEuropeAfrica')
        }
    },
    "podcastTopLang": {
        "ru": {
            "ro_msg": emojiCodes.get('crown') + " " + "Локальный топ"
        },
        "en": {
            "ro_msg": emojiCodes.get('crown') + " " + "Local Top"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('crown') + " " + "Top local"
        }
    },
    "generalTop": {
        "ru": {
            "ro_msg": emojiCodes.get('generalTop') + " " + "Общий топ"
        },
        "en": {
            "ro_msg": emojiCodes.get('generalTop') + " " + "General top"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('generalTop') + " " + "Top general"
        }
    },
    "help": {
        "ru": {
            "ro_msg": emojiCodes.get('information') + " " + "Помощь"
        },
        "en": {
            "ro_msg": emojiCodes.get('information') + " " + "Help"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('information') + " " + "Ajuda"
        },
        "es": {
            "ro_msg": emojiCodes.get('information') + " " + "Ayuda"
        },
        "de": {
            "ro_msg": emojiCodes.get('information') + " " + "Hilfe"
        },
        "he": {
            "ro_msg": emojiCodes.get('information') + " " + "עזרה"
        }

    },
    "another_projects": {
        "ru": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "Другое"
        },
        "en": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "Another"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "Outro"
        },
        "es": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "Otro"
        },
        "de": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "Ein weiterer"
        },
        "he": {
            "ro_msg": emojiCodes.get('goldenHeart') + " " + "אַחֵר"
        }
    },
    "another_projects_text": {
        "ru": {
            "ro_msg": "Кроме данного бота, существуют другие проекты от разработчика."
                      " На данный момент вы можете попробовать следующий проект:"
        },
        "en": {
            "ro_msg": "In addition to this bot, there are other projects from the "
                      "developer. For now, you can try the following project:"
        },
        "pt-BR": {
            "ro_msg": "Além desse bot, existem outros projetos do desenvolvedor. "
                      "Você pode experimentar o seguinte projeto, por enquanto:"
        },
        "es": {
            "ro_msg": "Además de este bot, hay otros proyectos del desarrollador. "
                      "Por ahora, puedes probar el siguiente proyecto:"
        },
        "de": {
            "ro_msg": "Neben diesem Bot gibt es noch weitere Projekte des Entwicklers."
                      " Im Moment können Sie das folgende Projekt ausprobieren:"
        },
        "he": {
            "ro_msg": "בנוסף לבוט זה, ישנם פרויקטים נוספים של היזם. "
                      "לעת עתה תוכל לנסות את הפרויקט הבא:"
        }
    },
    'advertisingQuestions': {
        'ru': {
            'ro_msg': "По вопросам рекламы пишите %s"
        },
        'en': {
            'ro_msg': "For advertising questions, write %s"
        }
    },
    "menuMessage": {
        "ru": {
            "ro_msg": "<b>Внимание! Автор бота не имеет отношения к "
                      "подкастам и их аудиозаписям и не несёт за них ответственность.</b>"
                      "\n\nВыберите действие из предложенных:"
        },
        "en": {
            "ro_msg": "<b>Attention! The bot author is not related to podcasts "
                      "and their audio recordings and is not responsible for them.</b>"
                      "\n\nPlease choose what you want to do:"
        },
        "pt-BR": {
            "ro_msg": "<b>Atenção! O autor do bot não tem vínculo com nenhum podcast e "
                      "suas gravaçõesm, e não é responsável por seu conteúdo ou publicação.</b>"
                      "\n\nPor favor, escolha uma das opções a seguir:"
        },
        "es": {
            "ro_msg": "<b>¡Atención! El autor del bot no está relacionado con los "
                      "podcasts y sus grabaciones de audio y no es responsable de ellos.</b>"
                      "\n\nPor favor, seleccione lo que quiere hacer:"
        },
        "de": {
            "ro_msg": "<b>Beachtung! Der Bot-Autor ist nicht mit Podcasts und deren "
                      "Audioaufnahmen verwandt und nicht dafür verantwortlich.</b>"
                      "\n\nBitte wähle eine der folgenden Möglichkeiten:"
        },
        "he": {
            "ro_msg": "<b>" + "תשומת הלב! מחבר הבוט אינו אחראי לפודקאסטים ולהקלטות השמע "
                      "שלהם ואינו אחראי עליהם." + "</b>"
                      "\n\nאנא בחר מה שברצונך לעשות:"
        }

    },
    "searchAdv": {
        "ru": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "Пришлите мне название подкаста, который вы хотите найти."
                      " Например, 'Лайфхакер'")
        },
        "en": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "Send me the name of a podcast you want to find."
                      " For example, 'Off The Vine with Kaitlyn Bristowe'")
        },
        "pt-BR": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "Envie o o nome do podcast que você deseja pesquisar."
                      " Por exemplo, 'Café Brasil'")
        },
        "es": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "Envíe el nombre del podcast que quiere encontrar."
                      " Por ejemplo, 'El enjambre'")
        },
        "de": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "Schicke mir den Namen eines Podcasts, den Du finden möchtest,"
                      " zum Beispiel „Whocast”.")
        },
        "he": {
            "ro_msg": (
                    emojiCodes.get('magnifier') + "\n"
                    + "שלח לי את שם הפודקאסט שברצונך למצוא."
                      " לדוגמא, 'עושים היסטוריה'")
        }

    },
    "cancel": {
        "ru": {
            "ro_msg": "Отмена"
        },
        "en": {
            "ro_msg": "Cancel"
        },
        "pt-BR": {
            "ro_msg": "Cancelar"
        },
        "es": {
            "ro_msg": "Cancelar"
        },
        "de": {
            "ro_msg": "Abbrechen"
        },
        "he": {
            "ro_msg": "ביטול"
        }
    },
    "searchResults": {
        "ru": {
            "ro_msg": "Результаты поиска:"
        },
        "en": {
            "ro_msg": "Search results:"
        },
        "pt-BR": {
            "ro_msg": "Resultados:"
        },
        "es": {
            "ro_msg": "Resultados:"
        },
        "de": {
            "ro_msg": "Suchergebnisse:"
        },
        "he": {
            "ro_msg": "תוצאות חיפוש:"
        }
    },
    'searchResultsNotFound': {
        'ru': {
            'ro_msg': "Ничего не найдено, попробуйте другой запрос"
        },
        'en': {
            'ro_msg': "Nothing found, please try another search query"
        }
    },
    "proTipSendPageNumToGo": {
        "ru": {
            "ro_msg": "ProTip: отправьте номер страницы, чтобы открыть её"
        },
        "en": {
            "ro_msg": "ProTip: send the page number to go to it"
        },
        "pt-BR": {
            "ro_msg": "Dica: envie o número da página para ir diretamente a ela"
        }
    },
    "proTipSendPageNumToGoWithSearch": {
        "ru": {
            "ro_msg": "ProTip: отправьте номер страницы, чтобы перейти на неё\n"
                      + emojiCodes.get("magnifier") + " " + "Отправьте текст, чтобы начать поиск"
        },
        "en": {
            "ro_msg": "ProTip: send the page number to go to it\n"
                      + emojiCodes.get("magnifier") + " " + "Send text to start searching"
        },
        "pt-BR": {
            "ro_msg": "Dica: envie o número da página para ir diretamente a ela\n"
                      + emojiCodes.get("magnifier") + " " + "Envie texto para começar a pesquisar"
        }
    },
    'sendTextToRestartSearch': {
        'ru': {
            'ro_msg': emojiCodes.get("magnifier") + " Отправьте текст, чтобы начать новый поиск"
        },
        'en': {
            'ro_msg': emojiCodes.get("magnifier") + " Send text to start new search"
        }
    },
    "loading": {
        "ru": {
            "ro_msg": "Загрузка... Пожалуйста, подождите!"
        },
        "en": {
            "ro_msg": "Loading... Please, wait for a while!"
        },
        "pt-BR": {
            "ro_msg": "Carregando... Por favor, aguarde!"
        },
        "es": {
            "ro_msg": "Cargando... Por favor, espere!"
        },
        "de": {
            "ro_msg": "Wird geladen… Bitte warte einen Moment!"
        },
        "he": {
            "ro_msg": "טוען... אנא המתן!"
        }
    },
    "donate": {
        "ru": {
            "ro_msg": "Помочь боту"
        },
        "en": {
            "ro_msg": "Support this bot"
        },
        "pt-BR": {
            "ro_msg": "Colabore com o bot"
        },
        "es": {
            "ro_msg": "Colabore con este bot"
        },
        "de": {
            "ro_msg": "Spenden"
        },
        "he": {
            "ro_msg": "תמיכה ברובוט זה"
        }
    },
    "subsMessage": {
        "ru": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "Список подкастов, на которые вы подписаны:")
        },
        "en": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "List of podcasts to which you are subscribed:")
        },
        "pt-BR": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "Podcasts que você assinou:")
        },
        "es": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "Lista de Podcasts a los que se ha suscrito:")
        },
        "de": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "Liste deiner Podcast-Abonnements:")
        },
        "he": {
            "ro_msg": (
                    emojiCodes.get('microphone') + "\n"
                    + "רשימת הפודקאסטים אליהם נרשמת:")
        }
    },
    "noNewRecords": {
        "ru": {
            "ro_msg": "Новых эпизодов нет!"
        },
        "en": {
            "ro_msg": "No new episodes!"
        },
        "pt-BR": {
            "ro_msg": "Nenhum episódio novo!"
        },
        "es": {
            "ro_msg": "No hay episodios nuevos!"
        },
        "de": {
            "ro_msg": "Keine neuen Folgen."
        },
        "he": {
            "ro_msg": "אין פרקים חדשים!"
        }
    },
    "youHaveNewEpisodes": {
        "ru": {
            "ro_msg": "*У вас есть новые эпизоды!*\n\nПодпишитесь на бота /subscription"
                      " или пригласите пользователей, чтобы получить аудиозаписи.\n"
                      "Ваша реферальная ссылка:"
        },
        "en": {
            "ro_msg": "*You have new episodes!*\n\n"
                      "Subscribe /subscribe to the bot or invite users to get audio records.\n"
                      "Your referral link:"
        },
        "pt-BR": {
            "ro_msg": "*Você tem novos episódios!*\n\nInscreva-se no bot enviando "
                      "/subscription ou convide usuários para receber arquivos de áudio.\n"
                      "Seu link de convite:"
        }
    },
    "youHaveNewEpisodesShort": {
        "ru": {
            "ro_msg": "<b>У вас есть новые эпизоды!</b>"
        },
        "en": {
            "ro_msg": "<b>You have new episodes!</b>"
        },
        "pt-BR": {
            "ro_msg": "<b>Você tem novos episódios!</b>"
        }
    },
    "noSubs": {
        "ru": {
            "ro_msg": "У вас нет подписок."
        },
        "en": {
            "ro_msg": "You have no subscriptions!"
        },
        "pt-BR": {
            "ro_msg": "Você não tem inscrições!"
        },
        "es": {
            "ro_msg": "Usted no tiene suscripciones!"
        },
        "de": {
            "ro_msg": "Du hast nichts abonniert."
        },
        "he": {
            "ro_msg": "אין לך מינויים!"
        }
    },
    "withoutTariffSubscriptionsLimited": {
        "ru": {
            "ro_msg": "Без тарифа количество подписок ограничено. Вы достигли"
                      " предела. Отпишитесь от другого подкаста или подпишитесь на бота"
                      " /subscription."
        },
        "en": {
            "ro_msg": "Without tariff, the number of subscriptions is limited."
                      " You have now reached the limit. Unsubscribe from another podcast"
                      " or upgrade to any tariff /subscription."
        },
        "pt-BR": {
            "ro_msg": "Sem um plano, o número de assinaturas é limitado. "
                      "Você agora atingiu o limite. Cancele a assinatura de outro podcast "
                      "ou atualize para qualquer plano enviando /subscription."
        },
        "es": {
            "ro_msg": "Sin tarifa, el número de suscripciones es limitado. "
                      "Ahora ha alcanzado el límite. Cancele la suscripción a otro podcast "
                      "o actualice a cualquier tarifa /subscription."
        },
        "de": {
            "ro_msg": "Ohne Tarif ist die Anzahl der Abonnements begrenzt. "
                      "Sie haben jetzt das Limit erreicht. Melden Sie sich von einem anderen "
                      "Podcast ab oder aktualisieren Sie auf einen Tarif /subscription."
        },
        "he": {
            "ro_msg": "ללא תעריף, מספר המנויים מוגבל. עכשיו הגעת לגבול. "
                      "בטל את הרישום לפודקאסט אחר או שדרג לתעריף כלשהו /subscription"
        }
    },
    "withoutTariffUpdateLimited": {
        "ru": {
            "ro_msg": "Без тарифа количество подкастов при ручном обновлении ограничено"
                      " " + str(max_subscriptions_without_tariff) + \
                      ". Перейдите на другой тариф /subscription \n\n"
                      "Вы можете помочь боту с развитием! /donate или пожертвуйте на"
                      " [Patreon.com](%s)" % donate_link
        },
        "en": {
            "ro_msg": "Without tariff, the number of podcasts with manual update is "
                      "limited to " + str(max_subscriptions_without_tariff) + \
                      ". Upgrade to any tariff /subscription\n\n"
                      "You can support this bot with a donation! /donate or"
                      " [Patreon.com](%s)" % donate_link
        },
        "pt-BR": {
            "ro_msg": "Sem plano, o número de podcasts com atualização manual é "
                      "limitado a " + str(max_subscriptions_without_tariff) + \
                      ". Atualize para qualquer plano usando /subscription\n\n"
                      "Você pode apoiar este bot com uma doação! Envie /donate ou"
                      "acesse [Patreon.com](%s)" % donate_link
        }
    },
    "withoutTariffCantChooseBitrate": {
        "ru": {
            "ro_msg": "Для смены битрейта нужна подписка на бота. Подробнее: /subscription"
        },
        "en": {
            "ro_msg": "Bot subscription is required to change bit rate. More info: /subscription"
        }
    },
    "podcastDoesNotExist": {
        "ru": {
            "ro_msg": "Не удалось получить данные подкаста, попробуйте позже."
                      " Возможно, он был удалён или автор не разрешает просматривать его.\n"
                      "Внимание, если вы подписаны и отпишетесь сейчас, то вы, возможно,"
                      " больше не сможете подписаться."
        },
        "en": {
            "ro_msg": "Failed to get podcast data, try again later."
                      " It may have been deleted or the author does not allow viewing it.\n"
                      "Attention, if you are subscribed and unsubscribe now,"
                      " then you may no longer be able to subscribe."
        },
        "pt-BR": {
            "ro_msg": "Falha ao obter dados do podcast, tente depois."
                      " Talvez tenha sido removido pelo autor ou o autor não permite a sua"
                      " visualização.\nAtenção! Se você estiver inscrito e cancelar sua"
                      " assinatura, talvez você não consiga mais se inscrever."
        },
        "es": {
            "ro_msg": "Error al obtener datos de podcast, intente nuevamente."
                      " Tal vez haya sido eliminado o el autor no permite la visualización.\n"
                      "Atención! Si está suscrito y cancelado su suscripción,"
                      " es posible que no pueda volver a suscribirse."
        },
        "de": {
            "ro_msg": "Abrufen der Podcast-Daten fehlgeschlagen. Versuche es später"
                      " erneut. Womöglich wurde er gelöscht oder der Besitzer verbietet den"
                      " Zugriff.\n"
                      "Vorsicht! Falls Du diesen Podcast abonniert hast und nun Dein Abo"
                      " beendest,"
                      " ist es Dir eventuell nicht mehr möglich, ihn erneut zu abonnieren."
        },
        "he": {
            "ro_msg": "השגת נתוני הפודקאסט נכשלה. נסה מאוחר יותר."
                      " יתכן שהוא נמחק או שהמחבר אינו מאפשר להציג אותו.\n"
                      "שים לב, אם אתה רשום ותבטל כעת את המינוי,"
                      " יתכן שלא תוכל לחזור ולהרשם."
        }
    },
    "botDescr": {
        "ru": {
            "ro_msg": "Этот бот позволяет вам искать, слушать и подписываться"
                      " на подкасты. Если вы подпишитесь на какой-нибудь канал,"
                      " то при выходе нового выпуска бот пришлёт его вам."
        },
        "en": {
            "ro_msg": "This bot allows you to search, listen and subscribe to podcasts."
                      " If you subscribe to any channel, then when a new release appears,"
                      " the bot will send it to you."
        },
        "pt-BR": {
            "ro_msg": "Este bot permite pesquisar, escutar e assinar podcasts."
                      " Se você assinar um podcast,"
                      " o bot irá enviar novos episódios assim que forem lançados."
        },
        "es": {
            "ro_msg": "Este bot le permite buscar, escuchar y suscribirse a podcasts."
                      " Si usted se suscribe a algún canal,"
                      " cuando haya nuevos episodios el bot se los enviará."
        },
        "de": {
            "ro_msg": "Dieser Bot ermöglicht es Dir, Podcasts zu suchen,"
                      " sie anzuhören und zu abonnieren."
                      " Nachdem Du einen Podcast abonniert hast,"
                      " wird der Bot dir neue Episoden schicken wann immer sie herauskommen."
        },
        "he": {
            "ro_msg": "בוט זה מאפשר לך לחפש, להאזין ולהירשם לפודקאסטים."
                      " אם אתה נרשם לערוץ מסוים, כשיופיע פרק חדש,"
                      " הבוט ישלח לך אותו."
        }
    },
    "whatPodcastIs": {
        "ru": {
            "ro_msg": "Что такое подкасты: "
                      "https://ru.wikipedia.org/wiki/%D0%9F%D0%BE%D0%B4%D0%BA%D0%B0%D1%81%D1%82%D0%B8%D0%BD%D0%B3"
        },
        "en": {
            "ro_msg": "What are podcasts: https://en.wikipedia.org/wiki/Podcast"
        },
        "pt-BR": {
            "ro_msg": "O que são podcasts: https://en.wikipedia.org/wiki/Podcast"
        },
        "es": {
            "ro_msg": "Que son los podcasts: https://en.wikipedia.org/wiki/Podcast"
        },
        "de": {
            "ro_msg": "Was sind Podcasts: https://en.wikipedia.org/wiki/Podcast"
        },
        "he": {
            "ro_msg": "מהם פודקאסטים: https://en.wikipedia.org/wiki/Podcast"
        }
    },
    "functsDescr": {
        "ru": {
            "ro_msg": "Открыть главное меню: /menu. Все команды, указанные ниже, могут"
                      " быть доступны также из меню\n\n"
                      "Поиск подкастов по названию: /search\n\n"
                      "При подписке на подкаст он сохраняется в ваш список, доступный с помощью /subscriptions."
                      " В этом режиме вы можете прислать цифру и перейти на эту страницу"
                      " или часть названия подкаста, чтобы включить фильтрацию\n\n"
                      "Чтобы скачать выпуск, нажмите на \"Слушать\" и выберите нужный выпуск."
                      " Здесь также работает постраничная навигация и фильтрация, а также есть полезные функции\n\n"
                      "Если у вас есть подписка на бота, он будет присылать новые выпуски автоматически, если у"
                      " подкаста активна кнопка с колокольчиком \"Новые эпизоды\"."
                      " Иначе вы можете использовать команду /update\n\n"
                      f"Бот также поддервижает inline-режим. В любом чате введите `@{botName} название_подкаста`,"
                      " чтобы увидеть предложения поисковых вариантов с этим подкастом и прямой ссылкой в бота. А если"
                      f" вы введёте `@{botName} название_подкаста / номер_страницы`, то увидите эпизоды этого подкаста"
                      " на выбранной странице. Нажмите на эпизод, чтобы сразу же отправить его (или ссылку) в чат.\n\n"
                      "Введите символ / и изучите все команды, или начните знакомство с /menu!"
        },
        "en": {
            "ro_msg": "Open main menu: /menu. All of the commands below can also be accessed from the menu\n\n"
                      "Search for podcasts by title: /search\n\n"
                      "When you subscribe to a podcast, it is saved to your list, accessible via /subscriptions."
                      " In this mode, you can send a number and go to this page"
                      " or part of the podcast title to enable filtering\n\n"
                      "To download an episode, click \"Listen\" and select the desired episode."
                      " Pagination and filtering also works here, and there are also some useful functions\n\n"
                      "If you have a subscription to the bot, it will send new episodes automatically"
                      " if the \"New episodes\" bell button is active on the podcast."
                      " Otherwise, you can use /update\n\n"
                      f"The bot also supports inline mode. In any chat, enter `@{botName} podcast_name` to see search"
                      " suggestions with this podcast and a direct link to the bot. And if you enter"
                      " `@{botName} podcast_name / page_number`, then you will see episodes of this podcast"
                      " on the selected page, click on an episode to send it (or a link) to chat immediately.\n\n"
                      "Type / and learn all the commands, or start with /menu!"
        },
        "pt-BR": {
            "ro_msg": "Abra o menu principal: /menu. Todos os comandos abaixo também podem ser acessados no menu\n\n"
                      "Pesquise podcasts por título: /search\n\n"
                      "Quando você assina um podcast, ele é salvo em sua lista, acessível via /subscriptions."
                      " Nesse modo, você pode enviar um número e acessar esta página"
                      " ou parte do título do podcast para ativar a filtragem\n\n"
                      "Para baixar um episódio, clique em \"Ouvir\" e selecione o episódio desejado."
                      " Paginação e filtragem também funcionam aqui, e também há funções úteis\n\n"
                      "Se você tiver uma assinatura do bot, ele enviará novos episódios automaticamente"
                      " se o botão de sino \"Novos episódios\" estiver ativo no podcast."
                      " Caso contrário, você pode usar o comando /update\n\n."
                      f"O bot também suporta o modo inline. Em qualquer chat, digite `@{botName} podcast_name` para ver"
                      " sugestões de pesquisa com este podcast e um link direto para o bot. E se você digitar"
                      " `@{botName} podcast_name / page_number`, então você verá episódios deste podcast na página"
                      " selecionada, clique em um episódio para enviá-lo (ou um link) para conversar imediatamente.\n\n"
                      "Digite o símbolo / e aprenda todos os comandos, ou comece com /menu!"
        },
        "es": {
            "ro_msg": "Abrir el menú principal: /menu."
                      " También se puede acceder a todos los comandos a continuación desde el menú\n\n"
                      "Busque podcasts por título: /search\n\n"
                      "Cuando se suscribe a un podcast, se guarda en su lista, accesible a través de /subscriptions."
                      " En este modo, puede enviar un número e ir a esta página o parte del"
                      " título del podcast para habilitar el filtrado\n\n"
                      "Para descargar un episodio, haga clic en \"Escuchar\" y seleccione el episodio deseado."
                      " La paginación y el filtrado también funcionan aquí, y también hay funciones útiles\n\n"
                      "Si tiene una suscripción al bot, enviará nuevos episodios automáticamente"
                      " si el botón de campana \"Nuevos episodios\" está activo en el podcast."
                      " De lo contrario, puede usar el comando /update\n\n."
                      f"El bot también es compatible con el modo en línea. En cualquier chat, ingrese"
                      " `@{botName} podcast_name` para ver sugerencias de búsqueda con este podcast y un enlace directo"
                      " al bot. Y si ingresa `@{botName} podcast_name / page_number`, luego verá episodios de este"
                      " podcast en la página seleccionada, haga clic en un episodio para enviarlo (o un enlace) para"
                      " chatear inmediatamente.\n\n"
                      "Ingrese el símbolo / y aprenda todos los comandos, ¡o comience con /menu!"
        },
        "de": {
            "ro_msg": "Hauptmenü öffnen: /menu."
                      " Auf alle unten aufgeführten Befehle kann auch über das Menü zugegriffen werden\n\n"
                      "Suche nach Podcasts anhand des Titels: /search\n\n"
                      "Wenn Sie einen Podcast abonnieren, wird er in Ihrer Liste gespeichert,"
                      " auf die Sie über /subscriptions zugreifen können. In diesem Modus können"
                      " Sie eine Nummer senden und zu dieser Seite oder einem Teil des Podcast-Titels"
                      " gehen, um die Filterung zu aktivieren\n\n"
                      "Um eine Folge herunterzuladen, klicken Sie auf \"Anhören\""
                      " und wählen Sie die gewünschte Folge aus."
                      " Auch hier funktionieren Paginierung und Filterung, außerdem gibt es nützliche Funktionen\n\n"
                      " Wenn du den Bot abonniert hast, sendet er neue Folgen automatisch, wenn die Glocke"
                      " \"Neue Folgen\" beim Podcast aktiv ist. Andernfalls können Sie den Befehl /update verwenden\n\n"
                      f"Der Bot unterstützt auch den Inline-Modus. Geben Sie in einem beliebigen Chat"
                      " `@{botName} podcast_name` ein, um Suchvorschläge mit diesem Podcast und einen direkten Link zum"
                      " Bot anzuzeigen. Und wenn Sie `@{botName} podcast_name / page_number` eingeben, dann sehen Sie"
                      " Episoden dieses Podcasts auf der ausgewählten Seite, klicken Sie auf eine Episode, um sie"
                      " (oder einen Link) sofort zum Chatten zu senden.\n\n"
                      "Geben Sie das Symbol / ein und lernen Sie alle Befehle, oder beginnen Sie mit /menu!"
        },
        "he": {
            "ro_msg": "פתח את התפריט הראשי: /menu. ניתן לגשת לכל הפקודות למטה גם מהתפריט\n\n"
                      "חפש פודקאסטים לפי כותרת: /search\n\n"
                      "כאשר אתה נרשם לפודקאסט, הוא נשמר ברשימה שלך, נגיש דרך /subscriptions."
                      " במצב זה, תוכל לשלוח מספר וללכת לדף זה או לחלק מכותרת הפודקאסט כדי לאפשר סינון\n\n"
                      "להורדת פרק, לחץ על \"האזן\" ובחר את הפרק הרצוי."
                      " גם עימוד וסינון עובדים כאן, ויש גם פונקציות שימושיות\n\n"
                      "אם יש לך מנוי לבוט, הוא ישלח פרקים חדשים באופן אוטומטי אם כפתור הפעמון של"
                      " \"פרקים חדשים\" פעיל בפודקאסט. אחרת, אתה יכול להשתמש ב- /update\n\n."
                      f"הבוט תומך גם במצב מוטבע. בכל צ'אט, הזן `@{botName} podcast_name` כדי לראות הצעות חיפוש עם"
                      " הפודקאסט הזה וקישור ישיר לבוט. ואם תזין `@{botName} podcast_name / page_number`, לאחר מכן"
                      " תראה פרקים של הפודקאסט הזה בעמוד הנבחר, לחץ על פרק כדי לשלוח אותו (או קישור) לצ'אט באופן מיידי.\n\n"
                      "הזן את הסמל / ולמד את כל הפקודות, או התחל עם /menu!"
        }
    },
    "yes": {
        "ru": {"ro_msg": "Да"},
        "en": {"ro_msg": "Yes"},
        "pt-BR": {"ro_msg": "Sim"},
        "es": {"ro_msg": "Sí"},
        "de": {"ro_msg": "Ja"},
        "he": {"ro_msg": "כן"}
    },
    "no": {
        "ru": {"ro_msg": "Нет"},
        "en": {"ro_msg": "No"},
        "pt-BR": {"ro_msg": "Não"},
        "es": {"ro_msg": "No"},
        "de": {"ro_msg": "Nein"},
        "he": {"ro_msg": "לא"}
    },
    "unlimited": {
        "ru": {
            "ro_msg": "Неограниченно"
        },
        "en": {"ro_msg": "Unlimited"},
        "pt-BR": {"ro_msg": "Ilimitado"},
        "es": {"ro_msg": "Ilimitado"},
        "de": {"ro_msg": "Unbegrenzt"},
        "he": {"ro_msg": "ללא הגבלה"}
    },
    "disable": {
        "ru": {
            "ro_msg": "Отключить"
        },
        "en": {
            "ro_msg": "Disable"
        },
        "pt-BR": {
            "ro_msg": "Desabilitar"
        },
        "es": {
            "ro_msg": "Desactivar"
        },
        "de": {
            "ro_msg": "Deaktivieren"
        },
        "he": {
            "ro_msg": "השבת"
        }
    },
    "not_selected": {
        "ru": {
            "ro_msg": "Не выбран"
        },
        "en": {
            "ro_msg": "Not selected"
        },
        "pt-BR": {
            "ro_msg": "Não selecionado"
        },
        "es": {
            "ro_msg": "No seleccionado"
        },
        "de": {
            "ro_msg": "Nicht ausgewählt"
        },
        "he": {
            "ro_msg": "לא נבחר"
        }
    },
    "youAlreadySubscribedOnTariff": {
        "ru": {
            "ro_msg": "Вы уже подписаны на данный тариф"
        },
        "en": {
            "ro_msg": "You are already subscribed to this tariff"
        },
        "de": {
            "ro_msg": "Du bist bereits in dieser Preisklasse."
        },
        "he": {
            "ro_msg": "אתה מנוי כבר למסלול זה."
        },
        "pt-BR": {
            "ro_msg": "Você já está inscrito neste plano."
        }
    },
    "tariffActivatedNotEnoughMoney": {
        "ru": {
            "ro_msg": "Вы уже подписаны на данный тариф, но он не активирован.\n"
                      "Чтобы активировать его, вам надо положить на баланс ещё %s" + \
                      emojiCodes.get('dollar') + "(доллары)."
        },
        "en": {
            "ro_msg": "You have already subscribed to this tariff, but it has not"
                      " been activated. \nTo activate it, you need to add %s to your balance" + \
                      emojiCodes.get('dollar') + "(dollars)."
        },
        "pt-BR": {
            "ro_msg": "Você já se inscreveu neste plano, mas ele não"
                      " foi ativado. \nPara ativá-lo, você precisa adicionar %s ao seu saldo" + \
                      emojiCodes.get('dollar') + "(dólares)."
        },
        "de": {
            "ro_msg": "Du bist bereits in dieser Preisklasse, sie wurde aber noch nicht"
                      " aktiviert. \nUm sie zu aktivieren musst Du Deinen Kontostand um %s "
                      "erhöhen" + emojiCodes.get('dollar') + "(in Dollar)."
        },
        "he": {
            "ro_msg": "נרשמת כבר למסלול זה, אבל המסלול עדיין לא"
                      " הופעל. \nעליך להוסיף %s דולר ליתרה שלך כבר להפעיל אותו " + \
                      emojiCodes.get('dollar') + "(dollars)."
        }
    },
    "notEnoughMoneyToActivate": {
        "ru": {
            "ro_msg": "Недостаточно средств чтобы активировать тариф.\n"
                      "Чтобы активировать его до конца текущего срока, вам надо положить на "
                      "баланс ещё %s" + emojiCodes.get('dollar') + "(доллары)."
        },
        "en": {
            "ro_msg": "Insufficient funds to activate the tariff.\n"
                      "To fully activate it, you need to add %s to your balance" + \
                      emojiCodes.get('dollar') + "(dollars)."
        },
        "pt-BR": {
            "ro_msg": "Fundos insuficientes para ativar o plano.\n"
                      "Para ativá-lo, você precisa adicionar %s ao seu saldo" + \
                      emojiCodes.get('dollar') + "(dólares)."
        },
        "de": {
            "ro_msg": "Deine Mittel sind unzureichend, um diese Preisklasse "
                      "freizuschalten.\nUm sie vollständig zu aktivieren musst Du Deinen "
                      "Kontostand um %s erhöhen" + emojiCodes.get('dollar') + "(in Dollar)."
        }
    },
    "tariffSuccessChanged": {
        "ru": {
            "ro_msg": "Тариф успешно применён!"
        },
        "en": {
            "ro_msg": "The tariff has been successfully applied!"
        },
        "pt-BR": {
            "ro_msg": "O plano foi ativado com sucesso!"
        },
        "he": {
            "ro_msg": "המסלול שלך אושר והתחיל בהצלחה!"
        },
        "de": {
            "ro_msg": "Deine Preisklasse wurde erfolgreich angepasst!"
        }
    },
    "tariffNotActive": {
        "ru": {
            "ro_msg": "Тариф не активирован! Чтобы активировать его, пополните баланс"
        },
        "en": {
            "ro_msg": "The tariff is not activated! To activate it, top up your balance"
        },
        "pt-BR": {
            "ro_msg": "O plano não está ativo! Para ativá-lo, recarregue seu saldo"
        },
        "he": {
            "ro_msg": "המסלול שלך לא הופעל! כדי להפעיל אותו - בדוק את היתרה שלך"
        },
        "de": {
            "ro_msg": "Die Preisklasse ist nicht aktiv! Lade zum Freischalten Dein "
                      "Konto auf!"
        }
    },
    "bot_subscription": {
        "ru": {
            "ro_msg": emojiCodes.get('creditCard') + " " + "Подписка"
        },
        "en": {
            "ro_msg": emojiCodes.get('creditCard') + " " + "Subscription"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('creditCard') + " " + "Planos"
        },
        "he": {
            "ro_msg": emojiCodes.get('creditCard') + " " + "מינויים"
        },
        "de": {
            "ro_msg": emojiCodes.get('creditCard') + " " + "Aufstocken"
        }
    },
    "bot_sub_page_header": {
        "ru": {
            "ro_msg": emojiCodes.get('creditCard') + " Подписка на бота"
        },
        "en": {
            "ro_msg": emojiCodes.get('creditCard') + " Bot subscription"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('creditCard') + " Assinatura do bot"
        },
        "he": {
            "ro_msg": emojiCodes.get('creditCard') + " מנויים לרובוט"
        },
        "de": {
            "ro_msg": emojiCodes.get('creditCard') + " Bot-Abonnement"
        }
    },
    "pay": {
        "ru": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Оплатить"
        },
        "en": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Pay"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Pagar"
        }
    },
    "donate_page_body": {
        "ru": {
            "ro_msg": "Подписка позволяет получить доступ ко всем возможностям бота\n\n"
                      "Существует несколько тарифов. Ознакомьтесь с ними, нажав на кнопку "
                      "\"Выбрать тариф\".\n\n"
                      "<b>Внимание! Любое пополнение счёта считаются безвозмездным "
                      "пожертвованием!</b> "
                      "Доллары в системе — это выдающиеся за пожертвования виртуальные очки, "
                      "которые не считаются деньгами, а их курс равен доллару США (USD), "
                      "при этом они принадлежат владельцу бота, а не пользователям. "
        },
        "en": {
            "ro_msg": "Subscription allows you to access all the features\n\n"
                      "There are several tariffs. Check them out by clicking on the button "
                      "\"Choose a tariff\" button.\n\n"
                      "<b>Attention! Any replenishment of the account is considered "
                      "a donation!</b> Dollars in the system are virtual points "
                      "awarded for donations, they are not considered money, "
                      "and their exchange rate is equal to the US dollar, "
                      "while they belong to the bot owner, not to users."
        },
        "pt-BR": {
            "ro_msg": "A assinatura permite que você acesse todos os recursos\n\n"
                      "Existem diversos planos. Confira cada um clicando no botão "
                      "\"Escolha um plano\".\n\n"
                      "<b>Atenção!  Qualquer inclusão de saldo é considerada "
                      "uma doação!</b> Dólares no saldo são como pontos virtuais "
                      "concedidos pelas doações. Eles não são considerados dinheiro, "
                      "e sua taxa de câmbio é igual ao dólar americano, "
                      "por pertencerem ao proprietário do bot, não aos usuários."
        },
        # "he": {
        # 	"ro_msg": "מנוי מאפשר לך לגשת לכל התכונות של הבוט.\n"
        # 	"ישנם מספר מסלולים. למידע נוסף והרשמה,"
        # 	"לחץ על כפתור \"Choose a tariff\".\nכדי להפקיד כסף לחשבון "
        # 	"שלך, לחץ על כפתור \"Top up balance\"."
        # },
        # "de": {
        # 	"ro_msg": "Im Abonnement erhälst Du Zugriff auf alle Funktionen des Bots.\n"
        # 	"Es gibt mehrere Preisklassen. Um mehr zu erfahren und um zu abonnieren, "
        # 	"drücke „Preisklasse wählen”!\nUm Dein Konto aufzuladen, "
        # 	"drücke „Konto aufladen”!"
        # }
    },
    "payViaCryptoBot": {
        "ru": {
            "ro_msg": "Пополнить с помощью Crypto Bot"
        },
        "en": {
            "ro_msg": "Top up balance via Crypto Bot"
        },
        "pt-BR": {
            "ro_msg": "Fazer uma recarga através do Crypto Bot"
        }
    },
    "bot_sub_cryptobot_page_body": {
        "ru": {
            "ro_msg": "Выберите криптовалюту, которая есть "
                      "на вашем счёте Crypto Bot\n\n"
                      "Подробнее: @cryptobot"
        },
        "en": {
            "ro_msg": "Select the cryptocurrency that you have "
                      "on your Crypto Bot account\n\n"
                      "More details: @cryptobot"
        },
        "pt_BR": {
            "ro_msg": "Selecione a criptomoeda que você tem "
                      "na sua conta do Crypto Bot\n\n"
                      "Para maiores detalhes, acesse @cryptobot"
        }
    },
    "bot_sub_cryptobot_amount_input": {
        "ru": {
            "ro_msg": "Введите значение, на которое вы хотите пополнить ваш баланс "
                      "внутри бота в долларах (USD)" + emojiCodes.get('dollar')
        },
        "en": {
            "ro_msg": "Enter the value you want to top up your bot balance "
                      "in USD " + emojiCodes.get('dollar') + "(dollars)"
        },
        "pt-BR": {
            "ro_msg": "Insira o valor que deseja recarregar o saldo do bot "
                      "em dólares " + emojiCodes.get('dollar') + "(dólares)"
        }
    },
    "cryptobot_generated_link_page": {
        "ru": {
            "ro_msg": "Вы собираетесь пополнить баланс бота на {summa}"
                      + emojiCodes.get('dollar') + "(долларов) с помощью "
                                                   "{assetAmount} {asset}\n\n"
                                                   "Обменный курс: 1 {asset} = {exchangeRateUSD}$ (долларов)\n\n"
                                                   "Нажмите на ссылку, чтобы произвести оплату: {paymentLink}"
        },
        "en": {
            "ro_msg": "You are going to top up the bot balance by {summa}"
                      + emojiCodes.get('dollar') + "(dollars) using "
                                                   "{assetAmount} {asset}\n\n"
                                                   "Exchange rate: 1 {asset} = {exchangeRateUSD}$ (dollars)\n\n"
                                                   "Click on the link to make payment: {paymentLink}"
        },
        "pt-BR": {
            "ro_msg": "Você vai recarregar o saldo do bot em {summa}"
                      + emojiCodes.get('dollar') + "(dólares) usando "
                                                   "{assetAmount} {asset}\n\n"
                                                   "Taxa de câmbio: 1 {asset} = {exchangeRateUSD}$ (dólares)\n\n"
                                                   "Clique no link para efetuar o pagamento: {paymentLink}"
        }
    },
    "payViaPatreon": {
        "ru": {
            "ro_msg": "Подписаться с помощью Patreon"
        },
        "en": {
            "ro_msg": "Subscribe via Patreon"
        }
    },
    "patreon_page_body": {
        "ru": {
            "ro_msg": "Чтобы подписка заработала, "
                      "зарегистрируйтесь на Patreon.com. Затем в этом меню бота нажмите на "
                      "кнопку \"Указать почту Patreon\" и пришлите боту почту, которую вы "
                      "использовали при регистрации на Patreon. Затем перейдите на "
                      + "<a href='%s'>%s</a> " % (donate_link, donate_link)
                      + "и пожертвуйте необходимую сумму."
                        "\n\nПроверка на подписку произойдёт автоматически, но вы также можете "
                        "нажать на кнопку \"Проверить Patreon\", чтобы сделать это вне очереди."
        },
        "en": {
            "ro_msg": "Register on Patreon.com to "
                      "activate your subscription. Then, in this bot menu, click on the "
                      "\"Specify Patreon Mail\" button and send to the bot the mail that you "
                      "used when registering on Patreon. Then go to "
                      + "<a href='%s'>%s</a> " % (donate_link, donate_link)
                      + "and donate the required amount."
                        "\n\nVerification for subscription will happen automatically, but you can "
                        "also click on the \"Check Patreon\" button to do it outside queue."
        },
        "pt-BR": {
            "ro_msg": "Registre-se no Patreon.com para "
                      "ativar sua assinatura. Então, neste menu do bot, clique em "
                      "\"Informar e-mail do Patreon\" e envie ao bot o e-mail "
                      "usado para registro no Patreon. Então, acesse "
                      + "<a href='%s'>%s</a> " % (donate_link, donate_link)
                      + "e realiza a doação do montante necessário."
                        "\n\nA verificação da assinatura acontecerá automaticamente, mas você pode "
                        "também clicar em \"Validar Patreon\" para verificar manualmente."
        }
    },
    "thisMonthHasAlreadyBeenReplenished": {
        "ru": {
            "ro_msg": "В этом месяце баланс уже был пополнен"
        },
        "en": {
            "ro_msg": "Balance has already been replenished this month"
        },
        "pt-BR": {
            "ro_msg": "O saldo já foi recarregado este mês"
        }
    },
    "noDataUpdatePatreon": {
        "ru": {
            "ro_msg": "Нет новых данных, проверьте почту и попробуйте позже"
        },
        "en": {
            "ro_msg": "No new data, check your email and try again later"
        },
        "pt-BR": {
            "ro_msg": "Sem novos dados, verifique seu e-mail e tente novamente mais "
                      "tarde"
        }
    },
    "balanceFromPatreonAdded": {
        "ru": {
            "ro_msg": "Вам начислен баланс в качестве благодарности за подписку на "
                      "Patreon! Выберите тариф, используя команду /subscription. "
                      "Текущие условия:"
        },
        "en": {
            "ro_msg": "You have been credited with a balance as a thank you for "
                      "subscribing to Patreon! Select tariff using command /subscription. "
                      "Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Você recebeu um crédito como agradecimento pela "
                      "inscrição no Patreon! Selecione o plano usando o comando /subscription. "
                      "Condições atuais:"
        }
    },
    "tellPatreonEmail": {
        "ru": {
            "ro_msg": emojiCodes.get('email') + " Указать почту Patreon"
        },
        "en": {
            "ro_msg": emojiCodes.get('email') + " Specify Patreon Mail"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('email') + " Informar e-mail do Patreon"
        }
    },
    "checkPatreonStatus": {
        "ru": {
            "ro_msg": emojiCodes.get('inboxTray') + " Проверить Patreon"
        },
        "en": {
            "ro_msg": emojiCodes.get('inboxTray') + " Check Patreon"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('inboxTray') + " Validar Patreon"
        }
    },
    "donate_page_email_input": {
        "ru": {
            "ro_msg": emojiCodes.get('email') + " Пришлите свой email"
        },
        "en": {
            "ro_msg": emojiCodes.get('email') + " Send your email"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('email') + " Envie o e-mail"
        }
    },
    "current_email": {
        "ru": {
            "ro_msg": "Текущий email"
        },
        "en": {
            "ro_msg": "Current email"
        },
        "pt-BR": {
            "ro_msg": "E-mail atual"
        }
    },
    "email_saved": {
        "ru": {
            "ro_msg": "Email сохранён"
        },
        "en": {
            "ro_msg": "Email saved"
        },
        "pt-BR": {
            "ro_msg": "E-mail salvo"
        }
    },
    "save_error": {
        "ru": {
            "ro_msg": "Ошибка сохранения"
        },
        "en": {
            "ro_msg": "Save error"
        },
        "pt-BR": {
            "ro_msg": "Erro ao salvar"
        }
    },
    "donate_page_referral": {
        "ru": {
            "ro_msg": "Приводите друзей и получайте бонусы! Если по вашей ссылке "
                      "перейдёт человек, то вы получите дополнительные " + str(
                int(tariff_ref_period / 24)) + " дней и " + str(tariff_ref_notifies) \
                      + " уведомлений к текущему тарифу или, если вы не подписаны, " \
                      + str(int(tariff_ref_no_subscription_period / 24)) + " дня подписки на "
                                                                           "минимальный тариф. Если по вашей ссылке пополнят баланс, то ваш тариф"
                                                                           " будет изменён на максимальный, а его срок увеличится на " + str(
                int(
                    tariff_ref_sub_period / 24)) + " дней."
        },
        "en": {
            "ro_msg": "Bring friends and get bonuses! If a person follows your link"
                      ", you will get additional" + str(
                int(tariff_ref_period / 24)) + " days and " + str(tariff_ref_notifies) \
                      + " notifications to the current tariff or, if you are not subscribed, " \
                      + str(int(tariff_ref_no_subscription_period / 24)) + " days of subscription"
                                                                           " for minimum tariff. If a person refills the balance using your link, then"
                                                                           " your tariff will be changed to the maximum, and its term will increase "
                                                                           "by " + str(
                int(tariff_ref_sub_period / 24)) + " days."
        },
        "pt-BR": {
            "ro_msg": "Traga amigos e ganhe bônus!  Se uma pessoa usar seu link de "
                      "convite, você irá receber adicionar mais" + str(
                int(tariff_ref_period / 24)) + " dias e " + str(tariff_ref_notifies) \
                      + " notificações ao plano atual. Ou, caso não tenha uma assinatura, "
                        "receberá " + str(int(tariff_ref_no_subscription_period / 24)) + " dias de "
                                                                                         "assinatura do plano mínimo. Se uma pessoa fizer uma recarga usando seu "
                                                                                         "link, então você receberá o plano máximo, e seu prazo aumentará "
                                                                                         "em " + str(
                int(tariff_ref_sub_period / 24)) + " dias."
        },
        "he": {
            "ro_msg": "הזמינו חברים וקבלו בונוסים! אם חבר שלך הצטרף ע\"י הקישור שלך"
                      ", תקבל תוספת של" + str(
                int(tariff_ref_period / 24)) + " ימים ו" + str(tariff_ref_notifies) \
                      + " התראות למסלול הנוכחי שלך, או אם אינך מנוי עדיין, תקבל" \
                      + str(int(tariff_ref_no_subscription_period / 24)) + " ימים למנוי"
                                                                           " למסלול המינימלי. אם חבר שלך ממלא את היתרה שלו באמצעות הקישור שלך,"
                                                                           " המסלול שלך ישתנה למסלול המקסימלי, והתקופה שלו תוארך ל"
                      + str(int(tariff_ref_sub_period / 24)) + " ימים."
        },
        "de": {
            "ro_msg": "Werbe Freunde und erhalte Prämien! Folgt jemand Deinem Link"
                      ", erhältst Du " + str(
                int(tariff_ref_period / 24)) + " zusätzliche Tage und " + \
                      str(tariff_ref_notifies) + " zusätzliche Benachrichtigungen in Deiner "
                                                 "aktuellen Preisklasse. Falls Du kein Abonnement besitzt, erhältst Du " + \
                      str(int(tariff_ref_no_subscription_period / 24)) + " Abonnement-Tage"
                                                                         " in der niedrigsten Preisklasse. Wenn jemand über Deinen Link seinen "
                                                                         "Kontostand auflädt, wechselst Du in die höchste Preisklasse und Dein "
                                                                         "Abonnement wird um " + str(
                int(tariff_ref_sub_period / 24)) + " Tage "
                                                   "verlängert."
        }
    },
    "curr_tariff": {
        "ru": {
            "ro_msg": "Текущий тариф"
        },
        "en": {
            "ro_msg": "Current tariff"
        },
        "pt-BR": {
            "ro_msg": "Plano atual"
        },
        "he": {
            "ro_msg": "מסלול נוכחי"
        },
        "de": {
            "ro_msg": "Aktuelle Preisklasse"
        }
    },
    "you_cant_recieve_notifications": {
        "ru": {
            "ro_msg": "С текущими условиями вам не будут приходить уведомления о новых "
                      "выпусках.\nПодробнее: /subscription"
        },
        "en": {
            "ro_msg": "With the current conditions, you will not receive notifications "
                      "about new releases.\nMore details: /subscription"
        },
        "pt-BR": {
            "ro_msg": "Nas condições atuais, você não receberá notificações "
                      "de novos lançamentos.\nMais detalhes em: /subscription"
        },
        "he": {
            "ro_msg": "בתנאים הנוכחיים לא תקבל תהראות על פרקים "
                      "ומהדורות חדשות.\nלפרטים נוספים /subscription"
        },
        "de": {
            "ro_msg": "Unter den aktuellen Bedingungen wirst Du keine "
                      "Benachrichtigungen bei neuen Folgen erhalten.\nWeitere Informationen unter"
                      " /subscription"
        }
    },
    "tariffs": {
        "ru": {
            "ro_msg": emojiCodes.get('clipboard') + " Выбрать тариф"
        },
        "en": {
            "ro_msg": emojiCodes.get('clipboard') + "Choose a tariff"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('clipboard') + "Escolha um plano"
        },
        "he": {
            "ro_msg": emojiCodes.get('clipboard') + "בחר מסלול"
        },
        "de": {
            "ro_msg": emojiCodes.get('clipboard') + "Preisklasse wählen"
        }
    },
    "bot_sub_trfs_page": {
        "ru": {
            "ro_msg": "<b>" + emojiCodes.get('clipboard') + " Тарифы</b>\n\n"
                                                          "Здесь вы можете выбрать подходящий тариф. Внимательно ознакомьтесь"
                                                          " с доступными вариантами, а затем нажмите на кнопку нужного тарифа\n\n"
                                                          "Тариф не активируется, пока вы не пополните ваш счёт."
                                                          "<b>Внимание! Пополнение счёта также считается безвозмездным пожертвованием!</b>"
                                                          "\n\nЕсли вы решите перейти на более дорогой тариф, то сразу же спишется "
                                                          "часть разницы между тарифами за оставшиеся дни\n<b>Но если решите перейти "
                                                          "на более дешёвый, то баланс увеличится на половину стоимости за оставшиеся"
                                                          " дни, кроме текущего!</b>\n\n"
                                                          "Кроме того, если вы не подписаны на тариф, то вы не сможете подписаться"
                                                          " более чем на " + str(
                max_subscriptions_without_tariff) + " подкастов."
        },
        "en": {
            "ro_msg": "<b>" + emojiCodes.get('clipboard') + " Tariffs</b>\n\n"
                                                          "Here you can choose a suitable tariff. Please read carefully"
                                                          " with available options, and then click on the button for the desired "
                                                          "tariff\n\nThe tariff is not activated until you fund your account."
                                                          "<b>Attention! Account funding is also considered a donation!</b>"
                                                          "\n\nIf you decide to switch to a more expensive tariff, then part of the "
                                                          "difference between the tariffs for the remaining days will be debited "
                                                          "immediately\n<b>But if you decide to switch to a cheaper one, the balance "
                                                          "will increase by half the cost for the remaining days, except for the "
                                                          "current one!</b>\n\n"
                                                          "In addition, if you are not subscribed to the tariff, then you will not be"
                                                          " able to subscribe to more than " \
                      + str(max_subscriptions_without_tariff) + " podcasts."
        },
        "pt-BR": {
            "ro_msg": "<b>" + emojiCodes.get('clipboard') + " Planos</b>\n\n"
                                                          "Aqui você pode escolher um plano. Por favor, leia atentamente"
                                                          " as opções disponíveis e, a seguir, clique no botão do plano "
                                                          "escolhido.\n\nO plano somente será ativado quando você realizar uma "
                                                          "recarga na conta. <b>Atenção! Qualquer recarga na conta será considerada uma"
                                                          " doação!</b> \n\nSe você decidir mudar para um plano mais caro, parte do "
                                                          "diferença entre os planos para os dias restantes será debitado "
                                                          "imediatamente.\n<b>Mas, se decidir mudar para um mais barato, o saldo "
                                                          "será aumentado pela metade do valor para os dias restantes, exceto "
                                                          "o dia atual!</b>\n\n"
                                                          "Além disso, se você não estiver inscrito em um plano, você não será"
                                                          " capaz de se inscrever em mais de " \
                      + str(max_subscriptions_without_tariff) + " podcasts."
        },
        "de": {
            "ro_msg": "<b>" + emojiCodes.get('clipboard') + " Preisklassen</b>\n\n"
                                                          "Hier kannst Du eine für Dich passende Preisklasse wählen. Lies Dir "
                                                          "die verfügbaren Optionen aufmerksam durch! Dann drücke auf die gewünschte "
                                                          "Preisklasse!\n\nDein Abonnement wird nicht freigeschaltet, bis Du Deinen "
                                                          "Kontostand auflädst. <b>Beachte: Deinen Kontostand aufzuladen wird auch als "
                                                          "Spende gesehen!</b>"
                                                          "\n\nWenn Du Dich entscheidest, in eine teurere Preisklasse zu wechseln, "
                                                          "wird ein Teil der Preisdifferenz für die verbleibende Laufzeit des "
                                                          "Abonnements sofort abgebucht.\n<b>Wenn Du aber entscheidest in eine "
                                                          "günstigere Preisklasse zu wechseln, wird Dein Kontostand um die Hälfte der"
                                                          " Kosten für die verbleibende Laufzeit erhöht, ausgenommen dem Tag des "
                                                          "Wechsels selbst!</b>\n\n"
                                                          "Wenn Sie den Plan nicht abonniert haben, können Sie nicht mehr als " \
                      + str(max_subscriptions_without_tariff) + " Podcasts abonnieren."
        }
    },
    "tariff_lvl1": {
        "ru": {
            "ro_msg": emojiCodes.get('bronze') + " Бронза"
        },
        "en": {
            "ro_msg": emojiCodes.get('bronze') + " Bronze"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('bronze') + " Bronze"
        },
        "de": {
            "ro_msg": emojiCodes.get('bronze') + " Bronze"
        }
    },
    "tariff_lvl2": {
        "ru": {
            "ro_msg": emojiCodes.get('silver') + " Серебро"
        },
        "en": {
            "ro_msg": emojiCodes.get('silver') + " Silver"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('silver') + " Prata"
        },
        "de": {
            "ro_msg": emojiCodes.get('silver') + " Silber"
        }
    },
    "tariff_lvl3": {
        "ru": {
            "ro_msg": emojiCodes.get('gold') + " Золото"
        },
        "en": {
            "ro_msg": emojiCodes.get('gold') + " Gold"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('gold') + " Ouro"
        },
        "de": {
            "ro_msg": emojiCodes.get('gold') + " Gold"
        }
    },
    "trf_descr_tmplt": {
        "ru": {
            "ro_msg": "Стоимость: %s" + emojiCodes.get('dollar') \
                      + "(долларов) за 30 дней.\nУведомлений (за период, 30 дней): %s\n"
                      # "Поддержка сжатия: (недоступно на данный момент) %s"
                        "Управление каналом: %s"
        },
        "en": {
            "ro_msg": "Cost: %s" + emojiCodes.get('dollar') \
                      + "(dollars) for 30 days.\nNotifications (for a period of 30 days): %s\n"
                      # "Compression support: (not available at the moment) %s"
                        "Channel management: %s"
        },
        "pt-BR": {
            "ro_msg": "Cost: %s" + emojiCodes.get('dollar') \
                      + "(dólares) por 30 dias.\nNotificações (por um período de 30 dias): %s\n"
                      # "Suporte a compressão: (não disponível no momento) %s"
                        "Channel management: %s"
        },
        "de": {
            "ro_msg": "Kosten: %s" + emojiCodes.get('dollar') \
                      + "(in Dollar) für 30 Tage.\nBenachrichtigungen (über eine Laufzeit von 30"
                        " Tagen): %s\n"
                      # "Compression support: (not available at the moment) %s"
                        "Kanalverwaltung: %s"
        }
    },
    "days_left": {
        "ru": {
            "ro_msg": "Осталось дней: %s"
        },
        "en": {
            "ro_msg": "Days left: %s"
        },
        "pt-BR": {
            "ro_msg": "Dias restantes: %s"
        },
        "de": {
            "ro_msg": "Verbleibende Tage: %s"
        }
    },
    "notify_left": {
        "ru": {
            "ro_msg": "Осталось уведомлений: %s"
        },
        "en": {
            "ro_msg": "Notifications left: %s"
        },
        "pt-BR": {
            "ro_msg": "Notificações restantes: %s"
        },
        "de": {
            "ro_msg": "Verbleibende Benachrichtigungen: %s"
        }
    },
    "curr_balance": {
        "ru": {
            "ro_msg": "Текущий баланс: %s" + emojiCodes.get('dollar')
        },
        "en": {
            "ro_msg": "Current balance: %s" + emojiCodes.get('dollar')
        },
        "pt-BR": {
            "ro_msg": "Saldo atual: %s" + emojiCodes.get('dollar')
        },
        "de": {
            "ro_msg": "Kontostand: %s" + emojiCodes.get('dollar')
        }
    },
    "not_enough_for_renewal": {
        "ru": {
            "ro_msg": "(не хватает для продления: %s" + emojiCodes.get('dollar') + ")"
        },
        "en": {
            "ro_msg": "(not enough for renewal: %s" + emojiCodes.get('dollar') + ")"
        },
        "pt-BR": {
            "ro_msg": "(insuficiente para renovação: %s" + emojiCodes.get('dollar') \
                      + ")"
        },
        "de": {
            "ro_msg": "(nicht genug für eine Erneuerung: %s" + \
                      emojiCodes.get('dollar') + ")"
        }
    },
    "payViaRobokassa": {
        "ru": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Пополнить с помощью Robokassa"
        },
        "en": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Top up balance via Robokassa"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Recarregar saldo do Robokassa"
        },
        "de": {
            "ro_msg": emojiCodes.get('moneyWithWings') + " Konto aufladen per Robokassa"
        }
    },
    "bot_sub_pmnt_page": {
        "ru": {
            "ro_msg": "<b>" + emojiCodes.get('moneyWithWings') + " Пополнение</b>\n\n"
                                                               "Здесь вы можете пополнить баланс. Для получения ссылки можно нажать"
                                                               " на кнопку или <b>ввести сумму вручную</b>.\n\n"
                                                               "<b>Внимание! Пополнение счёта также считается безвозмездным пожертвованием!</b>"
                                                               " Доллары в системе — это выдающиеся за пожертвования виртуальные очки, "
                                                               "курс которых равен доллару США (USD), "
                                                               "при этом они принадлежат владельцу бота. "
                                                               "Администрация и владелец бота не несут ответственность за пожертвованные "
                                                               "деньги, баланс в системе и виртуальные очки. Выбранный пользователем тариф"
                                                               " может быть отменён, а баланс аннулирован в любое время без объяснения "
                                                               "причин.\nВ то же время администрация будет идти на контакт и разрешать "
                                                               "споры по возможности и в зависимости от ситуации."
        },
        "en": {
            "ro_msg": "<b>" + emojiCodes.get('moneyWithWings') + " Deposit</b>\n\n"
                                                               "Here you can top up your balance. For a link you can click"
                                                               " on the button or <b>enter the amount manually</b>.\n\n"
                                                               "<b>Attention! Account funding is also considered a donation!</b>"
                                                               " Dollars in the system are virtual points awarded for donations, "
                                                               "the exchange rate of which is equal to the US dollar, "
                                                               "and they are owned by the bot owner."
                                                               "The administration and the owner of the bot are not responsible for "
                                                               "donated money, balance in the system and virtual points. The tariff chosen"
                                                               " by the user can be canceled and the balance canceled at any time without "
                                                               "giving any reason.\nAt the same time, the administration will contact and "
                                                               "resolve disputes whenever possible and depending on the situation."
        },
        "pt-BR": {
            "ro_msg": "<b>" + emojiCodes.get('moneyWithWings') + " Recarga</b>\n\n"
                                                               "Aqui pode completar o seu saldo. Para um link pode clicar"
                                                               " no botão ou <b>enter o montante manualmente</b>.\n\n"
                                                               "<b>Atenção! O crédito de conta é também considerado uma doação!</b>"
                                                               " Os dólares no sistema são pontos virtuais atribuídos por doações, "
                                                               "cuja taxa de câmbio é igual ao dólar, "
                                                               "e são propriedade do proprietário do bot."
                                                               "A administração e o proprietário do bot não são responsáveis por "
                                                               "dinheiro doado, equilíbrio no sistema e pontos virtuais. O plano escolhido"
                                                               " pelo usuário pode ser cancelado e o saldo cancelado a qualquer momento "
                                                               "sem qualquer razão.\nDe qualquer forma, a administração entrará em contato"
                                                               " e resolverá disputas sempre que possível e dependendo da situação."
        },
        "de": {
            "ro_msg": "<b>" + emojiCodes.get('moneyWithWings') + " Einzahlung</b>\n\n"
                                                               "Hier kannst Du Dein Konto aufladen. Durch Drücken auf den Knopf "
                                                               "oder <b>manuelle Eingabe eines Betrags</b> erhälst Du einen Link.\n\n"
                                                               "<b>Beachte: Deinen Kontostand aufzuladen wird auch als Spende betrachtet.</b>"
                                                               " Dollar im System sind virtuelle Punkte, die für Spenden vergeben werden, "
                                                               "deren Wechselkurs dem US-Dollar entspricht, und sie gehören dem "
                                                               "Bot-Besitzer."
                                                               "Weder die Betreiber noch der Besitzer des Bots sind verantwortlich für "
                                                               "gespendetes Geld, Kontostände im System, und virtuelle Token. Die "
                                                               "vom Nutzer gewählte Preisklasse und dessen Kontostand können jederzeit und"
                                                               " ohne Angabe von Gründen storniert werden.\nNichtsdestotrotz werden die"
                                                               " Betreiber wann immer möglich und situationsabhängig den Kontakt suchen, "
                                                               "um Streitigkeiten aufzuklären."
        }
    },
    "money_came": {
        "ru": {
            "ro_msg": "Ваш платёж зачислен!"
        },
        "en": {
            "ro_msg": "Your payment has been credited!"
        },
        "pt-BR": {
            "ro_msg": "Seu pagamento foi creditado!"
        },
        "de": {
            "ro_msg": "Deine Zahlung wurde gutgeschrieben!"
        }
    },
    "subscribe_now": {
        "ru": {
            "ro_msg": "Перейдите на страницу тарифов и выберите желаемый."
        },
        "en": {
            "ro_msg": "Go to the tariffs page and select the one you want."
        },
        "pt-BR": {
            "ro_msg": "Vá para a página de planos e selecione o que deseja."
        },
        "de": {
            "ro_msg": "Gehe zur Preisklassen-Übersicht und wähle aus, welche Du "
                      "möchtest."
        }
    },
    "enough_to_prolongation": {
        "ru": {
            "ro_msg": "У вас достаточно средств для продления."
        },
        "en": {
            "ro_msg": "You have sufficient funds to renew."
        },
        "pt-BR": {
            "ro_msg": "Você tem fundos suficientes para renovar."
        },
        "de": {
            "ro_msg": "Du hast ausreichende Mittel zur Erneuerung."
        }
    },
    "not_enough_to_prolongation": {
        "ru": {
            "ro_msg": "У вас недостаточно средств для продления."
        },
        "en": {
            "ro_msg": "You do not have enough funds to renew."
        },
        "pt-BR": {
            "ro_msg": "Você não tem fundos suficientes para renovar."
        },
        "de": {
            "ro_msg": "Du hast unzureichende Mittel um Dein Abonnement zu erneuern."
        }
    },
    "tariff_prolonged": {
        "ru": {
            "ro_msg": "Текущий тариф продлён."
        },
        "en": {
            "ro_msg": "The current tariff has been extended."
        },
        "pt-BR": {
            "ro_msg": "O plano atual foi estendido."
        },
        "de": {
            "ro_msg": "Das aktuelle Preisklassen-Abonnement wurde verlängert."
        }
    },
    "tariff_prolonged_by_daemon": {
        "ru": {
            "ro_msg": "Ваш тариф продлён! Текущие условия:"
        },
        "en": {
            "ro_msg": "Your tariff has been extended! Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Seu plano foi prorrogado!  Condições atuais:"
        },
        "de": {
            "ro_msg": "Dein Abonnement wurde verlängert! Aktuelle Konditionen:"
        }
    },
    "tariff_cannot_be_prolonged_by_daemon": {
        "ru": {
            "ro_msg": "Срок действия тарифа вышел, пополните баланс.\n"
                      "Текущие условия:"
        },
        "en": {
            "ro_msg": "The tariff has expired, top up the balance.\n"
                      "Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "O plano expirou, complete o saldo.\n"
                      "Condições atuais:"
        },
        "de": {
            "ro_msg": "Die Preisklasse ist ausgelaufen. Lade Dein Konto auf!\n"
                      "Aktuelle Konditionen:"
        }
    },
    "your_tariff_description": {
        "ru": {
            "ro_msg": "Описание вашего тарифа",
        },
        "en": {
            "ro_msg": "Description of your tariff"
        },
        "pt-BR": {
            "ro_msg": "Descrição do seu tarifário"
        },
        "de": {
            "ro_msg": "Beschreibung Ihres Tarifs"
        }
    },
    "notificationsEnded": {
        "ru": {
            "ro_msg": "Достигнут лимит уведомлений в этом сроке действия.\n"
                      "Дождитесь нового срока или перейдите на тариф с большим лимитом."
        },
        "en": {
            "ro_msg": "The notification limit has been reached within this expiration "
                      "date.\nWait for a new deadline or switch to a tariff with a higher limit."
        },
        "pt-BR": {
            "ro_msg": "O limite de notificações foi atingido dentro deste período "
                      "de assinatura.\nEspere por um novo período ou mude para um plano com um "
                      "limite maior."
        },
        "de": {
            "ro_msg": "Die maximale Anzahl an Benachrichtigungen für die aktuelle "
                      "Abrechnungsperiode wurde erreicht.\nWarte auf die nächste Periode oder "
                      "wechsle in eine höhere Preisklasse mit mehr Benachrichtigungen."
        }
    },
    "award_without_s_new_user": {
        "ru": {
            "ro_msg": "По вашей ссылке зарегистрировался новый пользователь, вы были "
                      "подписаны на тариф! Текущие условия:"
        },
        "en": {
            "ro_msg": "A new user has registered on your link, you were "
                      "subscribed to the tariff! Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Um novo usuário se cadastrou no seu link, você ganhou "
                      "uma incrição! Condições atuais:"
        },
        "de": {
            "ro_msg": "Ein neuer Nutzer hat sich mit Deinem Link registriert! "
                      "Du hast ein Abonnement erhalten! Aktuelle Konditionen:"
        }
    },
    "award_with_s_new_user": {
        "ru": {
            "ro_msg": "По вашей ссылке зарегистрировался новый пользователь, ваш тариф "
                      "улучшен!"
        },
        "en": {
            "ro_msg": "A new user has registered using your link, your tariff improved!"
        },
        "pt-BR": {
            "ro_msg": "Um novo usuário se cadastrou através do seu link, seu plano "
                      "sofreu um upgrade!"
        },
        "de": {
            "ro_msg": "Ein neuer Nutzer hat sich mit Deinem Link registriert! Deine "
                      "Preisklasse hat sich verbessert!"
        }
    },
    "award_without_s_subscribed": {
        "ru": {
            "ro_msg": "Приглашённый пользователь впервые пополнил баланс, вы были "
                      "подписаны на тариф! Текущие условия:"
        },
        "en": {
            "ro_msg": "The invited user has replenished the balance for the first time,"
                      " you were subscribed to the tariff! Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Um usuário que você convidou fez uma recarga pela primeira vez,"
                      " você ganhou um plano!  Condições atuais:"
        },
        "de": {
            "ro_msg": "Ein eingeladener Nutzer hat erstmals seinen Kontostand "
                      "aufgeladen! Du hast ein Abonnement erhalten! Aktuelle Konditionen:"
        }
    },
    "award_with_s_subscribed": {
        "ru": {
            "ro_msg": "Приглашённый пользователь впервые пополнил баланс, тариф "
                      "улучшен! Текущие условия:"
        },
        "en": {
            "ro_msg": "The invited user has replenished the balance for the first time,"
                      " your tariff improved! Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Um usuário que você convidou fez uma recarga pela primeira vez,"
                      " seu plano sofreu um upgrade! Condições atuais:"
        },
        "de": {
            "ro_msg": "Ein eingeladener Nutzer hat erstmals seinen Kontostand "
                      "aufgeladen! Deine Preisklasse hat sich verbessert! Aktuelle Konditionen:"
        }
    },
    "award_welcome": {
        "ru": {
            "ro_msg": "Добро пожаловать! В качестве приветственного бонуса попробуйте "
                      "лучший тариф! Текущие условия:"
        },
        "en": {
            "ro_msg": "Welcome! Try the best tariff as a welcome bonus! "
                      "Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Bem-vindo! Experimente o melhor plano como um bônus de "
                      "boas-vindas! Condições atuais:"
        }
    },
    "secret_award_welcome": {
        "ru": {
            "ro_msg": "Добро пожаловать! Вы вернулись к началу! В качестве "
                      "награды попробуйте лучший тариф! Текущие условия:"
        },
        "en": {
            "ro_msg": "Welcome! You are back to the beginning! Try the best tariff as "
                      "a reward! Current conditions:"
        },
        "pt-BR": {
            "ro_msg": "Bem-vindo! Você está de volta ao começo! Experimente o melhor "
                      "plano como uma recompensa! Condições atuais:"
        }
    },
    "donation": {
        "ru": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "Пожертвование"
        },
        "en": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "Donate"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "Doar"
        },
        "es": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "Donar"
        },
        "de": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "Spenden"
        },
        "he": {
            "ro_msg": emojiCodes.get('dollarBag') + " " + "תרומה"
        }
    },
    "donateMessage": {
        "ru": {
            "ro_msg": "Вы можете помочь боту с развитием!\n"
                      # "Отправьте сумму боту или пожертвуйте на"
                      "Пожертвуйте на"
                      " <a href='%s'>Patreon.com</a>" % donate_link
                      + "\n\nЭто также даст вам дополнительные возможности, "
                        "подробнее: /subscription"
        },
        "en": {
            "ro_msg": "You can support this bot with a donation!\n\n"
                      "Donate on <a href='%s'>Patreon.com</a>" % donate_link
                      # "Donate on <a href='%s'>Patreon.com</a>" % donate_link + \
                      # "\n\nOr send a message with the amount in rubles. "
                      # "You can see the exchange rate to the US dollar under this link:"
                      # " https://investing.com/currencies/usd-rub"
                      + "\n\nIt will also give you additional options, learn more: /subscription"
        },
        "pt-BR": {
            "ro_msg": "Você pode ajudar o bot com uma doação!\n\n"
                      "Faça uma doação em <a href='%s'>Patreon.com</a>" % donate_link
                      # "Faça uma doação em <a href='%s'>Patreon.com</a>" % donate_link + \
                      # "\n\nOu por favor, envie o valor em rublos. Você pode descobrir a taxa de "
                      # "câmbio neste link:"
                      # " https://br.investing.com/currencies/brl-rub"
                      + "\n\nEle também fornecerá opções adicionais, saiba mais: /subscription"
        },
        "es": {
            "ro_msg": "¡Puedes ayudar al bot con una donación!\n\n"
                      "Donar en <a href='%s'>Patreon.com</a>" % donate_link
                      # "Donar en <a href='%s'>Patreon.com</a>" % donate_link + \
                      # "\n\nO Por favor envíe la"
                      # " cantidad en rublos. Puede encontrar el tipo de cambio del dólar"
                      # " estadounidense en este enlace:"
                      # " https: //investing.com/currencies/usd-rub"
                      + "\n\nTambién te brindará opciones adicionales, obtén más "
                        "información: /subscription"
        },
        "de": {
            "ro_msg": "Du kannst den Bot mit einer Spende unterstützen!\n\n"
                      "Spenden Sie für <a href='%s'>Patreon.com</a>" % donate_link
                      # "Spenden Sie für <a href='%s'>Patreon.com</a>" % donate_link + \
                      # "\n\nAlternativ bitte sende den Betrag in Rubbeln als Nachricht. "
                      # "Den aktuellen Wechselkurs für Euro findest Du hier:"
                      # " https://www.investing.com/currencies/eur-rub"
                      + "\n\nEs gibt Ihnen auch zusätzliche Optionen, erfahren Sie "
                        "mehr: /subscription"
        },
        "he": {
            "ro_msg": "אתה יכול לעזור לרובוט הזה ולתרום!\n\n"
                      "לתרום הלאה "
                      "<a href='%s'>Patreon.com</a>" % donate_link
                      # "לתרום הלאה [Patreon.com](%s)" % donate_link + \
                      # "\n\nאו אנא שלחו את הסכום ברובלים. אתה יכול לגלות את שער החליפין לדולר"
                      # " בקישור הזה: https://investing.com/currencies/usd-rub"
                      + "\n\nזה גם ייתן לך אפשרויות נוספות, למידע נוסף: /subscription"
        }
    },
    "patreonShort": {
        "en": {
            "ro_msg": "<a gref='%s'>%s</a>" % (donate_link, donate_link)
        }
    },
    "openThePodcast": {
        "ru": {
            "ro_msg": "Открыть подкаст"
        },
        "en": {
            "ro_msg": "Open the podcast"
        },
        "pt-BR": {
            "ro_msg": "Abrir o podcast"
        }
    },
    "downloadEpisode": {
        "ru": {
            "ro_msg": "Скачать выпуск"
        },
        "en": {
            "ro_msg": "Download the episode"
        }
    },
    "linkInTheBotByPodcastId": {
        "ru": {
            "ro_msg": "[Открыть подкаст](t.me/{botName}?start={mode}_{id})"
        },
        "en": {
            "ro_msg": "[Open the podcast](t.me/{botName}?start={mode}_{id})"
        },
        "pt-BR": {
            "ro_msg": "[Abrir o podcast](t.me/{botName}?start={mode}_{id})"
        }
    },
    "linkInTheBotByPodcastId_HTML": {
        "ru": {
            "ro_msg":
                "<a href=\"t.me/{botName}?start={mode}_{id}\">Открыть подкаст</a>"
        },
        "en": {
            "ro_msg":
                "<a href=\"t.me/{botName}?start={mode}_{id}\">Open the podcast</a>"
        },
        "pt-BR": {
            "ro_msg":
                "<a href=\"t.me/{botName}?start={mode}_{id}\">Abrir o podcast</a>"
        }
    },
    'in_the_bot': {
        "ru": {
            "ro_msg":
                "в @{botName}"
        },
        "en": {
            "ro_msg":
                "with @{botName}"
        },
        "pt-BR": {
            "ro_msg":
                "com @{botName}"
        }
    },
    "cover_image": {
        "ru": {
            "ro_msg": "Обложка"
        },
        "en": {
            "ro_msg": "Cover"
        },
    },
    "notANumber": {
        "ru": {
            "ro_msg": "Пожалуйста, введите сумму."
        },
        "en": {
            "ro_msg": "Please enter the amount in rubles."
                      " You can see the exchange rate to the US dollar under this link:"
                      " https://investing.com/currencies/usd-rub."
        },
        "pt-BR": {
            "ro_msg": "Por favor, insira a quantidade em rublos."
                      " Você pode descobrir a taxa de câmbio para o dólar americano neste link:"
                      " https://br.investing.com/currencies/brl-rub."
        },
        "es": {
            "ro_msg": "Por favor, entre la cantidad en rublos."
                      " Puede encontrar la tasa de cambio a dólar americano en este link:"
                      " https://investing.com/currencies/usd-rub."
        },
        "de": {
            "ro_msg": "Bitte gib den Betrag in Rubeln an."
                      " Den aktuellen Wechselkurs für Euro"
                      " findest Du hier: https://www.investing.com/currencies/eur-rub."
        },
        "he": {
            "ro_msg": "אנא הכנס את הסכום בדולרים."
                      " אתה יכול למצוא את שער החליפין לדולר ב:"
                      " https://investing.com/currencies/usd-rub."
        }
    },
    "paymentLinkMessage": {
        "ru": {
            "ro_msg": "Перейдите по ссылке ниже и следуйте инструкциям\n\n"
        },
        "en": {
            "ro_msg": "Follow the link below and follow the instructions\n\n"
        },
        "pt-BR": {
            "ro_msg": "Siga o link abaixo e siga as instruções\n\n"
        },
        "es": {
            "ro_msg": "Siga el link debajo y luego siga las instrucciones\n\n"
        },
        "de": {
            "ro_msg": "Klicke auf den folgenden Link und folge den"
                      " Anweisungen auf der Webseite.\n\n"
        },
        "he": {
            "ro_msg": "עקוב אחר הקישור למטה ופעל על פי ההוראות\n\n"
        }
    },
    "notificationsFCDisabled": {
        "ru": {
            "ro_msg": "Не удалось получить rss ленту, "
                      "поэтому уведомления для подкаста были отключены.\n"
                      "Попробуйте открыть подкаст позже и включить уведомления заново."
        },
        "en": {
            "ro_msg": "Failed to get rss feed, "
                      "so podcast notifications were disabled.\n"
                      "Try opening the podcast later and re-enable notifications."
        },
        "pt-BR": {
            "ro_msg": "Falha ao obter feed RSS, "
                      "portanto, as notificações de podcast foram desativadas.\n"
                      "Tente abrir o podcast mais tarde e reative as notificações."
        },
        "es": {
            "ro_msg": "No se pudo obtener el feed rss, "
                      "por lo que las notificaciones de podcast se deshabilitaron.\n"
                      "Intente abrir el podcast más tarde y"
                      "vuelva a habilitar las notificaciones."
        },
        "de": {
            "ro_msg": "Der RSS-Feed konnte nicht geladen werden, "
                      "deshalb wurden Benachrichtigungen deaktiviert.\n"
                      "Versuche den Podcast später zu öffnen und die Benachrichtigungen"
                      " wieder zu aktivieren."
        },
        "he": {
            "ro_msg": "נכשלה קבלת עדכון RSS, "
                      "לכן התרעות הפודקאסט הושבתו.\n"
                      "נסה לפתוח מאוחר יותר את הפדקאסט והפעל מחדש התראות."
        }
    },
    "genresMessage": {
        "ru": {
            "ro_msg": "%s\nВыберите жанр"
        },
        "en": {
            "ro_msg": "%s\nChoose genre"
        },
        "pt-BR": {
            "ro_msg": "%s\nEscolha o gênero"
        }
    },
    "topMessage": {
        "ru": {
            "ro_msg": emojiCodes.get('crown') + "\nТоп жанра"
        },
        "en": {
            "ro_msg": emojiCodes.get('crown') + "\nТоп жанра"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('crown') + "\nTop gêneros"
        }
    },

    "connectTgChannelMessage": {
        "ru": {
            "ro_msg": emojiCodes.get('electricPlug') + "<b>Подключённые каналы</b>\n\n"
                                                       "Вы можете добавить канал Telegram, выбрать подкасты, а бот будет "
                                                       "автоматически присылать в него новые выпуски!\n\n"
                                                       "Позвольте боту вести канал о подкастах вместо вас!"
        },
        "en": {
            "ro_msg": emojiCodes.get('electricPlug') + "<b>Connected channels</b>\n\n"
                                                       "You can add a Telegram channel, select podcasts, and the bot will "
                                                       "automatically send new episodes to it!\n\n"
                                                       "Let the bot manage the podcast channel for you!"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('electricPlug') + "<b>Canais conectados</b>\n\n"
                                                       "Você pode adicionar um canal do Telegram, depois selecionar podcasts, e o "
                                                       "bot irá enviar automaticamente novos episódios para ele!\n\n"
                                                       "Deixe o bot gerenciar o canal de podcast para você!"
        }
    },
    "cantConnectTgChannelMessage": {
        "ru": {
            "ro_msg": "<b>Чтобы добавить канал, ваш тариф должен быть уровня %s.</b>\n"
                      "Ваш текущий тариф: %s.\n\nПодробнее: /subscription"
        },
        "en": {
            "ro_msg": "<b>To add a channel, your tariff must be level %s.</b>\n"
                      "Your current tariff: %s.\n\nMore info: /subscription"
        },
        "pt-BR": {
            "ro_msg": "<b>Para adicionar um canal, seu plano deve ser nível %s.</b>\n"
                      "Seu plano atual: %s.\n\nMais informações em /subscription"
        }
    },
    "myTgChannels": {
        "ru": {
            "ro_msg": "Мои каналы"
        },
        "en": {
            "ro_msg": "My channels"
        },
        "pt-BR": {
            "ro_msg": "Meus canais"
        }
    },
    "addTgChannel": {
        "ru": {
            "ro_msg": "Добавить канал"
        },
        "en": {
            "ro_msg": "Add channel"
        },
        "pt-BR": {
            "ro_msg": "Adicionar canal"
        }
    },
    "addTgChannelInput": {
        "ru": {
            "ro_msg": "Сделайте бота администратором вашего канала. "
                      "Затем введите id канала, оно начинается с минуса, или перешлите "
                      "боту любое сообщение канала"
        },
        "en": {
            "ro_msg": "Make this bot the administrator of your channel. "
                      "Then enter the channel id, it starts with a minus, or send "
                      "the bot any channel message"
        },
        "pt-BR": {
            "ro_msg": "Torne este bot o administrador do seu canal. "
                      "Em seguida, insira o id do canal, ele começa com um símbolo de menos '-', "
                      "ou encaminhe qualquer mensagem do canal para este bot"
        }
    },
    "tgChannelNotFoundEnsureBotAdmin": {
        "ru": {
            "ro_msg": "Канал не найден. "
                      "Убедитесь, что вы добавили бота в качестве администратора"
        },
        "en": {
            "ro_msg": "Channel not found. "
                      "Make sure you have added the bot as an administrator"
        },
        "pt-BR": {
            "ro_msg": "Canal não encontrardo. "
                      "Certifique-se de ter adicionado o bot como administrador"
        }
    },
    "tgChannelNotFoundEnsureBotAdminWithName": {
        "ru": {
            "ro_msg": "Канал <b>%s</b> не найден. "
                      "Убедитесь, что вы добавили бота в качестве администратора.\n\n"
                      "Подробнее: /my_tg_channels"
        },
        "en": {
            "ro_msg": "Channel <b>%s</b> not found. "
                      "Make sure you have added the bot as an administrator.\n\n"
                      "More info: /my_tg_channels"
        },
        "pt-BR": {
            "ro_msg": "Canal <b>%s</b> não encontrado. "
                      "Certifique-se de ter adicionado o bot como administrador.\n\n"
                      "Mais informações em: /my_tg_channels"
        }
    },
    "tgChannelAlreadyAdded": {
        "ru": {
            "ro_msg": "Канал уже добавлен"
        },
        "en": {
            "ro_msg": "The channel already added"
        },
        "pt-BR": {
            "ro_msg": "Este canal já foi adicionado"
        }
    },
    'maxTgChannelsForNow': {
        'ru': {
            'ro_msg': "Вы достигли максимального количества управляемых каналов"
        },
        'en': {
            'ro_msg': "You've reached the maximum number of channels"
        }
    },
    "tgChannelAdded": {
        "ru": {
            "ro_msg": "Канал успешно добавлен!"
        },
        "en": {
            "ro_msg": "The channel has been successfully added"
        },
        "pt-BR": {
            "ro_msg": "O canal foi adicionado com sucesso"
        }
    },
    "yourTgChannelList": {
        "ru": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "Список каналов, которые вы добавили"
        },
        "en": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "List of channels you have added"
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "Lista de canais que você adicionou"
        }
    },
    'yourTgChannelsEmpty': {
        'ru': {
            'ro_msg': "У вас нет добавленных каналов"
        },
        'en': {
            'ro_msg': "You have no channels yet"
        }
    },
    "yourTgChannel": {
        "ru": {
            "ro_msg": "Управление добавленным каналом"
        },
        "en": {
            "ro_msg": "Manage the added channel"
        },
        "pt-BR": {
            "ro_msg": "Gerenciar o canal adicionado"
        }
    },
    "tgChannelStatus": {
        "ru": {
            "ro_msg": "Состояние"
        },
        "en": {
            "ro_msg": "Status"
        },
        "pt-BR": {
            "ro_msg": "Status"
        }
    },
    "tgChannelSubs": {
        "ru": {
            "ro_msg": "Подкасты"
        },
        "en": {
            "ro_msg": "Podcasts"
        },
        "pt-BR": {
            "ro_msg": "Podcasts"
        }
    },
    "tgChannelDelete": {
        "ru": {
            "ro_msg": "Удалить канал"
        },
        "en": {
            "ro_msg": "Delete channel"
        },
        "pt-BR": {
            "ro_msg": "Apagar canal"
        }
    },
    "tapAgainToDeleteTgChannel": {
        "ru": {
            "ro_msg": "Нажмите ещё раз, чтобы подтвердить удаление"
        },
        "en": {
            "ro_msg": "Press again to confirm deletion"
        },
        "pt-BR": {
            "ro_msg": "Pressione novamente para confirmar a exclusão"
        }
    },
    "yourTgChannelSubList": {
        "ru": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "Нажмите на подкаст, чтобы бот начал отслеживать его новые "
                                                       "выпуски и присылать в канал. Нажмите ещё раз, чтобы отменить.\n"
                                                       "Внимание, если вы отпишитесь от подкаста, открыв его, например, "
                                                       "через команду /subscriptions, то его связь с Telegram "
                                                       "каналом также исчезнет."
        },
        "en": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "Click on the podcast to have the bot start tracking its new "
                                                       "releases and send them to the channel. Tap again to cancel."
                                                       "Note that if you unsubscribe from a podcast by opening it, for "
                                                       "example via the command /subscriptions, its connection to the Telegram "
                                                       "channel will also disappear."
        },
        "pt-BR": {
            "ro_msg": emojiCodes.get('electricPlug') + "\n"
                                                       "Clique no podcast para que o bot comece a rastrear seus novos "
                                                       "lançamentos e enviá-los para o canal. Toque novamente para cancelar."
                                                       "Saiba quem se você cancelar a assinatura de um podcast abrindo-o, por"
                                                       "exemplo, através do comando /subscriptions, a conexão dele com o "
                                                       "canal do Telegram também desaparecerá."
        }
    },

    "maintenance": {
        "ru": {
            "ro_msg": "Бот на обслуживании! Попробуйте позже."
        },
        "en": {
            "ro_msg": "The bot is undergoing maintenance! Please, wait for a while."
        },
        "pt-BR": {
            "ro_msg": "O bot está em manutenção! Aguarde um pouco."
        },
        "de": {
            "ro_msg": "Der Bot ist aufgrund von Wartungsarbeiten nicht erreichbar!"
                      " Bitte warte eine Weile."
        },
        "he": {
            "ro_msg": "הבוט בתחזוקה! אנא המתן."
        }
    },
}

routed_messages = {
    'errors': {
        'unknown': {
            'ru': "Возникла неизвестная ошибка, свяжитесь с администратором",
            'en': "An unknown error occurred, contact with administrator"
        },
    },

    'search': {
        'empty': {
            'ru': "Список пуст, попробуйте сузить поиск",
            'en': "No results, try to narrow your search"
        }
    },

    'subs': {
        'errors': {
            'paging': {
                'empty': {
                    'en': "You don't have any subscriptions, add the first one using the menu item 'Add chat'",
                    'ru': "У вас нет подписок, добавьте первую с помощью пункта меню 'Добавить группу'"
                },
                'empty_when_search': {
                    'en': "Subscriptions not found, narrow your search",
                    'ru': "Подписок не найдено, сузьте поиск"
                }
            }
        },
    },

    'buttons': {
        'back': {
            'en': "Back",
            'ru': "Назад"
        },
        'cancel': {
            'en': "Cancel",
            'ru': "Отмена"
        },
    },

    "genres": {
        "alternative health": {
            "ru": "Альтернативное здоровье",
            "en": "Alternative health"
        },
        "arts": {
            "ru": "Искусства",
            "en": "Arts",
            "pt-BR": "Artes"
        },
        "astronomy": {
            "ru": "Астрономия",
            "en": "astronomy"
        },
        "books": {
            "ru": "Книги",
            "en": "Books"
        },
        "business": {
            "ru": "Бизнес",
            "en": "Business",
            "pt-BR": "Negócios"
        },
        "careers": {
            "ru": "Карьера",
            "en": "Careers"
        },
        "comedy": {
            "ru": "Комедия",
            "en": "Comedy",
            "pt-BR": "Humor"
        },
        "comedy fiction": {
            "ru": "Комедийная фантастика",
            "en": "Comedy fiction"
        },
        "comedy interviews": {
            "ru": "Комедийные интервью",
            "en": "Comedy interviews"
        },
        "christianity": {
            "ru": "Христианство",
            "en": "Christianity"
        },
        "daily news": {
            "ru": "Ежедневные новости",
            "en": "Daily news"
        },
        "design": {
            "ru": "Дизайн",
            "en": "Design"
        },
        "documentary": {
            "ru": "Документальные",
            "en": "Documentary"
        },
        "drama": {
            "ru": "Драма",
            "en": "drama"
        },
        "earth sciences": {
            "ru": "Науки о Земле",
            "en": "Earth sciences"
        },
        "education": {
            "ru": "Образование",
            "en": "Education",
            "pt-BR": "Educação"
        },
        "entertainment news": {
            "ru": "Развлекательные новости",
            "en": "Entertainment news"
        },
        "entrepreneurship": {
            "ru": "Предпринимательство",
            "en": "Entrepreneurship"
        },
        "fashion & beauty": {
            "ru": "Мода и красота",
            "en": "Fashion & beauty"
        },
        "fiction": {
            "ru": "Художественная литература",
            "en": "fiction"
        },
        "film reviews": {
            "ru": "Обзоры фильмов",
            "en": "Film reviews"
        },
        "fitness": {
            "ru": "Фитнес",
            "en": "Fitness"
        },
        "football": {
            "ru": "Футбол",
            "en": "Football"
        },
        "government": {
            "ru": "Правительство",
            "en": "Government"
        },
        "health & fitness": {
            "ru": "Здоровье и фитнес",
            "en": "Health & fitness",
            "pt-BR": "Saúde e bem-estar"
        },
        "history": {
            "ru": "История",
            "en": "History"
        },
        "hobbies": {
            "ru": "Хобби",
            "en": "hobbies"
        },
        "how to": {
            "ru": "Как делать",
            "en": "How to"
        },
        "improv": {
            "ru": "Импровизация",
            "en": "Improv"
        },
        "investing": {
            "ru": "Инвестиции",
            "en": "Investing",
            "pt-BR": "Investimento e economia"
        },
        "islam": {
            "ru": "Ислам",
            "en": "Islam"
        },
        "judaism": {
            "ru": "Иудаизм",
            "en": "Judaism"
        },
        "language learning": {
            "ru": "Изучение языков",
            "en": "Language learning",
            "pt-BR": "Idiomas"
        },
        "leisure": {
            "ru": "Досуг",
            "en": "Leisure",
            "pt-BR": "Lazer"
        },
        "life sciences": {
            "ru": "Естественные науки",
            "en": "Life sciences",
            "pt-BR": "Ciências Humanas"
        },
        "marketing": {
            "ru": "Маркетинг",
            "en": "Marketing"
        },
        "mental health": {
            "en": "Mental health",
            "ru": "Душевное здоровье",
            "pt-BR": "Saúde Mental"
        },
        "music": {
            "ru": "Музыка",
            "en": "Music"
        },
        "music interviews": {
            "ru": "Музыкальные интервью",
            "en": "Music interviews"
        },
        "natural sciences": {
            "ru": "Eстественные науки",
            "en": "Natural sciences",
            "pt-BR": "Ciências Naturais"
        },
        "news": {
            "ru": "Новости",
            "en": "News",
            "pt-BR": "Notícias"
        },
        "news commentary": {
            "ru": "Новостные комментарии",
            "en": "News commentary"
        },
        "medicine": {
            "ru": "Медицина",
            "en": "Medicine",
            "pt-BR": "Medicina"
        },
        "performing arts": {
            "ru": "Исполнительское искусство",
            "en": "Performing arts"
        },
        "personal journals": {
            "ru": "Личные дневники",
            "en": "Personal journals"
        },
        "philosophy": {
            "ru": "Философия",
            "en": "philosophy"
        },
        "places & travel": {
            "ru": "Места и путешествия",
            "en": "Places & travel"
        },
        "politics": {
            "ru": "Политика",
            "en": "Politics",
            "pt-BR": "Política"
        },
        "religion & spirituality": {
            "ru": "Религия и духовность",
            "en": "Religion & spirituality",
            "pt-BR": "Religião e espiritualidade"
        },
        "running": {
            "ru": "Бег",
            "en": "Running",
            "pt-BR": "Corrida"
        },
        "science": {
            "ru": "Наука",
            "en": "Science",
            "pt-BR": "Ciência"
        },
        "self-improvement": {
            "ru": "Самосовершенствование",
            "en": "Self-improvement",
            "pt-BR": "Motivação e Auto-ajuda"
        },
        "society & culture": {
            "ru": "Общество и культура",
            "en": "Society & culture",
            "pt-BR": "Sociedade e cultura"
        },
        "sports": {
            "ru": "Спорт",
            "en": "Sports",
            "pt-BR": "Esportes"
        },
        "tech news": {
            "ru": "Технические новости",
            "en": "Tech news",
            "pt-BR": "Notícias de tecnologia"
        },
        "technology": {
            "ru": "Технологии",
            "en": "Technology",
            "pt-BR": "Tecnologia"
        },
        "true crime": {
            "ru": "Настоящее преступление",
            "en": "True crime",
            "pt-BR": "Crimes reais"
        },
        "video games": {
            "ru": "Видеоигры",
            "en": "Video games"
        },
    },

    "file_processing": {
        "getting_file_size": {
            "ru": "Получение размера файла",
            "en": "Getting file size"
        },
        "compressing": {
            "ru": "Сжатие...",
            "en": "Compressing..."
        },
        "uploading": {
            "ru": "Выгрузка",
            "en": "Uploading"
        },
        "downloading": {
            "ru": "Загрузка",
            "en": "Downloading"
        },
        "uploading_to_telegram_servers": {
            "ru": "Загрузка на сервера Telegram",
            "en": "Uploading to telegram servers"
        }
    }
}
