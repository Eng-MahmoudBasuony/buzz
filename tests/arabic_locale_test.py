import ast
import gettext
import io
import json
from pathlib import Path
import re
from string import Formatter

import polib
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "buzz/locale/ar/LC_MESSAGES/buzz.po"


def translation():
    return gettext.GNUTranslations(io.BytesIO(polib.pofile(CATALOG).to_binary()))


def placeholders(value):
    return [(name, spec, conversion) for _, name, spec, conversion in Formatter().parse(value) if name is not None]


def test_arabic_covers_all_source_messages_without_empty_or_fuzzy_entries():
    po = polib.pofile(CATALOG)
    entries = {entry.msgid: entry for entry in po if not entry.obsolete}
    assert not po.untranslated_entries()
    assert not po.fuzzy_entries()
    for path in (ROOT / "buzz").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                assert node.args[0].value in entries, (path, node.lineno)


def test_format_specifications_and_export_template_variables_are_preserved():
    for entry in polib.pofile(CATALOG):
        assert placeholders(entry.msgid) == placeholders(entry.msgstr), entry.msgid
        assert re.findall(r"\{\{.*?\}\}", entry.msgid) == re.findall(r"\{\{.*?\}\}", entry.msgstr), entry.msgid
        assert "\\n" not in entry.msgstr


def test_regional_arabic_locales_find_the_same_language_catalog(tmp_path):
    folder = tmp_path / "ar/LC_MESSAGES"
    folder.mkdir(parents=True)
    polib.pofile(CATALOG).save_as_mofile(folder / "buzz.mo")
    for code in ["ar", "ar_EG", "ar_SA", "ar_AE"]:
        catalog = gettext.translation("buzz", str(tmp_path), languages=[code])
        assert catalog.gettext("Preferences") != "Preferences"
        assert catalog.gettext("Arabic") == "العربية"


def test_arabic_plural_rule_supports_all_six_forms():
    catalog = translation()
    assert [catalog.plural(n) for n in [0, 1, 2, 3, 11, 100]] == list(range(6))


@pytest.mark.parametrize("path", sorted((ROOT / "buzz/plugins").glob("*/locale/ar.json")))
def test_bundled_plugin_arabic_has_complete_source_keys(path, monkeypatch):
    from buzz.plugins import base
    monkeypatch.setattr(base, "_current_locale", lambda: "ar_EG")
    strings = set()
    plugin = path.parent.parent / "plugin.py"
    for node in ast.walk(ast.parse(plugin.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_" and node.args and isinstance(node.args[0], ast.Constant)):
            strings.add(node.args[0].value)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert strings == data.keys()
    assert all(isinstance(value, str) and value.strip() for value in data.values())
    localized = base.plugin_gettext(str(plugin))
    for text in strings:
        assert localized(text) == data[text]
        assert placeholders(text) == placeholders(data[text])


def test_rtl_layout_standard_buttons_and_technical_inputs(qapp, qtbot):
    from buzz.locale import configure_ui_locale
    from buzz.widgets.import_url_dialog import ImportURLDialog
    from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit
    previous = qapp.layoutDirection()
    try:
        configure_ui_locale(qapp, "ar_EG")
        assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        qtbot.addWidget(buttons)
        assert any('\u0600' <= character <= '\u06ff' for character in buttons.button(QDialogButtonBox.StandardButton.Cancel).text())
        dialog = ImportURLDialog()
        qtbot.addWidget(dialog)
        url = "https://www.youtube.com/watch?v=abcdefghijk&t=399s"
        dialog.line_edit.setText(url)
        assert dialog.isRightToLeft()
        assert dialog.line_edit.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert dialog.line_edit.text() == url
        key = OpenAIAPIKeyLineEdit("fixture-value")
        qtbot.addWidget(key)
        assert key.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert key.text() == "fixture-value"
        assert key.echoMode() == key.EchoMode.Password
    finally:
        configure_ui_locale(qapp, "en_US")
        qapp.setLayoutDirection(previous)


def test_stage_localization_preserves_numbers_and_unknown_diagnostic_text(monkeypatch):
    import buzz.locale as locale
    monkeypatch.setattr(locale, "_", translation().gettext)
    stage = locale.localize_transcription_message("Transcribing 2/19 — waiting for OpenAI")
    assert "2" in stage and "19" in stage and "OpenAI" in stage
    assert "waiting" not in stage
    assert "75%" in locale.localize_transcription_message("Downloading audio (75%)")
    diagnostic = "provider diagnostic: CODE_123/path/file.wav"
    assert locale.localize_transcription_message(diagnostic) == diagnostic
    assert diagnostic in locale.localize_transcription_message("Audio preparation failed: " + diagnostic)


def test_display_translation_does_not_change_worker_checkpoints(monkeypatch):
    import buzz.locale as locale
    from buzz.transcriber.cloud_transcription import STAGES, VERSION
    monkeypatch.setattr(locale, "_", translation().gettext)
    STAGES["fixture"] = "Preparing audio 1/2"
    try:
        localized = locale.localize_transcription_message(STAGES["fixture"])
        assert localized != STAGES["fixture"]
        assert STAGES["fixture"] == "Preparing audio 1/2"
        assert VERSION == "1"
    finally:
        STAGES.pop("fixture")
