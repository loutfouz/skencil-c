# Sketch - A Python-based interactive drawing program
# Copyright (C) 1996, 1997, 1998, 1999, 2000, 2003 by Bernhard Herzog
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

#
# Classes:
#
# SketchDocument
# EditDocument(SketchDocument)
#
# The document class represents a complete Sketch drawing. Each drawing
# consists of one or more Layers, which in turn consist of zero of more
# graphics objects. Graphics objects can be primitives like rectangles
# or curves or composite objects like groups which consist of graphics
# objects themselves. Objects may be arbitrarily nested.
#
# The distinction between SketchDocument and EditDocument has only
# historical reasons...
#
from Sketch import const
from math import  sin, cos, atan, floor
from Sketch import StandardColors

from types import ListType, IntType, StringType, TupleType
from string import join

from Sketch.warn import pdebug, warn, warn_tb, USER, INTERNAL
from Sketch import SketchInternalError


from Sketch import config, _
from Sketch.connector import Issue, RemovePublisher, Connect, Disconnect, \
     QueueingPublisher, Connector
from Sketch.undodict import UndoDict

from Sketch import Rect, Point, UnionRects, InfinityRect, Trafo
from Sketch import UndoRedo, Undo, CreateListUndo, NullUndo, UndoAfter

import color, selinfo, pagelayout

from base import Protocols
from layer import Layer, GuideLayer, GridLayer
from group import Group
from bezier import CombineBeziers
from properties import EmptyProperties
from pattern import SolidPattern
import guide
from selection import SizeSelection, EditSelection, TrafoSelection

from Sketch.const import STYLE, SELECTION, EDITED, MODE, UNDO, REDRAW, LAYOUT
from Sketch.const import LAYER, LAYER_ORDER, LAYER_ACTIVE, GUIDE_LINES, GRID
from Sketch.const import SelectSet, SelectAdd,SelectSubtract,SelectSubobjects,\
     SelectDrag, SelectGuide, Button1Mask
from Sketch.const import SCRIPT_OBJECT, SCRIPT_OBJECTLIST, SCRIPT_GET

#
from text import CanCreatePathText, CreatePathText

#added by shumon
from Sketch.Graphics.ellipse import Ellipse
from Sketch.Graphics.rectangle import Rectangle
from Sketch.Graphics.bezier import PolyBezier
from clone import Clone
from Sketch.Graphics.arrow import Arrow
from Sketch import CreateRGBColor
import os
import time
import math

# SketchDocument is derived from Protocols for the benefit of the loader
# classes

    
class SketchDocument(Protocols):

    can_be_empty = 1

    script_access = {}
    
    state1 = 336
    state2 = 340
    
    uname = None #operating system
    tiled_clones_dialog = None
    
    
    
    def set_cloning_modifier_keys(self):
        u = os.uname()
        if u[0] == 'Darwin':
            self.state1 = 272 #Alt/Apple Button
            self.state2 = 276 #CTRL button
            self.uname = u[0][:]
            print "Running Skencil on",self.uname

    def CreateTiledClonesDialog(self):
        if self.tiled_clones_dialog != None:
            self.DestroyTiledClonesDialog()
        
        self.tiled_clones_dialog = TiledClones(self)
        self.tiled_clones_dialog.build_dialog()
        string = 'tiled_clones_dialog_opens'
        self.log(string)
        self.main_window.total_tiled_clones_dialog_openings += 1
        
    def DestroyTiledClonesDialog(self):

        if self.tiled_clones_dialog and self.tiled_clones_dialog.master != None:
            self.tiled_clones_dialog.close_window()
            del self.tiled_clones_dialog
            self.tiled_clones_dialog = None
            
        
    def __init__(self, create_layer = 0):
        #added by shumon
        del self.clones[:]
        self.set_cloning_modifier_keys()
        #-----------------------------------------------------
        self.snap_grid = GridLayer()
        self.snap_grid.SetDocument(self)
        self.guide_layer = GuideLayer(_("Guide Lines"))
        self.guide_layer.SetDocument(self)
        if create_layer:
            # a new empty document
            self.active_layer = Layer(_("Layer 1"))
            self.active_layer.SetDocument(self)
            self.layers = [self.active_layer, self.guide_layer,
                   self.snap_grid]
        else:
            # we're being created by the load module
            self.active_layer = None
            self.layers = []
  

 

    def __del__(self):
	if __debug__:
	    pdebug('__del__', '__del__', self.meta.filename)

    def __getitem__(self, idx):
	if type(idx) == IntType:
	    return self.layers[idx]
	elif type(idx) == TupleType:
	    if len(idx) > 1:
		return self.layers[idx[0]][idx[1:]]
	    elif len(idx) == 1:
		return self.layers[idx[0]]
	raise ValueError, 'invalid index %s' % `idx`

    def AppendLayer(self, layer_name = None, *args, **kw_args):
	try:
	    old_layers = self.layers[:]
	    if layer_name is None:
		layer_name = _("Layer %d") % (len(self.layers) + 1)
	    else:
		layer_name = str(layer_name)
	    layer = apply(Layer, (layer_name,) + args, kw_args)
	    layer.SetDocument(self)
	    self.layers.append(layer)
	    if not self.active_layer:
		self.active_layer = layer
	    return layer
	except:
	    self.layers[:] = old_layers
	    raise
    script_access['AppendLayer'] = SCRIPT_OBJECT

    def BoundingRect(self, visible = 1, printable = 0):
	rects = []
	for layer in self.layers:
	    if ((visible and layer.Visible())
		or (printable and layer.Printable())):
		rect = layer.bounding_rect
		if rect and rect != InfinityRect:
		    rects.append(rect)
	if rects:
	    return reduce(UnionRects, rects)
	return None
    script_access['BoundingRect'] = SCRIPT_GET

    def augment_sel_info(self, info, layeridx):
	if type(layeridx) != IntType:
	    layeridx = self.layers.index(layeridx)
	return selinfo.prepend_idx(layeridx, info)

    def insert(self, object, at = None, layer = None):
	undo_info = None
	try:
	    if layer is None:
		layer = self.active_layer
	    elif type(layer) == IntType:
		layer = self.layers[layer]
	    if layer is None or layer.Locked():
		raise SketchInternalError('Layer %s is locked' % layer)
	    if type(object) == ListType:
		for obj in object:
		    obj.SetDocument(self)
	    else:
		object.SetDocument(self)
	    sel_info, undo_info = layer.Insert(object, at)
	    sel_info = self.augment_sel_info(sel_info, layer)
	    return (sel_info, undo_info)
	except:
	    if undo_info is not None:
		Undo(undo_info)
	    raise

    def selection_from_point(self, p, hitrect, device, path = None):
	# iterate top down (i.e. backwards) through the list of layers
	if path:
	    path_layer = path[0]
	    path = path[1:]
	else:
	    path_layer = -1
	for idx in range(len(self.layers) - 1, -1, -1):
	    if idx == path_layer:
		info = self.layers[idx].SelectSubobject(p, hitrect, device,
							path)
	    else:
		info = self.layers[idx].SelectSubobject(p, hitrect, device)
	    if info:
		return self.augment_sel_info(info, idx)
	else:
	    return None

    def selection_from_rect(self, rect):
	info = []
	for layer in self.layers:
	    info = info + self.augment_sel_info(layer.SelectRect(rect), layer)
	return info

    def Draw(self, device, rect = None):
	for layer in self.layers:
	    layer.Draw(device, rect)

    def Grid(self):
	return self.snap_grid

    def SnapToGrid(self, p):
	return self.snap_grid.Snap(p)

    def SnapToGuide(self, p, maxdist):
	return self.guide_layer.Snap(p) #, maxdist)

    def DocumentInfo(self):
	info = []
	info.append('%d layers' % len(self.layers))
	for idx in range(len(self.layers)):
	    layer = self.layers[idx]
	    info.append('%d: %s,\t%d objects' % (idx + 1, layer.name,
						 len(layer.objects)))
	return join(info, '\n')

    def SaveToFile(self, file):
	file.BeginDocument()
	self.page_layout.SaveToFile(file)
	self.write_styles(file)
	for layer in self.layers:
	    layer.SaveToFile(file)
	file.EndDocument()

    def load_AppendObject(self, layer):
	self.layers.append(layer)

    def load_Done(self):
	pass

    def load_Completed(self):
	if not self.layers:
	    self.layers = [Layer(_("Layer 1"))]
	if self.active_layer is None:
	    for layer in self.layers:
		if layer.CanSelect():
		    self.active_layer = layer
		    break
	add_guide_layer = add_grid_layer = 1
	for layer in self.layers:
	    layer.SetDocument(self)
	    if isinstance(layer, GuideLayer):
		self.guide_layer = layer
		add_guide_layer = 0
	    if isinstance(layer, GridLayer):
		self.snap_grid = layer
		add_grid_layer = 0
	if add_guide_layer:
	    self.layers.append(self.guide_layer)
	if add_grid_layer:
	    self.layers.append(self.snap_grid)


#
#	Class MetaInfo
#
#	Each document has an instance of this class as the variable
#	meta. The application object uses this variable to store various
#	data about the document, such as the name of the file it was
#	read from, the file type, etc. See skapp.py
#
class MetaInfo:
    pass

class AbortTransactionError(SketchInternalError):
    pass

SelectionMode = 0
EditMode = 1

class EditDocument(SketchDocument, QueueingPublisher):

    drag_mask = Button1Mask # canvas sometimes has the doc as current
			    # object
    script_access = SketchDocument.script_access.copy()

    main_window = None #is set in main_window (added by shumon)

    
    
    
    
    #this function is called from main_window now (added shumon June 4, 2009 for experiment
    first_time_logging = True
    def log(self,string):
        if self.main_window != None and self.main_window.log_file != None:
            current_time =  time.time()
            elapsed_time = current_time - self.main_window.start_time
            
            
            participant = self.main_window.application.participant
            f1 = self.main_window.application.f1
            f2 = self.main_window.application.f2
            f3 = self.main_window.application.f3
            f4 = self.main_window.application.f4                   
            
            self.main_window.log_file.write(str(participant)+','+str(f1)+','+str(f2)+','+str(f3)+','+str(f4)+','+str(elapsed_time)+','+str(current_time)+','+ string +'\n')
            
            #don't count the last time for 'tiled_clones_dialog_closed'
            if string == 'tiled_clones_dialog_closed' or string == 'document_opened':
                print "not logging tiled_clones_dialog_closed or document_opened"
            else:
                self.main_window.last_user_action_time = elapsed_time #for statistics
            if self.first_time_logging:
                self.main_window.first_user_action_time = elapsed_time
                self.first_time_logging = False

        
            
    def __init__(self, create_layer = 0):
        SketchDocument.__init__(self, create_layer)
        QueueingPublisher.__init__(self)
        self.selection = SizeSelection()
        self.__init_undo()
        self.was_dragged = 0
        self.meta = MetaInfo()        
        self.hit_cache = None
        self.connector = Connector()
        self.init_transaction()
        self.init_clear()
        self.init_styles()
        self.init_after_handler()
        self.init_layout()

                



    def Destroy(self):
    	self.undo = None
    	self.destroy_styles()
    	RemovePublisher(self)
    	for layer in self.layers:
    	    layer.Destroy()
    	self.layers = []
    	self.active_layer = None
    	self.guide_layer = None
    	self.snap_grid = None
    	# make self.connector empty connector to remove circular refs
    	# and to allow object to call document.connector.RemovePublisher
    	# in their __del__ methods
    	self.connector = Connector()
    	self.selection = None
    	self.transaction_undo = []
    	self.transaction_sel = []
        


    def queue_layer(self, *args):
	if self.transaction:
	    apply(self.queue_message, (LAYER,) + args)
	    return (self.queue_layer, args)
	else:
	    apply(self.issue, (LAYER,) + args)

    def queue_selection(self):
	self.queue_message(SELECTION)

    def queue_edited(self):
	# An EDITED message should probably indicate the type of edit,
	# i.e. whether properties changed, the geometry of objects
	# changed, etc.; hence the additional string argument which may
	# hold this information in the future
	self.queue_message(EDITED, '')
	return (self.queue_edited,)

    def Subscribe(self, channel, func, *args):
	Connect(self, channel, func, args)

    def Unsubscribe(self, channel, func, *args):
	Disconnect(self, channel, func, args)

    def init_after_handler(self):
	self.after_handlers = []

    def AddAfterHandler(self, handler, args = (), depth = 0):
	handler = (depth, handler, args)
	try:
	    self.after_handlers.remove(handler)
	except ValueError:
	    pass
	self.after_handlers.append(handler)

    def call_after_handlers(self):
	if not self.after_handlers:
	    return 0

	while self.after_handlers:
            handlers = self.after_handlers

	    handlers.sort()
	    handlers.reverse()
	    depth = handlers[0][0]

	    count = 0
	    for d, handler, args in handlers:
		if d == depth:
		    count = count + 1
		else:
		    break
	    self.after_handlers = handlers[count:]
	    handlers = handlers[:count]

	    for d, handler, args in handlers:
		try:
		    apply(handler, args)
		except:
		    warn_tb(INTERNAL, "In after handler `%s'%s", handler, args)

	return 1

    def init_clear(self):
	self.clear_rects = []
	self.clear_all = 0

    reset_clear = init_clear

    def AddClearRect(self, rect):
	self.clear_rects.append(rect)
	return (self.AddClearRect, rect)

    def view_redraw_all(self):
	self.clear_all = 1
	return (self.view_redraw_all,)

    def issue_redraw(self):
	try:
	    if self.clear_all:
		Issue(self, REDRAW, 1)
	    else:
		Issue(self, REDRAW, 0, self.clear_rects)
	finally:
	    self.clear_rects = []
	    self.clear_all = 0

    def init_transaction(self):
	self.reset_transaction()

    def reset_transaction(self):
	self.transaction = 0
	self.transaction_name = ''
	self.transaction_sel = []
	self.transaction_undo = []
	self.transaction_sel_ignore = 0
	self.transaction_clear = None
	self.transaction_aborted = 0
	self.transaction_cleanup = []

    def cleanup_transaction(self):
	for handler, args in self.transaction_cleanup:
	    try:
		apply(handler, args)
	    except:
		warn_tb(INTERNAL, "in cleanup handler %s%s", handler, `args`)
	self.transaction_cleanup = []

    def add_cleanup_handler(self, handler, *args):
	handler = (handler, args)
	try:
	    self.transaction_cleanup.remove(handler)
	except ValueError:
	    pass
	self.transaction_cleanup.append(handler)

    def begin_transaction(self, name = '', no_selection = 0, clear_selection_rect = 1):
	if self.transaction_aborted:
	    raise AbortTransactionError
	if self.transaction == 0:
	    if not no_selection:
		selinfo = self.selection.GetInfo()[:]
		if selinfo != self.transaction_sel:
		    self.transaction_sel = selinfo
		self.transaction_sel_mode = self.selection.__class__
	    self.transaction_sel_ignore = no_selection
	    self.transaction_name = name
	    self.transaction_undo = []
	    if clear_selection_rect:
		if self.selection:
		    self.transaction_clear = self.selection.bounding_rect
	    else:
		self.transaction_clear = None
	elif not self.transaction_name:
	    self.transaction_name = name
	self.transaction = self.transaction + 1
        string = 'began_transac='+','+self.transaction_name
        #print string,self.varied_dupe_offset 
        if self.transaction_name == '':
            self.varied_dupe_offset = None
            '''self.old_sel_obj = None
            self.new_sel_obj = None'''           
        self.log(string)
        

    def end_transaction(self, issue = (), queue_edited = 0):
	self.transaction = self.transaction - 1
        string = 'ended_transac='+','+self.transaction_name
        self.log(string)
	if self.transaction_aborted:
	    # end an aborted transaction
	    if self.transaction == 0:
		# undo the changes already done...
		undo = self.transaction_undo
		undo.reverse()
		map(Undo, undo)
		self.cleanup_transaction()
		self.reset_transaction()
		self.reset_clear()
	else:
	    # a normal transaction
	    if type(issue) == StringType:
		self.queue_message(issue)
	    else:
		for channel in issue:
		    self.queue_message(channel)
	    if self.transaction == 0:
		# the outermost end_transaction
		# increase transaction flag temporarily because some
		# after handlers might call public methods that are
		# themselves transactions...
		self.transaction = 1
		if self.call_after_handlers():
		    self.selection.ResetRectangle()
		self.transaction = 0
		undo = CreateListUndo(self.transaction_undo)
		if undo is not NullUndo:
		    undo = [undo]
		    if self.transaction_clear is not None:
			undo.append(self.AddClearRect(self.transaction_clear))
			if self.selection:
			    self.selection.ResetRectangle()
			    rect = self.selection.bounding_rect
			    undo.append(self.AddClearRect(rect))
		    if queue_edited:
			undo.append(self.queue_edited())
		    undo = CreateListUndo(undo)
		    if self.transaction_sel_ignore:
			self.__real_add_undo(self.transaction_name, undo)
		    else:
			self.__real_add_undo(self.transaction_name, undo,
					     self.transaction_sel,
					     self.transaction_sel_mode)
		self.flush_message_queue()
		self.issue_redraw()
		self.cleanup_transaction()
		self.reset_transaction()
		self.reset_clear()
	    elif self.transaction < 0:
		raise SketchInternalError('transaction < 0')
    

    def abort_transaction(self):
    	self.transaction_aborted = 1
    	warn_tb(INTERNAL, "in transaction `%s'" % self.transaction_name)
        string = 'abortedtransaction_name='+self.transaction_name
        self.log(string)

    	raise AbortTransactionError

    # public versions of the transaction methods
    BeginTransaction = begin_transaction
    AbortTransaction = abort_transaction

    def EndTransaction(self):
	self.end_transaction(queue_edited = 1)

    def Insert(self, object, undo_text = _("Create Object")):
	if isinstance(object, guide.GuideLine):
	    self.add_guide_line(object)
	else:
	    self.begin_transaction(undo_text, clear_selection_rect = 0)
	    try:
		try:
		    object.SetDocument(self)
		    selected, undo = self.insert(object)
		    self.add_undo(undo)
		    self.add_undo(self.AddClearRect(object.bounding_rect))
		    self.__set_selection(selected, SelectSet)
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction(queue_edited = 1)

    def SelectPoint(self, p, device, type = SelectSet):
	# find object at point, and modify the current selection
	# according to type
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		if type == SelectSubobjects:
		    path = self.selection.GetPath()
		else:
		    path = ()
		rect = device.HitRectAroundPoint(p)
		if self.hit_cache:
		    cp, cdevice, hit = self.hit_cache
		    self.hit_cache = None
		    if p is cp and device is cdevice:
			selected = hit
		    else:
			selected = self.selection_from_point(p, rect, device,
							     path)
		else:
		    selected = self.selection_from_point(p, rect, device, path)
		if type == SelectGuide:
                    if selected and selected[-1].is_GuideLine:
                        return selected[-1]
		    return None
		elif selected:
		    path, object = selected
		    if self.layers[path[0]] is self.guide_layer:
			if object.is_GuideLine:
			    # guide lines cannot be selected in the
			    # ordinary way, but other objects on the
			    # guide layer can.
			    selected = None
		self.__set_selection(selected, type)

                if self.IsEditMode():
                    object = self.CurrentObject()
                    if object is not None and object.is_Text:
                        self.SelectPointPart(p, device, SelectSet)

	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
	return selected

    def SelectRect(self, rect, mode = SelectSet):
	# Find all objects contained in rect and modify the current
	# selection according to mode
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.hit_cache = None
		selected = self.selection_from_rect(rect)
		self.__set_selection(selected, mode)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
	return selected

    def SelectRectPart(self, rect, mode = SelectSet):
	# Select the part of the CSO that lies in rect. Currently this
	# works only in edit mode. For a PolyBezier this means that all
	# nodes within rect are selected.
	if not self.IsEditMode():
	    raise SketchInternalError('SelectRectPart requires edit mode')
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.hit_cache = None
		self.selection.SelectRect(rect, mode)
		self.queue_selection()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SelectPointPart(self, p, device, mode = SelectSet):
	# Select the part of the current object under the point p.
	# Like SelectRectPart this only works in edit mode.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
                self.hit_cache = None
                rect = device.HitRectAroundPoint(p)
                self.selection.SelectPoint(p, rect, device, mode)
		if mode != SelectDrag:
		    self.queue_selection()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SelectHandle(self, handle, mode = SelectSet):
	# Select the handle indicated by handle. This only works in edit
	# mode.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.hit_cache = None
		self.selection.SelectHandle(handle, mode)
		if mode != SelectDrag:
		    self.queue_selection()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SelectAll(self):
	# Select all objects that can currently be selected.
	# XXX should the objects in the guide layer also be selected by
	# this method? (currently they are)
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		sel_info = []
		for layer_idx in range(len(self.layers)):
		    sel = self.layers[layer_idx].SelectAll()
		    if sel:
			sel = self.augment_sel_info(sel, layer_idx)
			sel_info = sel_info + sel
		self.__set_selection(sel_info, SelectSet)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectAll'] = SCRIPT_GET

    def SelectNone(self):
	# Deselect all objects.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.__set_selection(None, SelectSet)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectNone'] = SCRIPT_GET

    def SelectObject(self, objects, mode = SelectSet):
	# Select the objects defined by OBJECTS. OBJECTS may be a single
	# GraphicsObject or a list of such objects. Modify the current
	# selection according to MODE.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		if type(objects) != ListType:
		    objects = [objects]
		selinfo = []
		for object in objects:
		    selinfo.append(object.SelectionInfo())
                if selinfo:
                    self.__set_selection(selinfo, mode)
                else:
                    self.__set_selection(None, SelectSet)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    #script_access['SelectObject'] = SCRIPT_GET


    def select_first_in_layer(self, idx = 0):
	for layer in self.layers[idx:]:
	    if layer.CanSelect() and not layer.is_SpecialLayer:
		object = layer.SelectFirstChild()
		if object is not None:
		    return object

    def SelectNextObject(self):
	# If exactly one object is selected select its next higher
	# sibling. If there is no next sibling and its parent is a
	# layer, select the first object in the next higher layer that
	# allows selections.
	#
	# If more than one object is currently selected, deselect all
	# but the the highest of them.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		info = self.selection.GetInfo()
		if len(info) > 1:
		    self.__set_selection(info[-1], SelectSet)
		elif info:
		    path, object = info[0]
		    parent = object.parent
		    object = parent.SelectNextChild(object, path[-1])
		    if object is None and parent.is_Layer:
			idx = self.layers.index(parent)
			object = self.select_first_in_layer(idx + 1)
		    if object is not None:
			self.SelectObject(object)
		else:
		    object = self.select_first_in_layer()
		    if object is not None:
			self.SelectObject(object)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectNextObject'] = SCRIPT_GET

    def select_last_in_layer(self, idx):
	if idx < 0:
	    return
	layers = self.layers[:idx + 1]
	layers.reverse()
	for layer in layers:
	    if layer.CanSelect() and not layer.is_SpecialLayer:
		object = layer.SelectLastChild()
		if object is not None:
		    return object

    def SelectPreviousObject(self):
	# If exactly one object is selected select its next lower
	# sibling. If there is no lower sibling and its parent is a
	# layer, select the last object in the next lower layer that
	# allows selections.
	#
	# If more than one object is currently selected, deselect all
	# but the the lowest of them.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		info = self.selection.GetInfo()
		if len(info) > 1:
		    self.__set_selection(info[0], SelectSet)
		elif info:
		    path, object = info[0]
		    parent = object.parent
		    object = parent.SelectPreviousChild(object, path[-1])
		    if object is None and parent.is_Layer:
			idx = self.layers.index(parent)
			object = self.select_last_in_layer(idx - 1)
		    if object is not None:
			self.SelectObject(object)
		else:
		    object = self.select_last_in_layer(len(self.layers))
		    if object is not None:
			self.SelectObject(object)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectPreviousObject'] = SCRIPT_GET

    def SelectFirstChild(self):
	# If exactly one object is selected and this object is a
	# compound object, select its first (lowest) child. The first
	# child is the object returned by the compound object's method
	# SelectFirstChild. If that method returns none, do nothing.
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		objects = self.selection.GetObjects()
		if len(objects) == 1:
		    object = objects[0]
		    if object.is_Compound:
			object = object.SelectFirstChild()
			if object is not None:
			    self.SelectObject(object)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectFirstChild'] = SCRIPT_GET

    def SelectParent(self):
	# Select the parent of the currently selected object(s).
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		if len(self.selection) > 1:
		    path = selinfo.common_prefix(self.selection.GetInfo())
		    if len(path) > 1:
			object = self[path]
			self.SelectObject(object)
		elif len(self.selection) == 1:
		    object = self.selection.GetObjects()[0].parent
		    if not object.is_Layer:
			self.SelectObject(object)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
    script_access['SelectParent'] = SCRIPT_GET

    def DeselectObject(self, object):
	# Deselect the object OBJECT.
	# XXX: for large selections this can be very slow.
	selected = self.selection.GetObjects()
	try:
	    index = selected.index(object)
	except ValueError:
	    return
	info = self.selection.GetInfo()
	del info[index]
	self.__set_selection(info, SelectSet)

    #
    #    Duplicate
    #
    varied_dupe_offset = None #added by shumon Nov 13, 2009
    old_sel_obj = None
    new_sel_obj = None
    def __get_new_dupe_offset(self):
        if self.transaction_name == _("Move Objects"):
            if self.new_sel_obj is not None and self.old_sel_obj is not None:
                dx = self.new_sel_obj.bounding_rect[0]-self.old_sel_obj.bounding_rect[0]        
                dy = self.new_sel_obj.bounding_rect[1]-self.old_sel_obj.bounding_rect[1]  
                self.varied_dupe_offset = Point(dx,dy)
                print "offset=",self.varied_dupe_offset
                
    def DuplicateSelected(self, offset = None):
        technique = self.main_window.application.technique
        offset = self.varied_dupe_offset
        if technique == _("e") or technique == None: #or self.main_window.application.session == _("q"):
            if self.varied_dupe_offset is None:
                offset = Point(config.preferences.duplicate_offset)
                print "objs:",self.new_sel_obj,self.old_sel_obj
                '''import random
                col = CreateRGBColor(random.random(),random.random(),random.random())
                self.canvas.fill_solid(col)'''
                
            self.__call_layer_method_sel(_("Duplicate"), 'DuplicateObjects',
                             offset)
        else:
            self.main_window.reopen_log_file()
                    
    def __set_selection(self, selected, type):
    	# Modify the current selection. SELECTED is a list of selection
    	# info describing the new selection, TYPE indicates how the
    	# current selection is modified:
    	#
    	# type			Meaning
    	# SelectSet		Replace the old selection by the new one
    	# SelectSubtract	Subtract the new selection from the old one
    	# SelectAdd		Add the new selection to the old one.
    	# SelectSubobjects	like SelectSet here

        self.old_sel_obj = self.CurrentObject()
        objects = self.selection.GetObjects()
        if len(objects) > 1:
             self.old_sel_obj = self.selection.GetObjects()[0]
        changed = 0
    	if type == SelectAdd:
    	    if selected:
    		changed = self.selection.Add(selected)
    	elif type == SelectSubtract:
    	    if selected:
    		changed = self.selection.Subtract(selected)
    	elif type == SelectGuide:
    	    if selected:
    		pass
    	else:
    	    # type is SelectSet or SelectSubobjects
    	    # set the selection. make a size selection if necessary
    	    if self.selection.__class__ == TrafoSelection:
    		self.selection = SizeSelection()
    		changed = 1
    	    changed = self.selection.SetSelection(selected) or changed
    	if changed:
    	    self.queue_selection()
        #added by shumon November 13, 2009 for Enhanced Repeated Paste
        self.new_sel_obj = self.CurrentObject()
        objects = self.selection.GetObjects()
        if len(objects) > 1:
             self.new_sel_obj = self.selection.GetObjects()[0]
            

    def SetMode(self, mode):
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		if mode == SelectionMode:
		    self.selection = SizeSelection(self.selection)
		else:
		    self.selection = EditSelection(self.selection)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction(issue = (SELECTION, MODE))

    def Mode(self):
	if self.selection.__class__ == EditSelection:
	    return EditMode
	return SelectionMode
    script_access['Mode'] = SCRIPT_GET

    def IsSelectionMode(self):
	return self.Mode() == SelectionMode
    script_access['IsSelectionMode'] = SCRIPT_GET

    def IsEditMode(self):
	return self.Mode() == EditMode
    script_access['IsEditMode'] = SCRIPT_GET


    def SelectionHit(self, p, device, test_all = 1):
	# Return true, if the point P hits the currently selected
	# objects.
	#
	# If test_all is true (the default), find the object that would
	# be selected by SelectPoint and return true if it or one of its
	# ancestors is contained in the current selection and false
	# otherwise.
	#
	# If test_all is false, just test the currently selected objects.
	rect = device.HitRectAroundPoint(p)
	if len(self.selection) < 10 or not test_all:
	    selection_hit = self.selection.Hit(p, rect, device)
	    if not test_all or not selection_hit:
		return selection_hit
	if test_all:
	    path = self.selection.GetPath()
	    if len(path) > 2:
		path = path[:-1]
	    else:
		path = ()
	    hit = self.selection_from_point(p, rect, device, path)
	    self.hit_cache = (p, device, hit)
	    while hit:
		if hit in self.selection.GetInfo():
		    return 1
		hit = selinfo.get_parent(hit)
	    #self.hit_cache = None
	    return 0

    def GetSelectionHandles(self):
	if self.selection:
	    return self.selection.GetHandles()
	else:
	    return []

    #
    #	Get information about the selected objects
    #

    def HasSelection(self):
	# Return true, if one or more objects are selected
	return len(self.selection)
    script_access['HasSelection'] = SCRIPT_GET

    def CountSelected(self):
	# Return the number of currently selected objects
	return len(self.selection)
    script_access['CountSelected'] = SCRIPT_GET

    def SelectionInfoText(self):
	# Return a string describing the selected object(s)
	return self.selection.InfoText()
    script_access['SelectionInfoText'] = SCRIPT_GET

    def CurrentInfoText(self):
        if self.is_drag_creating: #added by shumon June 19, 2009
            text = 'Clones:' + str(len(self.grid_clones))+ 'x' + str(len(self.draglist))
            return text
        return self.selection.CurrentInfoText()

    def SelectionBoundingRect(self):
	# Return the bounding rect of the current selection
	return self.selection.bounding_rect
    script_access['SelectionBoundingRect'] = SCRIPT_GET

    def CurrentObject(self):
	# If exactly one object is selected return that, None instead.
	if len(self.selection) == 1:
	    return self.selection.GetObjects()[0]
	return None
    script_access['CurrentObject'] = SCRIPT_OBJECT

    def SelectedObjects(self):
	# Return the selected objects as a list. They are listed in the
	# order in which they are drawn.
	return self.selection.GetObjects()
    script_access['SelectedObjects'] = SCRIPT_OBJECTLIST

    def CurrentProperties(self):
	# Return the properties of the current object if exactly one
	# object is selected. Return EmptyProperties otherwise.
	if self.selection:
	    if len(self.selection) > 1:
		return EmptyProperties
	    return self.selection.GetInfo()[0][-1].Properties()
	return EmptyProperties
    script_access['CurrentProperties'] = SCRIPT_OBJECT


    def CurrentFillColor(self):
	# Return the fill color of the current object if exactly one
	# object is selected and that object has a solid fill. Return
	# None otherwise.
	if len(self.selection) == 1:
	    properties = self.selection.GetInfo()[0][-1].Properties()
	    try:
		return	properties.fill_pattern.Color()
	    except AttributeError:
		pass
	return None
    script_access['CurrentFillColor'] = SCRIPT_GET


    def PickObject(self, device, point, selectable = 0):
	# Return the object that is hit by a click at POINT. The object
	# is not selected and should not be modified by the caller.
        #
	# If selectable is false, this function descends into compound
	# objects that are normally selected as a whole when one of
	# their children is hit. If selectable is true, the search is
	# done as for a normal selection.
        #
        # This method is intended to be used to
	# let the user click on the drawing and extract properties from
	# the indicated object. The fill and line dialogs use this
	# indirectly (through the canvas object's PickObject) for their
	# 'Update From...' button.
	#
	# XXX should this be implemented by calling WalkHierarchy
	# instead of requiring a special PickObject method in each
	# compound? Unlike the normal hit-test, this method is not that
	# time critical and WalkHierarchy is sufficiently fast for most
	# purposes (see extract_snap_points in the canvas).
	# WalkHierarchy would have to be able to traverse the hierarchy
	# top down and not just bottom up.
        object = None
	rect = device.HitRectAroundPoint(point)
        if not selectable:
            layers = self.layers[:]
            layers.reverse()
            for layer in layers:
                object = layer.PickObject(point, rect, device)
                if object is not None:
                    break
        else:
            selected = self.selection_from_point(point, rect, device)
            if selected:
                object = selected[-1]
	return object

    def PickActiveObject(self, device, p):
        # return the object under point if it's selected or a guide
        # line. None otherwise.
	rect = device.HitRectAroundPoint(p)
        path = self.selection.GetPath()
        if len(path) > 2:
            path = path[:-1]
        else:
            path = ()
        hit = self.selection_from_point(p, rect, device, path)
        #self.hit_cache = (p, device, ]hit)
        if hit:
            if not hit[-1].is_GuideLine:
                while hit:
                    if hit in self.selection.GetInfo():
                        hit = hit[-1]
                        break
                    hit = selinfo.get_parent(hit)
            else:
                hit = hit[-1]
        return hit
    
    #
    #
    #

    def WalkHierarchy(self, func, printable = 1, visible = 1, all = 0):
	# XXX make the selection of layers more versatile
	for layer in self.layers:
	    if (all
                or printable and layer.Printable()
                or visible and layer.Visible()):
		layer.WalkHierarchy(func)

    #
    #
    #
    #variables for cloning (I may gonna create a separate class for handling clones that would integrate into document.py and move all this stuff out
    #that way it will look cleaner
    
    draglist = []
    grid_clones = []
    delta = None     #all intervals will be 20% of width or height for now, so delta = 20
    d = 0.10        #this is supposed to be constant delta
    constant_delta = 1.2 #last experiment was 1.2
    interval_h = 0  #this will be current interval (15%) height
    interval_w= 0  #this will be current interval (15%) height    
    old_interval_h = 0
    old_interval_w = 0
    selection_width = 1   
    selection_height = 1      
    startDragCreationPoint = None
    is_drag_creating = 0 #boolean
    init_sel_br = None
    buffer_p = [] #old mouse point
    selection_diameter_sq = None
    clones_aligned_permanently = 1 #overriding CTRL cloning permanently - for experiment
    
    last_clone_obj = 0 #this one is needed, it will be added in the end (mouse move, mouse release)
    
    def change_clone_spacing(self, quantity): 
        self.old_interval_w = self.interval_w
        self.old_interval_h = self.interval_h
        
        length = len (self.draglist)
        if length < 2:
            return
        
        #determine the left right up or down
        p1 = self.draglist[0]
        p2 = self.draglist[1]
        
        p3 = self.grid_clones[0]
        p4 = 0.0
        grid_len = len(self.grid_clones)
        if grid_len > 1:
            p4 = self.grid_clones[1]
        
        selection = self.selection
        #obj = self.selection.rect.outline_object
        
        #rect = obj.bounding_rect
        rect = self.selection.bounding_rect
        width = abs(self.selection.bounding_rect[2]-self.selection.bounding_rect[0])
        height = abs(self.selection.bounding_rect[3]-self.selection.bounding_rect[1])
        
        #plast2 = self.draglist[len-1]
        
        
        #addx = 0
        #addy = 0
        
        dist = 0 
        #dist_list = [None, None, None, None] 
        
        condition = None
        if p2.x - p1.x < 0:
            #addx = -(self.interval_w - self.old_interval_w)          
            dist = abs(self.draglist[0].x-self.selection.rect.drag_cur[0]) - width
            condition = 0                        
        elif p2.x - p1.x > 0:
            #addx = self.interval_w - self.old_interval_w                
            dist = abs(self.draglist[0].x-self.selection.rect.drag_cur[0]) - width
            condition = 1            
        elif p2.y - p1.y < 0:
            #addy = -self.interval_h + self.old_interval_h
            dist = abs(self.draglist[0].y-self.selection.rect.drag_cur[1])-height
            condition = 2
        elif p2.y - p1.y > 0: 
            dist = abs(self.draglist[0].y-self.selection.rect.drag_cur[1])-height
            condition = 3

        condition_grid = None
        print 'p4',p4
        if p4 != 0.0:
            if p4.x - p3.x < 0:
                #addx = -(self.interval_w - self.old_interval_w)          
                dist_grid = abs(self.grid_clones[0].x-self.selection.rect.drag_cur[0]) - width
                condition_grid = 0                        
            elif p4.x - p3.x > 0:
                #addx = self.interval_w - self.old_interval_w                
                dist_grid = abs(self.grid_clones[0].x-self.selection.rect.drag_cur[0]) - width
                condition_grid = 1            
            elif p4.y - p1.y < 0:
                #addy = -self.interval_h + self.old_interval_h
                dist_grid = abs(self.grid_clones[0].y-self.selection.rect.drag_cur[1])-height
                condition_grid = 2
            elif p4.y - p3.y > 0: 
                dist_grid = abs(self.grid_clones[0].y-self.selection.rect.drag_cur[1])-height
                condition_grid = 3
            
            #addy = self.interval_h - self.old_interval_h
        print 'condition=',condition,'condition_grid=',condition_grid

        new_len = length-1
        print "len = ",  length
        if quantity == -1:
            self.delta = max (1,self.delta - self.d)             
            new_len -=1
        elif quantity == 1:
            self.delta = self.delta + self.d            
            new_len +=1
        
        #check if we can create this new number of clones
        print "new_len=", new_len
        if new_len == 0: #this causes devision by zero therefore return
            return
        new_interval = 0
        

        if condition == 0 or condition == 1:
            if dist/(new_len*width) > 1 :                        
                new_interval = (dist - width*new_len)/(new_len+1) 
                print "yes, you can create ",new_len,"clones, the new interval=", new_interval
                #if quantity is not zero, means it was called with mousewheel
                #therefore this step is necessary along with Show - to redisplay                
                if quantity != 0:
                    self.Hide(self.device)
                first_obj= self.draglist[0]
                del self.draglist[:]
                self.draglist.append(first_obj)
                n = 0
                for i in range(1, new_len + 1):              
                    n=n+1
                    if condition == 1:
                        point = Point(self.draglist[i-1].x+width + new_interval , self.draglist[i-1].y)
                    elif condition == 0:
                            point = Point(self.draglist[i-1].x - width - new_interval , self.draglist[i-1].y)
                    self.draglist.append(point)            
                
                if condition == 1:
                    self.last_clone_obj = Point(self.draglist[n].x+width + new_interval , self.draglist[n].y)
                elif condition == 0:
                    self.last_clone_obj = Point(self.draglist[n].x-width - new_interval , self.draglist[n].y)
                if quantity != 0:
                    self.Show(self.device)
                self.interval_w =  self.selection_width  + new_interval
                
            else:
                print "KTULXU BYL ZDES"
                return
        elif condition == 2 or condition == 3:
            if dist/(new_len*height) > 1 :                        
                new_interval = (dist - height*new_len)/(new_len+1) 
                print "yes, you can create ",new_len,"clones, the new interval=", new_interval
                
                if quantity != 0:
                    self.Hide(self.device)
                    
                first_obj= self.draglist[0]
                del self.draglist[:]
                self.draglist.append(first_obj)
                n = 0
                for i in range(1, new_len+1):              
                    n=n+1
                    if condition == 3:
                        point = Point(self.draglist[i-1].x,  self.draglist[i-1].y +height + new_interval)
                    elif condition == 2:
                        point = Point(self.draglist[i-1].x,  self.draglist[i-1]. y -height - new_interval)
                    self.draglist.append(point)            
                
                if condition == 3:
                    self.last_clone_obj = Point(self.draglist[n].x,  self.draglist[n].y+height + new_interval)
                elif condition == 2:
                    self.last_clone_obj = Point(self.draglist[n].x,  self.draglist[n].y-height - new_interval)
                if quantity != 0:
                    self.Show(self.device)
                self.interval_h = self.selection_height  + new_interval #i dont use it anymore, but still update
                self.interval_w = self.selection_height  + new_interval
            else:
                print "KTULXU height BYL ZDES"
           

        new_len = grid_len-1
        print "len = ",  grid_len
        if quantity == -1:
            self.delta = max (1,self.delta - self.d)             
            new_len -=1
        elif quantity == 1:
            self.delta = self.delta + self.d            
            new_len +=1
        
        #check if we can create this new number of clones
        print "new_len=", new_len
        if new_len == 0: #this causes devision by zero therefore return
            return
        new_interval = 0
        
        if p4 != 0.0 and (condition_grid == 0 or condition_grid == 1):
            if dist_grid/(new_len*width) > 1 :                        
                new_interval = (dist_grid - width*new_len)/(new_len+1) 
                print "yes, you can create ",new_len,"clones, the new interval=", new_interval
                #if quantity is not zero, means it was called with mousewheel
                #therefore this step is necessary along with Show - to redisplay                
                if quantity != 0:
                    self.Hide(self.device)
                first_obj= self.grid_clones[0]
                del self.grid_clones[:]
                self.grid_clones.append(first_obj)
                n = 0
                for i in range(1, new_len + 1):              
                    n=n+1
                    if condition_grid == 1:
                        point = Point(self.grid_clones[i-1].x+width + new_interval , self.grid_clones[i-1].y)
                    elif condition_grid == 0:
                            point = Point(self.grid_clones[i-1].x - width - new_interval , self.grid_clones[i-1].y)
                    self.grid_clones.append(point)            
                
                if condition_grid == 1:
                    self.last_clone_obj = Point(self.grid_clones[n].x+width + new_interval , self.grid_clones[n].y)
                elif condition_grid == 0:
                    self.last_clone_obj = Point(self.grid_clones[n].x-width - new_interval , self.grid_clones[n].y)
                if quantity != 0:
                    self.Show(self.device)
                self.interval_w =  self.selection_width  + new_interval
                
            else:
                print "KTULXU BYL ZDES"
                return
        elif p4 != 0.0 and (condition_grid == 2 or condition_grid == 3):
            if dist_grid/(new_len*height) > 1 :                        
                new_interval = (dist_grid - height*new_len)/(new_len+1) 
                print "yes, you can create ",new_len,"clones, the new interval=", new_interval
                
                if quantity != 0:
                    self.Hide(self.device)
                    
                first_obj= self.grid_clones[0]
                del self.grid_clones[:]
                self.grid_clones.append(first_obj)
                n = 0
                for i in range(1, new_len+1):              
                    n=n+1
                    if condition_grid == 3:
                        point = Point(self.grid_clones[i-1].x,  self.grid_clones[i-1].y +height + new_interval)
                    elif condition_grid == 2:
                        point = Point(self.grid_clones[i-1].x,  self.grid_clones[i-1]. y -height - new_interval)
                    self.grid_clones.append(point)            
                
                if condition_grid == 3:
                    self.last_clone_obj = Point(self.grid_clones[n].x,  self.grid_clones[n].y+height + new_interval)
                elif condition_grid == 2:
                    self.last_clone_obj = Point(self.grid_clones[n].x,  self.grid_clones[n].y-height - new_interval)
                if quantity != 0:
                    self.Show(self.device)
                self.interval_h = self.selection_height  + new_interval #i dont use it anymore, but still update
                self.interval_w = self.selection_height  + new_interval
            else:
                print "KTULXU height BYL ZDES"
          
        p_drag = self.selection.rect.drag_cur
       # print "DDistance=", abs(self.draglist[0].x-self.selection.rect.drag_cur[0])
       # print "DDistanceh=", self.draglist[0].y-self.selection.rect.drag_cur[1]
  
    def initDragCreation(self, p):
        self.old_parent_array = None       
        del self.draglist[:] #clreaing draglist
        del self.grid_clones[:] #clreaing draglist
        self.clear_parent_array_data()
        #self.startDragCreationPoint = Point(self.selection.bounding_rect[0], self.selection.bounding_rect[1])
       
       
        #temp = self.selection
        
       
        self.delta = self.constant_delta #restore delta
        self.init_sel_br = self.selection.bounding_rect        
        #selection width and height is retrieved only once in the beginning
        self.selection_width = abs(self.selection.bounding_rect[0]-self.selection.bounding_rect[2])        
        self.selection_height = abs(self.selection.bounding_rect[1]-self.selection.bounding_rect[3])  
        
        self.startDragCreationPoint = Point(self.init_sel_br[0], self.init_sel_br[1]+self.selection_height) #self.selection.rect.drag_start
        self.draglist.append(self.startDragCreationPoint)
        self.grid_clones.append(self.startDragCreationPoint)
        
        
        #precalculate current intervals for optimization (i dont if it indeed optimizes or not, but it certainly looks more cleaner)
        self.old_interval_w = self.interval_w = self.delta * self.selection_width
        self.old_interval_h = self.interval_h = self.delta * self.selection_height
        #self.buffer_p = p #initializing old_p
        self.clear_buffer_p()
        self.selection_diameter_sq = self.selection_width**2+self.selection_height**2
        
    
    def DragCreationMouseMoveFree(self, p, state):
        length = len(self.draglist)        
        #print "bounding_rect:", self.selection.bounding_rect
        
        obj = self.selection.rect.outline_object
        #Ellipse and Polybezier have different displacements when creating around free path
        if isinstance(obj, PolyBezier):
            p = Point(p.x, p.y+self.selection_height)
        elif isinstance(obj, Ellipse):
            p = Point(p.x, p.y+self.selection_height*.5)            
        distance_from_last_sq = (self.draglist[length - 1].x - p.x)**2 + (self.draglist[length - 1].y - p.y + self.selection_height)**2 #freeform creation        
        
        point = self.draglist[length - 1]
        point = point - self.selection.rect.drag_cur
        point.x**2+point.y**2
        
        distance_from_last_sq = point.x**2+point.y**2
        #num_potential_clones = abs(int(distance  / self.selection_width))
        '''string = None
        if distance_from_last_sq >  self.selection_diameter_sq:
            string = "greater"
        else:
            string = "smaller"
        print "distance_from_last_sq=", distance_from_last_sq, string,  "selection_diam_sq=", self.selection_diameter_sq'''
        
        #newp = None
        if distance_from_last_sq >  self.selection_diameter_sq:
            #self.draglist.append(Point(p.x, p.y-self.selection_height))
            if isinstance(obj, PolyBezier):
                p0 = self.selection.rect.drag_cur
                p0 = Point(self.selection.rect.drag_cur[0], self.selection.rect.drag_cur[1]+self.selection_height)
                self.draglist.append(p0)
            elif isinstance(obj, Ellipse):
                p0 = self.selection.rect.drag_cur
                p0 = Point(self.selection.rect.drag_cur[0], self.selection.rect.drag_cur[1]+self.selection_height*.5)
                self.draglist.append(p0)
            else:
                self.draglist.append(Point(self.selection.rect.drag_cur))
    

    def DragCreationMouseMoveX(self, p, state):
        #first along x,then along y
        
        #print "coming there"
        length = len(self.draglist)
        #print "bounding_rect:", self.selection.bounding_rect
        difference = self.draglist[length - 1].x - self.selection.rect.drag_cur[0] #horizontal creation
        distance = p.x - self.init_sel_br[0]
        #print "self.selection.rect.drag_cur[0] =", self.selection.rect.drag_cur[0] 
        #print "self.init_sel_br[0]=", self.init_sel_br[0]
        #print "distance=", distance
        newp = None
        num_potential_clones = abs(int(distance  / (self.interval_w)))     
        #print "num_potential clones=", num_potential_clones 
        if abs(difference) > self.interval_w:
            if difference >= 0:
                newp = Point (self.draglist[length - 1].x - self.interval_w,  self.selection.bounding_rect[3])
            else:
                newp = Point (self.draglist[length - 1].x +self.interval_w, self.selection.bounding_rect[3])
            self.draglist.append(newp)                

        extra_clones = max(0, length - num_potential_clones - 1)
        #print "extra_clones=", extra_clones
        for i in range(extra_clones):            
            self.draglist.pop()
        #print  "total clones", len(self.draglist)
        ######################################################################
        length = len(self.grid_clones)
        #print "bounding_rect:", self.selection.bounding_rect
        difference = self.grid_clones[length - 1].y - self.selection.rect.drag_cur[1] #vert creation
        distance = p.y - self.init_sel_br[3]            
        newp = None
        num_potential_clones = abs(int(distance  / self.interval_h))
        
        if abs(difference) > self.interval_h: #used to be interval_h
            if difference >= 0:
                newp = Point (self.selection.bounding_rect[0],  self.grid_clones[length - 1].y - self.interval_h ) #used to be interval_h
            else:
                newp = Point (self.selection.bounding_rect[0],  self.grid_clones[length - 1].y + self.interval_h) #used to be interval_h
            self.grid_clones.append(newp)                
        

        extra_clones = max(0, length - num_potential_clones - 1)        
        #print "extra_clones=", extra_clones
        for i in range(extra_clones):          
          self.grid_clones.pop()   
    
    def DragCreationMouseMoveY(self, p, state):
        #print "coming here"
        length = len(self.draglist)
        #print "bounding_rect:", self.selection.bounding_rect
        difference = self.draglist[length - 1].y - self.selection.rect.drag_cur[1] #vert creation
        distance = p.y - self.init_sel_br[3]            
        newp = None
        num_potential_clones = abs(int(distance  / self.interval_h))
        
        if abs(difference) > self.interval_h: #used to be interval_h
            if difference >= 0:
                newp = Point (self.selection.bounding_rect[0],  self.draglist[length - 1].y - self.interval_h ) #used to be interval_h
            else:
                newp = Point (self.selection.bounding_rect[0],  self.draglist[length - 1].y + self.interval_h) #used to be interval_h
            self.draglist.append(newp)                
        

        extra_clones = max(0, length - num_potential_clones - 1)        
        #print "extra_clones=", extra_clones
        for i in range(extra_clones):          
          self.draglist.pop()
        #print  "total clones", len(self.draglist)
        ##########################################
        length = len(self.grid_clones)
        #print "bounding_rect:", self.selection.bounding_rect
        difference = self.grid_clones[length - 1].x - self.selection.rect.drag_cur[0] #horizontal creation
        distance = p.x - self.init_sel_br[0]
        #print "self.selection.rect.drag_cur[0] =", self.selection.rect.drag_cur[0] 
        #print "self.init_sel_br[0]=", self.init_sel_br[0]
        #print "distance=", distance
        newp = None
        num_potential_clones = abs(int(distance  / self.interval_w))     
        #print "num_potential clones=", num_potential_clones 
        if abs(difference) > self.interval_w:
            if difference >= 0:
                newp = Point (self.grid_clones[length - 1].x - self.interval_w,  self.selection.bounding_rect[3])
            else:
                newp = Point (self.grid_clones[length - 1].x +self.interval_w, self.selection.bounding_rect[3])
            self.grid_clones.append(newp)                

        extra_clones = max(0, length - num_potential_clones - 1)
        #print "extra_clones=", extra_clones
        for i in range(extra_clones):            
            self.grid_clones.pop()
       
    
    def update_buffer_p(self,point):        
        if len(self.buffer_p) < 2: #10 is the max buffer size
            #self.buffer_p.pop(0) #remove the first one and append
            self.buffer_p.append(point)
            
    
    def get_buffer_p_w(self):
        return abs(self.buffer_p[0].x - self.buffer_p[-1].x)
    
    def get_buffer_p_h(self):
        return abs(self.buffer_p[0].y - self.buffer_p[-1].y)
            
    def clear_buffer_p(self):
        del self.buffer_p[:]
    
    more = None
    def DragCreationMouseMove(self, p, state):
        #everytime condition changes we delete draglist and start over
        if state == self.state1 and not self.clones_aligned_permanently:
   
            #print "c=",self.clones_aligned_permanently
            self.DragCreationMouseMoveFree(p, state)
            
            string = 'direct_cloning_free'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(len(self.draglist))
            self.log(string)
            self.main_window.total_direct_cloning_free_moves+=1 #increment statistic
            
 
        elif state == self.state2 or state == self.state1 and self.clones_aligned_permanently:        
            #print "crap","state=",state,"state2=",self.state2        
            
            #print "buffer_p=",self.buffer_p
            if len(self.buffer_p) > 1:
                
                pw = self.get_buffer_p_w()
                ph = self.get_buffer_p_h()           
                if  pw > ph:
                    self.more = 'x'                
                elif pw <= ph:
                    self.more = 'y'                
            else:
                self.update_buffer_p(p)
                return
            #diff_x = abs(self.buffer_p.x - p.x)
            #diff_y = abs(self.buffer_p.y-p.y)
            #print "old_px=",self.buffer_p            
            
            #treshold should be a percentage from the selection diameter
            #threshold = 0.0
            
            #if diff_x - diff_y > self.selection_width*threshold:
                #more x
            #print more, len(self.draglist)
            if self.more == 'x':
                self.DragCreationMouseMoveX(p, state)
                
                string = 'direct_cloning_x'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(len(self.draglist))
                self.main_window.total_direct_cloning_x_moves+=1 #increment statistic
                self.log(string)
            elif self.more == 'y':#if diff_y - diff_x > self.selection_height*threshold:
                #more y
                
                self.DragCreationMouseMoveY(p, state)
                
                string = 'direct_cloning_y'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(len(self.draglist))
                self.main_window.total_direct_cloning_y_moves+=1 #increment statistic
                self.log(string) 
        self.update_buffer_p(p)         



    def ClearDragCreationData(self):
        del self.draglist[:] #clreaing draglist
        '''
        self.selection_width = None    
        self.selection_height = None    
        self.startDragCreationPoint = None        
        self.init_sel_br = None'''
        self.is_drag_creating = 0
        
        self.draglist = []
        self.delta = 1.15    #all intervals will be 15% of width or height for now, so delta = 15
        self.interval_h = 0  #this will be current interval (15%) height
        self.interval_w= 0  #this will be current interval (15%) height    
        self.selection_width = None    
        self.selection_height = None        
        self.startDragCreationPoint = None
        self.is_drag_creating = 0 #boolean
        self.init_sel_br = None
        #self.buffer_p = None #old mouse point
        self.clear_buffer_p()
        #self.clones_aligned_permanently = 0
        self.selection_diameter_sq = None

    def ButtonDown(self, p, button, state):
        string = 'buttondown'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(button)
        self.log(string)
        self.main_window.total_button_downs+=1

        #print "[[[[[[[[[[[[selection = ", self.selection.GetObjects()[0]
        
        
        self.was_dragged = 0      
        if state == self.state1 or state == self.state2: #336 is Super_L button pressed
            if self.is_drag_creating == 0:
                self.initDragCreation(p) 
                self.is_drag_creating = 1                
        
        self.old_change_rect = self.selection.ChangeRect()        
        result = self.selection.ButtonDown(p, button, state)
        return result


    #this flag is used to prevent dragging when the user cancels aligned direct cloning
    stop_drag = 0
    
    dupe_x = None
    dupe_y = None
    
    def MouseMove(self, p, state):

        self.last_clone_obj = 0 #resetting last clone, this may not still fix the problem, need to test
        #print "state=", state
        #print "state = ", state  
        #print "state & const.ControlMask" , state & const.ControlMask
        #print "state & const.MetaMask" , state & const.MetaMask
        #print "state & const.ShiftMask",  state & const.MetaMask
        sel = self.selection        

        #it never goes in here anymore June 27, 2009
        '''if state != self.state1 and state !=self.state2 and state != 256: #340 was here before 
            self.was_dragged = 1 #supposed to be 1 here!!!
            if self.is_drag_creating == 1:
                self.is_drag_creating = 0
                self.ClearDragCreationData()
                self.initDragCreation(p)
                
            string = 'mouse_move'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(len(self.draglist))
            self.log(string)
            self.main_window.total_mouse_moves+=1  '''
        #This new crap I added on November 19
        if  (self.main_window.application.technique == 'e') and state == self.state1 and self.new_sel_obj is not None and self.old_sel_obj is not None:
            #self.was_dragged = 1      
            if len(self.buffer_p) > 1:
            
                pw = self.get_buffer_p_w()
                ph = self.get_buffer_p_h()           
                if  pw > ph:
                    self.more = 'x'                
                else:
                    self.more = 'y'                
            else:
                self.update_buffer_p(p)
                self.selection.MouseMove(p, state)
                return
            self.update_buffer_p(p)
            print self.more
            if self.more == 'x':
                self.dupe_x = p.x
                self.dupe_y = self.old_sel_obj.coord_rect[3]
                '''if len(self.selection.GetObjects()) > 1:
                    self.dupe_y = self.old_sel_obj.coord_rect[1]'''

                p = Point(self.dupe_x,self.dupe_y)

            elif self.more == 'y':
                self.dupe_x = self.old_sel_obj.coord_rect[0]
                '''if len(self.selection.GetObjects()) > 1:
                    self.dupe_y = self.old_sel_obj.coord_rect[2]'''
                self.dupe_y = p.y
                p = Point(self.dupe_x,self.dupe_y)
            self.selection.MouseMove(p, state)
            return

        elif self.is_drag_creating == 0 and not self.stop_drag and state != self.state1 and state != self.state2:
            self.was_dragged = 1
            string = 'mouse_move'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(len(self.draglist))
            self.log(string)
            self.main_window.total_mouse_moves+=1
        elif self.is_drag_creating == 1 and state != self.state1 and state != self.state2 and self.clones_aligned_permanently:            
            self.was_dragged = 0
            self.change_clone_spacing(0)
        else:
            #prevent direct cloning if it's a tile cloning session (for experiment only)
            technique = self.main_window.application.technique
            if technique == _("d") or technique == None or technique == _("e"):
                self.was_dragged = 0
                if self.is_drag_creating == 0:
                    self.initDragCreation(p)              
                    self.is_drag_creating = 1                            
                self.DragCreationMouseMove(p, state)
            else:
                #restart logging, since user screwed up
                self.main_window.reopen_log_file()         
        #print "state=",state,"state1=",self.state1,"state2=",self.state2
        if self.main_window.application.technique == 'e': self.clear_buffer_p()
        self.selection.MouseMove(p, state)
 


    def ButtonUp(self, p, button, state):        
        if self.main_window.application.technique == 'e': self.clear_buffer_p()
        if self.dupe_x is not None and self.dupe_y is not None:
            p = Point(self.dupe_x,self.dupe_y)
        string = 'buttonup'+','+str(p.x)+','+str(p.y)+','+str(state)+','+str(button)
        self.log(string)
        print time.time()- self.main_window.start_time,string
        self.main_window.total_button_ups+=1
        if state == 272:
            current_time =  time.time()
            elapsed_time = current_time - self.main_window.start_time
            self.main_window.last_up_on_272 = elapsed_time
            print "last up on 272",elapsed_time

        self.begin_transaction(clear_selection_rect = 1)
	try:
	    try:
		if (self.was_dragged and  not( state == self.state1 or state == self.state2)) or self.main_window.application.technique == 'e' :
                    #print "i came here"
		    undo_text, undo_edit \
			       = self.selection.ButtonUp(p, button, state)
		    if undo_edit is not None and undo_edit != NullUndo:
			self.add_undo(undo_text, undo_edit)
			uc1 = self.AddClearRect(self.old_change_rect)
			uc2 = self.AddClearRect(self.selection.ChangeRect())
			self.add_undo(uc1, uc2)
			self.add_undo(self.queue_edited())
                        #add condition here how to call this shit up                                                
                        self.EditClones()
                        #duplication
                        self.__get_new_dupe_offset() #Added Nov 13 ,2009
                        self.dupe_x = self.dupe_y = None
                   

		    else:
			# the user probably just moved the rotation
			# center point. The canvas has to update the
			# handles
			self.queue_selection()
		else:
		    self.selection.ButtonUp(p, button, state, forget_trafo = 1)
		    self.ToggleSelectionBehaviour()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
        if  self.is_drag_creating:#state == self.state1 or state == self.state2 or state == 256: 
            if self.last_clone_obj != 0:
                pass 
                #self.draglist.append(self.last_clone_obj)    
            self.DragCreation()   
            self.last_clone_obj = 0
            self.stop_drag = 0

        #ar=[1,2,3,4,5,6,7,8,9,10,[66,[44,77,88,99,[54,547] ],548, 550],12,13,[45,65],14,15]
        #ar = [[1], [2], [3],[ [6], [7],[ [9], [10], [11], [12], [13]     ],  [8] ],  [4]]
        #out = self.getInterpolationSequence( [17],  ar)
        #print "out=", out



    #added by shumon
    message = _("Which objects would you like to edit?")
    title = _("Editing clones")
    OnlyThisObject = _("Selected")
    AllTheObjects = _("All")
    AllTheFollowing = _("All following")
    AllTheFollowingSkippingOne = _("All following skipping one")
    Cancel = _("Cancel")
    #Calendar = (OnlyThisObject, AllTheObjects, AllTheFollowing, AllTheFollowingSkippingOne, Cancel)
    Calendar = (OnlyThisObject, AllTheObjects, AllTheFollowing, Cancel)
    
    
    clones = []
    tile_clones = []
    canvas = None
    #if continuing to drag create... should merge two sets
    #support for color change
    #edit begin_transaction to keep track of last transaction... we dont want this shit to pop up each you move the fucking thing
    #when you delete a clone don't forget to update the clones array
    #use this function to help the locate the array you need to delete the obsolete object
    
    #new document - clear clones array
    #add numbers to clones?
    
    #the following few lines are a copy of SelectObject method, but without being wrapped into a transaction, since we are in the transaction already 
    def select_object(self, obj):
        objects = obj
        if type(objects) != ListType:
            objects = [objects]
        selinfo = []
        for object in objects:
            selinfo.append(object.SelectionInfo())
        if selinfo:
            self.__set_selection(selinfo, SelectSet)
        else:
            self.__set_selection(None, SelectSet)

    def GetSubArray(self,array, object):        
        #if len(array) == 1: #if there is only one series of clones
        #    return array[0]
        for i in range (len(array)):
            for j in range (len(array[i])):
                if object == array[i][j]:
                    return array[i]
        #found nothing so returning None
        return None
    
    #get i and j of the two dimensional array
    def GetIndex(self, array,  object):
      for i in range (len(array)):
            for j in range (len(array[i])):
                if object == array[i][j]:
                    return i, j
      return None, None

    def FindIndex(self, array,  object):
        for i in range (len(array)):
                if object == array[i]:
                    return i
        return None

           
    
    ''''def edit_clones2(self,  array, object):
        for i in range (self.index_of_object_in_the_parent_array+1, len(array)):
            this = array[i]
            if this == object:
                self.edit_object(this, object)  
                return
            elif isinstance(this, type([])):                
                self.edit_clones2(this, object)    
    '''
   
    #this sucks still
    '''def edit_clones(self,L, obj):
        # if its empty do nothing
        if not L: return
        # if it's a list call printList on 1st element
        if type(L[0]) == type([]):
            self.edit_clones(L[0],obj)            
        else: #no list so just edit             
            if obj != L[0]:
                newobj = self.edit_object(L[0], obj)             
                L[0] = newobj
            #update object in the clones list too (no undo yet)
            
        # now process the rest of L 
        self.edit_clones(L[1:], obj)
    '''



    def CanInterpolateToRoot(self):
        #currently we only check whether the object is a clone or not
        #obj = self.CurrentObject()
        #return isinstance(obj, Clone)        
       

        #self.DisplayTileCloningDialog()
        
        return 1
    

    #for size interpolation
    def TransformClone(self, sel_obj, scale_x, scale_y): 
        #2d scaling
        #sel_obj = sel_obj_arr[0]
        #print "sel_obj_arr=", sel_obj
        sel_obj=sel_obj[0]
        #self.begin_transaction(_("Transform Clone"))
        try:
            try:
                #we can improve this by adding undo later                
                coord_rect = Rect(sel_obj.coord_rect[0],sel_obj.coord_rect[1], sel_obj.coord_rect[2], sel_obj.coord_rect[3])
                
                #center = Point((coord_rect[2]-coord_rect[0])/2, (coord_rect[3]-coord_rect[1])/2)
                
                undo = sel_obj.Translate(Point(-coord_rect[0],  -coord_rect[1]))
                self.add_undo(undo)
                #sel_obj.Translate(Point(-center.x,-center.y))
                
                #another way of doing translation, maybe useful for undo
                #trafo = Trafo(1, 0, 0, 1, -coord_rect[0],  -coord_rect[1]) #move to the origin        
                #sel_obj.Transform(trafo)
                
                trafo = Trafo(scale_x, 0, 0, scale_y, 0, 0)
                undo = sel_obj.Transform(trafo)
                self.add_undo(undo)
                
                undo = sel_obj.Translate(Point(coord_rect[0],  coord_rect[1]))      
                self.add_undo(undo)
                #sel_obj.Translate(Point(center.x,center.y))
                
                self.add_undo(self.queue_edited())                                                
                self.add_undo(self.view_redraw_all())       #we can use this function probably to solve bugs with arrow drawing
            except:
                #self.abort_transaction()
                "bla"
        finally:
            #self.end_transaction()
             "bla"
        
        #trafo = Trafo(1, 0, 0, 1, coord_rect[0],  coord_rect[1]) #move back where it was
        #sel_obj.Transform(trafo)
        
        #sel_obj.Transform(trafo)
        #center = coord_rect.center()
        #trafo = apply(Trafo, [2, 0, 0, 2])
        #sel_obj.Transform(trafo)
        
    
    def InterpolateToRoot(self):  #Andriy calls it gradient fill
        #sel = self.CurrentObject()
        #self.select_object(sel)
        string = 'InterpolateToRootCalled'
        self.log(string)
        self.main_window.total_interpolate_to_root_calls+=1
        
        sel_obj=self.selection.GetObjects()[0]
        
        seq = self.getInterpolationSequence(sel_obj)
        if seq == None:
            print "Color interpolation sequence is empty"
            return
        
        #get color of the selected object
        sel_col = self.CurrentFillColor()

        seq.insert(0, [sel_obj]) #inserting sel_obj into the interpolated list so it;s easier
        num = len(seq)
        #print "num=", num
        if num == 0:
            print "cannot interpolate single object in clone chain"
            return
        elif num == 1:
            print "no objects to interpolate between root and selected object"
        
        #get color of the root object
        self.select_object(seq[-1]) #last object
        root_col = self.CurrentFillColor()
        #print "selcol=", sel_col, "root_col=", root_col
        #print "seq=", seq
        
       #declare the variables
        delta_col_r = 0
        delta_col_g = 0
        delta_col_b = 0
        if sel_col != None and root_col != None:
            #print "Root color or selection color is not none"
            #return        
            #now interpolate colors of inbetween clones
            diff_r = sel_col[0] - root_col[0]
            diff_g = sel_col[1] - root_col[1]
            diff_b = sel_col[2] - root_col[2]
            
            
            
            delta_col_r = diff_r / (num-1) #because currently sel object is not included, its num instead num - 1
            delta_col_g = diff_g / (num-1)
            delta_col_b = diff_b / (num-1)
        

        
        
        #let's determine factor for size interpolation
        root_coord_rect = seq[-1][0].coord_rect
        sel_coord_rect = sel_obj.coord_rect
        
        root_width = root_coord_rect[2]-root_coord_rect[0]
        sel_width = sel_coord_rect[2]-sel_coord_rect[0]
        
        root_height = root_coord_rect[3]-root_coord_rect[1]
        sel_height = sel_coord_rect[3]-sel_coord_rect[1]
        
        
        diff_x = (root_width) - (sel_width)
        diff_y = (root_height) - (sel_height)
        interval_x = -diff_x / (num -1) 
        interval_y = -diff_y / (num -1)  
        
        #print "num=", num
        #print "sel_width=", sel_width
        #print "root_width=", root_width
        #print "interval", interval_x
        #print "seq=", seq
        
        for i in range (1, num-1):                        
            print "i=", i
            self.select_object(seq[i-1])
            
            #do color stuff first
            if sel_col != None and root_col != None:            
                prev_col = self.CurrentFillColor()
                
               # print "prev_col=", prev_col
                col = CreateRGBColor(prev_col[0] - delta_col_r, prev_col[1] - delta_col_g, prev_col[2] - delta_col_b) 
                print "inter_color = ", col
                self.select_object(seq[i])
                self.canvas.fill_solid(col)
            
            scale_x = (sel_width - interval_x*i)/sel_width
            scale_y = (sel_height - interval_y*i)/sel_height
            #print "scalex,scaley=", scale_x, scale_y   
            '''However we first need to scale current object to match the scale with the selected object before scaling it for interpolation. i know it's stupid, but i cannot find a method that does something like rectangle.setWidth, so i created my own function called TransformClone, which performs matrix scaling and translation to origin and back.'''
            scale_to_sel_obj_x = sel_width/(seq[i][0].coord_rect[2]-seq[i][0].coord_rect[0])
            scale_to_sel_obj_y = sel_height/(seq[i][0].coord_rect[3]-seq[i][0].coord_rect[1])
            
            
            
            #replace the object with selection before screwing with it
            self.TransformClone(seq[i], scale_to_sel_obj_x*scale_x,scale_to_sel_obj_y*scale_y)            

    def getInterpolationSequence(self, object):
        self.clear_parent_array_data()
        self.FindParentArray(self.clones, object)        #self.clones
        old_parent = None       
        
        if  self.parent_array == None or self.parent_array == []:
            return None
        index = self.parent_array.index(object)
        
        out  = []
        #out.append([self.selection.GetObjects()[0]]) #adding first object (we wont need this)
        for i in range(index-1,-1, -1):
            obj = self.parent_array[i]
            if type(obj) == type([]) and type(obj[0]) != type([]):            
                out.append(self.parent_array[i])
        #-----------------
        while self.parent_array != self.clones:
            old_parent = self.parent_array
            self.clear_parent_array_data()
            self.FindParentArray(self.clones, old_parent)
            index = self.parent_array.index(old_parent)
            for i in range(index-1,-1, -1):
                obj = self.parent_array[i]
                if type(obj) == type([]) and type(obj[0]) != type([]):            
                    out.append(self.parent_array[i])
        return out
    
    #modified this on dec 25,2008 to generalize it for use with unlink all clones
    def find_original_ancenstor_array(self, array, object):
        #setup code
        self.clear_parent_array_data()
        self.FindParentArray(array, object)        
        old_parent = None
        #-----------------

        while self.parent_array != array[0]:
            old_parent = self.parent_array
            self.clear_parent_array_data()
            self.FindParentArray(array, old_parent)        
        #edit
        return old_parent
    
    
    def edit_all(self, object, func, arg):
        ancestor = self.find_original_ancenstor_array([self.clones],object)
        self.edit_all_in_sublist(ancestor,  object, func, arg)
        
    #code duplication, but i dont give a damn now
    def edit_all_tiles(self, object, func, arg):
        ancestor = self.find_original_ancenstor_array([self.tile_clones],object)
        self.edit_all_in_sublist(ancestor,  object, func, arg)
    
    last_item = None
   
    prev_target = None
    arrow_stack = []
    
    #this definitely needs to be called, but it's not called now
    def clear_arrow_drawing_data(self):
       prev_target = None
       arrow_stack = []
    
    arrow_head_list = []
    arrow_width = 10
    arrow_length = 20
    def draw_arrow_head(self, obj, x, y, position, angle, second_obj):
      
      width = self.arrow_width
      length = self.arrow_length
      
      if x == None and y == None:
          x = obj.coord_rect[2]#+dx
          y = obj.coord_rect[3]#- dy    
      
      #path = None
      '''
      if position == "LEFT":
        path = [(0, 0-width), (0-length, 0), (0, 0+width), (0, 0-width)] #left
      elif position == "RIGHT":
            path = [(0, 0+width), (0+length, 0+0.0),(0+0.0, 0-width), (0+0.0, 0+width)]     #right
      elif position == "TOP":
       path = [(0-width, 0), (0, 0+length), (0+width, 0), (0-width, 0)] #top
      elif position == "BOTTOM":
           path = [(0-width, 0), (0, 0-length), (0+width, 0), (0-width, 0)] #bottom
        '''
        
      '''if position == "LEFT":            
            path = [(x, y-width), (x-length, y), (x, y+width), (x, y-width)] #left
      elif position == "RIGHT":
            path = [(x, y+width), (x+length, y+0.0),(x+0.0, y-width), (x+0.0, y+width)]     #right
      elif position == "TOP":
       path = [(x-width, y), (x, y+length), (x+width, y), (x-width, y)] #top
      elif position == "BOTTOM":
           path = [(x-width, y), (x, y-length), (x+width, y), (x-width, y)] #bottom'''
     
      p = [(0, -width), (-length, 0), (0, width), (0, -width)] #left      
      path = []
      #rotating

      for i in p:
            xx = i[0]+length
            yy = i[1]
            c = cos(angle)
            s = sin(angle)
            
            path.append((c*xx - s*yy+x, c*yy+s*xx+y))

        
      
      a = Arrow(path, 1)
      
      #self.device.SetFillColor(65280)
      '''found  = 0
      for i in self.arrow_head_list:
        if i[0] == second_obj and i[1] == position:
           found = 1
      #don't draw arrow head if there is one already
      if not found:'''
      a.Draw(self.device)
      self.arrow_head_list.append((second_obj, position))

      #print "arrow_head_list", self.arrow_head_list
      
      color = 0xffffff
      self.device.SetFillColor(color)           
      
    
    def draw_arrow_line(self, obj1, obj2):
      #constants 
      dx = 0
      dy = 0   
      
      
      p1 = Point(obj1.coord_rect[0],obj1.coord_rect[1])
      p2 = Point(obj2.coord_rect[0], obj2.coord_rect[1])
      pole = (p1 - p2).polar()

      angle = math.degrees(pole[1])
      #print "angle=",angle
      
      
      #print "ANGLE=", angle
      #location of the master relative to the clone
      location_of_master = None
      
      x10 = obj1.coord_rect[0]
      y10 = obj1.coord_rect[1]     
      x11 = obj1.coord_rect[2]
      y11 = obj1.coord_rect[3]
      
      x20 = obj2.coord_rect[0]
      y20 = obj2.coord_rect[1]
      x21 = obj2.coord_rect[2]
      y21 = obj2.coord_rect[3]
      
      #all to be set to None
      x1 = None
      y1 = None
      x2 = None
      y2 = None
     
      position = None #position relative to the master (needed for arrowhead
      side_angle = 22.5
      if angle > 135 or angle < -135:
            #print "RIGHT"            
            position = "RIGHT" 
            if angle > 180-side_angle or angle < -180+side_angle:
                position = "REALLY RIGHT"
                x1=x11
                y1=(y11+y10)/2
                x2 = x20
                x3 = x20-dx
                y3 = y2 = (y21+y20)/2 
                          
            elif angle > 135:
                position =  "RIGHT TOP" 
                x1=x11
                y1=(y10)
                x2 = x20
                x3 = x20-dx
                y3 = y2 = (y21)
                
            else:
                position =  "RIGHT BOTTOM"
                x1=x11
                y1=(y11)
                x2 = x20
                x3 = x20-dx
                y3=y2 = (y20)
            
      elif angle < -45 and angle >= -135:
            #print "TOP"
            position = "TOP" 
            if angle > -90-side_angle and angle < -90+side_angle:
                position =  "REALLY TOP"
           
                x1=(x11+x10)/2
                y1= y11
                x3 = x2 = (x21+x20)/2
                y2 = y20
                y3 = y20-dy
            elif angle > -90+side_angle:
                print "TOP LEFT"
                x1=x10
                y1= y11
                x3 = x2 = x21
                y2 = y20
                y3 = y20-dy
            else:
                position =  "TOP RIGHT"
                x1=(x11)
                y1= y11
                x2 = (x20)
                y2 = y20-dy            
      elif angle >= -45 and angle < 45:
            #print "LEFT"            
            position = "LEFT"
            if angle > -side_angle and angle < side_angle:
                position =  "REALLY LEFT"            
                x1=x10
                y1=(y11+y10)/2
                x2 = x21+dx
                y2 = (y21+y20)/2
            elif angle > side_angle:
                position =  "TOP LEFT"     
                x1=x10
                y1=y10
                x2 = x21+dx
                y2 = y21
            else:
                position =  "BOTTOM LEFT"  
                x1=x10
                y1=y11
                x2 = x21+dx
                y2 = y20
            
            
      elif angle >= 45 and angle <= 135:
            #print "BOTTOM" 
            position = "BOTTOM"
            if angle > 90-side_angle and angle < 90+side_angle:            
                position =  "REALLY BOTTOM"
                x1=(x11+x10)/2
                y1= y10
                x2 = (x21+x20)/2
                y2 = y21+dy
            elif angle > side_angle+90:
                position =  "BOTTOM RIGHT"
                x1=(x11)
                y1= y10
                x2 = (x20)
                y2 = y21+dy 
            else:
                position =  "BOTTOM LEFT"

                x1=(x10)
                y1= y10
                x2 = (x21)
                y2 = y21+dy            
            
            '''if (not(angle > 89 and angle < 91)):
                print "f"
                x1=x11
                x2=x20'''           
      #print position            
   
      #self.device.DrawLineXY(x10, y11,x21, y21 ) 
      #self.device.DrawLineXY(x10, y10,x20, y20 ) 
      self.device.SetLineDash()
      color = 0x666666
      self.device.SetFillColor(color)
      #we need the angle between the final points, not the original angle
      p3 = Point(x1, y1)
      p4 = Point (x2, y2)
      pole2 = (p3 - p4).polar()                                                  
      self.device.DrawLineXY(x1, y1,x2+self.arrow_length*cos(pole2[1]), y2+self.arrow_length*sin(pole2[1]) ) #20 is the length of arrow
      
      self.device.SetLineSolid()
      
      return x2, y2, position,pole2[1]

       #edit except color replace
    def replace_object_in_clone_tree(self,object, new_object):
        
        undo = self.replace_object_in_clone_tree, [new_object], object[0]
        self.clear_parent_array_data()
        self.FindParentArray(self.clones, object)
        #self.find_parent(self.clones, self.clones,  object)
        if self.parent_array == None:
            print "Could not replace object in clone tree!!!"
            return NullUndo
        
        #do the swapping
        index = self.index_of_object_in_the_parent_array
        self.parent_array[index] = [new_object]
                
        return undo
    
    def edit_object(self, pObj, selection):        
        object = pObj[0]
        offset = Point (object.coord_rect[0]-selection.coord_rect[0], object.coord_rect[1]-selection.coord_rect[1])
        #self.SelectObject(object)
       #the following few lines are a copy of SelectObject method, but without being wrapped into a transaction, since we are in the transaction already 
        self.select_object(object)
        #print "selected object = ",  object
        #print "selected selection",  selection
        self.add_undo(self.remove_selected())  
        newobj = selection.Duplicate()
        #update clones databse
        #object = newobj
        self.add_undo(self.replace_object_in_clone_tree(pObj, newobj))
        pObj[0] = newobj
        #print "pObj2 = ",  pObj
        newobj.Translate(offset)                                  
        select, undo_insert = self.insert(newobj)
        self.add_undo(undo_insert)
        #self.__set_selection(select, SelectSet)
        self.__set_selection(None, SelectSet)
        self.add_undo(self.queue_edited())                                                
        self.add_undo(self.view_redraw_all())  
        
####### 
        '''       
        self.copy_tree(clone_tree_copy,self.clones)
        self.clear_parent_array_data()
        self.find_parent(clone_tree_copy, clone_tree_copy,  object)        
        if self.parent_array == None:
            print "Something bad happened! Search me to see!"
            return
        we are not going to remove shit here. it has to be replaced properly.
        self.parent_array.remove(pObj)
               #delete empty list
        self.remove_empty_list(clone_tree_copy, clone_tree_copy)
        self.add_undo(self.view_redraw_all())
        self.add_undo(self.set_clone_tree([clone_tree_copy]))
        '''
        
        
        
  
    
    skip = 0
    current_edit = 0
    
    def edit_all_in_sublist(self, target,obj, func, arg):
        temp = self.current_edit
        for item in target:
           if isinstance(item[0], list):    # is item a polygon?               
               #if func == "draw_errors":
               #add previous which is not a list (roll back if necessary)               
               object = item               
               while isinstance(object[0], list):
                    index = target.index(object)
                    object = target[index-1]
                
               self.arrow_stack.append(object)     
               
               self.edit_all_in_sublist(item,obj, func, arg)      # Recursive version
           else:               
               length = len(item)
               
               for i in range(length):                    
                    if func == "draw_arrows":                                               

                        '''width = 10
                        length = 20
                        dx = 20
                        dy = 10                        
                        
                        x = item[i].coord_rect[2]+dx
                        y = item[i].coord_rect[3]- dy
                        #path = [(x, y+width), (x+length, y+0.0),(x+0.0, y-width), (x+0.0, y+width)]
                        path = [(x, y-width), (x-length, y), (x, y+width), (x, y)]                        
                        
                        a = Arrow(path, 1)
                        self.device.SetFillColor(65280)                                                
                        a.Draw(self.device)'''
                        
                        #draw arrow line
                        
                        #print "arrow_stack = ", self.arrow_stack
                        '''print "------------------------"
                        print "parent_array=", self.parent_array
                        print "lastitem", self.last_item 
                        print "i=", i, "itemi=", item[i]'''
                        
                        if self.prev_target != None and isinstance(self.prev_target[0], list):
                           if self.arrow_stack != []:
                               #print "STACK=", self.arrow_stack                               
                               popped_object = self.arrow_stack.pop()
                               #coordinates of the arrowhead and direction/position                               
                               x, y, position, angle = self.draw_arrow_line(item[i], popped_object[0])
                               self.draw_arrow_head(item[i], x, y, position, angle, popped_object[0])
                               ''''x0 = item[i].coord_rect[0]+dx                           
                               x2 = popped_object[0].coord_rect[2]+dx
                               y2 = popped_object[0].coord_rect[3]- dy
                               self.device.DrawLineXY(x0, y,x2, y2 )'''
                           else:
                                print "GOD FORBID TO END UP HERE!"
                        elif self.last_item != None:
                        #coordinates of the arrowhead and direction/position
                           x, y, position,  angle = self.draw_arrow_line(item[i], self.last_item)                           
                           self.draw_arrow_head(item[i], x, y, position, angle, self.last_item)
                           '''x0 = item[i].coord_rect[0]+dx                           
                           x2 = self.last_item.coord_rect[2]+dx
                           y2 = self.last_item.coord_rect[3]- dy
                           self.device.DrawLineXY(x0, y,x2, y2 )'''                        


                        self.last_item = item[i]
                    elif func != None: #filling color (filling color is currently independent from editing an object)
                        if self.skip != 0 and self.current_edit % self.skip == 0:
                            "do nothing"
                        else :
                            self.select_object(item[i])
                            func(arg)
                        self.current_edit+=1
                    else:
                        #self.edit_object(item[i], obj)
                        #print "self.current_edit % self.skip=", self.current_edit % self.skip
                        if self.skip != 0 and self.current_edit % self.skip == 0:
                            "do nothing here" #we skip                            
                        else:
                            
                            #print "itembefore=",item[i]
                             
                             #item is always equal to 1                           
                            self.edit_object(item,obj)
                            
                            #print "itemafter=",item[i],"fdfd",item
                            
                            ''' #object = item[i]
                            #print "obj1=",object
                            print "obj1=",object
                            selection = obj
                            offset = Point (object.coord_rect[0]-selection.coord_rect[0], object.coord_rect[1]-selection.coord_rect[1])
                            self.select_object(object)
                            #print "selected object = ",  object
                            #print "selected selection",  selection
                            self.add_undo(self.remove_selected())  
                            newobj = selection.Duplicate()
                            #update clones databse
                            #object = newobj
                            item[i] = newobj
                            newobj.Translate(offset)                                  
                            select, undo_insert = self.insert(newobj)
                            self.add_undo(undo_insert)
                            #self.__set_selection(select, SelectSet)
                            self.__set_selection(None, SelectSet)
                            self.add_undo(self.queue_edited())                                                
                            self.add_undo(self.view_redraw_all())
                            '''    
                        self.current_edit+=1
                    

           self.prev_target = item
        self.current_edit = temp

    def edit_from(self, start,array,obj, func, arg):        
        if start >= len(array) or start < 0 :
            return
        else:
            if not (isinstance (array[start][0],list)):
                #self.edit_object(array[start], obj)  
                
                #the following is just a cope of EDIT_OBJECT method
                #i did not bother to make it work without code duplication.
                print "func=", func
                if func != None: #filling color
                        if self.skip != 0 and self.current_edit % self.skip == 0:
                            "do nothing here"
                        else:
                            self.select_object(array[start][0])
                            func(arg)
                        self.current_edit+=1
                else:
                    #print "self.current_edit % self.skip=", self.current_edit % self.skip
                    if self.skip != 0 and self.current_edit % self.skip == 0:
                        #we skip
                        "do nothing here"
                    else:
                        
                        #print "arraybefore=",array[start]
                        self.edit_object(array[start],obj)
                        #print "arrayafter=",array[start]
                        #print "obj2=",object
                        
                        '''
                        object = array[start][0]
                        selection = obj
                        offset = Point (object.coord_rect[0]-selection.coord_rect[0], object.coord_rect[1]-selection.coord_rect[1])
                        self.select_object(object)
                        self.add_undo(self.remove_selected())  
                        newobj = selection.Duplicate()
                        #update clones databse
                        #object = newobj
                        array[start][0] = newobj                
                        newobj.Translate(offset)                                  
                        select, undo_insert = self.insert(newobj)
                        self.add_undo(undo_insert)
                        #self.__set_selection(select, SelectSet)
                        self.__set_selection(None, SelectSet)
                        self.add_undo(self.queue_edited())                                                
                        self.add_undo(self.view_redraw_all()) 
                        '''    
                    self.current_edit+=1
                
                self.edit_from(start+1,array,obj, func, arg)
            else:
                self.edit_all_in_sublist(array[start],obj, func, arg)
                self.edit_from(start+1,array,obj, func, arg)
    
    parent_array = None
    index_of_object_in_the_parent_array = None
    
    def clear_parent_array_data(self):
        self.parent_array = None
        self.index_of_object_in_the_parent_array = None
    
    
    def EditClones(self, func = None, arg = None  ): #func can be fill_solid from canvas, and col is its argument
        #if it's MOVE OBJECTS... then we ignore this for now
        if self.transaction_name == _("Move Objects"):
            self.add_undo(self.view_redraw_all()) #this is to prevent undo arrow screw ups, not the best place to put it but it works
            return        
        obj = self.selection.GetObjects()[0]       
        
        self.clear_parent_array_data()          
        self.find_parent(self.clones,self.clones, obj)
        #print "before editing clones = ",  self.clones
        #print "before editing selection = ",  obj
        #print "before editing parent array",   self.parent_array                 
        
        #print "obj =",  obj        
        #print "parent=",  self.parent_array
        
        self.current_edit = 1
        #self.skip
        if self.parent_array == None:
            #we have nothing to do here, since this is not a clone
            if func != None: #if it's fill_solid then color the object
                func(arg)
                
            #added by shumon May 26,2009 ---start
            #parent array is empty so it means this could be tiled clones, lets check
            '''self.clear_parent_array_data()          
            self.find_parent(self.tile_clones,self.tile_clones, obj)
            if  self.parent_array != None:
                self.edit_all_tiles(obj, func, arg)'''
            #print "kosyak"
            #----end by added by shumon May 26, 2009
            return        
        
        #print "obj2 =",  obj        
        #print "parent2=",  self.parent_array
        
        #this solves the problem of messed up arrows if you click on the object in edit mode
        if self.Mode() == EditMode:
            self.SetMode(SelectionMode)
        
        string = 'clone_editing_box_displayed'
        self.log(string)
        self.main_window.total_call_editing_box_displays+=1
        #for task i only
        current_time =  time.time()
        elapsed_time = current_time - self.main_window.start_time
        
        if self.main_window.first_editing_box_displayed_time == 0:#equals zero because we record first time only  
            self.main_window.first_editing_box_displayed_time=elapsed_time
        
        result = self.main_window.application.MessageBox(title = self.title,  message = self.message,  buttons = self.Calendar)
        
        #if it's fill_solid then color the object
        #it colors it for both cases: if the user selected only this object,
        #or if the user selected all the objects or all the following
        #it colors the first object, while recursive calls color the rest
        #print "obj3 =",  obj        
        #print "parent3=",  self.parent_array
        
        #SO WEIRD!!!!!!!!!!!!!!!!!!!!!!
        ''''if func != None: 
            print "I iz been to Document"
            func(arg)
        '''
        #print "obj4 =",  obj        
        #print "parent4=",  self.parent_array
        #if you want to edit all the clones, then delete the old stuff and replace it with new, keep the order        
        
        if result == self.Cancel:
            #self.abort_transaction()
            #to make this work for resizing and all other mouse dragging related stuff. preserve the original object and replace it here, if you want to fix the issue
            string = 'clone_editing_cancel_pressed'            
            self.log(string)
            self.main_window.total_call_editing_cancel_presses+=1
            return
        
        if result == self.AllTheObjects :           
           #self.edit_all_in_sublist(self.parent_array, obj) #not correct yet
           string = 'clone_editing_all_pressed'
           self.log(string)
           self.edit_all(obj, func, arg)
           self.main_window.total_clone_editing_all_presses+=1
        
        elif result == self.AllTheFollowing or result == self.AllTheFollowingSkippingOne:   
            
            #there was +1 in the first argument before i found problem with WEIRD
            if result == self.AllTheFollowingSkippingOne:
                self.skip = 2
                
                string = 'clone_editing_skip_pressed'
                self.log(string)
                self.main_window.total_clone_editing_skip_presses += 1
            else:
                string = 'clone_editing_all_following_pressed'
                self.log(string)
                self.main_window.total_clone_editing_all_following_presses +=1
            
            self.edit_from(self.index_of_object_in_the_parent_array, self.parent_array, obj, func, arg)
            
        else: #result is only this object
            #color single object i suppose
            string = 'clone_editing_selected_pressed'
            self.log(string)
            self.main_window.total_clone_editing_selected_presses += 1
            
            if func != None:
             func(arg)

        #print "after editing clones = ",  self.clones
        #print "after editing selection = ",  obj
        
        self.skip = 0 #reset skipping


    
    def FindParentArray(self,  array, object):
        for i in range (len(array)):
            this = array[i]
            if this == object:
                self.parent_array = array
                self.index_of_object_in_the_parent_array = array.index(object)
                #print "parent =",array
                #print "index =", array.index(object)	
                return
            elif isinstance(this, type([])):                
                self.FindParentArray(this, object)    
    
    
    
    def find_parent(self, target,parent,obj):
       for item in target:
           if isinstance(item[0], list):                 # is item a polygon?
               self.find_parent(item,item,obj)              # Recursive version
           else:           
               length = len(item)
               for i in range(length):
                if obj == item[i]:
                    #print "found item =",item[i]
                    #print "parent = ", parent        
                    #print "index = ",parent.index([item[i]])
                    self.parent_array = parent
                    self.index_of_object_in_the_parent_array  = parent.index([item[i]])

    def DeleteClone(self, object):
        #preserve clone tree copy for undo
        clone_tree_copy = []
        for i in self.clones:
            clone_tree_copy.append(i[:])
        
        self.add_undo(self.set_clone_tree([clone_tree_copy]))
        
        print "clones before deletion", self.clones
        self.delete_clone(self.clones, self.clones, object)
        self.remove_empty_list(self.clones, self.clones)
        
        
        print "clones after deletion=", self.clones
    
    def remove_empty_list(self,L,original):
        for item in L:
            if item == []:
                L.remove(item)
		self.remove_empty_list(original,original)
		return
            elif isinstance(item[0],list):
                self.remove_empty_list(item,original)
    
    def delete_clone(self, target,parent,obj):       
       for item in target:
           if isinstance(item[0], list): 		        # is item a polygon?
               self.delete_clone(item,item,obj)  	        # Recursive version
           else:           
               length = len(item)
               for i in range(length):
                if obj == item[i]:
                    parent.remove([obj])

    


    
    '''def find(self, L,parent,object):    
        # if its empty do nothing
        if not L: return 
        # if it's a list call Find on 1st element
        if type(L[0]) == type([]):
            self.find(L[0],L[0],object)
        elif L[0] == object: #no list so just print 
            self.parent_array = parent
            self.index_of_object_in_the_parent_array  = parent.index(object)	
           #print "parent=",parent
        # now process the rest of L 
        self.find(L[1:],parent,object)'''
  

    drag_objects = []
    
    
   

    def copy_tree(self,new,old):
        for i in old:
            temp = []
            if isinstance(i[0],list):
                #print i, "is a list"        
                self.copy_tree(temp,i)
            else:
                #print i, "i normal"
                new.append(i)
            if temp != []:
                    #print "temp not empty"
                    new.append(temp)    
    
    def DragCreation(self):
     if True: #self.CanCreateClone() prevents from cloning groups... disabled for now 
        length = len(self.draglist)
        if length < 1:
            #print "length < 1EditCl"
            return                
        
        if len(self.clones) > 0:
            print "Warning - clones list has stuff in it - expect problems - problem needs to be solved - right now assuming only one drag creation takes place"          
        

        self.begin_transaction(_("Create Clone"))
        try:
            try:
                objects = self.selection.GetObjects()
                no_objects = len(objects)
         
                for c in range (no_objects):
                    if c > 0: #if the selection is a compound
                        select = ((0,1),objects[c])
                        self.__set_selection(select, SelectSet)

                    #we need to merge with existing list of clones, if dragcreating from an exist clone
                    object = self.selection.GetObjects()[0]
                    new_array = []        
                    #I am going through all this trouble with clone_tree_copy just for the undo to work
                    clone_tree_copy = []
                    self.copy_tree(clone_tree_copy,self.clones)
                    self.clear_parent_array_data()
                    self.find_parent(clone_tree_copy, clone_tree_copy,  object)   
                         
                    if self.parent_array == None:            
                        new_array.append([object]) #we need every object to be inside of array because of the way python is passing arguments into function
                        print "appended to new"
                    else:
                        #if it already exists, we need to insert a new array after the object entry            
                        if self.index_of_object_in_the_parent_array == len(self.parent_array) - 1:
                            new_array = self.parent_array
                            print "appended to clones1"
                        else: 
                            self.parent_array.insert(self.index_of_object_in_the_parent_array+1, new_array)    
                            print "appended to clones2"

                    off_rc = Point (0,0)
                    '''for j in range(0, len(self.grid_clones)):           
                        if j == 1 :
                            length = length + 1 #one extra for subseq rows/cols     
                            if self.more == 'x':
                                off_rc = Point (-self.draglist[-1].x+self.draglist[0].x,-self.grid_clones[0].y+self.grid_clones[1].y)
                            elif self.more == 'y':
                                off_rc = Point (-self.grid_clones[0].x+self.grid_clones[1].x,-self.draglist[-1].y+self.draglist[0].y)

                        #elif j > 1 : off_rc = Point (-self.draglist[-1].x+self.draglist[1].x,-self.grid_clones[0].y+self.grid_clones[1].y)
                        print off_rc''' 
                        
       
                    for i in range(1,length):     
                        offset = self.draglist[i] - self.draglist[i-1]
                        obj = self.selection.GetObjects()[0]
                        
                        newobj = obj.Duplicate()
                        '''if i == 0 and j > 0:
                            offset=off_rc#+compound_offset)                
                        else:
                            pass'''
                        newobj.Translate(offset)
                                             
                        select, undo_insert = self.insert(newobj)
                        self.add_undo(undo_insert)                
                        self.__set_selection(select, SelectSet)                        
                        new_array.append([newobj])       #new way
                        self.add_undo(self.view_redraw_all())
                    
                    
                    if len(self.grid_clones) > 1:
                        list_of_lines = []
                        for i in range(0,len(new_array)):
                            self.select_object(new_array[i])
                            line = []
                            
                            for j in range(0, len(self.grid_clones)-1):
                                '''if self.more == 'x':
                                    off_rc = Point (-self.draglist[-1].x+self.draglist[0].x,-self.grid_clones[0].y+self.grid_clones[1].y)
                                elif self.more == 'y':
                                    off_rc = Point (-self.grid_clones[0].x+self.grid_clones[1].x,-self.draglist[-1].y+self.draglist[0].y)
                                '''
                                offset = self.grid_clones[1] - self.grid_clones[0]

                                obj = self.selection.GetObjects()[0]
                                
                                newobj = obj.Duplicate()
                                newobj.Translate(offset)
                                                     
                                select, undo_insert = self.insert(newobj)
                                self.add_undo(undo_insert)                
                                self.__set_selection(select, SelectSet)                        
                                line.append([newobj])       #new way
                            list_of_lines.append(line)
                            self.add_undo(self.view_redraw_all())                           
                        #now insert these things into the new_array
                        index = 1
                        size = len(list_of_lines)
                        for i in range (0, size):
                            if i < size - 1:
                                new_array.insert(index,list_of_lines[i])
                            else:
                                #just append these
                                for j in list_of_lines[i]:
                                    new_array.append(j)
                            index+=2
                            
                        print "new_array="
                        for i in new_array: print i
                       
                    
                    if self.parent_array == None:
                        clone_tree_copy.append(new_array)                            
                    self.drag_objects = new_array
                    self.add_undo(self.set_clone_tree([clone_tree_copy]))  
            except:
                self.abort_transaction()
        finally:
            self.end_transaction()
        self.main_window.total_direct_clones_created += length #for statistics
        self.ClearDragCreationData()           


    def set_clone_tree(self, array):        
        #print "new_array:", old_array, "new_new_array", new_array
        
        clone_tree_copy = []
        #for i in self.clones:
        #    clone_tree_copy.append(i[:])
        self.copy_tree(clone_tree_copy, self.clones)        
        
        undo = self.set_clone_tree, [clone_tree_copy]
        #print "BEFORE ARRAY=", self.clones
        self.clones = array[0]
        
        #print "new_array:", old_array, "new_new_array", new_array        
        self.view_redraw_all()
        
        #print "AFTER ARRAY=", self.clones
        return undo

    
    def UnlinkClone(self):
        string = 'unlink_clone_called'
        self.log(string)
        self.main_window.total_unlink_clone_calls += 1

          
        self.begin_transaction(_("Unlink Clone")) #wrapping around transaction for the undo
        try:
            try:      
                self.EditClones(self.unlink_clone)
            except:
                self.abort_transaction()
        finally:
            self.end_transaction()
        
    def unlink_clone(self,arg = None): #arg is ignored, its here because editclones is shared with color
        clone_tree_copy = []
        #for i in self.clones:
        #    clone_tree_copy.append(i[:])
        
        self.copy_tree(clone_tree_copy,self.clones)
        
        
        object = self.selection.GetObjects()[0]
        self.clear_parent_array_data()
        self.find_parent(clone_tree_copy, clone_tree_copy,  object)        
        if self.parent_array == None:
            return
            
        #self.begin_transaction(_("Unlink Clone"))
        #try:
         #   try:
        self.parent_array.remove([object])
               #delete empty list
        self.remove_empty_list(clone_tree_copy, clone_tree_copy)
        self.add_undo(self.view_redraw_all())
          #  except:
           #     self.abort_transaction()
        #finally:
        self.add_undo(self.set_clone_tree([clone_tree_copy]))
         #   self.end_transaction()            
        
        
    def CanUnlinkClone(self):
        #this may slow down menu popping up if implemented, because it will use recursion
        return 1
   
    def UnlinkAll(self):
        object = self.selection.GetObjects()[0]
        
        clone_tree_copy = []
        #for i in self.clones:
        #    clone_tree_copy.append(i[:])
        self.copy_tree(clone_tree_copy,self.clones)
        
        series = self.find_original_ancenstor_array([clone_tree_copy],object)
        if series == None:
            print "object doesn't belong to any clone series"
            return        
        
        self.begin_transaction(_("Unlink All Clones"))
        try:
            try:
                clone_tree_copy.remove(series)
                #delete empty list (just in case)
                self.remove_empty_list(clone_tree_copy, clone_tree_copy)
                self.add_undo(self.view_redraw_all())
            except:
                self.abort_transaction()
        finally:
            self.add_undo(self.set_clone_tree([clone_tree_copy]))
            self.end_transaction()
    
    def CanUnlinkAll(self):
        #not implemented yet
        return 1
    
    def BreakClones(self): #default parameter here to be used with delete clone
        string = 'break_clones_called'
        self.log(string)
        self.main_window.total_break_clones_calls += 1
        
        object = self.selection.GetObjects()[0]
        
        clone_tree_copy = []
        #for i in self.clones:
        #    clone_tree_copy.append(i[:])
        self.copy_tree(clone_tree_copy,self.clones)
        
        self.clear_parent_array_data()
        self.find_parent(clone_tree_copy, clone_tree_copy,  object)
        if self.parent_array == None:
            print "Could not break the clones"
        index = self.parent_array.index([object])
        self.begin_transaction(_("Break Clones"))
        try:
            try:
                '''if 0 == 1: #redundant step method turned out to have it put it back to index == 0
                    new_series = self.parent_array[:]
                    old_parent = self.parent_array
                    #find parent of parent
                    old_parent = self.parent_array
                    self.clear_parent_array_data()
                    
                    self.FindParentArray([clone_tree_copy], old_parent) 
            
                    
                    if self.parent_array != None:
                        #found
                        self.parent_array.remove(old_parent)
                        
                        #delete empty list (just in case)
                        self.remove_empty_list(clone_tree_copy, clone_tree_copy)
                        clone_tree_copy.append(new_series)
                        
                        self.add_undo(self.set_clone_tree([clone_tree_copy]))
                        
                        self.add_undo(self.view_redraw_all())            
                #elif index == len(self.parent_array)-1:
                 #   print "will not break because it's the last element in the series branch"
                else:'''

            
                new_series = []
                #print "self.clones before break:",self.clones
                for i in range(index,len(self.parent_array)):
                    arr = self.parent_array[i]
                    new_series.append(arr[:])                    
                for i in range(index,len(self.parent_array)):
                    self.parent_array.pop() 
                    #print "self.clones after pop:",clone_tree_copy 
                #if the last one is an array then all the arrows will be screwed up
                #so we have to remove it from the array
                #print "parentarr=",self.parent_array
                #this still would crash and i dont know why (list index out of range)
                if isinstance(self.parent_array[-1][0],list):
                    
                    
                    temp = []
                    self.copy_tree(temp,self.parent_array[-1])
                    #pop last object
                    self.parent_array.pop()
                    for i in temp:
                        self.parent_array.append(i)
                                      
                self.remove_empty_list(clone_tree_copy, clone_tree_copy)
                clone_tree_copy.append(new_series) 
                self.add_undo(self.set_clone_tree([clone_tree_copy]))
                self.add_undo(self.view_redraw_all())    
                #print "self.clones after append:",self.clones

                        
                
            except:
                self.abort_transaction()
        finally:
            
            self.end_transaction()
            
        
    def CanBreakClones(self):
        return 1
    
    #this is original skencil's mehtod, for unimplemented skencil clones, i commented it out
    '''def UnlinkClone(self):
        self.begin_transaction("Unlink Clone")
        try:
            try:
                obj = self.CurrentObject()            
                #obj.unregister()                                          
                #obj.register_as(dupe)                    
                dupe = obj._original.Duplicate()                          
                
                #obj._original = dupe
                #obj.orig_changed()                    
                #obj.register_as(dupe)
                obj.unregister()
                obj._original = dupe
                #obj._center = dupe._center
                #obj._offset = dupe._offset
                obj.register()
                #undo = obj.parent.ReplaceChild(obj, dupe)
                
                #self.add_undo(undo)                    
                #self.add_undo(self.queue_edited())
            except:
                self.abort_transaction()
        finally:
            self.end_transaction()        

        
        #print "obj = ",  obj    
        #print "obj.parent.objects = ",  obj.parent.objects
        #for i in obj.parent.objects[]:
        #print obj.parent.objects[i]
    
    def CanUnlinkAllClonesAfter(self):
        return 0
    
    def UnlinkAllClonesAfter(self):
        self.begin_transaction("Unlink All Clones After")
        try:
            try:
                obj = self.CurrentObject()            
                dupe = obj._original.Duplicate()                                          
                obj.unregister()
                obj._original = dupe
                obj.register()
            except:
                self.abort_transaction()
        finally:
            self.end_transaction()    
    '''
    def ToggleSelectionBehaviour(self):
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		if self.selection.__class__ == SizeSelection:
            #the following line changed to pass by shumon to prevent toggling June 27, 2009
		    pass#self.selection = TrafoSelection(self.selection)
		elif self.selection.__class__ == TrafoSelection:
		    self.selection = SizeSelection(self.selection)
		self.queue_selection()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def DrawDragged(self, device, partially = 0):
        self.selection.DrawDragged(device, partially)        


    def DrawCloneGuides(self, device, partially = 0):
        #self.draw_outlines(device, self.draglist, partially)
        arr = []
        
        for i in self.draglist:
            for j in self.grid_clones:
                #print self.more,"more"
                if self.more == 'x' : arr.append(Point(i.x,j.y))
                elif self.more == 'y' : arr.append(Point(j.x,i.y))
        self.draw_outlines(device, arr, partially)
        
    def draw_outlines(self, device, list, partially = 0):
    #this is really stupid
    #for some reason in skencil
    #different types of objects have different interpretations of bounding boxes or whatever
    #anyway just hacking here to make things done
        
        length = len(list)  
        #print "l=", length, "dl=", self.draglist
        if length >= 2:            
                        
            
            #print "drag", self.draglist
            #obj2 = self.selection
            obj = self.selection.coord_rect
            #rect = obj.coord_rect
            
            for i in range(1, length):           
                p0 = p = list[i]
                # a selection would have None object type
                
                #if it's an ellipse or a clone of an ellipse
                if  isinstance(obj, Ellipse):# or isinstance(obj, Clone) and isinstance(obj._original, Ellipse):
                    #print "It's an Ellipse"    
                    #p = Point(p.x-self.selection_width/2, p.y+self.selection_height/2)
                    p0 = Point(p.x+self.selection_width,  p.y-self.selection_height)
                    
                elif isinstance(obj, Rectangle):# or  isinstance(obj, Clone) and isinstance(obj._original, Rectangle):                
                    #print "It's a Rectangle"
                    #p = Point(p.x - self.selection_width, p.y)
                    p0 = Point(p.x+self.selection_width, p.y-self.selection_height)                
                elif isinstance(obj, PolyBezier):# or  isinstance(obj, Clone) and isinstance(obj._original, PolyBezier):
                    #print "It's a Polybezier" 
                    p0 = Point(p.x+self.selection_width,  p.y-self.selection_height)                                
                else:
                    #print "unable to draw guide - unrecognized clone type"
                    #this is for jpegs and all that
                    p0 = Point(p.x+self.selection_width, p.y-self.selection_height)            
                
                #print "p=", p, "p0=", p0
                device.DrawRubberRect(p, p0)    
        

    device = None #added by shumon
    
    def draw_master_outline(self):
        obj = self.selection.GetObjects()[0]       
        master = self.find_original_ancenstor_array([self.clones],obj)
        try:            
            while True: master = master[0]
        except:
            pass
        color = 0x666666
        
        self.device.SetLineDash()
        x1 = master.bounding_rect[0]
        x2 = master.bounding_rect[2]
        y1 = master.bounding_rect[1]
        y2 = master.bounding_rect[3]
        
        dx = x2-x1
        dy = y2-y1
        
        #self.device.DrawLineXY(x1, y1,x2, y2 )         
        self.device.DrawLineXY(x1, y1,x1+dx, y1)         
        self.device.DrawLineXY(x1, y1,x1, y1+dy)
        self.device.DrawLineXY(x2, y2,x2-dx, y2)         
        self.device.DrawLineXY(x2, y2,x2, y2-dy)         
         
        self.device.SetLineSolid()

        '''color = 0x666666
        self.device.SetFillColor(color)
        p3 = Point(x1, y1)
        p4 = Point (x2, y2)
        pole2 = (p3 - p4).polar()                                                  
        self.device.DrawLineXY(x1, y1,x2+self.arrow_length*cos(pole2[1]), y2+self.arrow_length*sin(pole2[1]) )         
        self.device.SetLineSolid()
      '''
    def draw_arrows(self):
        if self.device == None:
            return
        
        objects = self.selection.GetObjects()
        if objects == []:
            return
        
        obj = self.selection.GetObjects()[0]       
        self.clear_parent_array_data()   
        #sometimes, if user is screwing around it's possible to create empty array. let's make sure
        #there never be any        
        self.remove_empty_list(self.clones, self.clones)
        self.find_parent(self.clones,self.clones, obj)        
        #print "SetArrowParent = ", self.parent_array
        if self.parent_array == None:
            return #this object doesn't have a parent array, so no point to draw anything here
        
        self.arrow_head_list = []
        # Important! resetting last item
        self.last_item = None 
        #self.clear_arrow_drawing_data()       
  
        self.edit_all(obj, "draw_arrows", 0)
        self.draw_master_outline()
        
        '''width = 100
        length = 100
        dx = 200
        dy = 200
        path = [(dx, dy+width), (dx+length, dy+0.0),(dx+0.0, dy-width), (dx+0.0, dy+width)]
        a = Arrow(path, 1)
        #a.Draw(device)
        p = Point(dx, dy)
        '''
        #device.draw_arrow(a, width, p,  [1, 1])
        #center = Point(200, 200)        
        #self.device.SetFillColor(65280)
        #self.device.FillCircle(center, 20)
        #self.device.SetFillColor(0)
    #have to draw clone guides in both show and hide (they are exclusive and if call drawcloneguides in just one of them it will flicker
        
    
    def Hide(self, device, partially = 0):
        #print "device = ",  device
        self.selection.Hide(device, partially)
        self.DrawCloneGuides(device,partially)
        

    def Show(self, device, partially = 0):        
        self.selection.Show(device, partially)
        self.DrawCloneGuides(device,partially)
        


    def ChangeRect(self):
	return self.selection.ChangeRect()

    #CreateC
    #	The undo mechanism
    #

    def __init_undo(self):
	self.undo = UndoRedo()

    def CanUndo(self):
	return self.undo.CanUndo()
    script_access['CanUndo'] = SCRIPT_GET

    def CanRedo(self):
	return self.undo.CanRedo()
    script_access['CanRedo'] = SCRIPT_GET

    def do_stuff(self):
        info = self.undo.undoinfo[0]
        if _("Create Clone") == info[0]:
            print "hujase!"
            #self.Hide(self.device)
            #self.draw_arrows()
            self.DeleteClone(self.drag_objects.pop())
        self.undo.Undo()

    def Undo(self):
	if self.undo.CanUndo():
            self.main_window.total_undos += 1
	    self.begin_transaction(_("Undo"),clear_selection_rect = 0)
	    try:
		try:
		    self.undo.Undo() #self.do_stuff()
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction(issue = UNDO)
    script_access['Undo'] = SCRIPT_GET

    def add_undo(self, *infos):
	# Add undoinfo for the current transaction. should not be called
	# when not in a transaction.
	if infos:
	    if type(infos[0]) == StringType:
		if not self.transaction_name:
		    self.transaction_name = infos[0]
		infos = infos[1:]
		if not infos:
		    return
	    for info in infos:
		if type(info) == ListType:
		    info = CreateListUndo(info)
		else:
		    if type(info[0]) == StringType:
			if __debug__:
			    pdebug(None, 'add_undo: info contains text')
			info = info[1:]
		self.transaction_undo.append(info)

    # public version of add_undo. to be called between calls to
    # BeginTransaction and EndTransaction/AbortTransaction
    AddUndo = add_undo

    def __undo_set_sel(self, selclass, selinfo, redo_class, redo_info):
	old_class = self.selection.__class__
	if old_class != selclass:
	    self.selection = selclass(selinfo)
	    self.queue_message(MODE)
	else:
	    # keep the same selection object to avoid creating a new
	    # editor object in EditMode
	    self.selection.SetSelection(selinfo)
	self.queue_selection()
	return (self.__undo_set_sel, redo_class, redo_info, selclass, selinfo)

    def __real_add_undo(self, text, undo, selinfo = None, selclass = None):
	if undo is not NullUndo:
	    if selinfo is not None:
		new_class = self.selection.__class__
		new_info = self.selection.GetInfo()[:]
		if new_info == selinfo:
		    # make both lists identical
		    new_info = selinfo
		undo_sel = (self.__undo_set_sel, selclass, selinfo,
			    new_class, new_info)
		info = (text, UndoAfter, undo_sel, undo)
	    else:
		info = (text, undo)
	    self.undo.AddUndo(info)
	    self.queue_message(UNDO)


    redo_called = 0
    def Redo(self):
	if self.undo.CanRedo():
	    self.begin_transaction(clear_selection_rect = 0)
	    redo_called = 1
	    try:
		try:
		    self.undo.Redo()
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction(issue = UNDO)
    script_access['Redo'] = SCRIPT_GET

    def ResetUndo(self):
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.undo.Reset()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction(issue = UNDO)
    script_access['ResetUndo'] = SCRIPT_GET

    def UndoMenuText(self):
	return self.undo.UndoText()
    script_access['UndoMenuText'] = SCRIPT_GET

    def RedoMenuText(self):
	return self.undo.RedoText()
    script_access['RedoMenuText'] = SCRIPT_GET

    def SetUndoLimit(self, limit):
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		self.undo.SetUndoLimit(limit)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction(issue = UNDO)
    script_access['SetUndoLimit'] = SCRIPT_GET

    def WasEdited(self):
	# return true if document has changed since last save
	return self.undo.UndoCount()
    script_access['WasEdited'] = SCRIPT_GET

    def ClearEdited(self):
	self.undo.ResetUndoCount()
	self.issue(UNDO)

    #
    #

    def apply_to_selected(self, undo_text, func):
	if self.selection:
	    self.begin_transaction(undo_text)
	    try:
		try:
		    self.add_undo(self.selection.ForAllUndo(func))
		    self.queue_selection()
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def AddStyle(self, style):
	if type(style) == StringType:
	    style = self.GetDynamicStyle(style)
	self.apply_to_selected(_("Add Style"),
			       lambda o, style = style: o.AddStyle(style))

    def SetLineColor(self, color):
	# Set the line color of the currently selected objects.
	# XXX this method shpuld be removed in favour of the more
	# generic SetProperties.
	self.SetProperties(line_pattern = SolidPattern(color),
			   if_type_present = 1)

    def SetProperties(self, **kw):
	self.apply_to_selected(_("Set Properties"),
			       lambda o, kw=kw: apply(o.SetProperties, (), kw))

    def SetStyle(self, style):
	if type(style) == StringType:
	    style = self.get_dynamic_style(style)
	    self.AddStyle(style)

    #
    #	Deleting and rearranging objects...
    #

    def remove_objects(self, infolist):
	split = selinfo.list_to_tree(infolist)
	undo = []
	try:
	    for layer, infolist in split:
		undo.append(self.layers[layer].RemoveObjects(infolist))
	    return CreateListUndo(undo)
	except:
	    Undo(CreateListUndo(undo))
	    raise

    def remove_selected(self):
	return self.remove_objects(self.selection.GetInfo())


    def RemoveSelected(self):
        # Remove all selected objects. After successful completion, the
        # selection will be empty.
        if self.selection:
            self.begin_transaction(_("Delete"))
            try:
                try:
                    #check to see if the object to be deleted is part of self.clones
                    obj = self.selection.GetObjects()[0]
                    self.clear_parent_array_data()
                    self.find_parent(self.clones, self.clones,  obj)
                    if self.parent_array !=None:                    
                        self.DeleteClone(obj)
                        string = 'clone_deleted'
                        self.log(string)
                        self.main_window.total_clone_deleted_calls += 1
                    self.add_undo(self.remove_selected())
                    self.__set_selection(None, SelectSet)
                    self.add_undo(self.queue_edited())
                except:
                    self.abort_transaction()
            finally:
                self.end_transaction()


    def __call_layer_method_sel(self, undotext, methodname, *args):
	if not self.selection:
	    return
	self.begin_transaction(undotext)
	try:
	    try:
		split = selinfo.list_to_tree(self.selection.GetInfo())
		edited = 0
		selection = []
		for layer, infolist in split:
		    method = getattr(self.layers[layer], methodname)
		    sel, undo = apply(method, (infolist,) + args)
		    if undo is not NullUndo:
			self.add_undo(undo)
			edited = 1
		    selection = selection + self.augment_sel_info(sel, layer)
		self.__set_selection(selection, SelectSet)
		if edited:
		    self.add_undo(self.queue_edited())
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def MoveSelectedToTop(self):
	self.__call_layer_method_sel(_("Move To Top"), 'MoveObjectsToTop')

    def MoveSelectedToBottom(self):
	self.__call_layer_method_sel(_("Move To Bottom"),'MoveObjectsToBottom')

    def MoveSelectionDown(self):
	self.__call_layer_method_sel(_("Lower"), 'MoveObjectsDown')

    def MoveSelectionUp(self):
	self.__call_layer_method_sel(_("Raise"), 'MoveObjectsUp')

    def MoveSelectionToLayer(self, layer):
	if self.selection:
	    self.begin_transaction(_("Move Selection to `%s'")
				   % self.layers[layer].Name())
	    try:
		try:
		    # remove the objects from the document...
		    self.add_undo(self.remove_selected())
		    # ... and insert them a the end of the layer
		    objects = self.selection.GetObjects()
		    select, undo_insert = self.insert(objects, layer = layer)

		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    #
    #	Cut/Copy
    #

    def copy_objects(self, objects):
	copies = []
	for obj in objects:
	    copies.append(obj.Duplicate())

	if len(copies) > 1:
	    copies = Group(copies)
	else:
	    copies = copies[0]
            # This is ugly: Special case for internal path text objects.
            # If the internal path text object is the only selected
            # object, turn the copy into a normal simple text object.
            # Thsi avoids some of the problems when you "Copy" an
            # internal path text.
            import text
            if copies.is_PathTextText:
                properties = copies.Properties().Duplicate()
                copies = text.SimpleText(text = copies.Text(),
                                         properties = properties)

	copies.UntieFromDocument()
	copies.SetDocument(None)
	return copies

    def CopyForClipboard(self):
	if self.selection:
	    return self.copy_objects(self.selection.GetObjects())

    def CutForClipboard(self):
	result = None
	if self.selection:
	    self.begin_transaction(_("Cut"))
	    try:
		try:
		    objects = self.selection.GetObjects()
		    result = self.copy_objects(objects)
		    self.add_undo(self.remove_selected())
		    self.__set_selection(None, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    result = None
		    self.abort_transaction()
	    finally:
		self.end_transaction()
	return result



    #
    #	Group
    #

    def group_selected(self, title, creator):
        self.begin_transaction(title)
        try:
            try:
                self.add_undo(self.remove_selected())
                objects = self.selection.GetObjects()
                group = creator(objects)
                parent = selinfo.common_prefix(self.selection.GetInfo())
                if parent:
                    layer = parent[0]
                    at = parent[1:]
                else:
                    layer = None
                    at = None
                select, undo_insert = self.insert(group, at = at, layer =layer)
                self.add_undo(undo_insert)
                self.__set_selection(select, SelectSet)
            except:
                self.abort_transaction()
        finally:
            self.end_transaction()

    def CanGroup(self):
	return len(self.selection) > 1

    def GroupSelected(self):
	if self.CanGroup():
            self.group_selected(_("Create Group"), Group)

    def CanUngroup(self):
	infos = self.selection.GetInfo()
	return len(infos) == 1 and infos[0][-1].is_Group

    def UngroupSelected(self):
	if self.CanUngroup():
	    self.begin_transaction(_("Ungroup"))
	    try:
		try:
		    self.add_undo(self.remove_selected())
		    info, group = self.selection.GetInfo()[0]
		    objects = group.Ungroup()
		    select, undo_insert = self.insert(objects, at = info[1:],
						      layer = info[0])
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def CanCreateMaskGroup(self):
	infos = self.selection.GetInfo()
	return len(infos) > 1 and infos[-1][-1].is_clip

    def CreateMaskGroup(self):
	if self.CanCreateMaskGroup():
	    self.begin_transaction(_("Create Mask Group"))
	    try:
		try:
		    import maskgroup
		    self.add_undo(self.remove_selected())
		    objects = self.selection.GetObjects()
		    if config.preferences.topmost_is_mask:
			mask = objects[-1]
			del objects[-1]
			objects.insert(0, mask)
		    group = maskgroup.MaskGroup(objects)
		    parent = selinfo.common_prefix(self.selection.GetInfo())
		    if parent:
			layer = parent[0]
			at = parent[1:]
		    else:
			layer = None
			at = None
		    select, undo_insert = self.insert(group, at = at,
						      layer = layer)
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()


    #
    #	Transform, Translate, ...
    #

    def TransformSelected(self, trafo, undo_text = _("Transform")):
	self.apply_to_selected(undo_text, lambda o, t = trafo: o.Transform(t))

    def TranslateSelected(self, offset, undo_text = _("Translate")):
	self.apply_to_selected(undo_text, lambda o, v = offset: o.Translate(v))

    def RemoveTransformation(self):
	self.apply_to_selected(_("Remove Transformation"),
			       lambda o: o.RemoveTransformation())

    #
    #	Align, Flip, ...
    #
    # XXX These functions could be implemented outside of the document.
    # (Maybe by command plugins or scripts?)
    #

    def AlignSelection(self, x, y, reference = 'selection'):
        if self.selection and (x or y):
	    self.begin_transaction(_("Align Objects"))
	    try:
		try:
                    add_undo = self.add_undo
                    objects = self.selection.GetObjects()
		    if reference == 'page':
			br = self.PageRect()
                    elif reference == 'lowermost':
                        br = objects[0].coord_rect
		    else:
			br = self.selection.coord_rect
		    for obj in objects:
			r = obj.coord_rect
			xoff = yoff = 0
			if x == 1:
			    xoff = br.left - r.left
			elif x == 3:
			    xoff = br.right - r.right
			elif x == 2:
			    xoff = (br.left + br.right - r.left - r.right) / 2

			if y == 1:
			    yoff = br.top - r.top
			elif y == 3:
			    yoff = br.bottom - r.bottom
			elif y == 2:
			    yoff = (br.top + br.bottom - r.top - r.bottom) / 2

			add_undo(obj.Translate(Point(xoff, yoff)))

		    add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def AbutHorizontal(self):
	if len(self.selection) > 1:
	    self.begin_transaction(_("Abut Horizontal"))
	    try:
		try:
		    pos = []
		    for obj in self.selection.GetObjects():
			rect = obj.coord_rect
			pos.append((rect.left, rect.top,
				    rect.right - rect.left, obj))
		    pos.sort()
		    undo = []
		    start, top, width, ob = pos[0]
		    next = start + width
		    for left, top, width, obj in pos[1:]:
			off = Point(next - left, 0)
			self.add_undo(obj.Translate(off))
			next = next + width

		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def AbutVertical(self):
	if len(self.selection) > 1:
	    self.begin_transaction(_("Abut Vertical"))
	    try:
		try:
		    pos = []
		    for obj in self.selection.GetObjects():
			rect = obj.coord_rect
			pos.append((rect.top, -rect.left,
				    rect.top - rect.bottom, obj))
		    pos.sort()
		    pos.reverse()
		    undo = []
		    start, left, height, ob = pos[0]
		    next = start - height
		    for top, left, height, obj in pos[1:]:
			off = Point(0, next - top)
			self.add_undo(obj.Translate(off))
			next = next - height

		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def FlipSelected(self, horizontal = 0, vertical = 0):
	if self.selection and (horizontal or vertical):
	    self.begin_transaction()
	    try:
		try:
		    rect = self.selection.coord_rect
		    if horizontal:
			xoff = rect.left + rect.right
			factx = -1
			text = _("Flip Horizontal")
		    else:
			xoff = 0
			factx = 1
		    if vertical:
			yoff = rect.top + rect.bottom
			facty = -1
			text = _("Flip Vertical")
		    else:
			yoff = 0
			facty = 1
		    if horizontal and vertical:
			text = _("Flip Both")
		    trafo = Trafo(factx, 0, 0, facty, xoff, yoff)
		    self.TransformSelected(trafo, text)
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    #
    #
    #

    def CallObjectMethod(self, aclass, description, methodname, *args):
	self.begin_transaction(description)
	try:
	    try:
		undo = self.selection.CallObjectMethod(aclass, methodname,
						       args)
		if undo != NullUndo:
		    self.add_undo(undo)
		    self.add_undo(self.queue_edited())
		    # force recomputation of selections rects:
		    self.selection.ResetRectangle()
		else:
		    # in case the handles have to be updated
		    self.queue_selection()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def GetObjectMethod(self, aclass, method):
	return self.selection.GetObjectMethod(aclass, method)

    def CurrentObjectCompatible(self, aclass):
	obj = self.CurrentObject()
	if obj is not None:
	    if aclass.is_Editor:
		return isinstance(obj, aclass.EditedClass)
	    else:
		return isinstance(obj, aclass)
	return 0

    # XXX the following methods for blend groups, path text, clones and
    # bezier objects should perhaps be implemented in their respective
    # modules (and then somehow grafted onto the document class?)

    def CanBlend(self):
	info = self.selection.GetInfo()
	if len(info) == 2:
	    path1, obj1 = info[0]
	    path2, obj2 = info[1]
	    if len(path1) == len(path2) + 1:
		return obj1.parent.is_Blend and 2
	    if len(path1) + 1 == len(path2):
		return obj2.parent.is_Blend and 2
	    return len(path1) == len(path2)
	return 0

    def Blend(self, steps):
	info = self.selection.GetInfo()
	path1, obj1 = info[0]
	path2, obj2 = info[1]
	if len(path1) == len(path2) + 1:
	    if obj1.parent.is_Blend:
		del info[0]
	    else:
		return
	elif len(path1) + 1 == len(path2):
	    if obj2.parent.is_Blend:
		del info[1]
	    else:
		return
	elif len(path1) != len(path2):
	    return
	if steps >= 2:
	    import blendgroup, blend
	    self.begin_transaction(_("Blend"))
	    try:
		try:
		    self.add_undo(self.remove_objects(info))
		    try:
			blendgrp, undo = blendgroup.CreateBlendGroup(obj1,obj2,
								     steps)
			self.add_undo(undo)
		    except blend.MismatchError:
			warn(USER, _("I can't blend the selected objects"))
			# XXX: is there some other solution?:
			raise

		    if len(info) == 2:
			select, undo_insert = self.insert(blendgrp,
							  at = path1[1:],
							  layer = path1[0])
			self.add_undo(undo_insert)
			self.__set_selection(select, SelectSet)
		    else:
			self.SelectObject(blendgrp)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def CanCancelBlend(self):
	info = self.selection.GetInfo()
	return len(info) == 1 and info[0][-1].is_Blend

    def CancelBlend(self):
	if self.CanCancelBlend():
	    self.begin_transaction(_("Cancel Blend"))
	    try:
		try:
		    info = self.selection.GetInfo()[0]
		    self.add_undo(self.remove_selected())
		    group = info[-1]
		    objs = group.CancelEffect()
		    info = info[0]
		    layer = info[0]
		    at = info[1:]
		    select, undo_insert = self.insert(objs, at = at,
						      layer = layer)
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    #
    #

    def CanCreatePathText(self):
	return CanCreatePathText(self.selection.GetObjects())

    def CreatePathText(self):
	if self.CanCreatePathText():
	    self.begin_transaction(_("Create Path Text"))
	    try:
		try:
		    self.add_undo(self.remove_selected())
		    object = CreatePathText(self.selection.GetObjects())

		    select, undo_insert = self.insert(object)
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    #
    #	Clone (under construction...)
    #

    def CanCreateClone(self):
	if len(self.selection) == 1:
	    obj = self.selection.GetObjects()[0]
	    return not obj.is_Compound
	return 0

    def CreateClone(self):
    	if self.CanCreateClone():
            clone = None
    	    self.begin_transaction(_("Create Clone"))
    	    try:
        		try:
        		    from clone import CreateClone
        		    object = self.selection.GetObjects()[0]
        		    clone, undo_clone = CreateClone(object)
        		    self.add_undo(undo_clone)
        		    select, undo_insert = self.insert(clone)
        		    self.add_undo(undo_insert)
        		    self.__set_selection(select, SelectSet)
        		    self.add_undo(self.queue_edited())
        		except:
        		    self.abort_transaction()           
    	    finally:
    		          self.end_transaction()
        return clone


    #
    #	Bezier Curves
    #

    def CanCombineBeziers(self):
	if len(self.selection) > 1:
	    can = 1
	    for obj in self.selection.GetObjects():
		can = can and obj.is_Bezier
	    return can
	return 0

    def CombineBeziers(self):
	if self.CanCombineBeziers():
	    self.begin_transaction(_("Combine Beziers"))
	    try:
		try:
		    self.add_undo(self.remove_selected())
		    objects = self.selection.GetObjects()
		    combined = CombineBeziers(objects)
		    select, undo_insert = self.insert(combined)
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def CanSplitBeziers(self):
	return len(self.selection) == 1 \
	       and self.selection.GetObjects()[0].is_Bezier

    def SplitBeziers(self):
	if self.CanSplitBeziers():
	    self.begin_transaction(_("Split Beziers"))
	    try:
		try:
		    self.add_undo(self.remove_selected())
		    info, bezier = self.selection.GetInfo()[0]
		    objects = bezier.PathsAsObjects()
		    select, undo_insert = self.insert(objects, at = info[1:],
						      layer =info[0])
		    self.add_undo(undo_insert)
		    self.__set_selection(select, SelectSet)
		    self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def CanConvertToCurve(self):
	return len(self.selection) == 1 \
	       and self.selection.GetObjects()[0].is_curve

    def ConvertToCurve(self):
	if self.CanConvertToCurve():
	    self.begin_transaction(_("Convert To Curve"))
	    try:
		try:
                    selection = []
                    edited = 0
                    for info, object in self.selection.GetInfo():
                        if object.is_Bezier:
                            selection.append((info, object))
                        else:
                            bezier = object.AsBezier()
                            parent = object.parent
                            self.add_undo(parent.ReplaceChild(object, bezier))
                            selection.append((info, bezier))
                            edited = 1
                    self.__set_selection(selection, SelectSet)
                    if edited:
                        self.add_undo(self.queue_edited())
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    #
    #
    #

    def Layers(self):
	return self.layers[:]

    def NumLayers(self):
	return len(self.layers)

    def ActiveLayer(self):
	return self.active_layer

    def ActiveLayerIdx(self):
	if self.active_layer is None:
	    return None
	return self.layers.index(self.active_layer)

    def SetActiveLayer(self, idx):
	if type(idx) == IntType:
	    layer = self.layers[idx]
	else:
	    layer = idx
	if not layer.Locked():
	    self.active_layer = layer
	self.queue_layer(LAYER_ACTIVE)

    def LayerIndex(self, layer):
	return self.layers.index(layer)

    def update_active_layer(self):
	if self.active_layer is not None and self.active_layer.CanSelect():
	    return
	self.find_active_layer()

    def find_active_layer(self, idx = None):
	if idx is not None:
	    layer = self.layers[idx]
	    if layer.CanSelect():
		self.SetActiveLayer(idx)
		return
	for layer in self.layers:
	    if layer.CanSelect():
		self.SetActiveLayer(layer)
		return
	self.active_layer = None
	self.queue_layer(LAYER_ACTIVE)

    def deselect_layer(self, layer_idx):
	# Deselect all objects in layer given by layer_idx
	# Called when a layer is deleted or becomes locked
	sel = selinfo.list_to_tree(self.selection.GetInfo())
	for idx, info in sel:
	    if idx == layer_idx:
		self.__set_selection(selinfo.tree_to_list([(idx, info)]),
				     SelectSubtract)

    def SelectLayer(self, layer_idx, mode = SelectSet):
	# Select all children of the layer given by layer_idx
	self.begin_transaction(_("Select Layer"), clear_selection_rect = 0)
	try:
	    try:
		layer = self.layers[layer_idx]
		info = self.augment_sel_info(layer.SelectAll(), layer_idx)
		self.__set_selection(info, mode)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SetLayerState(self, layer_idx, visible, printable, locked, outlined):
	self.begin_transaction(_("Change Layer State"),
			       clear_selection_rect = 0)
	try:
	    try:
		layer = self.layers[layer_idx]
		self.add_undo(layer.SetState(visible, printable, locked,
					     outlined))
		if not layer.CanSelect():
		    # XXX: this depends on whether we're drawing visible or
		    # printable layers
		    self.deselect_layer(layer_idx)
		    self.update_active_layer()
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SetLayerColor(self, layer_idx, color):
	self.begin_transaction(_("Set Layer Outline Color"),
			       clear_selection_rect = 0)
	try:
	    try:
		layer = self.layers[layer_idx]
		self.add_undo(layer.SetOutlineColor(color))
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def SetLayerName(self, idx, name):
	self.begin_transaction(_("Rename Layer"), clear_selection_rect = 0)
	try:
	    try:
		layer = self.layers[idx]
		self.add_undo(layer.SetName(name))
		self.add_undo(self.queue_layer())
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def AppendLayer(self, *args, **kw_args):
	self.begin_transaction(_("Append Layer"),clear_selection_rect = 0)
	try:
	    try:
		layer = apply(SketchDocument.AppendLayer, (self,) + args,
			      kw_args)
		self.add_undo((self._remove_layer, len(self.layers) - 1))
		self.queue_layer(LAYER_ORDER, layer)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()
	return layer

    def NewLayer(self):
	self.begin_transaction(_("New Layer"), clear_selection_rect = 0)
	try:
	    try:
		self.AppendLayer()
		self.active_layer = self.layers[-1]
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def _move_layer_up(self, idx):
	# XXX: exception handling
	if idx < len(self.layers) - 1:
	    # move the layer...
	    layer = self.layers[idx]
	    del self.layers[idx]
	    self.layers.insert(idx + 1, layer)
	    other = self.layers[idx]
	    # ... and adjust the selection
	    sel = self.selection.GetInfoTree()
	    newsel = []
	    for i, info in sel:
		if i == idx:
		    i = idx + 1
		elif i == idx + 1:
		    i = idx
		newsel.append((i, info))
	    self.__set_selection(selinfo.tree_to_list(newsel), SelectSet)
	    self.queue_layer(LAYER_ORDER, layer, other)
	    return (self._move_layer_down, idx + 1)
	return None

    def _move_layer_down(self, idx):
	# XXX: exception handling
	if idx > 0:
	    # move the layer...
	    layer = self.layers[idx]
	    del self.layers[idx]
	    self.layers.insert(idx - 1, layer)
	    other = self.layers[idx]
	    # ...and adjust the selection
	    sel = self.selection.GetInfoTree()
	    newsel = []
	    for i, info in sel:
		if i == idx:
		    i = idx - 1
		elif i == idx - 1:
		    i = idx
		newsel.append((i, info))
	    self.__set_selection(selinfo.tree_to_list(newsel), SelectSet)
	    self.queue_layer(LAYER_ORDER, layer, other)
	    return (self._move_layer_up, idx - 1)
	return NullUndo

    def MoveLayerUp(self, idx):
	if idx < len(self.layers) - 1:
	    self.begin_transaction(_("Move Layer Up"), clear_selection_rect=0)
	    try:
		try:
		    self.add_undo(self._move_layer_up(idx))
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def MoveLayerDown(self, idx):
	if idx > 0:
	    self.begin_transaction(_("Move Layer Down"),clear_selection_rect=0)
	    try:
		try:
		    self.add_undo(self._move_layer_down(idx))
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def _remove_layer(self, idx):
	layer = self.layers[idx]
	del self.layers[idx]
	if layer is self.active_layer:
	    if idx < len(self.layers):
		self.find_active_layer(idx)
	    else:
		self.find_active_layer()
	sel = self.selection.GetInfoTree()
	newsel = []
	for i, info in sel:
	    if i == idx:
		continue
	    elif i > idx:
		i = i - 1
	    newsel.append((i, info))
	self.__set_selection(selinfo.tree_to_list(newsel), SelectSet)

	self.queue_layer(LAYER_ORDER, layer)
	return (self._insert_layer, idx, layer)

    def _insert_layer(self, idx, layer):
	self.layers.insert(idx, layer)
	layer.SetDocument(self)
	self.queue_layer(LAYER_ORDER, layer)
	return (self._remove_layer, idx)

    def CanDeleteLayer(self, idx):
	return (len(self.layers) > 3 and not self.layers[idx].is_SpecialLayer)

    def DeleteLayer(self, idx):
	if self.CanDeleteLayer(idx):
	    self.begin_transaction(_("Delete Layer"), clear_selection_rect = 0)
	    try:
		try:
		    self.add_undo(self._remove_layer(idx))
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()



    #
    #	Style management
    #

    def queue_style(self):
	self.queue_message(STYLE)
	return (self.queue_style,)

    def init_styles(self):
	self.styles = UndoDict()
	self.auto_assign_styles = 1
	self.asked_about = {}

    def destroy_styles(self):
	for style in self.styles.values():
	    style.Destroy()
	self.styles = None

    def get_dynamic_style(self, name):
	return self.styles[name]

    def GetDynamicStyle(self, name):
	try:
	    return self.styles[name]
	except KeyError:
	    return None

    def Styles(self):
	return self.styles.values()

    def write_styles(self, file):
	for style in self.styles.values():
	    style.SaveToFile(file)

    def load_AddStyle(self, style):
	self.styles.SetItem(style.Name(), style)

    def add_dynamic_style(self, name, style):
	if style:
	    style = style.AsDynamicStyle()
	    self.add_undo(self.styles.SetItem(name, style))
	    self.add_undo(self.queue_style())
	    return style

    def update_style_dependencies(self, style):
	def update(obj, style = style):
	    obj.ObjectChanged(style)
	self.WalkHierarchy(update)
	return (self.update_style_dependencies, style)

    def UpdateDynamicStyleSel(self):
        if len(self.selection) == 1:
            self.begin_transaction(_("Update Style"), clear_selection_rect = 0)
            try:
                try:
                    properties = self.CurrentProperties()
                    # XXX hack
                    for style in properties.stack:
                        if style.is_dynamic:
                            break
                    else:
                        return
                    undo = []
                    # we used to use dir(style) to get at the list of
                    # instance variables of style. In Python 2.2 dir
                    # returns class attributes as well. So we use
                    # __dict__.keys() now.
                    for attr in style.__dict__.keys():
                        if attr not in ('name', 'is_dynamic'):
                            undo.append(style.SetProperty(attr,
                                                          getattr(properties,
                                                                  attr)))
                    undo.append(properties.AddStyle(style))
                    undo = (UndoAfter, CreateListUndo(undo),
                            self.update_style_dependencies(style))
                    self.add_undo(undo)
                except:
                    self.abort_transaction()
            finally:
                self.end_transaction()

    def CanCreateStyle(self):
	if len(self.selection) == 1:
	    obj = self.selection.GetObjects()[0]
	    return obj.has_fill or obj.has_line
	return 0

    def CreateStyleFromSelection(self, name, which_properties):
	if self.CanCreateStyle():
	    properties = self.CurrentProperties()
	    style = properties.CreateStyle(which_properties)
	    self.begin_transaction(_("Create Style %s") % name,
				   clear_selection_rect = 0)
	    try:
		try:
		    style = self.add_dynamic_style(name, style)
		    self.AddStyle(style)
		except:
		    self.abort_transaction()
	    finally:
		self.end_transaction()

    def RemoveDynamicStyle(self, name):
	style = self.GetDynamicStyle(name)
	if not style:
	    # style does not exist. XXX: raise an exception ?
	    return
	self.begin_transaction(_("Remove Style %s") % name,
			       clear_selection_rect = 0)
	try:
	    try:
		def remove(obj, style = style, add_undo = self.add_undo):
		    add_undo(obj.ObjectRemoved(style))
		self.WalkHierarchy(remove)
		self.add_undo(self.styles.DelItem(name))
		self.add_undo(self.queue_style())
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def GetStyleNames(self):
	names = self.styles.keys()
	names.sort()
	return names

    #
    #	Layout
    #

    def queue_layout(self):
	self.queue_message(LAYOUT)
	return (self.queue_layout,)

    def init_layout(self):
	self.page_layout = pagelayout.PageLayout()

    def Layout(self):
	return self.page_layout

    def PageSize(self):
	return (self.page_layout.Width(), self.page_layout.Height())

    def PageRect(self):
	w, h = self.page_layout.Size()
	return Rect(0, 0, w, h)

    def load_SetLayout(self, layout):
	self.page_layout = layout

    def __set_page_layout(self, layout):
	undo = (self.__set_page_layout, self.page_layout)
	self.page_layout = layout
	self.queue_layout()
	return undo

    def SetLayout(self, layout):
	self.begin_transaction(clear_selection_rect = 0)
	try:
	    try:
		undo = self.__set_page_layout(layout)
		self.add_undo(_("Change Page Layout"), undo)
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    #
    #	Grid Settings
    #

    def queue_grid(self):
	self.queue_message(GRID)
	return (self.queue_grid,)

    def SetGridGeometry(self, geometry):
	self.begin_transaction(_("Set Grid Geometry"))
	try:
	    try:
		self.add_undo(self.snap_grid.SetGeometry(geometry))
		self.add_undo(self.queue_grid())
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def GridGeometry(self):
        return self.snap_grid.Geometry()

    def GridLayerChanged(self):
	return self.queue_grid()


    #
    #	Guide Lines
    #

    def add_guide_line(self, line):
	self.begin_transaction(_("Add Guide Line"), clear_selection_rect = 0)
	try:
	    try:
		sel, undo = self.guide_layer.Insert(line, 0)
		self.add_undo(undo)
		self.add_undo(self.AddClearRect(line.get_clear_rect()))
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def AddGuideLine(self, point, horizontal):
	self.add_guide_line(guide.GuideLine(point, horizontal))

    def RemoveGuideLine(self, line):
	if not line.parent is self.guide_layer or not line.is_GuideLine:
	    return
	self.begin_transaction(_("Delete Guide Line"),
			       clear_selection_rect = 0)
	try:
	    try:
		self.add_undo(self.remove_objects([line.SelectionInfo()]))
		self.add_undo(self.AddClearRect(line.get_clear_rect()))
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def MoveGuideLine(self, line, point):
	if not line.parent is self.guide_layer or not line.is_GuideLine:
	    return
	self.begin_transaction(_("Move Guide Line"), clear_selection_rect = 0)
	try:
	    try:
		self.add_undo(self.AddClearRect(line.get_clear_rect()))
		self.add_undo(line.SetPoint(point))
		self.add_undo(self.AddClearRect(line.get_clear_rect()))
		self.add_undo(self.GuideLayerChanged(line.parent))
	    except:
		self.abort_transaction()
	finally:
	    self.end_transaction()

    def GuideLayerChanged(self, layer):
	self.queue_message(GUIDE_LINES, layer)
	return (self.GuideLayerChanged, layer)

    def GuideLines(self):
	return self.guide_layer.GuideLines()


    #
    #
    def as_group(self):
	for name in self.GetStyleNames():
	    self.RemoveDynamicStyle(name)
	layers = self.layers
	self.layers = []
	groups = []
	for layer in layers:
	    if not layer.is_SpecialLayer:
		layer.UntieFromDocument()
		objects = layer.GetObjects()
		layer.objects = []
		if objects:
		    groups.append(Group(objects))
	    else:
		layer.Destroy()
	if groups:
	    return Group(groups)
	else:
	    return None


#####for experiment 2############
    def add_col_circular_on_doc_open(self,num): #number of objects
        #select the object before adding
        self.initDragCreation(None)
        interval = self.interval_w
        for i in range (0,num): #n-1
            if num % 2 == 0:
                if i < num/2:
                    p = Point (self.draglist[i].x + interval,  self.draglist[i].y - self.interval_h)
                else:
                    p = Point (self.draglist[i].x - interval,  self.draglist[i].y - self.interval_h)
                
                self.draglist.append(p)
            else:
                if i < num/2:
                    p = Point (self.draglist[i].x + interval,  self.draglist[i].y - self.interval_h)
                elif i == num /2:
                     p = Point (self.draglist[i].x,  self.draglist[i].y - self.interval_h)
                else:
                    p = Point (self.draglist[i].x - interval,  self.draglist[i].y - self.interval_h)
                self.draglist.append(p)
        
        self.DragCreation()
        self.ClearDragCreationData()

    def add_row_circular_on_doc_open(self,num): #number of objects
        #select the object before adding
        self.initDragCreation(None)
        interval = self.interval_w
        for i in range (0,num): #n-1
            if num % 2 == 0:
                if i < num/2:
                    p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y-interval)
                else:
                    p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y+interval)
                
                self.draglist.append(p)
            else:
                if i < num/2:
                    p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y-interval)
                elif i == num /2:
                     p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y)
                else:
                    p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y+interval)
                self.draglist.append(p)
        
        self.DragCreation()
        self.ClearDragCreationData()
    
    def circle_grid(self,spokes,radii,layer): #circular_grid
        #this whole thing is done to consider there are only 12 spokes
        self.active_layer = self.layers[layer]
        select = (0,1),self.layers[layer].objects[0]
        self.__set_selection(select, SelectSet)        
        distance = self.selection.bounding_rect[2]-self.selection.bounding_rect[0]
        temp = distance
        multipler = 3
        distance *=multipler
        '''if task_size > 5:
            distance *=2
        else:
            distance*=2'''
        center_p = Point(self.selection.bounding_rect[0]-distance,self.selection.bounding_rect[3])
        self.initDragCreation(None)
        for i in range(1,spokes):
            angle = math.pi*2*i/spokes
            
            x = center_p.x+math.cos(angle)*distance
            y = center_p.y+math.sin(angle)*distance
            p = Point(x,y)
            self.draglist.append(p) 
        self.DragCreation()
        self.ClearDragCreationData()
        disp = float(multipler) /2
        distance = temp*2
        #distance = temp*2
        '''if task_size > 5:
            distance = temp*2
        else:
            distance = temp*2
            disp = 1 # no disp for small task'''
        for i in range (0,spokes):
            select = (0,1),self.layers[layer].objects[i]
            self.__set_selection(select, SelectSet)
            self.initDragCreation(None)
            for j in range (1,radii):
                angle = math.pi*2*i/spokes                
                x = center_p.x+math.cos(angle)*distance*(j+disp)
                y = center_p.y+math.sin(angle)*distance*(j+disp)
                p = Point(x,y)
                self.draglist.append(p) 
            self.DragCreation()
            self.ClearDragCreationData()

                #angle+=increment    
                
    def circle_arrangement(self,spokes,radii, layer = 0):
        self.active_layer = self.layers[layer]
        select = (0,1),self.layers[layer].objects[0]
        self.__set_selection(select, SelectSet)
        
        #angle = 0
        #while angle < math.pi*2:
        for i in range(0,spokes):
            angle = math.pi*2*i/spokes
            select = (0,1),self.layers[layer].objects[0]
            self.__set_selection(select, SelectSet)
            #add selection as the center point
            center_p = Point(self.selection.bounding_rect[0],self.selection.bounding_rect[3])
            #self.draglist.append(center_p)
            distance = self.selection.bounding_rect[2]-self.selection.bounding_rect[0]
            distance *=2
            #print "distance:",distance          

            self.initDragCreation(None)
            for j in range (1,radii):
                #print "angle:",math.degrees(angle),"radius",j*distance
                x = center_p.x+math.cos(angle)*j*distance
                y = center_p.y+math.sin(angle)*j*distance
                p = Point(x,y)
                self.draglist.append(p) 
            self.DragCreation()
            self.ClearDragCreationData()

    def create_star_arrangment(self,num):
        dirs = ['N','S','E','W','SW','SE','NW','NE','SSE','SEE','SSW','SWW','NWW','NNW','NEE','NNE']
        for i in dirs:

            self.add_a_bunch(num,i)
    
    def add_a_bunch(self,num, direction):
        select = (0,1),self.layers[0].objects[0]
        self.__set_selection(select, SelectSet)
            
        self.initDragCreation(None)
        for i in range (0,num-1): #n-1
            print 'i=',i
            p = None
            if direction == 'N':
                p = Point (self.selection.bounding_rect[0],  self.draglist[i].y + self.interval_h )
            elif direction == 'S':
                p = Point (self.selection.bounding_rect[0],  self.draglist[i].y - self.interval_h )
            elif direction == 'W':
                 p = Point (self.draglist[i].x - self.interval_w,  self.selection.bounding_rect[3]) 
            elif direction == 'E':
                p = Point (self.draglist[i].x + self.interval_w,  self.selection.bounding_rect[3])                  
            elif direction == 'NW':
                p = Point (self.draglist[i].x - self.interval_w,  self.draglist[i].y + self.interval_h )
            elif direction == 'NE':
                p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y + self.interval_h )
            elif direction == 'SW':
                p = Point (self.draglist[i].x - self.interval_w,  self.draglist[i].y - self.interval_h )
            elif direction == 'SE':
                p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y - self.interval_h )
            elif direction == 'SSE':
                p = Point (self.draglist[i].x + 0.5*self.interval_w,  self.draglist[i].y - self.interval_h )
            elif direction == 'SEE':
                p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y - 0.5*self.interval_h )
            elif direction == 'SSW':
                p = Point (self.draglist[i].x - 0.5*self.interval_w,  self.draglist[i].y - self.interval_h )
            elif direction == 'SWW':
                p = Point (self.draglist[i].x - self.interval_w,  self.draglist[i].y - 0.5*self.interval_h )
            elif direction == 'NWW':
                p = Point (self.draglist[i].x - self.interval_w,  self.draglist[i].y + .5*self.interval_h )
            elif direction == 'NNW':
                p = Point (self.draglist[i].x - .5*self.interval_w,  self.draglist[i].y + self.interval_h )
            elif direction == 'NEE':
                p = Point (self.draglist[i].x + self.interval_w,  self.draglist[i].y + 0.5*self.interval_h )
            elif direction == 'NNE':
                p = Point (self.draglist[i].x + 0.5*self.interval_w,  self.draglist[i].y + self.interval_h )  
            self.draglist.append(p) 
        self.DragCreation()
        self.ClearDragCreationData()
        
    def add_row_on_doc_open(self,num): #number of objects
        #select the object before adding
        self.initDragCreation(None)
        for i in range (0,num): #n-1
        
            p = Point (self.draglist[i].x + self.interval_w,  self.selection.bounding_rect[3])
            self.draglist.append(p)                
        
        self.DragCreation()
        self.ClearDragCreationData()
        
    def add_col_on_doc_open(self,num): #number of objects
        self.initDragCreation(None)
        for i in range (0,num): #n-1
        
            p = Point (self.selection.bounding_rect[0],  self.draglist[i].y - self.interval_h )
            #p = Point (self.draglist[i].x + self.interval_w,  self.selection.bounding_rect[3])
            self.draglist.append(p)                
        
        self.DragCreation()
        self.ClearDragCreationData()
    
    def create_grid(self,rows,cols, circular = False, layer = 0):
        #create row 1
        self.active_layer = self.layers[layer]
        select = (0,1),self.layers[layer].objects[0]
        self.__set_selection(select, SelectSet)
        
        if not circular or True: #disabled circular for rows for now
            self.add_row_on_doc_open(cols-1)
        else:
            self.add_row_circular_on_doc_open(cols-1)
        if rows > 1:
            for i in range (0, cols):
                #create column 1
                select = (0,1),self.layers[layer].objects[i]
                self.__set_selection(select, SelectSet)
                
                if not circular:
                    self.add_col_on_doc_open(rows-1)
                else:
                    self.add_col_circular_on_doc_open(rows-1)
  
          
    def on_document_open(self):
        self.constant_delta = 2 #for editing task it will be equal to 2

        self.canvas.ZoomFactor(0.4)
        #self.canvas.TogglePageOutlineMode()
        print "document opened! voila!"
       
        task = self.main_window.application.task
        task_size = int(self.main_window.application.task_size)
        technique = self.main_window.application.technique
        trial = int(self.main_window.application.f1) #f1 will be trial for this experiment and not session
        
        #maybe decrease the distance between them as well
        if task_size == 1:
            task_size = 3
        elif task_size == 2:
            task_size = 7

        
        #lets assume task e is grid, f is star
        branch = None
        col = CreateRGBColor(1,0,0)
        n_spokes = 13
        n_trials = 3

        #num_trials = 1#may want to pass this as an argument later, but for now just hardcode it
        print "task,size,tech,trial:",task,task_size,technique,trial
        if task == 'e':
            #task_size = 2            
            self.create_grid(task_size+1,task_size, False)
            term = (task_size-1)/n_trials
            factor = term if term > 0 else 1
            branch = 1+((trial-1)*2*factor)%(task_size*2-2) #last branch doesn't work, so i disabled it by subtracting 2 from denom

            print "cloneS=",self.clones

            #branch = 10
            #if this is grid task then we need to start from second  
            for i in self.clones[0][branch]: #anywhere from 1 to n-1 is good
                self.SelectObject(i)
                self.canvas.fill_solid(col)
            
            self.create_grid(task_size+1,task_size, False,1)
                            
        elif task == 'f':
            self.circle_arrangement(n_spokes,task_size)
            branch = 1+((trial-1)*(n_spokes+1)/n_trials)%(n_spokes-1)
                        
            for i in self.clones[0][branch]: #anywhere from 1 to n-1 is good
                self.SelectObject(i)
                self.canvas.fill_solid(col)
            self.circle_arrangement(n_spokes,task_size,1)


        elif task == 'g' or task == 'h':
            diagonal = task == 'h'
            self.create_grid(task_size,n_spokes, diagonal,0)
            i = 0
            counter = 0
            cols = CreateRGBColor(1,0,0),CreateRGBColor(0,0,1)
            col = cols[0]
            while True:
                print "i=",i
                if i % 4 == 0 and i < 25:
                    counter+=1
                    col = cols[counter % 2]
                    
                try:
                    for j in self.clones[0][i]: #anywhere from 1 to n-1 is good
                        self.SelectObject(j)
                        self.canvas.fill_solid(col)
                except:
                    break
                i+=1

            self.create_grid(task_size,n_spokes, diagonal,1)
            if technique == "c":
                 self.SelectObject(self.clones[1][0])
                 col = CreateRGBColor(0,0,0)
                 self.canvas.fill_solid(col)
            
        elif task == 'i':
            self.circle_grid(n_spokes,task_size,0)
            i = 0
            counter = 0
            cols = CreateRGBColor(1,0,0),CreateRGBColor(0,0,1)
            col = cols[0] 
            while True:
                if i % 4 == 0 and i < 25:
                    counter+=1
                    col = cols[counter % 2]                   
                try:
                    for j in self.clones[0][i]: #anywhere from 1 to n-1 is good
                        self.SelectObject(j)
                        self.canvas.fill_solid(col)
                except:
                    break
                i+=1
            #create one for layer2
           
            self.circle_grid(n_spokes,task_size,1)
            if technique == "c":
                self.SelectObject(self.clones[1][0])
                col = CreateRGBColor(0,0,0)
                self.canvas.fill_solid(col)
                            
        if technique == "s": #for selection based editing task, we disable clone structure
            self.clones = []
        
        #select first object on the 2nd layer's thingie
        self.active_layer = self.layers[1]
        select = (0,1),self.layers[1].objects[0]
        self.__set_selection(select, SelectSet)

        #self.create_star_arrangment(5)
        #self.create_grid(9,6, True)
        #self.clones = []

        #d) 5,6 (size1)
                        

##################################################################
###############TILE CLONING STUFF#################################
##################################################################

class TiledClones:

    
   
    
    document = None #sketch document
    
    alternate = 0
 
    master = None #Tile Cloning TK Root
    #frame = None
    
    shift_x_row = 0
    shift_x_col = 0
    shift_y_row = 0
    shift_y_col = 0
    shift_alt_row = 0
    shift_alt_col = 0
    chk_shift_alt_row = None
    chk_shift_alt_col = None
    
    scale_x_row = 0
    scale_x_col = 0
    scale_y_row = 0
    scale_y_col = 0
    scale_alt_row = 0
    scale_alt_col = 0
    chk_scale_alt_row = None
    chk_scale_alt_col = None
    
    color_h_row = 0
    color_h_col = 0
    color_s_row = 0
    color_s_col = 0
    color_l_row = 0
    color_l_col = 0
    color_alt_row = 0
    color_alt_col = 0
    chk_color_alt_row = None
    chk_color_alt_col = None
    
    rows = 0
    columns = 0
    
    
    def __init__(self, doc = None):
        self.document = doc
   
    def delete_tile_clone(self, object):
        #preserve clone tree copy for undo
        '''clone_tree_copy = []
        for i in self.document.tile_clones:
            clone_tree_copy.append(i[:])
        
        self.document.add_undo(self.set_tile_clone_tree([clone_tree_copy]))'''
                
                   
        
        self.document.delete_clone(self.document.tile_clones, self.document.tile_clones, object[0])
        
        self.document.select_object(object)
        #self.document.add_undo(
        self.document.remove_selected()            
  
  
        self.document.remove_empty_list(self.document.tile_clones, self.document.tile_clones)
    
    '''def delete_new_tile_clones(self,object):
        self.document.clear_parent_array_data()
        self.document.find_parent(self.document.tile_clones, self.document.tile_clones,  object)
        if self.document.parent_array == None:
                return
        print "clones before deletion", self.document.tile_clones
 
        l=len(self.document.parent_array)

        for i in range(0,l):

            if self.document.parent_array[l-1-i][0]!=object:
                self.document.select_object(self.document.parent_array[l-1-i])
                self.document.remove_selected()
                
        self.document.select_object(object) #initial object select it back after done
        
        #pop them all!
        for i in range(0,l):
            self.document.parent_array.pop()
            print "popka!",i  
       
        self.document.remove_empty_list(self.document.tile_clones, self.document.tile_clones)
        print "clones after deletion", self.document.tile_clones'''
 
    def delete_new_tile_clones(self,object,clone_arr):
        self.document.clear_parent_array_data()
        self.document.find_parent(clone_arr, clone_arr,  object)
        if self.document.parent_array == None:
                return
        #print "clones before deletion", clone_arr
    
        l=len(self.document.parent_array)
    
        for i in range(0,l):
    
            if self.document.parent_array[l-1-i][0]!=object:
                self.document.select_object(self.document.parent_array[l-1-i])
                self.document.add_undo(self.document.remove_selected())
                
        self.document.select_object(object) #initial object select it back after done
        
        #pop them all!
        for i in range(0,l):
            self.document.parent_array.pop()
            #print "popka!",i  
       
        self.document.remove_empty_list(clone_arr, clone_arr)
        print "clones after deletion", clone_arr
        
    def can_create(self):
        #for experiment only
        #if the technique is not tiled clones don't display it
  
        return 1
        
    
    def display_check_your_entries(self):
            title = _("Warning!")
            message = _("Check your entries!")
            buttons = _("OK")
            response = self.document.main_window.application.MessageBox(title = title,  message =message,  buttons = buttons)
                    
    def create(self):
        string = 'create_tiled_clones_button_pressed'
        self.document.log(string)
        self.document.main_window.total_create_tiled_clones_button_presses += 1
        
        if not self.can_create():
            return
        master = self.document.selection.GetObjects()[0]
        
        exception = 0 # we assume exception didn't happpen
        rows = 0
        cols = 0
        try:
            rows = self.rows.get()
        except:
            exception = 1
            rows = 0
        
        try:
            cols = self.columns.get()
        except:
            exception = 1
            cols = 0
       
        if exception:
            self.display_check_your_entries()
            
        if rows == 0 or cols == 0 or rows == 1 and cols == 0 or cols == 1 and rows == 0:
            return
        
        new_array = []
        clone_tree_copy = []
        
        self.document.copy_tree(clone_tree_copy,self.document.tile_clones)
        self.document.begin_transaction(_("Create Tiled Clones"))
        try:
            try:
       
                self.delete_new_tile_clones(master,clone_tree_copy) #delete all except master first
                
                self.document.clear_parent_array_data()
                self.document.find_parent(clone_tree_copy, clone_tree_copy,  master)        
                if self.document.parent_array == None:
                    
                    new_array.append([master]) #we need every object to be inside of array because of the way python is passing arguments into function
                    print "appended to new"
                    #print "new_array=", new_array
                else:
                    #if it already exists, we need to insert a new array after the object entry            
                    if self.document.index_of_object_in_the_parent_array == len(self.document.parent_array) - 1:
                        new_array = self.document.parent_array
                        print "appended to clones1"
                    else: 
                        self.document.parent_array.insert(self.document.index_of_object_in_the_parent_array+1, new_array)    
                        print "appended to clones2"
    
                width = abs(self.document.selection.bounding_rect[0]-self.document.selection.bounding_rect[2])        
                height = abs(self.document.selection.bounding_rect[1]-self.document.selection.bounding_rect[3])  
           
    
                
                #get current color, before it's manipulated
                sel_col = self.document.CurrentFillColor()
    
                #precalculating dialog values for speedup
                scale_alt_row = self.scale_alt_row.get()
                scale_alt_col = self.scale_alt_col.get()
                
                color_alt_row = self.color_alt_row.get()
                color_alt_col = self.color_alt_col.get()
                
                shift_alt_row = self.shift_alt_row.get()
                shift_alt_col = self.shift_alt_col.get()
                
                #but first we have to check whether the user inputted crap or not for entries
                shift_x_row = 0
                shift_x_col = 0
                shift_y_row = 0
                shift_y_col = 0
                
                scale_x_row = 0
                scale_y_row = 0
                scale_x_col = 0
                scale_y_col = 0
                
                hh_row = 0
                hh_col = 0
                
                ss_row = 0
                ss_col = 0
                
                ll_row = 0
                ll_col = 0
                

                
                try:
                    shift_x_row = self.shift_x_row.get()/100
                except:
                    shift_x_row = 0
                    exception = 1
                
                try:
                    shift_x_col = self.shift_x_col.get()/100
                except:
                    shift_x_col = 0
                    exception = 1
                
                try:
                    shift_y_row = self.shift_y_row.get()/100
                except:
                    shit_y_row = 0
                    exception = 1
                
                try:
                    shift_y_col = self.shift_y_col.get()/100
                except:
                    shift_y_col = 0
                    exception = 1
                
                try:
                    scale_x_row = self.scale_x_row.get()/100
                except:
                    scale_x_row = 0
                    exception = 1
                
                try:
                    scale_y_row = self.scale_y_row.get()/100
                except:
                    scale_y_row = 0
                    exception = 1
                    
                try:
                    scale_x_col = self.scale_x_col.get()/100
                except:
                    scale_x_col = 0
                    exception = 1
                    
                try:
                    scale_y_col = self.scale_y_col.get()/100
                except:
                    scale_y_col = 0
                    exception = 1
                
                try:
                    hh_row = self.color_h_row.get()/100
                except:
                    hh_row = 0
                    exception = 1
                
                try:
                    hh_col = self.color_h_col.get()/100
                except:
                    hh_col = 0
                    exception = 1
                
                try:
                    ss_row = self.color_s_row.get()/100
                except:
                    ss_row = 0
                    exception = 1
                
                try:
                    ss_col = self.color_s_col.get()/100
                except:
                    ss_col = 0
                    exception = 1
                
                try:
                    ll_row = self.color_l_row.get()/100
                except:
                    ll_row = 0
                    exception = 1
                
                try:
                    ll_col = self.color_l_col.get()/100
                except:
                    ll_col = 0
                    exception = 1
               
                if exception:
                    self.display_check_your_entries()
                 

                for i in range (0,rows):
                    for j in range(0,cols):
                        if i != 0 or j != 0:
                            #calculate modulo for alternation
                            alt_row = 1
                            alt_col = 1
                            if shift_alt_row:
                                alt_row = (i % 2)
                                #print "altrow = ",alt_row
                            if shift_alt_col:
                                alt_col = (j % 2)
                            #SHIFT    
                            offset = Point(width*j + width*i*shift_x_row*alt_row + width*j*shift_x_col*alt_col ,-height*i - height*i*shift_y_row*alt_row - height*j*shift_y_col*alt_col)
                            newobj = master.Duplicate()
                            newobj.Translate(offset)
                            
                            #SCALE                                
                            scale_x = 1
                            scale_y = 1
                            
                            alti = i
                            altj = j
                            
                            
                            if scale_alt_row and not i % 2:
                                    alti = 0
                            if scale_alt_col and not j % 2:
                                    altj = 0
                                    
                            #abs in case user screws up, scale cannot be negative
                            
                            if scale_x_row:
                                scale_x = (scale_x_row)*alti+1
                            
                            if scale_y_row:
                                scale_y = (scale_y_row)*alti+1

                            if scale_x_col:
                                scale_x = scale_x+(scale_x_col)*altj
                            
                            if scale_y_col:
                                scale_y = scale_y+(scale_y_col)*altj
                                
                           
                            self.document.TransformClone([newobj], scale_x, scale_y)
                            
                                   
                            select, undo_insert = self.document.insert(newobj)
                            self.document.add_undo(undo_insert)                
                            #self.document.__set_selection(select, SelectSet)
                            
                            new_array.append([newobj])
                            #clone_tree_copy.append([newobj]) 
                            
                            #COLOR 
                            if sel_col != None: #the object is transparent
                                alt_color_i = i
                                alt_color_j = j
                                if color_alt_row and not i % 2:
                                        alt_color_i = 0
                                if color_alt_col and not j % 2:
                                        alt_color_j = 0
                                #color entry cannot be negative, so incase user screws up
                                h_row = hh_row*(alt_color_i)
                                h_col = hh_col*(alt_color_j)
                                
                                s_row = ss_row*(alt_color_i)
                                s_col = ss_col*(alt_color_j)
                                
                                l_row = ll_row*(alt_color_i)
                                l_col = ll_col*(alt_color_j)
                                
                                ''' print"-----------------------------"
                                print "h_row=",h_row,"h_col=",h_col
                                print "s_row=",s_row,"s_col=",s_col
                                print "l_row=",l_row,"l_col=",l_col
                                
                                print "orig h",sel_col[0]'''
                                
                                #color cannot be more than 1 an less than 0, thats why truncate it with max min
                                r = max(0,min(1,sel_col[0] + h_row + h_col))
                                g = max(0,min(1,sel_col[1] + s_row + s_col))
                                b = max(0,min(1,sel_col[2] + l_row + l_col))
                                
                                #print "rgb",r,g,b
                                col = CreateRGBColor(r, g, b) 
                                
                                self.document.select_object(newobj)
                                self.document.canvas.fill_solid(col)
     
                                self.document.add_undo(self.document.view_redraw_all())
                                    
            except:
                self.document.abort_transaction()
        finally:
            if self.document.parent_array == None:
                clone_tree_copy.append(new_array)                            
            self.document.add_undo(self.set_tile_clone_tree([clone_tree_copy]))
            self.document.select_object(master) #select thee first object again because of color interpolation
            self.document.end_transaction()
            
            string = 'tiled_clones_successfully_created'+','+str(rows)+','+str(cols)
            self.document.log(string)
            self.document.main_window.total_tiled_clones_sucessfully_created_attempts += 1
            #for the statistics we are only interested in the last one created set
            #self.document.main_window.total_tiled_clones_created = len(self.document.tile_clones[-1])            
            self.document.main_window.total_tiled_clones_created = len(new_array)            
            

            #print "clones after insertion=",self.document.tile_clones

    def set_tile_clone_tree(self, array):              
        clone_tree_copy = []
        self.document.copy_tree(clone_tree_copy, self.document.tile_clones)        
        undo = self.set_tile_clone_tree, [clone_tree_copy]
        self.document.tile_clones = array[0]
        self.document.view_redraw_all()
        return undo               
        
    def remove(self):
        string = 'remove_tiled_clones_button_pressed'
        self.document.log(string)
        self.document.main_window.total_remove_tiled_clones_button_presses += 1

        #######DOESNT SEEM TO WORK
        master = self.document.selection.GetObjects()[0]

        clone_tree_copy = []
        self.document.begin_transaction(_("Remove Tiled Clones"))
        try:
            try:
                self.document.copy_tree(clone_tree_copy,self.document.tile_clones)
                self.delete_new_tile_clones(master,clone_tree_copy) #delete all except master first
                self.document.add_undo(self.document.view_redraw_all())
            except:
                print "bla"
        finally:
            self.document.add_undo(self.set_tile_clone_tree([clone_tree_copy]))
            self.document.end_transaction()
            
            string = 'tiled_clones_successfully_removed'
            self.document.log(string)
            self.document.main_window.total_tiled_clones_sucessfullly_removes += 1

                
        

    def reset(self):
        string = 'reset_tiled_clones_button_pressed'        
        self.document.log(string)
        self.document.total_reset_tiled_clones_button_presses += 1
        
        self.rows.set(0)
        self.columns.set(0)
        self.shift_x_row.set(0.0)
        self.shift_x_col.set(0.0)
        self.shift_y_row.set(0.0)
        self.shift_y_col.set(0.0)
        self.shift_alt_row.set(0)
        self.shift_alt_col.set(0)
        
        self.scale_x_row.set(0.0)
        self.scale_x_col.set(0.0)
        self.scale_y_row.set(0.0)
        self.scale_y_col.set(0.0)
        self.scale_alt_row.set(0)
        self.scale_alt_col.set(0)
        
        self.color_h_row.set(0.0)
        self.color_h_col.set(0.0)
        self.color_s_row.set(0.0)
        self.color_s_col.set(0.0)
        self.color_l_row.set(0.0)
        self.color_l_col.set(0.0)
        self.color_alt_row.set(0)
        self.color_alt_col.set(0)
        
        self.chk_shift_alt_row.deselect()
        self.chk_shift_alt_col.deselect()
        
        self.chk_scale_alt_row.deselect()
        self.chk_scale_alt_col.deselect()
        
        self.chk_color_alt_row.deselect()
        self.chk_color_alt_col.deselect()
        
 
    def close_window(self): #my own interpretation of user closing the window
        self.master.destroy()
        del self.master
        self.master = None
        string = 'tiled_clones_dialog_closed'
        #self.document.log(string) #we dont log it anymore because it's useless
        self.document.main_window.total_tiled_clones_dialog_closes += 1
        
    def build_dialog(self):
        
        from Tkinter import Frame, Button, Tk, LEFT,RIGHT,BOTTOM,E,W,S,N, Checkbutton, DoubleVar,IntVar, Entry, Label
        from Sketch.UI.tkext import UpdatedButton, MyEntry
        
        self.master = Tk()
        self.master.title(_("Create Tiled Clones"))
        self.master.focus_force()  
        
        self.master.protocol("WM_DELETE_WINDOW", self.close_window)
      
        
        width = self.master.winfo_reqwidth()
        height =self.master.winfo_reqheight()
    
        mx = self.master.winfo_rootx() + self.master.winfo_screenwidth()/ 2
        my = self.master.winfo_rooty() + self.master.winfo_screenheight() / 2
        
        posx = max(min(self.master.winfo_screenwidth() - width, mx - width / 2), 0)
        posy = max(min(self.master.winfo_screenheight() - height, my - height / 2), 0)
    
        self.master.geometry('%+d%+d' % (posx, posy))
        
 
        #self.frame = self.master
        #self.frame = Frame(self.master)
        #self.frame.pack()
        #button = Button(frame, text="QUIT", fg="red", command=frame.quit)
        #button.pack(side=LEFT)
        
        ENTRY_WIDTH = 8
        self.rows = IntVar(self.master)
        self.columns = IntVar(self.master)
        self.rows.set(0)
        self.columns.set(0)
        
        #for experiment july 6 2009
        task = self.document.main_window.application.task        
        '''if task == 'h' or task == 'j':
            task_size = self.document.main_window.application.task_size
            if task_size == '1':
                self.rows.set(1)
                self.columns.set(5)
            elif task_size == '2':
                self.rows.set(1)
                self.columns.set(10)
        elif task == 'i':
            task_size = self.document.main_window.application.task_size
            if task_size == '1':
                self.rows.set(5)
                self.columns.set(5)
            elif task_size == '2':
                self.rows.set(10)
                self.columns.set(10)'''
               
        Label(self.master, text="Grid").grid(row=0,column=1)
          
        Label(self.master, text="rows,columns:").grid(row=1, column=0, sticky=W)
        Entry(self.master, textvariable = self.rows,width=ENTRY_WIDTH).grid(row=1,column=1,sticky=W)
        Entry(self.master, textvariable = self.columns,width=ENTRY_WIDTH).grid(row=1,column=2,sticky=W)
        
        
        Label(self.master, text="Shift").grid(row=2,column=1)
        Label(self.master, text="Per Row").grid(row=3, column=1, sticky=W)
        Label(self.master, text="Per Column").grid(row=3, column=2, sticky=W)
        Label(self.master, text="X (%)").grid(row=4, column=0, sticky=W)
        Label(self.master, text="Y (%)").grid(row=5, column=0, sticky=W)
        Label(self.master, text="Alternate").grid(row=6, column=0, sticky=W)
        
        self.shift_x_row = DoubleVar(self.master)
        self.shift_x_row.set(0.0)
        self.shift_x_col = DoubleVar(self.master)
        self.shift_x_col.set(0.0)
        self.shift_y_row = DoubleVar(self.master)
        self.shift_y_row.set(0.0)
        self.shift_y_col = DoubleVar(self.master)
        self.shift_y_col.set(0.0)
        self.shift_alt_row = IntVar(self.master)
        self.shift_alt_col = IntVar(self.master)
        
        #this is purely for experiment June 9, 2009

 
        self.document.constant_delta
        fixed_val = (self.document.constant_delta-1)*100    
        #if task == 'b' or task == 'h' or task == 'j':
        if task == 'a':
            self.shift_x_row = DoubleVar(self.master)
            self.shift_x_row.set(0.0)
            self.shift_x_col = DoubleVar(self.master)
            self.shift_x_col.set(fixed_val)
            self.shift_y_row = DoubleVar(self.master)
            self.shift_y_row.set(0.0)
            self.shift_y_col = DoubleVar(self.master)
            self.shift_y_col.set(0.0)
        #elif task == 'd' or task == 'i' or task == 'k' or task == 'l':
        elif task == 'b':
            self.shift_x_row = DoubleVar(self.master)
            self.shift_x_row.set(0.0)
            self.shift_x_col = DoubleVar(self.master)
            self.shift_x_col.set(fixed_val)
            self.shift_y_row = DoubleVar(self.master)
            self.shift_y_row.set(fixed_val)
            self.shift_y_col = DoubleVar(self.master)
            self.shift_y_col.set(0.0)
        '''elif task == 'c':
            self.shift_x_row = DoubleVar(self.master)
            self.shift_x_row.set(0.0)
            self.shift_x_col = DoubleVar(self.master)
            self.shift_x_col.set(0.0)
            self.shift_y_row = DoubleVar(self.master)
            self.shift_y_row.set(20.0)
            self.shift_y_col = DoubleVar(self.master)
            self.shift_y_col.set(0.0)'''
                

        

        Entry(self.master, textvariable = self.shift_x_row,width=ENTRY_WIDTH).grid(row=4,column=1,sticky=W)
        Entry(self.master, textvariable = self.shift_y_row,width=ENTRY_WIDTH).grid(row=5,column=1,sticky=W)
        Entry(self.master, textvariable = self.shift_x_col,width=ENTRY_WIDTH).grid(row=4,column=2,sticky=W)
        Entry(self.master, textvariable = self.shift_y_col,width=ENTRY_WIDTH).grid(row=5,column=2,sticky=W)
        self.chk_shift_alt_row = Checkbutton(self.master, variable=self.shift_alt_row)
        self.chk_shift_alt_row.grid(row=6,column=1)
        self.chk_shift_alt_col = Checkbutton(self.master, variable=self.shift_alt_col)
        self.chk_shift_alt_col.grid(row=6,column=2)
        
        Label(self.master, text="Scale").grid(row=7,column=1)
        Label(self.master, text="Per Row").grid(row=8, column=1, sticky=W)
        Label(self.master, text="Per Column").grid(row=8, column=2, sticky=W)
        Label(self.master, text="X (%)").grid(row=9, column=0, sticky=W)
        Label(self.master, text="Y (%)").grid(row=10, column=0, sticky=W)
        Label(self.master, text="Alternate").grid(row=11, column=0, sticky=W)


        self.scale_x_row = DoubleVar(self.master)
        self.scale_x_row.set(0.0)
        self.scale_x_col = DoubleVar(self.master)
        self.scale_x_col.set(0.0)
        self.scale_y_row = DoubleVar(self.master)
        self.scale_y_row.set(0.0)
        self.scale_y_col = DoubleVar(self.master)
        self.scale_y_col.set(0.0)
        self.scale_alt_row = IntVar(self.master)
        self.scale_alt_col = IntVar(self.master)
        
        Entry(self.master, textvariable = self.scale_x_row,width=ENTRY_WIDTH).grid(row=9,column=1,sticky=W)
        Entry(self.master, textvariable = self.scale_y_row,width=ENTRY_WIDTH).grid(row=10,column=1,sticky=W)
        Entry(self.master, textvariable = self.scale_x_col,width=ENTRY_WIDTH).grid(row=9,column=2,sticky=W)
        Entry(self.master, textvariable = self.scale_y_col,width=ENTRY_WIDTH).grid(row=10,column=2,sticky=W)
        self.chk_scale_alt_row = Checkbutton(self.master, variable=self.scale_alt_row)
        self.chk_scale_alt_row.grid(row=11,column=1)
        self.chk_scale_alt_col = Checkbutton(self.master, variable=self.scale_alt_col)
        self.chk_scale_alt_col.grid(row=11,column=2)
        
        Label(self.master, text="Color").grid(row=12,column=1)
        Label(self.master, text="Per Row").grid(row=13, column=1, sticky=W)
        Label(self.master, text="Per Column").grid(row=13, column=2, sticky=W)
        Label(self.master, text="R (%)").grid(row=14, column=0, sticky=W)
        Label(self.master, text="G (%)").grid(row=15, column=0, sticky=W)
        Label(self.master, text="B (%)").grid(row=16, column=0, sticky=W)
        Label(self.master, text="Alternate").grid(row=17, column=0, sticky=W)

        self.color_h_row = DoubleVar(self.master)
        self.color_h_col = DoubleVar(self.master)
        self.color_s_row = DoubleVar(self.master)
        self.color_s_col = DoubleVar(self.master)
        self.color_l_row = DoubleVar(self.master)
        self.color_l_col = DoubleVar(self.master)
        self.color_alt_row = IntVar(self.master)
        self.color_alt_col = IntVar(self.master)
        
        self.color_h_row.set(0.0)
        self.color_h_col.set(0.0)
        self.color_s_row.set(0.0)
        self.color_s_col.set(0.0)
        self.color_l_row.set(0.0)
        self.color_l_col.set(0.0)
        
        Entry(self.master, textvariable = self.color_h_row,width=ENTRY_WIDTH).grid(row=14,column=1,sticky=W)
        Entry(self.master, textvariable = self.color_s_row,width=ENTRY_WIDTH).grid(row=15,column=1,sticky=W)
        Entry(self.master, textvariable = self.color_l_row,width=ENTRY_WIDTH).grid(row=16,column=1,sticky=W)
        
        Entry(self.master, textvariable = self.color_h_col,width=ENTRY_WIDTH).grid(row=14,column=2,sticky=W)
        Entry(self.master, textvariable = self.color_s_col,width=ENTRY_WIDTH).grid(row=15,column=2,sticky=W)
        Entry(self.master, textvariable = self.color_l_col,width=ENTRY_WIDTH).grid(row=16,column=2,sticky=W)
        
        self.chk_color_alt_row = Checkbutton(self.master, variable=self.color_alt_row)
        self.chk_color_alt_row.grid(row=17,column=1)
        self.chk_color_alt_col = Checkbutton(self.master, variable=self.color_alt_col)
        self.chk_color_alt_col.grid(row=17,column=2)
        
        
 
        
        btn_reset = Button(self.master, text=_("Reset"), command=self.reset)
        btn_reset.grid(row=18,column=0)
        
        btn_remove = Button(self.master, text=_("Remove"), command=self.remove)
        btn_remove.grid(row=18,column=1)
        
        btn_create = Button(self.master, text=_("Create"), command=self.create)
        btn_create.grid(row=18,column=2)
        
        ''''
        btn_remove = Button(self.frame, text=_("Remove"), command=self.remove)
        btn_remove.pack(side=LEFT)
        
        btn_create = Button(self.frame, text="Create", command=self.create)
        btn_create.pack(side=LEFT)
        
        self.alternate = IntVar(self.frame)
        
        chk_alternate = Checkbutton(self.frame, text="Alternate", variable=self.alternate)
        #c.var = self.v
        chk_alternate.pack(side=LEFT)
        
        #frame of root?
        var_steps = IntVar(self.frame)
        var_steps.set(2)
        label = Label(self.frame, text = _("Steps"), anchor = 'e')
        
        entry = Entry(self.frame, textvariable = var_steps, width = 5)
        entry.grid(column = 1, row = 1, sticky = 'ew')
        entry.pack(side=LEFT)
        '''        

        #root.mainloop()

        #############################################################################    
        ##################END OF TILE CLONING STUFF##################################
        #############################################################################    
