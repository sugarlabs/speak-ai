# Speak.activity
# A simple front end to the espeak text-to-speech engine on the XO laptop
# http://wiki.laptop.org/go/Speak
#
# Copyright (C) 2008  Joshua Minor
# This file is part of Speak.activity
#
# Parts of Speak.activity are based on code from Measure.activity
# Copyright (C) 2007  Arjun Sarwal - arjun@laptop.org
#
# Speak.activity is free software: you can redistribute it and/or modify
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

import math
from gi.repository import Gtk


class Eye(Gtk.DrawingArea):
    """A GTK drawing area representing an animated eye."""

    def __init__(self, fill_color):
        super().__init__()
        self.connect("draw", self.draw)

        self.x = 0
        self.y = 0
        self.fill_color = fill_color

    def has_padding(self) -> bool:
        return True

    def has_left_center_right(self) -> bool:
        return False

    def look_at(self, x: float, y: float) -> None:
        """Move pupil to look at given screen coordinates."""
        self.x = x
        self.y = y
        self.queue_draw()

    def look_ahead(self) -> None:
        """Reset eye to forward position."""
        self.x = None
        self.y = None
        self.queue_draw()

    def compute_pupil(self):
        """Compute pupil position inside eye bounds."""
        allocation = self.get_allocation()

        if self.x is None or self.y is None:
            parent = self.get_parent()
            if parent:
                pw = parent.get_allocation().width
                cx = allocation.width * (0.6 if allocation.x + allocation.width // 2 < pw // 2 else 0.4)
            else:
                cx = allocation.width / 2

            return cx, allocation.height * 0.6

        eye_x, eye_y = self.translate_coordinates(
            self.get_toplevel(),
            allocation.width // 2,
            allocation.height // 2
        )

        dx = self.x - eye_x
        dy = self.y - eye_y

        if dx or dy:
            angle = math.atan2(dy, dx)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            h = math.hypot(allocation.height * cos_a,
                           allocation.width * sin_a)

            if h != 0:
                x = (allocation.width * allocation.height) * cos_a / h
                y = (allocation.width * allocation.height) * sin_a / h

                ball_dist = allocation.width / 4
                dist = ball_dist * math.hypot(x, y)

                if dist < math.hypot(dx, dy):
                    dx = dist * cos_a
                    dy = dist * sin_a

        return allocation.width // 2 + dx, allocation.height // 2 + dy

    def draw(self, widget, cr):
        """Draw the eye and pupil."""
        bounds = self.get_allocation()

        eye_size = min(bounds.width, bounds.height)
        outline_width = eye_size / 20.0
        pupil_size = eye_size / 10.0

        pupil_x, pupil_y = self.compute_pupil()

        dx = pupil_x - bounds.width / 2.0
        dy = pupil_y - bounds.height / 2.0

        distance = math.hypot(dx, dy)
        limit = eye_size // 2 - outline_width * 2 - pupil_size

        if distance > limit and distance != 0:
            pupil_x = bounds.width // 2 + dx * limit // distance
            pupil_y = bounds.height // 2 + dy * limit // distance

        # Background
        cr.set_source_rgba(*self.fill_color.get_rgba())
        cr.rectangle(0, 0, bounds.width, bounds.height)
        cr.fill()

        # Eyeball
        cr.arc(bounds.width // 2, bounds.height // 2,
               eye_size // 2 - outline_width // 2, 0, 2 * math.pi)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()

        # Outline
        cr.set_line_width(outline_width)
        cr.arc(bounds.width // 2, bounds.height // 2,
               eye_size // 2 - outline_width // 2, 0, 2 * math.pi)
        cr.set_source_rgb(0, 0, 0)
        cr.stroke()

        # Pupil
        cr.arc(pupil_x, pupil_y, pupil_size, 0, 2 * math.pi)
        cr.set_source_rgb(0, 0, 0)
        cr.fill()

        return True