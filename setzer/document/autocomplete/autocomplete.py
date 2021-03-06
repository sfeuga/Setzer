#!/usr/bin/env python3
# coding: utf-8

# Copyright (C) 2017, 2018 Robert Griesel
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

import setzer.document.autocomplete.autocomplete_viewgtk as view
from setzer.app.service_locator import ServiceLocator


class Autocomplete(object):

    def __init__(self, document, document_view):
        self.document = document
        self.document_view = document_view
        self.main_window = ServiceLocator.get_main_window()

        self.view = view.DocumentAutocompleteView()

        self.line_height = 0
        self.char_width = 0
        self.update_char_size()
        self.shortcuts_bar_height = 37
        self.number_of_matches = 0

        self.insert_iter_offset = None
        self.insert_iter_matched = False
        self.current_word = ""
        self.autocomplete_height = None
        self.autocomplete_width = None
        self.autocomplete_visible = False
        self.autocomplete_focus_was_visible = False

        self.static_proposals = dict()
        self.dynamic_proposals = dict()
        self.generate_proposals()
        GObject.timeout_add(500, self.generate_dynamic_proposals)

        self.view.list.connect('row-activated', self.on_autocomplete_row_activated)
        self.view.list.connect('row-selected', self.on_autocomplete_row_selected)

        self.document_view.scrolled_window.get_vadjustment().connect('value-changed', self.on_adjustment_value_changed)
        self.document_view.scrolled_window.get_hadjustment().connect('value-changed', self.on_adjustment_value_changed)
        self.document_view.source_view.connect('focus-out-event', self.on_focus_out)
        self.document_view.source_view.connect('focus-in-event', self.on_focus_in)
        self.document.get_buffer().connect('changed', self.on_buffer_changed)
        self.document.get_buffer().connect('mark-set', self.on_mark_set)
        self.document.get_buffer().connect('mark-deleted', self.on_mark_deleted)

    def on_adjustment_value_changed(self, adjustment, user_data=None):
        self.update_autocomplete_position(False)
        return False

    def on_mark_set(self, buffer, insert, mark, user_data=None):
        self.update_autocomplete_position(False)
    
    def on_buffer_changed(self, buffer, user_data=None):
        self.update_autocomplete_position(True)
    
    def on_mark_deleted(self, buffer, mark, user_data=None):
        self.update_autocomplete_position(False)

    def on_autocomplete_row_activated(self, box, row, user_data=None):
        self.document_view.source_view.grab_focus()
        self.autocomplete_insert()

    def on_autocomplete_row_selected(self, box, row, user_data=None):
        if row != None:
            command = row.get_child().command
            self.view.infobox.set_text(command['description'])

    def on_focus_out(self, widget, event, user_data=None):
        self.focus_hide()

    def on_focus_in(self, widget, event, user_data=None):
        self.focus_show()

    def on_keypress(self, event):
        ''' returns whether the keypress has been handled. '''
        modifiers = Gtk.accelerator_get_default_mod_mask()

        if event.keyval == Gdk.keyval_from_name('Down'):
            if event.state & modifiers == 0:
                return self.on_down_press()

        if event.keyval == Gdk.keyval_from_name('Up'):
            if event.state & modifiers == 0:
                return self.on_up_press()

        if event.keyval == Gdk.keyval_from_name('Escape'):
            if event.state & modifiers == 0:
                return self.on_escape_press()

        if event.keyval == Gdk.keyval_from_name('Return'):
            if event.state & modifiers == 0:
                return self.on_return_press()

        tab_keyvals = [Gdk.keyval_from_name('Tab'), Gdk.keyval_from_name('ISO_Left_Tab')]
        if event.keyval in tab_keyvals:
            if event.state & modifiers == 0:
                return self.on_tab_press()

    def on_return_press(self):
        if self.autocomplete_visible == True:
            self.autocomplete_insert()
            return True
        else:
            return False

    def on_escape_press(self):
        if self.autocomplete_visible == True:
            self.view.hide()
            self.autocomplete_visible = False
            return True
        else:
            return False

    def on_up_press(self):
        if self.autocomplete_visible == True:
            self.view.select_previous()
            return True
        else:
            return False

    def on_down_press(self):
        if self.autocomplete_visible == True:
            self.view.select_next()
            return True
        else:
            return False

    def on_tab_press(self):
        return False

    def focus_hide(self):
        self.view.hide()
        if self.autocomplete_visible:
            self.autocomplete_focus_was_visible = True
        self.autocomplete_visible = False

    def focus_show(self):
        if self.autocomplete_focus_was_visible:
            self.autocomplete_focus_was_visible = False
            self.view.show_all()
            self.autocomplete_visible = True

    def update_char_size(self):
        context = self.document_view.source_view.get_pango_context()
        layout = Pango.Layout.new(context)
        layout.set_text(" ", -1)
        layout.set_font_description(context.get_font_description())
        self.char_width, self.line_height = layout.get_pixel_size()

    def get_current_word(self, insert_iter):
        limit_iter = insert_iter.copy()
        limit_iter.backward_chars(50)
        word_start_iter = insert_iter.copy()
        if not word_start_iter.get_char() == '\\':
            result = word_start_iter.backward_search('\\', Gtk.TextSearchFlags.TEXT_ONLY, limit_iter)
            if result != None:
                word_start_iter = result[0]
        word = word_start_iter.get_slice(insert_iter)
        return word

    def autocomplete_insert(self):
        buffer = self.document.get_buffer()
        if buffer != None:
            insert_iter = buffer.get_iter_at_mark(buffer.get_insert())
            current_word = self.get_current_word(insert_iter)
            start_iter = insert_iter.copy()
            start_iter.backward_chars(len(current_word))
            row = self.view.list.get_selected_row()
            text = row.get_child().label.get_text()
            if text.startswith('\\begin'):
                text += '\n\t•\n' + text.replace('\\begin', '\\end')
            self.document.replace_range(start_iter, insert_iter, text, indent_lines=True)
            self.view.hide()
            self.autocomplete_visible = False

    def update_autocomplete_position(self, can_show=False):
        buffer = self.document.get_buffer()
        if buffer != None:
            self.number_of_matches = 0
            if self.autocomplete_visible == False and can_show == False: return
            insert_iter = buffer.get_iter_at_mark(buffer.get_insert())
            if self.insert_iter_offset == None: self.insert_iter_offset = insert_iter.get_offset()
            if self.insert_iter_offset != insert_iter.get_offset():
                self.insert_iter_offset = insert_iter.get_offset()
                self.current_word = self.get_current_word(insert_iter)
                self.insert_iter_matched = False
                self.view.empty_list()

                items = list()
                try: items = self.static_proposals[self.current_word[1:].lower()]
                except KeyError: pass
                try: items += self.dynamic_proposals[self.current_word[1:].lower()][:5 - len(items)]
                except KeyError: pass
                items.reverse()

                self.number_of_matches = len(items)
                for command in items:
                    item = view.DocumentAutocompleteItem(command)
                    self.view.prepend(item)
                    self.insert_iter_matched = True
                    self.view.select_first()

            if self.insert_iter_matched:
                self.autocomplete_height = self.view.get_allocated_height()
                full_autocomplete_height = 114
                self.autocomplete_width = self.view.get_allocated_width()

                iter_location = self.document_view.source_view.get_iter_location(insert_iter)
                gutter = self.document_view.source_view.get_window(Gtk.TextWindowType.LEFT)
                if gutter != None:
                    gutter_width = gutter.get_width()
                else:
                    gutter_width = 0
                x_offset = - self.document_view.scrolled_window.get_hadjustment().get_value()
                y_offset = - self.document_view.scrolled_window.get_vadjustment().get_value()
                x_position = x_offset + iter_location.x - 4 + gutter_width - len(self.current_word) * self.char_width
                y_position = y_offset + iter_location.y + self.line_height + self.shortcuts_bar_height

                show_x = False
                show_y = False
                if y_position >= self.line_height - 1 + self.shortcuts_bar_height and y_position <= self.document_view.scrolled_window.get_allocated_height() - full_autocomplete_height:
                    self.view.set_margin_top(y_position)
                    show_y = True
                elif y_position >= self.line_height - 1 + self.shortcuts_bar_height and y_position <= self.document_view.scrolled_window.get_allocated_height() + self.shortcuts_bar_height:
                    self.view.set_margin_top(y_position - self.autocomplete_height - self.line_height)
                    show_y = True
                else:
                    show_y = False

                if x_position >= 0 and x_position <= self.main_window.preview_paned.get_allocated_width() - self.autocomplete_width:
                    self.view.set_margin_left(x_position)
                    show_x = True
                elif x_position >= 0 and x_position <= self.main_window.preview_paned.get_allocated_width():
                    self.view.set_margin_left(x_position - self.autocomplete_width)
                    show_x = True
                else:
                    show_x = False

                if show_x and show_y:
                    self.view.show_all()
                    self.autocomplete_visible = True
                else:
                    self.view.hide()
                    self.autocomplete_visible = False
            else:
                self.view.hide()
                self.autocomplete_visible = False

    def save_data(self):
        pass
        
    def generate_proposals(self):
        self.commands = ServiceLocator.get_autocomplete_commands()
        
        self.static_proposals = dict()
        for command in self.commands.values():
            for i in range(1, len(command['command']) + 1):
                try:
                    if len(self.static_proposals[command['command'][0:i].lower()]) < 5:
                        self.static_proposals[command['command'][0:i].lower()].append(command)
                except KeyError:
                    self.static_proposals[command['command'][0:i].lower()] = [command]

    def generate_dynamic_proposals(self):
        labels = self.document.parser.get_labels()
        if labels != None:
            self.dynamic_proposals = dict()
            for label in iter(labels):
                command = {'command': 'ref{' + label + '}', 'description': _('Reference to \'{label}\'').format(label=label)}
                for i in range(1, len(command['command']) + 1):
                    try:
                        if len(self.dynamic_proposals[command['command'][0:i].lower()]) < 5:
                            self.dynamic_proposals[command['command'][0:i].lower()].append(command)
                    except KeyError:
                        self.dynamic_proposals[command['command'][0:i].lower()] = [command]
        return True


