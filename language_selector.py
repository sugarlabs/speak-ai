# Copyright (C) 2025 Sugar Labs
# SPDX-License-Identifier: GPL-3.0-or-later
#
# language_selector.py — GTK3 language-picker widget for Speak-AI toolbar

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from language_manager import LANGUAGE_REGISTRY, LanguageManager

_LANG_FLAGS = {
    'English (US)': '🇺🇸',
    'English (UK)': '🇬🇧',
    'Spanish': '🇪🇸',
    'French': '🇫🇷',
    'Hindi': '🇮🇳',
    'Italian': '🇮🇹',
    'Japanese': '🇯🇵',
    'Portuguese (Brazilian)': '🇧🇷',
    'Chinese (Mandarin)': '🇨🇳',
    'Arabic': '🇸🇦',
    'Swahili': '🇰🇪',
    'Kinyarwanda': '🇷🇼',
    'Quechua': '🇵🇪',
    'Guaraní': '🇵🇾',
}

_BACKEND_BADGE = {
    True: '🔊',   # Kokoro native 
    False: '📢',  # espeak-ng fallback 
}


class LanguageSelectorWidget(Gtk.Box):
    """Horizontal box containing a ComboBoxText for language selection.

    Emits 'language-changed' signal with the new language name when the
    user picks a different language.

    Usage in activity.py::

        self._lang_selector = LanguageSelectorWidget(speech_manager)
        toolbar_box.toolbar.insert(self._lang_selector.tool_item(), -1)
    """

    def __init__(self, speech_manager):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._sm = speech_manager
        self._suppress_signal = False

        label = Gtk.Label(label='Language:')
        label.get_style_context().add_class('speech-lang-label')
        self.pack_start(label, False, False, 4)

        self._combo = Gtk.ComboBoxText()
        self._combo.set_tooltip_text(
            'Select speech language\n'
            '🔊 = Kokoro neural TTS\n'
            '📢 = espeak-ng synthesis'
        )
        self._populate_combo()
        self._combo.connect('changed', self._on_combo_changed)
        self.pack_start(self._combo, False, False, 0)

        self.show_all()

    def _populate_combo(self) -> None:
        current = self._sm.get_language()
        active_idx = 0
        for idx, name in enumerate(LANGUAGE_REGISTRY.keys()):
            entry = LANGUAGE_REGISTRY[name]
            flag = _LANG_FLAGS.get(name, '')
            badge = _BACKEND_BADGE[entry['kokoro_lang_code'] is not None]
            self._combo.append_text(f'{flag} {name} {badge}')
            if name == current:
                active_idx = idx
        self._combo.set_active(active_idx)

    def _on_combo_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._suppress_signal:
            return
        idx = combo.get_active()
        if idx < 0:
            return
        lang_name = list(LANGUAGE_REGISTRY.keys())[idx]
        self._sm.set_language(lang_name)

    def set_language(self, language_name: str) -> None:
        names = list(LANGUAGE_REGISTRY.keys())
        if language_name not in names:
            return
        self._suppress_signal = True
        self._combo.set_active(names.index(language_name))
        self._suppress_signal = False

    def tool_item(self) -> Gtk.ToolItem:
        item = Gtk.ToolItem()
        item.add(self)
        return item