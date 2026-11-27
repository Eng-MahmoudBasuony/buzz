import gettext
import re

from PyQt6.QtCore import QLocale, QLibraryInfo, QTranslator

from buzz.assets import get_path
from buzz.settings.settings import APP_NAME, Settings

locale_dir = get_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

settings = Settings()

languages = [
    settings.value(settings.Key.UI_LOCALE, QLocale().name())
]

translate = gettext.translation(
    APP_NAME.lower(), locale_dir, languages=languages, fallback=True
)

_ = translate.gettext


def configure_ui_locale(app, locale_code=None):
    """Set layout direction and translate Qt's own buttons before widgets exist.

    Buzz text is loaded by gettext at startup; changing UI language still takes
    effect after restarting. Do not change the global date/number locale.
    """
    code = locale_code or settings.value(settings.Key.UI_LOCALE, QLocale().name())
    app.setLayoutDirection(QLocale(code).textDirection())
    previous = getattr(app, "qt_ui_translator", None)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(code), "qtbase", "_", path):
        app.installTranslator(translator)
        app.qt_ui_translator = translator
    else:
        translator.deleteLater()
        app.qt_ui_translator = None


def localize_transcription_message(message):
    """Localize machine status/errors without importing Qt in the audio worker.

    Match only known messages. User transcripts, model identifiers and raw
    diagnostic details are never translated or rewritten.
    """
    messages = {
        "Checking audio": _("Checking audio"),
        "Downloading audio": _("Downloading audio"),
        "Transcription checked; saving": _("Transcription checked; saving"),
        "The audio has no valid duration.": _("The audio has no valid duration."),
        "This model returns text without precise timestamps. Select TXT only, or use whisper-1 for SRT/VTT and word timings.": _("This model returns text without precise timestamps. Select TXT only, or use whisper-1 for SRT/VTT and word timings."),
        "Prepared audio chunk exceeds the API upload limit.": _("Prepared audio chunk exceeds the API upload limit."),
        "No speech was recognized. Check the audio before another paid attempt.": _("No speech was recognized. Check the audio before another paid attempt."),
        "Transcription quality check failed: repeated text. Processing stopped; no automatic paid retry.": _("Transcription quality check failed: repeated text. Processing stopped; no automatic paid retry."),
        "Transcription quality check failed: a phrase repeats continuously. Review the audio before retrying.": _("Transcription quality check failed: a phrase repeats continuously. Review the audio before retrying."),
    }
    if message in messages:
        return messages[message]
    patterns = [
        (r"Preparing audio (\d+)/(\d+)", lambda a, b: _("Preparing audio {current}/{total}").format(current=a, total=b)),
        (r"Transcribing (\d+)/(\d+) — waiting for OpenAI", lambda a, b: _("Transcribing {current}/{total} — waiting for OpenAI").format(current=a, total=b)),
        (r"Transcribed (\d+)/(\d+)", lambda a, b: _("Transcribed {current}/{total}").format(current=a, total=b)),
        (r"Downloading audio \((\d+%)\)", lambda p: _("Downloading audio ({percent})").format(percent=p)),
    ]
    for pattern, render in patterns:
        match = re.fullmatch(pattern, message or "")
        if match:
            return render(*match.groups())
    prefix = "Audio preparation failed: "
    if isinstance(message, str) and message.startswith(prefix):
        return _("Audio preparation failed: {details}").format(details=message[len(prefix):])
    return message
