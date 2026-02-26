# Speak.activity
# A simple front end to the espeak text-to-speech engine on the XO laptop
# http://wiki.laptop.org/go/Speak
#
# Copyright (C) 2008 Joshua Minor
# This file is part of Speak.activity
#
# Parts of Speak.activity are based on code from Measure.activity
# Copyright (C) 2007 Arjun Sarwal - arjun@laptop.org
#
# New face features
# Copyright (C) 2014 Walter Bender
# Copyright (C) 2014 Sam Parkinson
#
# Speak.activity is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Speak.activity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Speak.activity. If not, see <http://www.gnu.org/licenses/>.

import math
from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from sugar3.graphics.icon import Icon

_POINT_CIRCUMFERENCE = 5
_LIMIT_VERTICAL = 1
_LIMIT_HORIZONTAL = 2

_STEPS = [
    _("Draw a line from the center to the edge of the left eye's iris"),
    _("Draw a line from the center to the edge of the right eye's iris"),
    _("Draw a line across the mouth")
]


# -----------------------
# Helpers
# -----------------------
def _scale(iw, ih, aw, ah):
    """Scale image while maintaining aspect ratio."""
    factor = min(aw / iw, ah / ih)
    return int(iw * factor), int(ih * factor)


def _distance(a, b):
    """Safe Euclidean distance."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


# -----------------------
# Data Classes
# -----------------------
class Eye:
    def __init__(self, center, radius):
        self.center = center
        self.radius = radius


class Mouth:
    def create(self, y, left_x, right_x, pixbuf):
        self.y = y
        self.x = left_x
        self.w = right_x - left_x
        self.h = pixbuf.get_height() - y
        self.pixbuf = pixbuf.new_subpixbuf(
            int(self.x), int(self.y), int(self.w), int(self.h)
        )
        return self


# -----------------------
# Face Selector UI
# -----------------------
class FaceSelector(Gtk.VBox):

    __gsignals__ = {
        'face-processed': (GObject.SIGNAL_RUN_FIRST, None,
                           [GObject.TYPE_OBJECT,
                            GObject.TYPE_PYOBJECT,
                            GObject.TYPE_PYOBJECT,
                            GObject.TYPE_PYOBJECT]),
        'cancel': (GObject.SIGNAL_RUN_FIRST, None, [])
    }

    def __init__(self, file_):
        super().__init__()
        self._step = 0
        self._step_lines = []

        self._drawing = FaceSelectorDrawing(file_)
        self.pack_start(self._drawing, True, True, 0)

        self._toolbar = Gtk.Toolbar()
        self.pack_start(self._toolbar, False, True, 0)

        self._label = Gtk.Label()
        self._add_widget(self._label)

        # Undo button
        undo_btn = Gtk.Button(label=_("Undo"))
        undo_btn.connect("clicked", self._undo)
        self._add_widget(undo_btn)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda *_: self.emit('cancel'))
        self._add_widget(cancel_btn)

        next_btn = Gtk.Button(label=_("Next"))
        next_btn.set_image(Icon(icon_name='go-next'))
        next_btn.set_image_position(Gtk.PositionType.RIGHT)
        next_btn.connect("clicked", self._next)
        self._add_widget(next_btn)

        self._show_step(0)

    def _add_widget(self, widget):
        t = Gtk.ToolItem()
        t.add(widget)
        widget.show()
        self._toolbar.insert(t, -1)
        t.show()

    def _show_step(self, step):
        self._label.set_text(_STEPS[step])
        self._drawing.clear_line()

    def _undo(self, *_):
        """Undo last selection."""
        if self._step > 0:
            self._step -= 1
            if self._step_lines:
                self._step_lines.pop()
            self._drawing.limit_axis = None
            self._show_step(self._step)

    def _next(self, *_):
        sp, ep = self._drawing.get_line()

        # Safety check
        if not sp or not ep:
            return

        self._step_lines.append((sp, ep))
        self._step += 1

        if self._step == 2:
            self._drawing.limit_axis = _LIMIT_VERTICAL

        if self._step == len(_STEPS):
            self._process_data()
        else:
            self._show_step(self._step)

    def _process_data(self):
        left = self._step_lines[0]
        right = self._step_lines[1]
        mouth = self._step_lines[2]

        left_eye = Eye(left[0], _distance(*left))
        right_eye = Eye(right[0], _distance(*right))

        mouth_y = mouth[0][1]
        mouth_x_left = min(mouth[0][0], mouth[1][0])
        mouth_x_right = max(mouth[0][0], mouth[1][0])

        self.emit(
            'face-processed',
            self._drawing.get_pixbuf(),
            left_eye,
            right_eye,
            Mouth().create(mouth_y, mouth_x_left, mouth_x_right,
                           self._drawing.get_pixbuf())
        )


# -----------------------
# Drawing Area
# -----------------------
class FaceSelectorDrawing(Gtk.DrawingArea):

    def __init__(self, file_):
        super().__init__()
        self.limit_axis = None
        self._start = None
        self._end = None
        self._mouse = None

        self._full_pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_)
        self._pixbuf = None
        self._offset_x = 0
        self._offset_y = 0

        self.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )

        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._move)

    def _draw(self, widget, cr):
        alloc = widget.get_allocation()

        if not self._pixbuf:
            sw, sh = _scale(
                self._full_pixbuf.get_width(),
                self._full_pixbuf.get_height(),
                alloc.width,
                alloc.height
            )
            self._pixbuf = self._full_pixbuf.scale_simple(
                sw, sh, GdkPixbuf.InterpType.BILINEAR
            )
            self._offset_x = (alloc.width - sw) // 2
            self._offset_y = (alloc.height - sh) // 2

        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf,
                                   self._offset_x, self._offset_y)
        cr.paint()

        # Draw line preview
        if self._start and (self._mouse or self._end):
            sx, sy = self._start
            mx, my = self._end if self._end else self._mouse
            cr.set_source_rgb(1, 1, 0)
            cr.set_line_width(1)
            cr.move_to(sx, sy)
            cr.line_to(mx, my)
            cr.stroke()

        return False

    def _press(self, widget, event):
        self._start = (event.x, event.y)
        self._end = None
        self.queue_draw()

    def _release(self, widget, event):
        if not self._start:
            return
        sx, sy = self._start
        self._end = (
            sx if self.limit_axis == _LIMIT_HORIZONTAL else event.x,
            sy if self.limit_axis == _LIMIT_VERTICAL else event.y
        )
        self.queue_draw()

    def _move(self, widget, event):
        if not self._start:
            return
        sx, sy = self._start
        self._mouse = (
            sx if self.limit_axis == _LIMIT_HORIZONTAL else event.x,
            sy if self.limit_axis == _LIMIT_VERTICAL else event.y
        )
        self.queue_draw()

    def get_line(self):
        if not self._start or not self._end:
            return None, None

        return (
            self._start[0] - self._offset_x,
            self._start[1] - self._offset_y
        ), (
            self._end[0] - self._offset_x,
            self._end[1] - self._offset_y
        )

    def clear_line(self):
        self._start = None
        self._end = None
        self._mouse = None
        self.queue_draw()

    def get_pixbuf(self):
        return self._pixbuf