def user_language(lang):
    try:
        if lang is None:
            return "en"
        else:
            return str(lang)
    except Exception:
        return "en"
