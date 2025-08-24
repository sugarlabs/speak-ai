# Speak.activity
# A simple front end to the espeak text-to-speech engine on the XO laptop
# http://wiki.laptop.org/go/Speak
#
# Copyright (C) 2008  Joshua Minor
# Copyright (C) 2014  Walter Bender (major refactoring)
# This file is part of Speak.activity
#
# Parts of Speak.activity are based on code from Measure.activity
# Copyright (C) 2007  Arjun Sarwal - arjun@laptop.org
#
#     Speak.activity is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Speak.activity is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Speak.activity.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import dbus
import subprocess
import json
import random
import threading
from gettext import gettext as _
from dbus import PROPERTIES_IFACE

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version('TelepathyGLib', '0.12')

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gst
from gi.repository import TelepathyGLib

GObject.threads_init()
Gst.init(None)

from sugar3.activity import activity
from sugar3.presence import presenceservice
from sugar3.graphics import style
from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.radiotoolbutton import RadioToolButton
from sugar3.graphics.toolbarbox import ToolbarBox, ToolbarButton
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.graphics.objectchooser import ObjectChooser

from sugar3 import mime
from sugar3 import profile

import eye
import glasses
import eyelashes
import halfmoon
import sleepy
import sunglasses
import wireframes

import mouth
import fft_mouth
import waveform_mouth

import face
import photoface

import voice as voice_model
import brain
import chat

from faceselect import FaceSelector

import speech

# Import GGUF model inference class
# Putting this into a try-except block to handle the case where llama-cpp-python is not installed
try:
    from GenAI import load_gguf_model
    USING_BRAIN = False
except ImportError:
    USING_BRAIN = True

from LLM import is_connected, ask_llm_prompted, DEFAULT_PROMPT
from GenAI import is_profane

SERVICE = 'org.sugarlabs.Speak'
IFACE = SERVICE
PATH = '/org/sugarlabs/Speak'

logger = logging.getLogger('speak')

ACCELEROMETER_DEVICE = '/sys/devices/platform/lis3lv02d/position'
MODE_TYPE = 1
MODE_BOT = 2
MODE_CHAT = 3
FACE_CARTOON = 1
FACE_PHOTO = 2
MOUTHS = [mouth.PeakMouth, waveform_mouth.WaveformMouth, fft_mouth.FFTMouth, ]
NUMBERS = ['one', 'two', 'three', 'four', 'five']
SLEEPY_EYES = sleepy.Sleepy
EYE_DICT = {
    'eyes': {'label': _('Round'), 'widget': eye.Eye, 'index': 1},
    'glasses': {'label': _('Glasses'), 'widget': glasses.Glasses, 'index': 2},
    'halfmoon': {'label': _('Half moon'), 'widget': halfmoon.Halfmoon,
                 'index': 3},
    'eyelashes': {'label': _('Eye lashes'), 'widget': eyelashes.Eyelashes,
                  'index': 4},
    'sunglasses': {'label': _('Sunglasses'), 'widget': sunglasses.Sunglasses,
                   'index': 5},
    'wireframes': {'label': _('Wire frames'), 'widget': wireframes.Wireframes,
                   'index': 6},
}
DELAY_BEFORE_SPEAKING = 1500  # milleseconds
IDLE_DELAY = 120000  # milleseconds
IDLE_PHRASES = ['zzzzzzzzz', _('I am bored.'), _('Talk to me.'),
                _('I am sleepy.'), _('Are you still there?'),
                _('Please type something.'),
                _('Do you have anything to say to me?'), _('Hello?')]
SIDEWAYS_PHRASES = [_('Whoa! Sideways!'), _("I'm on my side."), _('Uh oh.'),
                    _('Wheeeee!'), _('Hey! Put me down!'), _('Falling over!')]
SLASH = '-x-SLASH-x-'  # slash safe encoding

CHANNEL_INTERFACE = TelepathyGLib.IFACE_CHANNEL
CHANNEL_INTERFACE_GROUP = TelepathyGLib.IFACE_CHANNEL_INTERFACE_GROUP
CHANNEL_TYPE_TEXT = TelepathyGLib.IFACE_CHANNEL_TYPE_TEXT
CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES = \
    TelepathyGLib.ChannelGroupFlags.CHANNEL_SPECIFIC_HANDLES
CHANNEL_TEXT_MESSAGE_TYPE_NORMAL = TelepathyGLib.ChannelTextMessageType.NORMAL
CONN_INTERFACE = TelepathyGLib.IFACE_CONNECTION
CONN_INTERFACE_ALIASING = TelepathyGLib.IFACE_CONNECTION_INTERFACE_ALIASING


def _luminance(color):
    ''' Calculate luminance value '''
    return int(color[1:3], 16) * 0.3 + int(color[3:5], 16) * 0.6 + \
        int(color[5:7], 16) * 0.1


def _lighter_color(colors):
    ''' Which color is lighter? Use that one for the text nick color '''
    if _luminance(colors[0]) > _luminance(colors[1]):
        return 0
    return 1


def _has_accelerometer():
    return os.path.exists(ACCELEROMETER_DEVICE) and _is_tablet_mode()


def _is_tablet_mode():
    try:
        fp = open('/dev/input/event4', 'rb')
        fp.close()
    except IOError:
        return False

    try:
        output = subprocess.call(
            ['evtest', '--query', '/dev/input/event4', 'EV_SW',
             'SW_TABLET_MODE'])
    except (OSError, subprocess.CalledProcessError):
        return False
    if output == 10:
        return True
    return False


class SpeakActivity(activity.Activity):
    def __init__(self, handle):
        super(SpeakActivity, self).__init__(handle)

        self._notebook = Gtk.Notebook()
        self.set_canvas(self._notebook)
        self._notebook.show()

        self._colors = profile.get_color().to_string().split(',')
        lighter = style.Color(self._colors[
            _lighter_color(self._colors)])

        self._mode = MODE_TYPE
        self._tablet_mode = _is_tablet_mode()
        self._robot_idle_id = None
        self._active_eyes = None
        self._active_number_of_eyes = None
        self._current_voice = None
        self._face_type = FACE_CARTOON

        # Load personas from `personas.json`
        self._personas = {}
        self._current_persona = None
        try:
            with open('personas.json', 'r') as f:
                self._personas = json.load(f)
            # Set default persona to Jane
            self._current_persona = 'Jane'
        except FileNotFoundError:
            logger.warning("personas.json not found, using default persona")
            # Fallback default persona, in case personas.json is missing
            self._personas = {
                'Jane': {
                    'voice': 'af_bella',
                    'prompt': (
                        "You are a friendly teacher named Jane who is 28 years old. "
                        "You teach 10 year old children. Always give helpful, "
                        "educational responses in simple words that children can "
                        "understand. Keep your answers between 20-40 words. "
                        "Be encouraging and enthusiastic but never use emojis(ever). "
                        "If you notice spelling mistakes, gently correct them. "
                        "Stay focused on the topic and give relevant answers."
                    )
                }
            }
            self._current_persona = 'Jane'

        # make an audio device for playing back and rendering audio
        self.connect('notify::active', self._active_cb)
        self._cfg = {}

        # make a box to type into
        self._entry_box = Gtk.HBox()

        if self._tablet_mode:
            self._entry = Gtk.Entry()
            self._entry_box.pack_start(self._entry, True, True, 0)
            talk_button = ToolButton('microphone')
            talk_button.set_tooltip(_('Speak'))
            talk_button.connect('clicked', self._talk_cb)
            self._entry_box.pack_end(talk_button, False, True, 0)
        else:
            self._entrycombo = Gtk.ComboBoxText.new_with_entry()
            self._entrycombo.connect('changed', self._combo_changed_cb)
            self._entry = self._entrycombo.get_child()
            self._entry.set_size_request(-1, style.GRID_CELL_SIZE)
            self._entry_box.pack_start(self._entrycombo, True, True, 0)
        self._entry.set_editable(True)
        self._entry.connect('activate', self._entry_activate_cb)
        self._entry.connect('key-press-event', self._entry_key_press_cb)
        self._entry.modify_font(Pango.FontDescription('sans bold 24'))
        self._entry_box.show()

        self.face = face.View(fill_color=lighter)
        self._cartoon_face = self.face
        self.face.set_size_request(
            -1, Gdk.Screen.height() - 2 * style.GRID_CELL_SIZE)
        self.face.show()

        # layout the screen
        self._box = Gtk.VBox(homogeneous=False)
        if self._tablet_mode:
            self._box.pack_start(self._entry_box, False, True, 0)
            self._box.pack_start(self.face, True, True, 0)
        else:
            self._box.pack_start(self.face, True, False, 0)
            self._box.pack_start(self._entry_box, True, True, 0)

        self.add_events(Gdk.EventMask.POINTER_MOTION_HINT_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('motion_notify_event', self._mouse_moved_cb)

        self._box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._box.connect('button_press_event', self._mouse_clicked_cb)

        # desktop
        self._notebook.show()
        self._notebook.props.show_border = False
        self._notebook.props.show_tabs = False

        self._box.show_all()
        self._notebook.append_page(self._box, Gtk.Label(''))

        self._chat = chat.View()
        self._chat.show_all()
        self._notebook.append_page(self._chat, Gtk.Label(''))

        # make the text box active right away
        if not self._tablet_mode:
            self._entry.grab_focus()

        self._entry.connect('move-cursor', self._cursor_moved_cb)
        self._entry.connect('changed', self._cursor_moved_cb)

        toolbox = ToolbarBox()
        self._activity_button = ActivityToolbarButton(self)
        self._activity_button.connect('clicked', self._configure_cb)

        toolbox.toolbar.insert(self._activity_button, -1)

        self._mode_type = RadioToolButton(
            icon_name='mode-type')
        self._mode_type.set_tooltip(_('Type something to hear it'))
        self._mode_type.connect('toggled', self.__toggled_mode_type_cb)
        toolbox.toolbar.insert(self._mode_type, -1)

        mode_robot = RadioToolButton(
            icon_name='mode-robot',
            group=self._mode_type)
        mode_robot.set_tooltip(_('Ask robot any question'))
        mode_robot.connect('toggled', self.__toggled_mode_robot_cb)
        toolbox.toolbar.insert(mode_robot, -1)

        self._mode_chat = RadioToolButton(
            icon_name='mode-chat',
            group=self._mode_type)
        self._mode_chat.set_tooltip(_('Voice chat'))
        self._mode_chat.connect('toggled', self.__toggled_mode_chat_cb)
        toolbox.toolbar.insert(self._mode_chat, -1)

        self._voice_button = ToolbarButton(
            page=self._make_voice_bar(),
            label=_('Voice'),
            icon_name='voice')
        self._voice_button.connect('clicked', self._configure_cb)
        toolbox.toolbar.insert(self._voice_button, -1)

        # Add Persona button
        self._persona_button = ToolbarButton(
            page=self._make_persona_bar(),
            label=_('Persona'),
            icon_name='Personas_Icon')
        self._persona_button.connect('clicked', self._configure_cb)
        toolbox.toolbar.insert(self._persona_button, -1)

        # Add Kokoro button
        self._kokoro_button = ToolbarButton(
            page=self._make_kokoro_bar(),
            label=_('Kokoro'),
            icon_name='module-language')  # TODO: currently re-using an old icon, need to change this.
        self._kokoro_button.connect('clicked', self._configure_cb)
        toolbox.toolbar.insert(self._kokoro_button, -1)

        self._face_button = ToolbarButton(
            page=self._make_face_bar(),
            label=_('Face'),
            icon_name='face')
        self._face_button.connect('clicked', self._configure_cb)
        toolbox.toolbar.insert(self._face_button, -1)

        separator = Gtk.SeparatorToolItem()
        separator.set_draw(False)
        separator.set_expand(True)
        toolbox.toolbar.insert(separator, -1)

        toolbox.toolbar.insert(StopButton(self), -1)

        toolbox.show_all()
        self.toolbar_box = toolbox

        Gdk.Screen.get_default().connect('size-changed',
                                         self._configure_cb)

        self._first_time = True
        self._new_instance()

        self._configure_cb()
        self._poll_accelerometer()

        if self.shared_activity:
            # we are joining the activity
            self.connect('joined', self._joined_cb)
            if self.get_shared():
                # we have already joined
                self._joined_cb(self)
            self._mode_chat.set_active(True)
            self._setup_chat_mode()
        elif handle.uri:
            # XMPP non-sugar3 incoming chat, not sharable
            self._activity_button.props.page.share.props.visible = \
                False
            self._one_to_one_connection(handle.uri)
        else:
            # we are creating the activity
            self.connect('shared', self._shared_cb)

    def _toolbar_expanded(self):
        if self._activity_button.is_expanded():
            return True
        if self._voice_button.is_expanded():
            return True
        if self._persona_button.is_expanded():
            return True
        if self._face_button.is_expanded():
            return True
        return False

    def _configure_cb(self, event=None):
        self._entry.set_size_request(-1, style.GRID_CELL_SIZE)
        if self._toolbar_expanded():
            self.face.set_size_request(
                -1, Gdk.Screen.height() - 3 * style.GRID_CELL_SIZE)
            self._chat.resize_chat_box(expanded=True)
            self._chat.resize_buddy_list()
        else:
            self.face.set_size_request(
                -1, Gdk.Screen.height() - 2 * style.GRID_CELL_SIZE)
            self._chat.resize_chat_box()
            self._chat.resize_buddy_list()

    def _new_instance(self):
        if self._first_time:
            # self.voices.connect('changed', self.__changed_voices_cb)
            self.pitchadj.connect('value_changed', self._pitch_adjusted_cb)
            self.rateadj.connect('value_changed', self._rate_adjusted_cb)
            
            # Set initial persona voice
            self._set_persona_voice()
            
        if self._active_number_of_eyes is None:
            self._number_of_eyes_changed_event_cb(None, None, 'two', True)
        if self._active_eyes is None:
            self._eyes_changed_event_cb(None, None, 'eyes', True)

        self._mouth_changed_cb(None, True)

        self.face.look_ahead()

        presenceService = presenceservice.get_instance()
        self.owner = presenceService.get_owner()
        if self._first_time:
            # say hello to the user
            if self._tablet_mode:
                self._entry.props.text = _('Hello %s.') \
                    % self.owner.props.nick
            self.face.say_notification(_('Hello %s. Please Type something.')
                                       % self.owner.props.nick)
        else:
            if self._tablet_mode:
                self._entry.props.text = _('Welcome back %s.') \
                    % self.owner.props.nick
            self.face.say_notification(_('Welcome back %s.')
                                       % self.owner.props.nick)
        self._set_idle_phrase(speak=False)
        self._first_time = False

    def read_file(self, file_path):
        self._cfg = json.loads(open(file_path, 'r').read())

        current_voice = self.face.status.voice

        type_ = self._cfg['face_type']
        lighter = style.Color(self._colors[_lighter_color(self._colors)])
        if type_ == self._face_type:
            status = self.face.status = \
                face.Status().deserialize(self._cfg['status'])
        elif type_ == FACE_CARTOON:
            self._set_face(face.View(fill_color=lighter), FACE_CARTOON)
            self._cartoon_face = self.face
            status = self.face.status = \
                face.Status().deserialize(self._cfg['status'])
        else:
            status = photoface.Status().deserialize(self._cfg['status'])
            view = photoface.View(*status.get_args(), fill_color=lighter)
            status = view.status
            self._set_face(view, FACE_PHOTO)

        found_my_voice = False
        for name in list(self._voice_evboxes.keys()):
            if self._voice_evboxes[name][1] == current_voice:
                self._voice_evboxes[name][0].modify_bg(
                    0, style.COLOR_BLACK.get_gdk_color())
            if self._voice_evboxes[name][1] == status.voice and \
               not found_my_voice:
                self._voice_evboxes[name][0].modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())
                self.face.set_voice(status.voice)
                if self._mode == MODE_BOT:
                    brain.load(self, status.voice)
                found_my_voice = True

        self.pitchadj.value = self.face.status.pitch
        self.rateadj.value = self.face.status.rate

        if self._face_type == FACE_CARTOON:
            if status.mouth in MOUTHS:
                self._mouth_type[MOUTHS.index(status.mouth)].set_active(True)

            self._number_of_eyes_changed_event_cb(
                None, None, NUMBERS[len(status.eyes) - 1], True)
            for name in list(EYE_DICT.keys()):
                if status.eyes[0] == EYE_DICT[name]['widget']:
                    self._eye_type[name].set_icon_name(name + '-selected')
                    self._eyes_changed_event_cb(None, None, name, True)
                    break

        self._entry.props.text = self._cfg['text']
        if not self._tablet_mode:
            for i in self._cfg['history']:
                self._entrycombo.append_text(i)

        # Load persona if saved
        if 'persona' in self._cfg and self._cfg['persona'] in self._personas:
            self._current_persona = self._cfg['persona']
            # Update persona visual selection
            for persona_name in list(self._persona_evboxes.keys()):
                self._persona_evboxes[persona_name].modify_bg(
                    0, style.COLOR_BLACK.get_gdk_color())
            if self._current_persona in self._persona_evboxes:
                self._persona_evboxes[self._current_persona].modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())

        self._new_instance()

    def write_file(self, file_path):
        if self._tablet_mode:
            if 'history' in self._cfg:
                history = self._cfg['history']  # retain old history
            else:
                history = []
        else:
            history = [i[0] for i in self._entrycombo.get_model()]
        cfg = {'status': self.face.status.serialize(),
               'face_type': self._face_type,
               'text': self._entry.props.text,
               'history': history,
               'persona': self._current_persona, }
        open(file_path, 'w').write(json.dumps(cfg))

    def _look_at_cursor(self, entry, *ignored):
        # make the eyes track the motion of the text cursor
        index = entry.props.cursor_position
        layout = entry.get_layout()
        pos = layout.get_cursor_pos(index)
        x = pos[0].x / Pango.SCALE - entry.props.scroll_offset
        y = entry.get_allocation().y
        self.face.look_at(pos=(x, y))
        return False

    def _cursor_moved_cb(self, entry, *ignored):
        GLib.timeout_add(50, self._look_at_cursor, entry)

    def _poll_accelerometer(self):
        if _has_accelerometer():
            idle_time = self._test_orientation()
            GLib.timeout_add(idle_time, self._poll_accelerometer)

    def _test_orientation(self):
        if _has_accelerometer():
            fh = open(ACCELEROMETER_DEVICE)
            string = fh.read()
            fh.close()
            xyz = string[1:-2].split(',')
            x = int(xyz[0])
            y = int(xyz[1])
            # DO SOMETHING HERE
            if ((Gdk.Screen.width() > Gdk.Screen.height()
                 and abs(x) > abs(y))
                or (Gdk.Screen.width() < Gdk.Screen.height()
                    and abs(x) < abs(y))):
                sideways_phrase = random.randint(0, len(SIDEWAYS_PHRASES) - 1)
                self.face.say(SIDEWAYS_PHRASES[sideways_phrase])
                return IDLE_DELAY  # Don't repeat the message for a while
            return 1000  # Test again soon

    def get_mouse(self):
        display = Gdk.Display.get_default()
        screen, mouseX, mouseY, modifiers = display.get_pointer()
        return mouseX, mouseY

    def _mouse_moved_cb(self, widget, event):
        # make the eyes track the motion of the mouse cursor
        self.face.look_at()
        self._chat.look_at()

    def _mouse_clicked_cb(self, widget, event):
        pass

    def _make_voice_bar(self):
        voicebar = Gtk.Toolbar()

        all_voices = []
        for name in sorted(voice_model.allVoices().keys()):
            if len(name) < 26:
                friendly_name = name
            else:
                friendly_name = name[:26] + '...'
            all_voices.append([voice_model.allVoices()[name], friendly_name])

        # A palette for the voice selection
        self._voice_evboxes = {}
        self._voice_box = Gtk.HBox()
        vboxes = [Gtk.VBox(), Gtk.VBox(), Gtk.VBox()]
        count = len(list(voice_model.allVoices().keys()))
        found_my_voice = False
        for i, voice in enumerate(sorted(all_voices)):
            label = Gtk.Label()
            label.set_use_markup(True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_markup('<span size="large">%s</span>' % voice[1])

            alignment = Gtk.Alignment.new(0, 0, 0, 0)
            alignment.add(label)
            label.show()

            evbox = Gtk.EventBox()
            self._voice_evboxes[voice[1]] = [evbox, voice[0]]
            self._voice_evboxes[voice[1]][0].connect(
                'button-press-event', self._voices_changed_event_cb, voice)
            if voice[0] == self.face.status.voice and not found_my_voice:
                self._current_voice = voice
                evbox.modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())
                found_my_voice = True
            evbox.add(alignment)
            alignment.show()
            if i < count // 3:
                vboxes[0].pack_start(evbox, True, True, 0)
            elif i < 2 * count // 3:
                vboxes[1].pack_start(evbox, True, True, 0)
            else:
                vboxes[2].pack_start(evbox, True, True, 0)
        self._voice_box.pack_start(vboxes[0], True, True,
                                   style.DEFAULT_PADDING)
        self._voice_box.pack_start(vboxes[1], True, True,
                                   style.DEFAULT_PADDING)
        self._voice_box.pack_start(vboxes[2], True, True,
                                   style.DEFAULT_PADDING)

        voice_palette_button = ToolButton('module-language')
        voice_palette_button.set_tooltip(_('Choose voice:'))
        self._voice_palette = voice_palette_button.get_palette()
        self._voice_palette.set_content(self._voice_box)
        self._voice_box.show_all()
        voice_palette_button.connect('clicked', self._face_palette_cb)
        voicebar.insert(voice_palette_button, -1)
        voice_palette_button.show()

        brain_voices = []
        for name in sorted(brain.BOTS.keys()):
            brain_voices.append([voice_model.allVoices()[name], name])

        self._brain_evboxes = {}
        self._brain_box = Gtk.HBox()
        vboxes = Gtk.VBox()
        found_my_voice = False
        for i, voice in enumerate(brain_voices):
            label = Gtk.Label()
            label.set_use_markup(True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_markup('<span size="large">%s</span>' % voice[1])

            alignment = Gtk.Alignment.new(0, 0, 0, 0)
            alignment.add(label)
            label.show()

            evbox = Gtk.EventBox()
            self._brain_evboxes[voice[1]] = [evbox, voice[0]]
            self._brain_evboxes[voice[1]][0].connect(
                'button-press-event', self._voices_changed_event_cb, voice)
            if voice[0] == self.face.status.voice and not found_my_voice:
                evbox.modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())
                found_my_voice = True
            evbox.add(alignment)
            alignment.show()
            vboxes.pack_start(evbox, True, True, 0)
        self._brain_box.pack_start(vboxes, True, True, style.DEFAULT_PADDING)
        self._brain_box.show_all()

        separator = Gtk.SeparatorToolItem()
        separator.set_draw(True)
        separator.set_expand(False)
        voicebar.insert(separator, -1)

        self.pitchadj = Gtk.Adjustment(self.face.status.pitch,
                                       speech.PITCH_MIN, speech.PITCH_MAX,
                                       1, speech.PITCH_MAX // 10, 0)
        pitchbar = Gtk.HScale.new(self.pitchadj)
        pitchbar.set_draw_value(False)
        pitchbar.set_size_request(240, 15)

        pitchbar_toolitem = ToolWidget(widget=pitchbar, label_text=_('Pitch:'))
        voicebar.insert(pitchbar_toolitem, -1)

        self.rateadj = Gtk.Adjustment(self.face.status.rate,
                                      speech.RATE_MIN, speech.RATE_MAX,
                                      1, speech.RATE_MAX // 10, 0)
        ratebar = Gtk.HScale.new(self.rateadj)
        ratebar.set_draw_value(False)
        ratebar.set_size_request(240, 15)

        ratebar_toolitem = ToolWidget(widget=ratebar, label_text=_('Rate:'))
        voicebar.insert(ratebar_toolitem, -1)

        voicebar.show_all()
        return voicebar

    def _pitch_adjusted_cb(self, adjustment):
        self.face.status.pitch = adjustment.get_value()
        self.face.say_notification(_('pitch adjusted'))

    def _rate_adjusted_cb(self, adjustment):
        self.face.status.rate = adjustment.get_value()
        self.face.say_notification(_('rate adjusted'))

    def _make_face_bar(self):
        facebar = Gtk.Toolbar()

        self._photo_face = ToolButton('photoface')
        self._photo_face.set_tooltip(_('Set face from photo'))
        self._photo_face.connect('clicked', self._photo_face_cb)
        facebar.insert(self._photo_face, -1)
        self._photo_face.show()

        self._clear = ToolButton('face')
        self._clear.set_tooltip(_('Clear photo face'))
        self._clear.set_sensitive(False)
        self._clear.connect('clicked', self._clear_photo_cb)
        facebar.insert(self._clear, -1)
        self._clear.show()

        separator = Gtk.SeparatorToolItem()
        separator.set_draw(True)
        separator.set_expand(False)
        facebar.insert(separator, -1)

        self._mouth_type = []
        button = RadioToolButton(
            icon_name='mouth',
            group=None)
        button.set_tooltip(_('Simple'))
        button.connect('clicked', self._mouth_changed_cb, False)
        facebar.insert(button, -1)
        self._mouth_type.append(button)

        button = RadioToolButton(
            icon_name='waveform',
            group=self._mouth_type[0])
        button.set_tooltip(_('Waveform'))
        button.connect('clicked', self._mouth_changed_cb, False)
        facebar.insert(button, -1)
        self._mouth_type.append(button)

        button = RadioToolButton(
            icon_name='frequency',
            group=self._mouth_type[0])
        button.set_tooltip(_('Frequency'))
        button.connect('clicked', self._mouth_changed_cb, False)
        facebar.insert(button, -1)
        self._mouth_type.append(button)

        separator = Gtk.SeparatorToolItem()
        separator.set_draw(True)
        separator.set_expand(False)
        facebar.insert(separator, -1)

        eye_box = Gtk.VBox()
        self._eye_type = {}
        for name in list(EYE_DICT.keys()):
            self._eye_type[name] = ToolButton(name)
            self._eye_type[name].connect('clicked',
                                         self._eyes_changed_event_cb,
                                         None, name, False)
            label = Gtk.Label(EYE_DICT[name]['label'])
            hbox = Gtk.HBox()
            hbox.pack_start(self._eye_type[name], True, True, 0)
            self._eye_type[name].show()
            hbox.pack_start(label, True, True, 0)
            label.show()
            evbox = Gtk.EventBox()
            evbox.connect('button-press-event', self._eyes_changed_event_cb,
                          name, False)
            evbox.add(hbox)
            hbox.show()
            eye_box.pack_start(evbox, True, True, 0)

        eye_palette_button = ToolButton('eyes')
        eye_palette_button.set_tooltip(_('Choose eyes:'))
        palette = eye_palette_button.get_palette()
        palette.set_content(eye_box)
        eye_box.show_all()
        eye_palette_button.connect('clicked', self._face_palette_cb)
        facebar.insert(eye_palette_button, -1)
        eye_palette_button.show()

        number_of_eyes_box = Gtk.VBox()
        self._number_of_eyes_type = {}
        for name in NUMBERS:
            self._number_of_eyes_type[name] = ToolButton(name)
            self._number_of_eyes_type[name].connect(
                'clicked', self._number_of_eyes_changed_event_cb,
                None, name, False)
            label = Gtk.Label(name)
            hbox = Gtk.HBox()
            hbox.pack_start(self._number_of_eyes_type[name], True, True, 0)
            self._number_of_eyes_type[name].show()
            hbox.pack_start(label, True, True, 0)
            label.show()
            evbox = Gtk.EventBox()
            evbox.connect('button-press-event',
                          self._number_of_eyes_changed_event_cb,
                          name, False)
            evbox.add(hbox)
            hbox.show()
            number_of_eyes_box.pack_start(evbox, True, True, 0)

        number_of_eyes_palette_button = ToolButton('number')
        number_of_eyes_palette_button.set_tooltip(_('Eyes number:'))
        palette = number_of_eyes_palette_button.get_palette()
        palette.set_content(number_of_eyes_box)
        number_of_eyes_box.show_all()
        number_of_eyes_palette_button.connect('clicked', self._face_palette_cb)
        facebar.insert(number_of_eyes_palette_button, -1)
        number_of_eyes_palette_button.show()

        self._cartoon_face_buttons = self._mouth_type + \
            [eye_palette_button, number_of_eyes_palette_button]

        facebar.show_all()
        return facebar

    def _make_kokoro_bar(self):
        kokoro_bar = Gtk.Toolbar()
        self._kokoro_voice_evboxes = {}
        self._kokoro_voice_box = Gtk.VBox()

        # Add heading for DEFAULT VOICES
        default_heading = Gtk.Label()
        default_heading.set_markup('<b>DEFAULT VOICES</b>')
        default_heading.set_justify(Gtk.Justification.CENTER)
        default_heading.set_alignment(0.5, 0)
        self._kokoro_voice_box.pack_start(default_heading, False, False, style.DEFAULT_PADDING)
        default_heading.show()

        # Arrange default voices in 3 columns
        default_voices = speech.get_speech().get_default_kokoro_voices()
        current_voice = speech.get_speech().current_kokoro_voice
        default_vboxes = [Gtk.VBox(), Gtk.VBox(), Gtk.VBox()]
        count = len(default_voices)
        for i, voice_name in enumerate(default_voices):
            label = Gtk.Label()
            label.set_use_markup(True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_markup('<span size="large">%s</span>' % voice_name)
            alignment = Gtk.Alignment.new(0, 0, 0, 0)
            alignment.add(label)
            label.show()
            evbox = Gtk.EventBox()
            self._kokoro_voice_evboxes[voice_name] = evbox
            evbox.connect('button-press-event', self._kokoro_voice_changed_event_cb, voice_name)
            if voice_name == current_voice:
                evbox.modify_bg(0, style.COLOR_BUTTON_GREY.get_gdk_color())
            evbox.add(alignment)
            alignment.show()
            if i < count // 3:
                default_vboxes[0].pack_start(evbox, True, True, 0)
            elif i < count // 3 * 2:
                default_vboxes[1].pack_start(evbox, True, True, 0)
            else:
                default_vboxes[2].pack_start(evbox, True, True, 0)
            evbox.show()
        default_hbox = Gtk.HBox()
        default_hbox.pack_start(default_vboxes[0], True, True, style.DEFAULT_PADDING)
        default_hbox.pack_start(default_vboxes[1], True, True, style.DEFAULT_PADDING)
        default_hbox.pack_start(default_vboxes[2], True, True, style.DEFAULT_PADDING)
        self._kokoro_voice_box.pack_start(default_hbox, False, False, style.DEFAULT_PADDING)
        default_hbox.show_all()

        # Add heading for Add-on Voices
        addon_heading = Gtk.Label()
        addon_heading.set_markup('<b>ADD-ON VOICES</b>')
        addon_heading.set_justify(Gtk.Justification.CENTER)
        addon_heading.set_alignment(0.5, 0)
        self._kokoro_voice_box.pack_start(addon_heading, False, False, style.DEFAULT_PADDING)
        addon_heading.show()

        # Arrange add-on voices in 3 columns
        addon_voices = speech.get_speech().get_addon_kokoro_voices()
        addon_vboxes = [Gtk.VBox(), Gtk.VBox(), Gtk.VBox()]
        count = len(addon_voices)
        for i, voice_name in enumerate(addon_voices):
            label = Gtk.Label()
            label.set_use_markup(True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_markup('<span size="large">%s</span>' % voice_name)
            alignment = Gtk.Alignment.new(0, 0, 0, 0)
            alignment.add(label)
            label.show()
            evbox = Gtk.EventBox()
            self._kokoro_voice_evboxes[voice_name] = evbox
            evbox.connect('button-press-event', self._kokoro_voice_changed_event_cb, voice_name)
            if voice_name == current_voice:
                evbox.modify_bg(0, style.COLOR_BUTTON_GREY.get_gdk_color())
            evbox.add(alignment)
            alignment.show()
            if i < count // 3:
                addon_vboxes[0].pack_start(evbox, True, True, 0)
            elif i < count // 3 * 2:
                addon_vboxes[1].pack_start(evbox, True, True, 0)
            else:
                addon_vboxes[2].pack_start(evbox, True, True, 0)
            evbox.show()
        addon_hbox = Gtk.HBox()
        addon_hbox.pack_start(addon_vboxes[0], True, True, style.DEFAULT_PADDING)
        addon_hbox.pack_start(addon_vboxes[1], True, True, style.DEFAULT_PADDING)
        addon_hbox.pack_start(addon_vboxes[2], True, True, style.DEFAULT_PADDING)
        self._kokoro_voice_box.pack_start(addon_hbox, False, False, style.DEFAULT_PADDING)
        addon_hbox.show_all()

        kokoro_palette_button = ToolButton('module-language')
        kokoro_palette_button.set_tooltip(_('Choose Kokoro voice:'))
        self._kokoro_palette = kokoro_palette_button.get_palette()
        self._kokoro_palette.set_content(self._kokoro_voice_box)
        self._kokoro_voice_box.show_all()
        kokoro_palette_button.connect('clicked', self._face_palette_cb)
        kokoro_bar.insert(kokoro_palette_button, -1)
        kokoro_palette_button.show()
        kokoro_bar.show_all()
        return kokoro_bar

    def _make_persona_bar(self):
        persona_bar = Gtk.Toolbar()
        
        self._persona_evboxes = {}
        self._persona_box = Gtk.VBox()
        
        # Heading
        persona_heading = Gtk.Label()
        persona_heading.set_markup('<b>PERSONAS</b>')
        persona_heading.set_justify(Gtk.Justification.CENTER)
        persona_heading.set_alignment(0.5, 0)
        self._persona_box.pack_start(persona_heading, False, False, style.DEFAULT_PADDING)
        persona_heading.show()

        # Arrange in columns
        persona_names = list(self._personas.keys())
        persona_vboxes = [Gtk.VBox(), Gtk.VBox(), Gtk.VBox()]
        count = len(persona_names)
        
        for i, persona_name in enumerate(persona_names):
            label = Gtk.Label()
            label.set_use_markup(True)
            label.set_justify(Gtk.Justification.LEFT)
            label.set_markup('<span size="large">%s</span>' % persona_name)
            
            alignment = Gtk.Alignment.new(0, 0, 0, 0)
            alignment.add(label)
            label.show()
            
            evbox = Gtk.EventBox()
            self._persona_evboxes[persona_name] = evbox
            evbox.connect('button-press-event', self._persona_changed_event_cb, persona_name)
            
            # Highlight current persona
            if persona_name == self._current_persona:
                evbox.modify_bg(0, style.COLOR_BUTTON_GREY.get_gdk_color())
            
            evbox.add(alignment)
            alignment.show()
            
            # Distribute personas across 3 columns
            if count <= 3:
                persona_vboxes[i].pack_start(evbox, True, True, 0)
            elif i < count // 3:
                persona_vboxes[0].pack_start(evbox, True, True, 0)
            elif i < 2 * count // 3:
                persona_vboxes[1].pack_start(evbox, True, True, 0)
            else:
                persona_vboxes[2].pack_start(evbox, True, True, 0)
            evbox.show()
        
        # Pack the columns
        persona_hbox = Gtk.HBox()
        persona_hbox.pack_start(persona_vboxes[0], True, True, style.DEFAULT_PADDING)
        persona_hbox.pack_start(persona_vboxes[1], True, True, style.DEFAULT_PADDING)
        persona_hbox.pack_start(persona_vboxes[2], True, True, style.DEFAULT_PADDING)
        self._persona_box.pack_start(persona_hbox, False, False, style.DEFAULT_PADDING)
        persona_hbox.show_all()
        
        # Create the palette button
        persona_palette_button = ToolButton('Personas_Icon')
        persona_palette_button.set_tooltip(_('Choose persona:'))
        self._persona_palette = persona_palette_button.get_palette()
        self._persona_palette.set_content(self._persona_box)
        self._persona_box.show_all()
        persona_palette_button.connect('clicked', self._face_palette_cb)
        persona_bar.insert(persona_palette_button, -1)
        persona_palette_button.show()
        
        persona_bar.show_all()
        return persona_bar

    def _kokoro_voice_changed_event_cb(self, widget, event, voice_name):
        # Show info label(Indication of voice changing) upon click
        info_label = Gtk.Label()
        info_label.set_markup('<span foreground="blue" size="large">%s</span>' % _('Please wait...'))
        self._kokoro_voice_box.pack_start(info_label, False, False, style.DEFAULT_PADDING)
        info_label.show()
        while Gtk.events_pending():
            Gtk.main_iteration()

        def async_check_and_update():
            kokoro_pipeline = speech.get_speech().kokoro_pipeline
            is_local = False
            if kokoro_pipeline:
                is_local = voice_name in kokoro_pipeline.voices
                if not is_local:
                    try:
                        from huggingface_hub import hf_hub_download
                    except ImportError:
                        logging.error("Hugging Face Hub was not installed, or could not be imported. Aborting")
                        info_label.set_markup('<span foreground="red" size="large">%s</span>' % _('Hugging Face Hub is not installed.'))
                        return False
                    
                    repo_id = kokoro_pipeline.repo_id
                    voice_path = hf_hub_download(repo_id=repo_id, filename=f'voices/{voice_name}.pt', cache_dir=None, force_download=False, resume_download=False)
                    is_local = os.path.exists(voice_path)
            else:
                is_local = True
            # Always speak notification before changing voice
            
            if not is_local:
                info_label.set_markup('<span foreground="blue" size="large">%s</span>' % _('This voice is being downloaded, please wait'))
            else:
                info_label.set_markup('<span foreground="green" size="large">%s</span>' % _('Changing voice, please wait'))
            while Gtk.events_pending():
                Gtk.main_iteration()
            def remove_info_label():
                self._kokoro_voice_box.remove(info_label)
                return False
            GLib.timeout_add(3000, remove_info_label)

            # Now update UI for voice selection
            for old_name, evbox in self._kokoro_voice_evboxes.items():
                if old_name == speech.get_speech().current_kokoro_voice:
                    evbox.modify_bg(0, style.COLOR_BLACK.get_gdk_color())
            self._kokoro_voice_evboxes[voice_name].modify_bg(0, style.COLOR_BUTTON_GREY.get_gdk_color())
            
            # Actually set the voice (may trigger download from Hugging Face Hub)
            speech.get_speech().set_kokoro_voice(voice_name)
            self.face.say_notification(_('Kokoro voice changed'))
            return False

        GLib.idle_add(async_check_and_update)

    def _persona_changed_event_cb(self, widget, event, persona_name):
        """Handle persona selection change"""
        logger.debug('persona_changed_event_cb %s' % persona_name)
        
        # Update visual selection
        for old_persona in list(self._persona_evboxes.keys()):
            self._persona_evboxes[old_persona].modify_bg(
                0, style.COLOR_BLACK.get_gdk_color())
        
        self._persona_evboxes[persona_name].modify_bg(
            0, style.COLOR_BUTTON_GREY.get_gdk_color())
        
        # Set current persona
        self._current_persona = persona_name
        
        # Get the persona's voice and set it (using Kokoro voices)
        persona_voice_name = self._personas[persona_name]['voice']
        
        # Update Kokoro voice selection visually
        current_kokoro_voice = speech.get_speech().current_kokoro_voice
        if persona_voice_name in self._kokoro_voice_evboxes:
            # Clear old Kokoro voice selection
            if current_kokoro_voice in self._kokoro_voice_evboxes:
                self._kokoro_voice_evboxes[current_kokoro_voice].modify_bg(
                    0, style.COLOR_BLACK.get_gdk_color())
            
            # Highlight new Kokoro voice selection
            self._kokoro_voice_evboxes[persona_voice_name].modify_bg(
                0, style.COLOR_BUTTON_GREY.get_gdk_color())
            
            # Set the Kokoro voice
            speech.get_speech().set_kokoro_voice(persona_voice_name)
        
        # Notify about persona change
        self.face.say_notification(_('Persona changed to %s') % persona_name)

    def _set_persona_voice(self):
        """Set the voice based on the current persona"""
        if not self._current_persona or self._current_persona not in self._personas:
            return
            
        persona_voice_name = self._personas[self._current_persona]['voice']
        
        # Set the Kokoro voice for the persona
        if persona_voice_name in speech.get_speech().get_available_kokoro_voices():
            speech.get_speech().set_kokoro_voice(persona_voice_name)
            logger.debug(f"Set persona voice to Kokoro voice: {persona_voice_name}")
            
            # Update Kokoro voice visual selection if the kokoro bar exists
            if hasattr(self, '_kokoro_voice_evboxes') and persona_voice_name in self._kokoro_voice_evboxes:
                # Clear old selection
                current_kokoro_voice = speech.get_speech().current_kokoro_voice
                if current_kokoro_voice in self._kokoro_voice_evboxes:
                    self._kokoro_voice_evboxes[current_kokoro_voice].modify_bg(
                        0, style.COLOR_BLACK.get_gdk_color())
                
                # Highlight new selection
                self._kokoro_voice_evboxes[persona_voice_name].modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())
        else:
            logger.warning(f"Persona voice {persona_voice_name} not found in available Kokoro voices")

    def _photo_face_cb(self, widget):
        chooser = ObjectChooser(parent=self,
                                what_filter=mime.GENERIC_TYPE_IMAGE)

        result = chooser.run()
        if result == Gtk.ResponseType.ACCEPT:
            jobject = chooser.get_selected_object()
            if jobject and jobject.file_path:
                selector = FaceSelector(jobject.file_path)
                selector.connect('face-processed',
                                 self._photo_face_processed_cb)
                selector.connect('cancel', self._photo_face_cancel_cb)
                self._notebook.append_page(selector, Gtk.Label(''))
                selector.show()

                num = self._notebook.page_num(selector)
                self._notebook.set_current_page(num)
        chooser.destroy()

    def _photo_face_processed_cb(self, widget, *face_data):
        lighter = style.Color(self._colors[_lighter_color(self._colors)])
        self._set_face(photoface.View(*face_data, fill_color=lighter),
                       FACE_PHOTO)

    def _photo_face_cancel_cb(self, widget):
        self._notebook.set_current_page(0)

    def _set_face(self, view, type_):
        self._face_type = type_
        cartoon = type_ == FACE_CARTOON

        self.face.shut_up()
        self._box.remove(self.face)
        self._box.remove(self._entry_box)

        self.face = view
        self.face.set_size_request(
            -1, Gdk.Screen.height() - 2 * style.GRID_CELL_SIZE)

        if self._tablet_mode:
            self._box.pack_start(self._entry_box, False, True, 0)
            self._box.pack_start(self.face, True, True, 0)
        else:
            self._box.pack_start(self.face, True, True, 0)
            self._box.pack_start(self._entry_box, True, True, 0)
        self.face.show()

        if not cartoon and self._mode == MODE_CHAT:
            self._mode = MODE_TYPE
            self._mode_type.set_active(True)
            self._mode_chat.set_active(False)

            self._chat.shut_up()
            self._voice_palette.set_content(self._voice_box)
            self._set_voice()
        self._notebook.set_current_page(0)

        self._photo_face.set_sensitive(cartoon)
        self._clear.set_sensitive(not cartoon)
        for bnt in self._cartoon_face_buttons:
            bnt.set_sensitive(cartoon)
        self._mode_chat.set_sensitive(cartoon)

    def _clear_photo_cb(self, widget):
        self._set_face(self._cartoon_face, FACE_CARTOON)

    def _face_palette_cb(self, button):
        palette = button.get_palette()
        palette.popdown(immediate=True)

    def _get_active_mouth(self):
        for i, button in enumerate(self._mouth_type):
            if button.get_active():
                return MOUTHS[i]

    def _mouth_changed_cb(self, ignored, quiet):
        if self._face_type == FACE_PHOTO:
            return

        value = self._get_active_mouth()
        if value is None:
            return

        self.face.status.mouth = value
        self._update_face()

        if not quiet:
            self.face.say_notification(_('mouth changed'))

    def _voices_changed_event_cb(self, widget, event, voice):
        logging.debug('voices_changed_event_cb %r %s' % (voice[0], voice[1]))
        if self._mode == MODE_BOT:
            evboxes = self._brain_evboxes
        else:
            evboxes = self._voice_evboxes
        for old_voice in list(evboxes.keys()):
            if evboxes[old_voice][1] == self.face.status.voice:
                evboxes[old_voice][0].modify_bg(
                    0, style.COLOR_BLACK.get_gdk_color())
                break

        evboxes[voice[1]][0].modify_bg(
            0, style.COLOR_BUTTON_GREY.get_gdk_color())

        self.face.set_voice(voice[0])
        if self._mode == MODE_BOT:
            brain.load(self, voice[0])
        else:
            self._current_voice = voice

    def _get_active_eyes(self):
        for name in list(EYE_DICT.keys()):
            if EYE_DICT[name]['index'] == self._active_eyes:
                return EYE_DICT[name]['widget']
        return None

    def _eyes_changed_event_cb(self, widget, event, name, quiet):
        if self._face_type == FACE_PHOTO:
            return

        if self._active_eyes is not None:
            for old_name in list(EYE_DICT.keys()):
                if EYE_DICT[old_name]['index'] == self._active_eyes:
                    self._eye_type[old_name].set_icon_name(old_name)
                    break

        if self._active_number_of_eyes is None:
            self._active_number_of_eyes = 2

        if name is not None:
            self._active_eyes = EYE_DICT[name]['index']
            self._eye_type[name].set_icon_name(name + '-selected')
            value = EYE_DICT[name]['widget']
            self.face.status.eyes = [value] * self._active_number_of_eyes
            self._update_face()
            if not quiet:
                self.face.say_notification(_('eyes changed'))

    def _number_of_eyes_changed_event_cb(self, widget, event, name, quiet):
        if self._face_type == FACE_PHOTO:
            return

        if self._active_number_of_eyes is not None:
            old_name = NUMBERS[self._active_number_of_eyes - 1]
            self._number_of_eyes_type[old_name].set_icon_name(old_name)

        if name in NUMBERS:
            self._active_number_of_eyes = NUMBERS.index(name) + 1
            self._number_of_eyes_type[name].set_icon_name(name + '-selected')
            if self._active_eyes is not None:
                for eye_name in list(EYE_DICT.keys()):
                    if EYE_DICT[eye_name]['index'] == self._active_eyes:
                        value = EYE_DICT[eye_name]['widget']
                        self.face.status.eyes = \
                            [value] * self._active_number_of_eyes
                        self._update_face()
                        if not quiet:
                            self.face.say_notification(_('eyes changed'))
                        break

    def _update_face(self):
        self.face.update()
        self._chat.update(self.face.status)

    def _combo_changed_cb(self, combo):
        # when a new item is chosen, make sure the text is selected
        if not self._entry.is_focus():
            if not self._tablet_mode:
                self._entry.grab_focus()
            self._entry.select_region(0, -1)

    def _entry_key_press_cb(self, combo, event):
        # make the up/down arrows navigate through our history
        if self._tablet_mode:
            return
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == 'Up':
            index = self._entrycombo.get_active()
            if index > 0:
                index -= 1
            self._entrycombo.set_active(index)
            self._entry.select_region(0, -1)
            return True
        elif keyname == 'Down':
            index = self._entrycombo.get_active()
            if index < len(self._entrycombo.get_model()) - 1:
                index += 1
            self._entrycombo.set_active(index)
            self._entry.select_region(0, -1)
            return True
        return False

    def _entry_activate_cb(self, entry):
        # the user pressed Return, say the text and clear it out
        text = entry.get_text()
        if self._tablet_mode:
            self._dismiss_OSK(entry)
            timeout = DELAY_BEFORE_SPEAKING
        else:
            timeout = 100
        GLib.timeout_add(timeout, self._speak_the_text, entry, text)

    def _dismiss_OSK(self, entry):
        entry.hide()
        entry.show()

    def _talk_cb(self, button):
        text = self._entry.props.text
        self._speak_the_text(self._entry, text)

    def _try_llm_response(self, text):
        """Try to get response from LLM. Returns response string or None if failed."""

        if not is_profane(text):
            return "Hmm, that word isn't very friendly. Talking with kind words makes chatting more fun! Can you try again with a friendly word?"
        
        try:
            # Get the current persona's prompt
            custom_prompt = self._personas.get(self._current_persona, {}).get('prompt', None)
            if not custom_prompt:
                custom_prompt = DEFAULT_PROMPT
            
            llm_response = ask_llm_prompted(question=text, custom_prompt=custom_prompt)

            if llm_response == None:
                logging.error("LLM returned None response")
                return None

            if not is_profane(llm_response):
                llm_response = "Sorry, I was not able to generate this response."

            return llm_response
        
        except Exception as e:
            logging.error(f"Error in LLM: {e}")
            return None

    def _try_slm_response(self, text):
        """Try to get response from SLM. Returns response string or None if failed."""

        if not is_profane(text):
            return "Hmm, that word isn't very friendly. Talking with kind words makes chatting more fun! Can you try again with a friendly word?"

        try:
            model_path = "./GenAI/LlaMA-135-Claude-RUN2-q4.gguf"
            model = load_gguf_model(model_path)
            model.set_generation_mode(3)

            model_output = model.ask_question(text)
            if not is_profane(model_output):
                model_output = "Sorry, I was not able to generate this response."
            return model_output
        
        except Exception as e:
            logging.error(f"Error using SLM model: {e}")
            return None

    def _speak_the_text(self, entry, text):
        self._remove_idle()
        if text:
            self.face.look_ahead()

            if self._mode == MODE_BOT: # Chatbot mode

                # ORDER OF PRIORITY:
                # 1. LLM (if internet is available)
                # 2. SLM (if LLM fails or no internet)
                # 3. Brain (if both LLM and SLM fail)

                if not USING_BRAIN: #SpeakAI compatibility code
                    # Try LLM first
                    # But check if connected to internet first,
                    # otherwise go to SLM fallback
                    if is_connected():
                        self.face.say("Thinking...")
                        
                        def fetch_and_speak_response():
                            response = self._try_llm_response(text)
                            
                            if not response:
                                response = self._try_slm_response(text)
                            
                            if not response:
                                response = brain.respond(text)

                            def safe_face_say():
                                self.face.say(response)
                                return False
                            GLib.idle_add(safe_face_say)
                        
                        # Start the thread
                        # Threading here to stop blocking the UI. The response from SugarAI service takes a while, so it's better this way
                        llm_thread = threading.Thread(target=fetch_and_speak_response)
                        llm_thread.daemon = True
                        llm_thread.start()
                    else:
                        # No internet, try SLM -> Brain
                        response = self._try_slm_response(text)
                        if not response:
                            response = brain.respond(text)
                        self.face.say(response)
                else:
                    # Use traditional brain chatbot
                    brain_response = brain.respond(text)

                    if not is_profane(text):
                        brain_response = "Sorry, looks like you have entered a blacklisted word. Please try typing something else."
                    
                    if not is_profane(brain_response):
                        brain_response = "Sorry, I was not able to generate this response. Profanity intercept."

                    self.face.say(brain_response)
            else:
                if not is_profane(text):
                    text = "Sorry, looks like you have entered a blacklisted word. Please try typing something else."
                self.face.say(text)

        if text and not self._tablet_mode:
            # add this text to our history unless it is the same as
            # the last item
            history = self._entrycombo.get_model()
            if len(history) == 0 or history[-1][0] != text:
                self._entrycombo.append_text(text)
                # don't let the history get too big
                while len(history) > 20:
                    self._entrycombo.remove(0)
                # select the new item
                self._entrycombo.set_active(len(history) - 1)
        if text:
            # select the whole text
            entry.select_region(0, -1)

        # Launch an robot idle phrase after 2 minutes
        self._robot_idle_id = GLib.timeout_add(IDLE_DELAY,
                                               self._set_idle_phrase)

    def _load_sleeping_face(self):
        if self._face_type == FACE_PHOTO:
            return
        current_eyes = self.face.status.eyes
        self.face.status.eyes = [SLEEPY_EYES] * self._active_number_of_eyes
        self._update_face()
        self.face.status.eyes = current_eyes

    def _set_idle_phrase(self, speak=True):
        if speak:
            self._load_sleeping_face()
            if self.props.active and not self.shared_activity:
                idle_phrase = IDLE_PHRASES[random.randint(
                    0, len(IDLE_PHRASES) - 1)]
                self.face.say(idle_phrase)

        self._robot_idle_id = GLib.timeout_add(IDLE_DELAY,
                                               self._set_idle_phrase)

    def _active_cb(self, widget, pspec):
        # only generate sound when this activity is active
        if not self.props.active:
            self._load_sleeping_face()
            self.face.shut_up()
            self._chat.shut_up()

    def _set_voice(self, new_voice=None):
        if new_voice is not None:
            logging.debug('set_voice %r' % new_voice)
            self.face.status.voice = new_voice
        else:
            logging.debug('set_voice to current voice %s' %
                          self._current_voice[1])
            self.face.status.voice = self._current_voice[0]

    def __toggled_mode_type_cb(self, button):
        if not button.props.active:
            return

        self._mode = MODE_TYPE
        self._chat.shut_up()
        self.face.shut_up()
        self._notebook.set_current_page(0)

        self._voice_palette.set_content(self._voice_box)
        self._set_voice()

    def __toggled_mode_robot_cb(self, button):
        if not button.props.active:
            return

        self._remove_idle()

        self._mode = MODE_BOT
        self._chat.shut_up()
        self.face.shut_up()
        self._notebook.set_current_page(0)

        self._voice_palette.set_content(self._brain_box)

        if USING_BRAIN:
            new_voice = None
            for name in list(brain.BOTS.keys()):
                if self._current_voice[0].short_name == name:
                    new_voice == self._current_voice[0]
                    break
            if new_voice is None:
                new_voice = brain.get_default_voice()
                if new_voice.friendlyname in self._current_voice[0].friendlyname:
                    logging.debug('skipping sorry message for %s %s' %
                                (new_voice.friendlyname,
                                self._current_voice[0].friendlyname))
                    sorry = None
                else:
                    sorry = _("Sorry, I can't speak %(old_voice)s, "
                            "let's talk %(new_voice)s instead.") % {
                                'old_voice': self._current_voice[0].friendlyname,
                                'new_voice': new_voice.friendlyname}
            else:
                new_voice = new_voice[0]
                sorry = None

            self._set_voice(new_voice)

            evboxes = self._brain_evboxes
            for old_voice in list(evboxes.keys()):
                evboxes[old_voice][0].modify_bg(
                    0, style.COLOR_BLACK.get_gdk_color())

            if new_voice.short_name in evboxes:
                evboxes[new_voice.short_name][0].modify_bg(
                    0, style.COLOR_BUTTON_GREY.get_gdk_color())

            if not brain.load(self, new_voice, sorry):
                if sorry:
                    self.face.say_notification(sorry)

    def __toggled_mode_chat_cb(self, button):
        if not button.props.active:
            return

        self._remove_idle()

        is_first_session = not self.shared_activity

        self._setup_chat_mode()

        if is_first_session:
            self._chat.me.say_notification(
                _('You are in off-line mode, share and invite someone.'))

    def _remove_idle(self):
        if self._robot_idle_id is not None:
            GLib.source_remove(self._robot_idle_id)
            self._robot_idle_id = None

            if self._face_type == FACE_PHOTO:
                return

            value = self._get_active_eyes()
            if value is not None:
                self.face.status.eyes = [value] * self._active_number_of_eyes
                self._update_face()

    def _setup_chat_mode(self):
        self._mode = MODE_CHAT
        self._remove_idle()
        self.face.shut_up()
        self._notebook.set_current_page(1)

        self._voice_palette.set_content(self._voice_box)
        self._set_voice()

    def _shared_cb(self, sender):
        logging.debug('SHARED A CHAT')
        self._setup_text_channel()

    def _joined_cb(self, sender):
        '''Joined a shared activity.'''
        if not self.shared_activity:
            return
        logger.error('JOINED A SHARED CHAT')
        for buddy in self.shared_activity.get_joined_buddies():
            self._buddy_already_exists(buddy)
        self._setup_text_channel()

    def _one_to_one_connection(self, tp_channel):
        '''Handle a private invite from a non-sugar3 XMPP client.'''
        if self.shared_activity or self.text_channel:
            return
        bus_name, connection, channel = json.loads(tp_channel)
        logger.debug('GOT XMPP: %s %s %s', bus_name, connection, channel)
        text_channel = {}
        text_proxy = dbus.Bus().get_object(bus_name, channel)
        text_channel[PROPERTIES_IFACE] = dbus.Interface(
            text_proxy, PROPERTIES_IFACE)
        self.text_channel = TextChannelWrapper(text_channel, connection)
        self.text_channel.set_received_callback(self._received_cb)
        self.text_channel.handle_pending_messages()
        self.text_channel.set_closed_callback(
            self._one_to_one_connection_closed_cb)

        # XXX How do we detect the sender going offline?
        self._chat.chat_post.set_sensitive(True)
        # self._chat.chat_post.props.placeholder_text = None
        self._chat.chat_post.grab_focus()

    def _one_to_one_connection_closed_cb(self):
        '''Callback for when the text channel closes.'''
        pass

    def _setup_text_channel(self):
        logging.debug('_SETUP_TEXTCHANNEL')
        self.text_channel = TextChannelWrapper(
            self.shared_activity.telepathy_text_chan,
            self.shared_activity.telepathy_conn)
        self.text_channel.set_received_callback(self._received_cb)
        self.shared_activity.connect('buddy-joined', self._buddy_joined_cb)
        self.shared_activity.connect('buddy-left', self._buddy_left_cb)
        self._chat.messenger = self.text_channel
        self._chat.chat_post.set_sensitive(True)
        self._chat.chat_post.grab_focus()

    def _buddy_joined_cb(self, sender, buddy):
        '''Show a buddy who joined'''
        if buddy == self.owner:
            return
        logging.debug('%s joined the chat (%r)' % (buddy.props.nick, buddy))
        self._chat.post(
            buddy, _('%s joined the chat') % buddy.props.nick,
            status_message=True)

    def _buddy_left_cb(self, sender, buddy):
        '''Show a buddy who joined'''
        if buddy == self.owner:
            return
        logging.debug('%s left the chat (%r)' % (buddy.props.nick, buddy))
        self._chat.post(
            buddy, _('%s left the chat') % buddy.props.nick,
            status_message=True)
        self._chat.farewell(buddy)

    def _buddy_already_exists(self, buddy):
        '''Show a buddy already in the chat.'''
        if buddy == self.owner:
            return
        logging.debug('%s is here (%r)' % (buddy.props.nick, buddy))
        self._chat.post(
            buddy, _('%s is here') % buddy.props.nick,
            status_message=True)

    def _received_cb(self, buddy, text):
        '''Show message that was received.'''
        if buddy:
            if type(buddy) is dict:
                nick = buddy['nick']
            else:
                nick = buddy.props.nick
        else:
            nick = '???'
        logger.debug('Received message from %s: %s', nick, text)
        self._chat.post(buddy, text)


class TextChannelWrapper(object):
    '''Wrap a telepathy Text Channfel to make usage simpler.'''

    def __init__(self, text_chan, conn):
        '''Connect to the text channel'''
        self._activity_cb = None
        self._activity_close_cb = None
        self._text_chan = text_chan
        self._conn = conn
        self._logger = logging.getLogger(
            'chat-activity.TextChannelWrapper')
        self._signal_matches = []
        m = self._text_chan[CHANNEL_INTERFACE].connect_to_signal(
            'Closed', self._closed_cb)
        self._signal_matches.append(m)

    def post(self, text):
        if text is not None:
            self.send(text)

    def send(self, text):
        '''Send text over the Telepathy text channel.'''
        # XXX Implement CHANNEL_TEXT_MESSAGE_TYPE_ACTION
        logging.debug('sending %s' % text)

        text = text.replace('/', SLASH)

        if self._text_chan is not None:
            self._text_chan[CHANNEL_TYPE_TEXT].Send(
                CHANNEL_TEXT_MESSAGE_TYPE_NORMAL, text)

    def close(self):
        '''Close the text channel.'''
        self._logger.debug('Closing text channel')
        try:
            self._text_chan[CHANNEL_INTERFACE].Close()
        except Exception:
            self._logger.debug('Channel disappeared!')
            self._closed_cb()

    def _closed_cb(self):
        '''Clean up text channel.'''
        self._logger.debug('Text channel closed.')
        for match in self._signal_matches:
            match.remove()
        self._signal_matches = []
        self._text_chan = None
        if self._activity_close_cb is not None:
            self._activity_close_cb()

    def set_received_callback(self, callback):
        '''Connect the function callback to the signal.

        callback -- callback function taking buddy and text args
        '''
        if self._text_chan is None:
            return
        self._activity_cb = callback
        m = self._text_chan[CHANNEL_TYPE_TEXT].connect_to_signal(
            'Received', self._received_cb)
        self._signal_matches.append(m)

    def handle_pending_messages(self):
        '''Get pending messages and show them as received.'''
        for identity, timestamp, sender, type_, flags, text in \
            self._text_chan[
                CHANNEL_TYPE_TEXT].ListPendingMessages(False):
            self._received_cb(identity, timestamp, sender, type_, flags, text)

    def _received_cb(self, identity, timestamp, sender, type_, flags, text):
        '''Handle received text from the text channel.

        Converts sender to a Buddy.
        Calls self._activity_cb which is a callback to the activity.
        '''
        logging.debug('received_cb %r %s' % (type_, text))
        if type_ != 0:
            # Exclude any auxiliary messages
            return

        text = text.replace(SLASH, '/')

        if self._activity_cb:
            try:
                self._text_chan[CHANNEL_INTERFACE_GROUP]
            except Exception:
                # One to one XMPP chat
                nick = self._conn[
                    CONN_INTERFACE_ALIASING].RequestAliases([sender])[0]
                buddy = {'nick': nick, 'color': '#000000,#808080'}
            else:
                # Normal sugar MUC chat
                # XXX: cache these
                buddy = self._get_buddy(sender)
            self._activity_cb(buddy, text)
            self._text_chan[
                CHANNEL_TYPE_TEXT].AcknowledgePendingMessages([identity])
        else:
            self._logger.debug('Throwing received message on the floor'
                               ' since there is no callback connected. See'
                               ' set_received_callback')

    def set_closed_callback(self, callback):
        '''Connect a callback for when the text channel is closed.

        callback -- callback function taking no args

        '''
        self._activity_close_cb = callback

    def _get_buddy(self, cs_handle):
        '''Get a Buddy from a (possibly channel-specific) handle.'''
        # XXX This will be made redundant once Presence Service
        # provides buddy resolution
        # Get the Presence Service
        pservice = presenceservice.get_instance()
        # Get the Telepathy Connection
        tp_name, tp_path = pservice.get_preferred_connection()
        obj = dbus.Bus().get_object(tp_name, tp_path)
        conn = dbus.Interface(obj, CONN_INTERFACE)
        group = self._text_chan[CHANNEL_INTERFACE_GROUP]
        my_csh = group.GetSelfHandle()
        if my_csh == cs_handle:
            handle = conn.GetSelfHandle()
        elif group.GetGroupFlags() & \
                CHANNEL_GROUP_FLAG_CHANNEL_SPECIFIC_HANDLES:
            handle = group.GetHandleOwners([cs_handle])[0]
        else:
            handle = cs_handle

            # XXX: deal with failure to get the handle owner
            assert handle != 0

        return pservice.get_buddy_by_telepathy_handle(
            tp_name, tp_path, handle)


class ToolWidget(Gtk.ToolItem):

    def __init__(self, **kwargs):
        self._widget = None
        self._label = None
        self._label_text = None
        self._box = Gtk.HBox(False, style.DEFAULT_SPACING)

        GObject.GObject.__init__(self, **kwargs)
        self.props.border_width = style.DEFAULT_PADDING

        self._box.show()
        self.add(self._box)

        if self.label is None:
            self.label = Gtk.Label()

    def get_label_text(self):
        return self._label_text

    def set_label_text(self, value):
        self._label_text = value
        if self.label is not None and value:
            self.label.set_text(self._label_text)

    label_text = GObject.Property(getter=get_label_text, setter=set_label_text)

    def get_label(self):
        return self._label

    def set_label(self, label):
        if self._label is not None:
            self._box.remove(self._label)
        self._label = label
        self._box.pack_start(label, False, True, 0)
        self._box.reorder_child(label, 0)
        label.show()
        self.set_label_text(self._label_text)

    label = GObject.Property(getter=get_label, setter=set_label)

    def get_widget(self):
        return self._widget

    def set_widget(self, widget):
        if self._widget is not None:
            self._box.remove(self._widget)
        self._widget = widget
        self._box.pack_end(widget, True, True, 0)
        widget.show()

    widget = GObject.Property(getter=get_widget, setter=set_widget)
