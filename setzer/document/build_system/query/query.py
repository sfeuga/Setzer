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

import _thread as thread
import os
import os.path
import base64
import tempfile
import shutil
import subprocess

from setzer.app.service_locator import ServiceLocator


class Query(object):

    def __init__(self):
        self.config_folder = ServiceLocator.get_config_folder()

        self.backward_synctex_regex = ServiceLocator.get_backward_synctex_regex()
        self.forward_synctex_regex = ServiceLocator.get_forward_synctex_regex()
        self.doc_regex = ServiceLocator.get_build_log_doc_regex()
        self.item_regex = ServiceLocator.get_build_log_item_regex()
        self.badbox_line_number_regex = ServiceLocator.get_build_log_badbox_line_number_regex()
        self.other_line_number_regex = ServiceLocator.get_build_log_other_line_number_regex()
        self.bibtex_log_item_regex = ServiceLocator.get_bibtex_log_item_regex()

        self.process = None
        self.build_result = None
        self.build_result_lock = thread.allocate_lock()
        self.forward_sync_result = None
        self.forward_sync_result_lock = thread.allocate_lock()
        self.backward_sync_result = None
        self.backward_sync_result_lock = thread.allocate_lock()
        self.done_executing = False
        self.done_executing_lock = thread.allocate_lock()
        self.synctex_file = None
        self.synctex_file_lock = thread.allocate_lock()

        self.build_data = dict()
        self.forward_sync_data = dict()
        self.backward_sync_data = dict()
        self.tex_filename = None

        self.log_messages = list()
        self.bibtex_log_messages = list()
        self.force_building_to_stop = False
        self.error_count = 0

    def stop_building(self):
        if self.process != None:
            self.process.kill()
            self.process = None
            self.force_building_to_stop = True

    def get_build_result(self):
        return_value = None
        with self.build_result_lock:
            if self.build_result != None:
                return_value = self.build_result
        return return_value

    def get_forward_sync_result(self):
        return_value = None
        with self.forward_sync_result_lock:
            if self.forward_sync_result != None:
                return_value = self.forward_sync_result
        return return_value

    def get_backward_sync_result(self):
        return_value = None
        with self.backward_sync_result_lock:
            if self.backward_sync_result != None:
                return_value = self.backward_sync_result
        return return_value

    def mark_done(self):
        with self.done_executing_lock:
            self.done_executing = True
    
    def is_done(self):
        with self.done_executing_lock:
            return self.done_executing
    
