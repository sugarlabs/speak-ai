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

# This code is a super-stripped down version of the waveform view from Measure

import math
import cairo
from gi.repository import Gtk, GLib
from sugar3.graphics import style


class Mouth(Gtk.DrawingArea):
    def __init__(self, audio, fill_color):
        Gtk.DrawingArea.__init__(self)
        self.set_size_request(-1, style.GRID_CELL_SIZE * 4)

        self.fill_color = fill_color
        self.audio = audio
        self.connect("draw", self.draw_cb)

    def stop(self):
        if self.audio:
            self.audio.disconnect_all()
            self.audio = None


class PeakMouth(Mouth):

    def __init__(self, audio, fill_color):
        super().__init__(audio, fill_color)

        audio.connect_peak(self.__peak_cb)
        audio.connect_idle(self.__idle_cb)

        self.target_volume = 0
        self.display_volume = 0
        self.idle_phase = 0

        # 60 FPS animation timer
        GLib.timeout_add(16, self.__animate)

    # -----------------------------
    # Audio Callbacks
    # -----------------------------
    def __peak_cb(self, me, volume):
        self.target_volume = min(volume, 30000)

    def __idle_cb(self, me):
        self.target_volume = 0

    # -----------------------------
    # Smooth animation loop
    # -----------------------------
    def __animate(self):
        # Smooth interpolation
        self.display_volume += (self.target_volume - self.display_volume) * 0.15

        # Idle breathing
        if self.target_volume == 0:
            self.idle_phase += 0.05
            self.display_volume = 2000 * abs(math.sin(self.idle_phase))

        self.queue_draw()
        return True

    # -----------------------------
    # Drawing
    # -----------------------------
    def draw_cb(self, widget, cr):
        bounds = self.get_allocation()
        cr.set_antialias(cairo.ANTIALIAS_NONE)

        # Background
        cr.set_source_rgba(*self.fill_color.get_rgba())
        cr.rectangle(0, 0, bounds.width, bounds.height)
        cr.fill()

        volume = self.display_volume / 30000.0

        mouthH = volume * bounds.height
        mouthW = volume ** 2 * (bounds.width / 2.0) + bounds.width / 2.0

        cx = bounds.width // 2
        cy = bounds.height // 2

        Lx, Ly = cx - mouthW // 2, cy
        Tx, Ty = cx, cy - mouthH // 2
        Rx, Ry = cx + mouthW // 2, cy
        Bx, By = cx, cy + mouthH // 2

        cr.set_line_width(min(bounds.height / 10.0, 10))

        # Volume-based dynamic color
        red_intensity = min(1.0, volume + 0.2)
        cr.set_source_rgb(red_intensity, 0, 0)

        cr.move_to(Lx, Ly)
        cr.curve_to(Tx, Ty, Tx, Ty, Rx, Ry)
        cr.curve_to(Bx, By, Bx, By, Lx, Ly)
        cr.close_path()
        cr.stroke()

        return False