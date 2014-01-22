# Sketch - A Python-based interactive drawing program
# Copyright (C) 1997, 1998, 1999, 2001, 2003 by Bernhard Herzog
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307	USA

from math import floor, ceil, hypot
from string import atoi
from types import TupleType
import operator

import pax

from Sketch import config, const, GuideLine, Point
from Sketch.warn import warn, USER
from Sketch.const import CHANGED

from tkext import PyWidget

from Sketch.Lib import units

HORIZONTAL = 0
VERTICAL = 1

tick_lengths = (8, 5, 3, 2)

# (base_unit_factor, (subdiv1, subdiv2,...))
tick_config = {'in': (1.0, (2, 2, 2, 2)),
               'cm': (1.0, (2, 5)),
               'mm': (10.0, (2, 5)),
               'pt': (100.0, (2, 5, 2, 5)),
               #'pt': (72.0, (2, 3, 12)),
               }

class Ruler(PyWidget):

    def __init__(self, master=None, orient = HORIZONTAL, canvas = None, **kw):
	apply(PyWidget.__init__, (self, master), kw)
	self.orient = orient
        self.canvas = canvas
	self.gcs_initialized = 0
	self.gc = None
        self.positions = None
	self.SetRange(0.0, 1.0, force = 1)
        if orient == VERTICAL:
            self.text_type = config.preferences.ruler_text_type
        else:
            self.text_type = 'horizontal'
	font = None
	fontname = config.preferences.ruler_font
	try:
	    font = self.tkwin.LoadQueryFont(fontname)
	except:
	    # NLS
	    warn(USER, 'Could not load font %s for ruler. using defaults.',
		 `fontname`)
            font = self.tkwin.LoadQueryFont('fixed')
	self.font = font
        
        font = None
        if self.text_type == 'rotated':
            fontname = config.preferences.ruler_font_rotated
            try:
                font = self.tkwin.LoadQueryFont(fontname)
            except:
                # NLS
                warn(USER, 'Could not load font %s for ruler. using defaults.',
                     `fontname`)
        self.rotated_font = font
        if not self.rotated_font and self.text_type == 'rotated':
            self.text_type = 'horizontal'
            
	border_width = self.option_get('borderWidth', 'BorderWidth')
	if border_width:
	    self.border_width = atoi(border_width)
	else:
	    self.border_width = 0

        height = self.font.ascent + self.font.descent \
                 + self.border_width + tick_lengths[0]
	if orient == HORIZONTAL:
	    self['height'] = height
	else:
            if self.text_type == 'rotated':
                self['width'] = height
            elif self.text_type == 'vertical':
                self['width'] = self.font.TextWidth('0') + self.border_width \
                        + tick_lengths[0]
            else: # horizontal
                width = self.font.TextWidth('000') + self.border_width \
                        + tick_lengths[0]
                self['width'] = width

	self.bind('<ButtonPress>', self.ButtonPressEvent)
	self.bind('<ButtonRelease>', self.ButtonReleaseEvent)
	self.bind('<Motion>', self.PointerMotionEvent)
        self.button_down = 0
        self.forward_motion = 0

        config.preferences.Subscribe(CHANGED, self.preference_changed)

    def destroy(self):
	PyWidget.destroy(self)
        self.canvas = None

    def MapMethod(self):
	if not self.gcs_initialized:
	    self.init_gcs()
	    self.gcs_initialized = 1

    def init_gcs(self):
	cmap = self.tkwin.colormap()
	foreground = cmap.AllocColor(0, 0, 0)[0]
	attrs = {'foreground': foreground, 'line_width':0}
        if not self.rotated_font:
            if self.font:
                attrs['font'] = self.font
        else:
            attrs['font'] = self.rotated_font
	self.gc = self.tkwin.GetGC(attrs)
        if self.font is None:
            self.font = self.gc.font

    def ResizedMethod(self, width, height):
	self.SetRange(self.start, self.pixel_per_pt, force = 1)

    def SetRange(self, start, pixel_per_pt, force = 0):
	if not force and start==self.start and pixel_per_pt==self.pixel_per_pt:
	    return
	self.start = start
	self.pixel_per_pt = pixel_per_pt
        self.positions = None
	self.UpdateWhenIdle()

    def preference_changed(self, pref, value):
        if pref == 'default_unit':
            self.positions = None # force recomputation
            self.UpdateWhenIdle()

    def get_positions(self):
        if self.positions is not None:
            return self.positions, self.texts

        min_text_step = config.preferences.ruler_min_text_step
        max_text_step = config.preferences.ruler_max_text_step
        min_tick_step = config.preferences.ruler_min_tick_step
	if self.orient == HORIZONTAL:
	    length = self.tkwin.width
            origin = self.start
	else:
	    length = self.tkwin.height
            origin = self.start - length / self.pixel_per_pt
        unit_name = config.preferences.default_unit
        pt_per_unit = units.unit_dict[unit_name]
        units_per_pixel = 1.0 / (pt_per_unit * self.pixel_per_pt)
        factor, subdivisions = tick_config[unit_name]
        subdivisions = (1,) + subdivisions

        factor = factor * pt_per_unit
        start_pos = floor(origin / factor) * factor
        main_tick_step = factor * self.pixel_per_pt
        num_ticks = floor(length / main_tick_step) + 2

        if main_tick_step < min_tick_step:
            tick_step = ceil(min_tick_step / main_tick_step) * main_tick_step
            subdivisions = (1,)
            ticks = 1
        else:
            tick_step = main_tick_step
            ticks = 1
            for depth in range(len(subdivisions)):
                tick_step = tick_step / subdivisions[depth]
                if tick_step < min_tick_step:
                    tick_step = tick_step * subdivisions[depth]
                    depth = depth - 1
                    break
                ticks = ticks * subdivisions[depth]
            subdivisions = subdivisions[:depth + 1]
        
        positions = range(int(num_ticks * ticks))
        positions = map(operator.mul, [tick_step] * len(positions), positions)
        positions = map(operator.add, positions,
                        [(start_pos - origin) * self.pixel_per_pt]
                        * len(positions))

        stride = ticks
        marks = [None] * len(positions)
        for depth in range(len(subdivisions)):
            stride = stride / subdivisions[depth]
            if depth >= len(tick_lengths):
                height = tick_lengths[-1]
            else:
                height = tick_lengths[depth]
            for i in range(0, len(positions), stride):
                if marks[i] is None:
                    marks[i] = (height, int(round(positions[i])))

        texts = []
        if main_tick_step < min_text_step:
            stride = int(ceil(min_text_step / main_tick_step))
            start_index = stride - (floor(origin / factor) % stride)
            start_index = int(start_index * ticks)
            stride = stride * ticks
        else:
            start_index = 0
            stride = ticks
            step = main_tick_step
            for div in subdivisions:
                step = step / div
                if step < min_text_step:
                    break
                stride = stride / div
                if step < max_text_step:
                    break

        for i in range(start_index, len(positions), stride):
            pos = positions[i] * units_per_pixel + origin / pt_per_unit
            pos = round(pos, 3)
            if pos == 0.0:
                # avoid '-0' strings
                pos = 0.0
            texts.append(("%g" % pos, marks[i][-1]))
        self.positions = marks
        self.texts = texts

        return self.positions, self.texts
        

    def RedrawMethod(self, region = None):
	pixmap = self.tkwin.CreatePixmap()
	width = self.tkwin.width
	height = self.tkwin.height
	bd = self.border_width
	self.gc.SetDrawable(pixmap)
	self.tkborder.Fill3DRectangle(pixmap, 0, 0, width, height,
				      bd, pax.TK_RELIEF_RAISED);
	if self.orient == HORIZONTAL:
	    self.draw_ruler_horizontal()
	else:
	    self.draw_ruler_vertical()
	self.gc.SetDrawable(self.tkwin)
	pixmap.CopyArea(self.tkwin, self.gc, 0, 0, width, height, 0, 0)


    def draw_ruler_horizontal(self):
	darkgc = self.tkborder.BorderGC(pax.TK_3D_DARK_GC)
	darkgc.SetDrawable(self.gc.drawable)
	lightgc = self.tkborder.BorderGC(pax.TK_3D_LIGHT_GC)
	lightgc.SetDrawable(self.gc.drawable)
	DrawString = self.gc.DrawString
	DrawDarkLine = darkgc.DrawLine
	DrawLightLine = lightgc.DrawLine
	TextWidth = self.font.TextWidth
	descent = self.font.descent
	height = self.tkwin.height
        
        ticks, texts = self.get_positions()
        for h, pos in ticks:
	    DrawDarkLine(pos, height, pos, height - h)
	    pos = pos + 1
	    DrawLightLine(pos, height, pos, height - h)

        y = height - tick_lengths[0] - descent
        for text, pos in texts:
            if text[0] != '-':
                tw = TextWidth(text)
            else:
                tw = TextWidth(text[1:])
                pos = pos - TextWidth('-')
            DrawString(pos - tw / 2, y, text)

    def draw_ruler_vertical(self):
	darkgc = self.tkborder.BorderGC(pax.TK_3D_DARK_GC)
	darkgc.SetDrawable(self.gc.drawable)
	lightgc = self.tkborder.BorderGC(pax.TK_3D_LIGHT_GC)
	lightgc.SetDrawable(self.gc.drawable)
	DrawString = self.gc.DrawString
	DrawDarkLine = darkgc.DrawLine
	DrawLightLine = lightgc.DrawLine
        descent = self.font.descent
	height = self.tkwin.height
        width = self.tkwin.width
	font_height = self.font.ascent + self.font.descent

        ticks, texts = self.get_positions()
        for h, pos in ticks:
            pos = height - pos
	    DrawDarkLine(width - h, pos, width, pos)
	    pos = pos + 1
	    DrawLightLine(width - h, pos, width, pos)

        if self.text_type == 'rotated':
            TextWidth = self.font.TextWidth
            x = width - self.font.descent - tick_lengths[0]
            for text, pos in texts:
                pos = height - pos
                if text[0] != '-':
                    tw = TextWidth(text)
                else:
                    tw = TextWidth(text[1:])
                    pos = pos + TextWidth('-')
                y = pos + tw / 2
                for c in text:
                    DrawString(x, y, c)
                    y = y - TextWidth(c)
        elif self.text_type == 'vertical':
            x = width - self.font.TextWidth('0') - tick_lengths[0]
            for text, pos in texts:
                pos = height - pos
                #print `text`
                y = pos + self.font.ascent - (len(text) * font_height) / 2
                for c in text:
                    DrawString(x, y, c)
                    y = y + font_height
        else: # horizontal
            TextWidth = self.font.TextWidth 
            dx = width - tick_lengths[0]
            dy = self.font.ascent - font_height / 2
            for text, pos in texts:
                pos = height - pos + dy
                #print `text`
                DrawString(dx - TextWidth(text), pos, text)

    def ButtonPressEvent(self, event):
        if event.num == const.Button1:
            self.button_down = 1
            self.pressevent = event
        
    def ButtonReleaseEvent(self, event):
        if event.num == const.Button1:
            self.button_down = 0

    def PointerMotionEvent(self, event):
        if self.button_down:
            if self.canvas is not None:
                press = self.pressevent
                if hypot(press.x - event.x, press.y - event.y) > 3:
                    guide = GuideLine(Point(0, 0), self.orient == HORIZONTAL)
                    self.canvas.PlaceObject(guide)
                    press.x = press.x_root - self.canvas.winfo_rootx()
                    press.y = press.y_root - self.canvas.winfo_rooty()
                    self.canvas.ButtonPressEvent(press)
                    self.canvas.grab_set()
                    self.button_down = 0

    def SetCanvas(self, canvas):
        self.canvas = canvas
