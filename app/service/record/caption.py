import re

from lib.markup.cleaner import html_mrkd_cleaner


def prepare_message_text(
        text, max_length=1024, clear_markup=True, parse_mode=None):
    if clear_markup:
        text = html_mrkd_cleaner(text)

    # убрать тройные+ переносы
    text = re.sub(r'\n\n\n+', '\n\n', text)
    # убрать пробелы в начале строк
    text = re.sub(r'\n +', '\n', text)

    # if parseMode == "HTML":
    # 	effective_length = len(htmlmrkdcleaner(text))
    # elif parseMode == "markdown":
    # 	effective_length = len(markdownCleaner(text))
    # else:
    # 	effective_length = len(text)
    # if effective_length > max_length:

    if len(text) > max_length:

        if parse_mode is None:
            text = text[0:max_length]
        else:
            # считаем длину без учёта разметки
            real_last_index = 0
            if parse_mode == "HTML":
                markup_entities = [x for x in re.finditer(r'<.*?>', text)]
            elif parse_mode == "markdown":
                markup_entities = [x for x in re.finditer(r'[\*[_`]', text)]

            if len(markup_entities) > 0:
                markup_entities.reverse()
                future_entity_start_end = markup_entities.pop().span()
            else:
                future_entity_start_end = None

            for i in range(len(text)):
                if future_entity_start_end is None:
                    i += max_length - real_last_index
                    break
                if i < future_entity_start_end[0]:
                    real_last_index += 1
                    if real_last_index > max_length:
                        break
                elif i == future_entity_start_end[1] - 1:
                    if len(markup_entities) > 0:
                        future_entity_start_end = markup_entities.pop().span()
                    else:
                        future_entity_start_end = None

            text = text[0:i]

        # ищем теги, знаки препинания, переносы
        # убираем текст после них
        ends_of_entities = [x.start() for x in re.finditer(
            r'([.?!] )|(<\/[a-z]*>)|(\n)', text)]  # . ! ? или </*>
        if len(ends_of_entities) > 0:

            # Сохранение последнего знака препинания или закр. тега
            last_match = ends_of_entities.pop()
            if text[last_match] != "<":  # не тег - знак препинания
                save_len = 1
            else:  # тег, сохраняем его длину
                save_len = (text[last_match:]).find(">") + 1

            text = text[:last_match + save_len]

        # особые случаи
        regulars = [
            r'\n\s*[0-9]+[\.:)]\s*\Z',  # если оканчивается на пункт списка, например, 23
            r'\s([^\s])*:\Z|\s([^\s])*:\n\Z'  # заканчивается на ' abc:'
        ]
        for regular in regulars:
            ends_of_entities = [x for x in re.finditer(regular, text)]
            if len(ends_of_entities) > 0:
                last_match = ends_of_entities.pop().start()
                text = text[:last_match]

    return text
