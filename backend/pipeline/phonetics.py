SCRIPT_MAP = {
    "hi": "Devanagari",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "mr": "Devanagari",
    "gu": "Gujarati",
    "pa": "Gurmukhi",
}


def romanize_word(word, language_code):
    """
    Romanize a single word from its native script.
    Returns the original word unchanged if language is unsupported
    or if transliteration fails.
    """
    source_script = SCRIPT_MAP.get((language_code or "").lower())
    if not source_script:
        return word

    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        script_const = getattr(sanscript, source_script.upper(), None)
        if script_const is None:
            return word
        return transliterate(word, script_const, sanscript.ITRANS)
    except Exception:
        return word


def romanize_words(words, language_code):
    """
    Add a 'phonetic' key to each word dict with its romanized form.
    Input:  [{"word": "ನಮಸ್ಕಾರ", "start": 1.2, "end": 1.8}, ...]
    Output: [{"word": "ನಮಸ್ಕಾರ", "phonetic": "namaskAra", "start": 1.2, "end": 1.8}, ...]
    """
    return [
        {**w, "phonetic": romanize_word(w.get("word", ""), language_code)}
        for w in words
    ]
