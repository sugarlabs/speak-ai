# HablarConSara.activity
# Modernized version for Sugar Labs contribution
# Improvements: error handling, logging, safer memory handling

import time
import logging
from gettext import gettext as _

from gi.repository import Gdk, GLib, Gio
from sugar3 import profile

from aiml.Kernel import Kernel
import voice

logger = logging.getLogger('speak')

# -------------------------------
# Bot Configurations
# -------------------------------
BOTS = {
    _('Spanish'): {
        'name': 'Sara',
        'brain': 'bot/sara.brn',
        'predicates': {
            'nombre_bot': 'Sara',
            'botmaster': 'La comunidad Azucar'
        }
    },
    _('English'): {
        'name': 'Alice',
        'brain': 'bot/alice.brn',
        'predicates': {
            'name': 'Alice',
            'master': 'The Sugar Community'
        }
    }
}

# -------------------------------
# Memory Utilities
# -------------------------------
def get_mem_info(tag):
    """Safely read memory info from /proc/meminfo"""
    try:
        with open('/proc/meminfo') as f:
            meminfo = f.readlines()
        return int([i for i in meminfo if i.startswith(tag)][0].split()[1])
    except Exception as e:
        logger.warning(f"Failed reading memory info: {e}")
        return 0


# Adjust AIML load based on system memory
if get_mem_info('MemTotal:') < 524288:
    mem_free = get_mem_info('MemFree:') + get_mem_info('Cached:')
    if mem_free < 102400:
        BOTS[_('English')]['brain'] = None
    else:
        BOTS[_('English')]['brain'] = 'bot/alisochka.brn'

_kernel = None
_kernel_voice = None

# -------------------------------
# User Utilities
# -------------------------------
def _get_age():
    """Estimate user age from Sugar settings"""
    settings = Gio.Settings('org.sugarlabs.user')
    birth_timestamp = settings.get_int('birth-timestamp')

    if not birth_timestamp:
        return 8

    current_timestamp = time.time()
    age = (current_timestamp - birth_timestamp) / (365 * 24 * 60 * 60)

    if age < 5 or age > 16:
        age = 8
    return int(age)


def get_default_voice():
    """Get valid default voice"""
    default_voice = voice.defaultVoice()
    if default_voice.friendlyname not in BOTS:
        return voice.allVoices()[_('English')]
    return default_voice


# -------------------------------
# Chat Response
# -------------------------------
def respond(text):
    global _kernel
    if _kernel:
        response = _kernel.respond(text)
        if response:
            return response

    return _("Sorry, I can't understand what you are asking about.")


# -------------------------------
# Brain Loader
# -------------------------------
def load(activity, voice, sorry=None):
    """Load AIML brain asynchronously"""
    old_cursor = activity.get_window().get_cursor()
    activity.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))

    def load_brain():
        global _kernel, _kernel_voice

        is_first_session = _kernel is None

        try:
            brain = BOTS.get(voice.friendlyname, BOTS[_('English')])
            brain_name = brain['name']

            logger.debug(f"Loading bot: {brain_name}")

            if voice != _kernel_voice or _kernel is None:
                kernel = Kernel()

                if brain['brain'] is None:
                    warning = _("Low memory. Close other activities and try again.")
                    activity.face.say_notification(warning)
                    return

                kernel.loadBrain(brain['brain'])

                for name, value in brain['predicates'].items():
                    kernel.setBotPredicate(name, value)

                # Cleanup previous kernel
                if _kernel:
                    import gc
                    del _kernel
                    gc.collect()

                _kernel = kernel
                _kernel_voice = voice

        except Exception as e:
            logger.exception("Brain loading failed")
            activity.face.say_notification(_("Failed to load AI brain."))
            return

        finally:
            activity.get_window().set_cursor(old_cursor)

        # First-time initialization
        if is_first_session:
            _kernel.respond(_('my name is %s') % profile.get_nick_name())
            _kernel.respond(_('I am %d years old') % _get_age())

            hello = _("Hello, I'm a robot \"%s\". Ask me anything!") % brain_name
            if sorry:
                hello += ' ' + sorry
            activity.face.say_notification(hello)

        elif sorry:
            activity.face.say_notification(sorry)
        else:
            activity.face.say_notification(_("Hi again!"))

    GLib.idle_add(load_brain)
    return True