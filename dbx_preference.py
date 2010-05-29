#!/usr/bin/python

#   dbx_preference.py
#
#	Copyright 2008, 2009, 2010 Aleksey Shaferov and Matias Sars
#
#	DockbarX is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	DockbarX is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with dockbar.  If not, see <http://www.gnu.org/licenses/>.

import pygtk
pygtk.require('2.0')
import gtk
import gconf
import os
from tarfile import open as taropen
from xml.sax import make_parser
from xml.sax.handler import ContentHandler

from dockbarx.common import Globals, ODict

GCONF_CLIENT = gconf.client_get_default()
GCONF_DIR = '/apps/dockbarx'


class ThemeHandler(ContentHandler):
    """Reads the xml-file into a ODict"""
    def __init__(self):
        self.dict = ODict()
        self.name = None
        self.nested_contents = []
        self.nested_contents.append(self.dict)
        self.nested_attributes = []

    def startElement(self, name, attrs):
        name = name.lower().encode()
        if name == 'theme':
            for attr in attrs.keys():
                if attr.lower() == 'name':
                    self.name = attrs[attr]
            return
        # Add all attributes to a dictionary
        d = {}
        for attr in attrs.keys():
            # make sure that all text is in lower
            d[attr.encode().lower()] = attrs[attr].encode().lower()
        # Add a ODict to the dictionary in which all
        # content will be put.
        d['content'] = ODict()
        self.nested_contents[-1][name] = d
        # Append content ODict to the list so that it
        # next element will be put there.
        self.nested_contents.append(d['content'])

        self.nested_attributes.append(d)

    def endElement(self, name):
        if name == 'theme':
            return
        # Pop the last element of nested_contents
        # so that the new elements won't show up
        # as a content to the ended element.
        if len(self.nested_contents)>1:
            self.nested_contents.pop()
        # Remove Content Odict if the element
        # had no content.
        d = self.nested_attributes.pop()
        if d['content'].keys() == []:
                d.pop('content')

    def get_dict(self):
        return self.dict

    def get_name(self):
        return self.name

class Theme():
    @staticmethod
    def check(path_to_tar):
        #TODO: Optimize this
        tar = taropen(path_to_tar)
        config = tar.extractfile('config')
        parser = make_parser()
        theme_handler = ThemeHandler()
        try:
            parser.setContentHandler(theme_handler)
            parser.parse(config)
        except:
            tar.close()
            raise
        tar.close()
        return theme_handler.get_name()

    def __init__(self, path_to_tar):
        tar = taropen(path_to_tar)
        config = tar.extractfile('config')

        # Parse
        parser = make_parser()
        theme_handler = ThemeHandler()
        parser.setContentHandler(theme_handler)
        parser.parse(config)
        self.theme = theme_handler.get_dict()

        # Name
        self.name = theme_handler.get_name()

        # Colors
        self.color_names = {}
        self.default_colors = {}
        self.default_alphas = {}
        colors = {}
        if self.theme.has_key('colors'):
            colors = self.theme['colors']['content']
        for i in range(1, 9):
            c = 'color%s'%i
            if colors.has_key(c):
                d = colors[c]
                if d.has_key('name'):
                    self.color_names[c] = d['name']
                if d.has_key('default'):
                    if self.test_color(d['default']):
                        self.default_colors[c] = d['default']
                    else:
                        print 'Theme error: %s\'s default for theme %s cannot be read.'%(c, self.name)
                        print 'A default color should start with an "#" and be followed by six hex-digits, ' + \
                              'for example "#FF13A2".'
                if d.has_key('opacity'):
                    alpha = d['opacity']
                    if self.test_alpha(alpha):
                        self.default_alphas[c] = alpha
                    else:
                        print 'Theme error: %s\'s opacity for theme %s cannot be read.'%(c, self.name)
                        print 'The opacity should be a number ("0"-"100") or the words "not used".'

        tar.close()

    def get_name(self):
        return self.name

    def get_gap(self):
        return int(self.theme['button_pixmap'].get('gap', 0))

    def get_windows_cnt(self):
        return int(self.theme['button_pixmap'].get('windows_cnt', 1))

    def get_aspect_ratio(self):
        ar = self.theme['button_pixmap'].get('aspect_ratio', "1")
        l = ar.split('/',1)
        if len(l) == 2:
            ar = float(l[0])/float(l[1])
        else:
            ar = float(ar)
        return ar

    def get_default_colors(self):
        return self.default_colors

    def get_default_alphas(self):
        return self.default_alphas

    def get_color_names(self):
        return self.color_names

    def test_color(self, color):
        if len(color) != 7:
            return False
        try:
            t = int(color[1:], 16)
        except:
            return False
        return True

    def test_alpha(self, alpha):
        if 'no' in alpha:
            return True
        try:
            t = int(alpha)
        except:
            return False
        if t<0 or t>100:
            return False
        return True

class PrefDialog():

    def __init__ (self):

        self.globals = Globals()
        self.globals.connect('theme-changed', self.on_theme_changed)
        self.globals.connect('preference-update', self.update)
        self.load_theme()

        self.dialog = gtk.Dialog("DockBarX preferences")
        self.dialog.connect("response", self.dialog_close)
        self.dialog.set_icon_name('dockbarx')

        try:
            ca = self.dialog.get_content_area()
        except:
            ca = self.dialog.vbox
        notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        appearance_box = gtk.VBox()
        windowbutton_box = gtk.VBox()
        groupbutton_box = gtk.VBox()
        advanced_box = gtk.VBox()

        #--- WindowButton page
        label = gtk.Label("<b>Windowbutton actions</b>")
        label.set_alignment(0,0.5)
        label.set_use_markup(True)
        table = gtk.Table(4,4)
        table.attach(label, 0, 4, 0, 1)

        # A directory of combobox names and the name of corresponding setting
        self.wb_labels_and_settings = ODict((
                    ('Left mouse button', "windowbutton_left_click_action"),
                    ('Shift + left mouse button', "windowbutton_shift_and_left_click_action"),
                    ('Middle mouse button', "windowbutton_middle_click_action"),
                    ('Shift + middle mouse button', "windowbutton_shift_and_middle_click_action"),
                    ('Right mouse button', "windowbutton_right_click_action"),
                    ('Shift + right mouse button', "windowbutton_shift_and_right_click_action"),
                    ('Scroll up', "windowbutton_scroll_up"),
                    ('Scroll down', "windowbutton_scroll_down")
                                           ))

        wb_actions = ('select or minimize window',
                     'select window',
                     'maximize window',
                     'close window',
                     'show menu',
                     'shade window',
                     'unshade window',
                     'no action')

        self.wb_combos = {}
        for text in self.wb_labels_and_settings:
            label = gtk.Label(text)
            label.set_alignment(1,0.5)
            self.wb_combos[text] = gtk.combo_box_new_text()
            for action in wb_actions:
                self.wb_combos[text].append_text(action)
            self.wb_combos[text].connect('changed', self.cb_changed)

            i = self.wb_labels_and_settings.get_index(text)
            # Every second label + combobox on a new row
            row = i // 2 + 1
            # Pack odd numbered comboboxes from 3rd column
            column = (i % 2) * 2
            table.attach(label, column, column + 1, row, row + 1 )
            table.attach(self.wb_combos[text], column + 1, column + 2, row, row + 1 )

        windowbutton_box.pack_start(table, False, padding=5)

        #--- Appearance page
        hbox = gtk.HBox()
        vbox = gtk.VBox()
        label1 = gtk.Label("<b><big>Needs attention effect</big></b>")
        label1.set_alignment(0,0.5)
        label1.set_use_markup(True)
        vbox.pack_start(label1,False)
        self.rb1_1 = gtk.RadioButton(None, "Compiz water")
        self.rb1_1.connect("toggled", self.rb_toggled, "rb1_compwater")
        self.rb1_2 = gtk.RadioButton(self.rb1_1, "Blinking")
        self.rb1_2.connect("toggled", self.rb_toggled, "rb1_blink")
        self.rb1_3 = gtk.RadioButton(self.rb1_1, "Static")
        self.rb1_3.connect("toggled", self.rb_toggled, "rb1_red")
        self.rb1_4 = gtk.RadioButton(self.rb1_1, "No effect")
        self.rb1_4.connect("toggled", self.rb_toggled, "rb1_nothing")
        vbox.pack_start(self.rb1_1, False)
        vbox.pack_start(self.rb1_2, False)
        vbox.pack_start(self.rb1_3, False)
        vbox.pack_start(self.rb1_4, False)
        hbox.pack_start(vbox, True, padding=5)

        vbox = gtk.VBox()
        label1 = gtk.Label("<b><big>Popup Settings</big></b>")
        label1.set_alignment(0,0.5)
        label1.set_use_markup(True)
        vbox.pack_start(label1,False)
        self.rb3_1 = gtk.RadioButton(None, "Align left")
        self.rb3_1.connect("toggled", self.rb_toggled, "rb3_left")
        self.rb3_2 = gtk.RadioButton(self.rb3_1, "Align center")
        self.rb3_2.connect("toggled", self.rb_toggled, "rb3_center")
        self.rb3_3 = gtk.RadioButton(self.rb3_1, "Align right")
        self.rb3_3.connect("toggled", self.rb_toggled, "rb3_right")
        vbox.pack_start(self.rb3_1, False)
        vbox.pack_start(self.rb3_2, False)
        vbox.pack_start(self.rb3_3, False)
        hbox.pack_start(vbox, True, padding=5)

        vbox = gtk.VBox()
        label1 = gtk.Label("<b><big>Opacify</big></b>")
        label1.set_alignment(0,0.5)
        label1.set_use_markup(True)
        vbox.pack_start(label1,False)
        self.opacify_cb = gtk.CheckButton('Opacify')
        self.opacify_cb.connect('toggled', self.checkbutton_toggled, 'opacify')
        vbox.pack_start(self.opacify_cb, False)
        self.opacify_group_cb = gtk.CheckButton('Opacify group')
        self.opacify_group_cb.connect('toggled', self.checkbutton_toggled, 'opacify_group')
        vbox.pack_start(self.opacify_group_cb, False)
        scalebox = gtk.HBox()
        scalelabel = gtk.Label("Opacity:")
        scalelabel.set_alignment(0,0.5)
        adj = gtk.Adjustment(0, 0, 100, 1, 10, 0)
        self.opacify_scale = gtk.HScale(adj)
        self.opacify_scale.set_digits(0)
        self.opacify_scale.set_value_pos(gtk.POS_RIGHT)
        adj.connect("value_changed", self.adjustment_changed, 'opacify_alpha')
        scalebox.pack_start(scalelabel, False)
        scalebox.pack_start(self.opacify_scale, True)
        vbox.pack_start(scalebox, False)
        hbox.pack_start(vbox, True, padding=5)

        appearance_box.pack_start(hbox, False, padding=5)

        hbox = gtk.HBox()
        label = gtk.Label('Theme:')
        label.set_alignment(1,0.5)
        self.theme_combo = gtk.combo_box_new_text()
        theme_names = self.themes.keys()
        theme_names.sort()
        for theme in theme_names:
                self.theme_combo.append_text(theme)
        button = gtk.Button()
        image = gtk.image_new_from_stock(gtk.STOCK_REFRESH,gtk.ICON_SIZE_SMALL_TOOLBAR)
        button.add(image)
        button.connect("clicked", self.set_theme)
        hbox.pack_start(label, False)
        hbox.pack_start(self.theme_combo, False)
        hbox.pack_start(button, False)

        appearance_box.pack_start(hbox, False, padding=5)

        frame = gtk.Frame('Colors')
        frame.set_border_width(5)
        table = gtk.Table(True)

        self.default_color_names = {
            "color1": 'Popup background',
            "color2": 'Normal text',
            "color3": 'Active window text',
            "color4": 'Minimized window text',
            "color5": 'Active color',
            "color6": 'Not used',
            "color7": 'Not used',
            "color8": 'Not used' }
        if self.theme:
            color_names = self.theme.get_color_names()
        else:
            color_names={}
            for i in range(1,9):
                color_names['color%s'%i]='Not used'
        self.color_labels = {}
        self.color_buttons = {}
        self.clear_buttons = {}
        for i in range(0, 8):
            c = "color%s"%(i+1)
            if color_names.has_key(c):
                text = color_names[c].capitalize()
            else:
                text = self.default_color_names[c]
            self.color_labels[c] = gtk.Label(text)
            self.color_labels[c].set_alignment(1,0.5)
            self.color_buttons[c] = gtk.ColorButton()
            self.color_buttons[c].set_title(text)
            self.color_buttons[c].connect("color-set",  self.color_set, c)
            self.clear_buttons[c] = gtk.Button()
            image = gtk.image_new_from_stock(gtk.STOCK_CLEAR,gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.clear_buttons[c].add(image)
            self.clear_buttons[c].connect("clicked", self.color_reset, c)
            # Every second label + combobox on a new row
            row = i // 2
            # Pack odd numbered comboboxes from 3rd column
            column = (i % 2)*3
            table.attach(self.color_labels[c], column, column + 1, row, row + 1, xoptions = gtk.FILL, xpadding = 5)
            table.attach(self.color_buttons[c], column+1, column+2, row, row + 1)
            table.attach(self.clear_buttons[c], column+2, column+3, row, row + 1, xoptions = gtk.FILL)

        table.set_border_width(5)
        frame.add(table)
        appearance_box.pack_start(frame, False, padding=5)

        #--- Groupbutton page
        table = gtk.Table(6,4)
        label = gtk.Label("<b>Groupbutton actions</b>")
        label.set_alignment(0,0.5)
        label.set_use_markup(True)
        table.attach(label, 0, 6, 0, 1)

        # A directory of combobox names and the name of corresponding setting
        self.gb_labels_and_settings = ODict((
                                             ('Left mouse button', "groupbutton_left_click_action"),
                                             ('Shift + left mouse button', "groupbutton_shift_and_left_click_action"),
                                             ('Middle mouse button', "groupbutton_middle_click_action"),
                                             ('Shift + middle mouse button', "groupbutton_shift_and_middle_click_action"),
                                             ( 'Right mouse button', "groupbutton_right_click_action"),
                                             ('Shift + right mouse button', "groupbutton_shift_and_right_click_action"),
                                             ('Scroll up', "groupbutton_scroll_up"),
                                             ('Scroll down', "groupbutton_scroll_down")
                                           ))

        gb_actions = ("select",
                      "close all windows",
                      "minimize all windows",
                      "maximize all windows",
                      "launch application",
                      "show menu",
                      "remove launcher",
                      "select next window",
                      "select previous window",
                      "minimize all other groups",
                      "compiz scale windows",
                      "compiz shift windows",
                      "compiz scale all",
                      "show preference dialog",
                      "no action")

        self.gb_combos = {}
        for text in self.gb_labels_and_settings:
            label = gtk.Label(text)
            label.set_alignment(1,0.5)
            self.gb_combos[text] = gtk.combo_box_new_text()
            for action in gb_actions:
                self.gb_combos[text].append_text(action)
            self.gb_combos[text].connect('changed', self.cb_changed)

            i = self.gb_labels_and_settings.get_index(text)
            # Every second label + combobox on a new row
            row = i // 2 + 1
            # Pack odd numbered comboboxes from 3rd column
            column = (i % 2) * 3
            table.attach(label, column, column + 1, row, row + 1, xpadding = 5 )
            table.attach(self.gb_combos[text],column + 1, column + 2, row, row + 1 )

        self.gb_doubleclick_checkbutton_names = ['groupbutton_left_click_double',
                            'groupbutton_shift_and_left_click_double',
                            'groupbutton_middle_click_double',
                            'groupbutton_shift_and_middle_click_double',
                            'groupbutton_right_click_double',
                            'groupbutton_shift_and_right_click_double']
        self.gb_doubleclick_checkbutton = {}
        for i in range(len(self.gb_doubleclick_checkbutton_names)):
            name = self.gb_doubleclick_checkbutton_names[i]
            self.gb_doubleclick_checkbutton[name] = gtk.CheckButton('Double click')

            self.gb_doubleclick_checkbutton[name].connect('toggled', self.checkbutton_toggled, name)
            # Every second label + combobox on a new row
            row = i // 2 + 1
            # Pack odd numbered comboboxes from 3rd column
            column = (i % 2) * 3
            table.attach(self.gb_doubleclick_checkbutton[name], column + 2, column + 3, row, row + 1, xpadding = 5 )

        groupbutton_box.pack_start(table, False, padding=5)

        hbox = gtk.HBox()
        table = gtk.Table(2,4)
        label = gtk.Label("<b>\"Select\" action options</b>")
        label.set_alignment(0,0.5)
        label.set_use_markup(True)
        table.attach(label,0,2,0,1)

        label = gtk.Label("One window open:")
        label.set_alignment(1,0.5)
        self.select_one_cg = gtk.combo_box_new_text()
        self.select_one_cg.append_text("select window")
        self.select_one_cg.append_text("select or minimize window")
        self.select_one_cg.connect('changed', self.cb_changed)
        table.attach(label,0,1,1,2)
        table.attach(self.select_one_cg,1,2,1,2)

        label = gtk.Label("Multiple windows open:")
        label.set_alignment(1,0.5)
        self.select_multiple_cg = gtk.combo_box_new_text()
        self.select_multiple_cg.append_text("select all")
        self.select_multiple_cg.append_text("select or minimize all")
        self.select_multiple_cg.append_text("compiz scale")
        self.select_multiple_cg.append_text("cycle through windows")
        self.select_multiple_cg.append_text("show popup")
        self.select_multiple_cg.connect('changed', self.cb_changed)
        table.attach(label,0,1,2,3)
        table.attach(self.select_multiple_cg,1,2,2,3)

        label = gtk.Label("Workspace behavior:")
        label.set_alignment(1,0.5)
        self.select_workspace_cg = gtk.combo_box_new_text()
        self.select_workspace_cg.append_text("Ignore windows on other workspaces")
        self.select_workspace_cg.append_text("Switch workspace when needed")
        self.select_workspace_cg.append_text("Move windows from other workspaces")
        self.select_workspace_cg.connect('changed', self.cb_changed)
        table.attach(label,0,1,3,4)
        table.attach(self.select_workspace_cg,1,2,3,4)

        hbox.pack_start(table, False, padding=5)


        vbox = gtk.VBox()
        label1 = gtk.Label("<b>Popup</b>")
        label1.set_alignment(0,0.5)
        label1.set_use_markup(True)
        vbox.pack_start(label1,False)
        spinbox = gtk.HBox()
        spinlabel = gtk.Label("Delay:")
        spinlabel.set_alignment(0,0.5)
        adj = gtk.Adjustment(0, 0, 2000, 1, 50)
        self.delay_spin = gtk.SpinButton(adj, 0.5, 0)
        adj.connect("value_changed", self.adjustment_changed, 'popup_delay')
        spinbox.pack_start(spinlabel, False)
        spinbox.pack_start(self.delay_spin, False)
        vbox.pack_start(spinbox, False)

        self.no_popup_cb = gtk.CheckButton('Show popup only if more than one window is open')
        self.no_popup_cb.connect('toggled', self.checkbutton_toggled, 'no_popup_for_one_window')
        vbox.pack_start(self.no_popup_cb, False)
        hbox.pack_start(vbox, False, padding=20)
        groupbutton_box.pack_start(hbox, False, padding=10)

        #--- Advanced page
        self.preview_cb = gtk.CheckButton('Show previews (beta feature)')
        self.preview_cb.connect('toggled', self.checkbutton_toggled, 'preview')
        advanced_box.pack_start(self.preview_cb, False)

        self.remember_previews_cb = gtk.CheckButton('Remember previews for minimized windows (Increaced memory usage)')
        self.remember_previews_cb.connect('toggled', self.checkbutton_toggled, 'remember_previews')
        advanced_box.pack_start(self.remember_previews_cb, False)

        spinbox = gtk.HBox()
        spinlabel = gtk.Label("Preview size:")
        spinlabel.set_alignment(0,0.5)
        adj = gtk.Adjustment(200, 50, 800, 1, 50)
        self.preview_size_spin = gtk.SpinButton(adj, 0.5, 0)
        adj.connect("value_changed", self.adjustment_changed, 'preview_size')
        spinbox.pack_start(spinlabel, False)
        spinbox.pack_start(self.preview_size_spin, False)
        advanced_box.pack_start(spinbox, False)

        self.ignore_workspace_cb = gtk.CheckButton('Ignore windows on other viewports/workspaces')
        self.ignore_workspace_cb.connect('toggled', self.checkbutton_toggled, 'show_only_current_desktop')
        advanced_box.pack_start(self.ignore_workspace_cb, False)

        self.wine_apps_cb = gtk.CheckButton('Give each wine application its own group button')
        self.wine_apps_cb.connect('toggled', self.checkbutton_toggled, 'separate_wine_apps')
        advanced_box.pack_start(self.wine_apps_cb, False)

        self.ooo_apps_cb = gtk.CheckButton('Keep open office application (Writer, Calc, etc.) separated')
        self.ooo_apps_cb.connect('toggled', self.checkbutton_toggled, 'separate_ooo_apps')
        advanced_box.pack_start(self.ooo_apps_cb, False)


        label = gtk.Label("Appearance")
        notebook.append_page(appearance_box, label)
        ca.pack_start(notebook)
        label = gtk.Label("Group Button")
        notebook.append_page(groupbutton_box, label)
        label = gtk.Label("Window Button")
        notebook.append_page(windowbutton_box, label)
        label = gtk.Label("Advanced")
        notebook.append_page(advanced_box, label)

        self.update()

        self.dialog.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.dialog.show_all()

    def load_theme(self):
        self.themes = self.find_themes()
        default_theme_path = None
        for theme, path in self.themes.items():
            if theme.lower() == self.globals.settings['theme'].lower():
                self.theme = Theme(path)
                break
            if theme.lower == self.globals.DEFAULT_SETTINGS['theme'].lower():
                default_theme_path = path
        else:
            if default_theme_path:
                # If the current theme according to gconf couldn't be found,
                # the default theme is used.
                self.theme = Theme(default_theme_path)
            else:
                self.theme = None

        if self.theme != None:
            self.theme_colors = self.theme.get_default_colors()
            self.theme_alphas = self.theme.get_default_alphas()
            self.globals.theme_name = self.theme.get_name()
            self.globals.update_colors(self.theme.get_name(),
                                       self.theme.get_default_colors(),
                                       self.theme.get_default_alphas())
        else:
            self.theme_colors = {}
            self.theme_alphas = {}

    def find_themes(self):
        # Reads the themes from /usr/share/dockbarx/themes and ~/.dockbarx/themes
        # and returns a dict of the theme names and paths so that
        # a theme can be loaded
        themes = {}
        theme_paths = []
        homeFolder = os.path.expanduser("~")
        theme_folder = homeFolder + "/.dockbarx/themes"
        dirs = ["/usr/share/dockbarx/themes", theme_folder]
        for dir in dirs:
            if os.path.exists(dir) and os.path.isdir(dir):
                for f in os.listdir(dir):
                    if f[-7:] == '.tar.gz':
                        theme_paths.append(dir+"/"+f)
        for theme_path in theme_paths:
            try:
                name = Theme.check(theme_path)
            except Exception, detail:
                print "Error loading theme from %s"%theme_path
                print detail
                name = None
            if name != None:
                name = str(name)
                themes[name] = theme_path
        if not themes:
            md = gtk.MessageDialog(None,
                gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                'No working themes found in "/usr/share/dockbarx/themes" or "~/.dockbarx/themes"')
            md.run()
            md.destroy()
        return themes


    def update(self, arg=None):
        """Set widgets according to settings."""

        # Attention notification
        settings_attention = self.globals.settings["groupbutton_attention_notification_type"]
        if settings_attention == 'compwater':
            self.rb1_1.set_active(True)
        elif settings_attention == 'blink':
            self.rb1_2.set_active(True)
        elif settings_attention == 'red':
            self.rb1_3.set_active(True)
        elif settings_attention == 'nothing':
            self.rb1_4.set_active(True)

        # Popup alignment
        settings_align = self.globals.settings["popup_align"]
        if settings_align == 'left':
            self.rb3_1.set_active(True)
        elif settings_align == 'center':
            self.rb3_2.set_active(True)
        elif settings_align == 'right':
            self.rb3_3.set_active(True)

        # Popup
        self.delay_spin.set_value(self.globals.settings['popup_delay'])
        self.no_popup_cb.set_active(self.globals.settings['no_popup_for_one_window'])

        # Group button keys
        for cb_name, setting_name in self.gb_labels_and_settings.items():
            value = self.globals.settings[setting_name]
            combobox = self.gb_combos[cb_name]
            model = combobox.get_model()
            for i in range(len(combobox.get_model())):
                if model[i][0] == value:
                    combobox.set_active(i)
                    break

        # Window button keys
        for cb_name, setting_name in self.wb_labels_and_settings.items():
            value = self.globals.settings[setting_name]
            combobox = self.wb_combos[cb_name]
            model = combobox.get_model()
            for i in range(len(combobox.get_model())):
                if model[i][0] == value:
                    combobox.set_active(i)
                    break

        for name in self.gb_doubleclick_checkbutton_names:
            self.gb_doubleclick_checkbutton[name].set_active(self.globals.settings[name])

        # Opacify
        self.opacify_cb.set_active(self.globals.settings['opacify'])
        self.opacify_group_cb.set_active(self.globals.settings['opacify_group'])
        self.opacify_scale.set_value(self.globals.settings['opacify_alpha'])

        self.opacify_group_cb.set_sensitive(self.globals.settings['opacify'])
        self.opacify_scale.set_sensitive(self.globals.settings['opacify'])

        # Colors
        if self.theme:
            self.theme_colors = self.theme.get_default_colors()
            self.theme_alphas = self.theme.get_default_alphas()
        else:
            self.theme_colors = {}
            self.theme_alphas = {}

        for i in range(1, 9):
            c = 'color%s'%i
            a = c+"_alpha"
            color = gtk.gdk.color_parse(self.globals.colors[c])
            self.color_buttons[c].set_color(color)
            #Alpha
            if a in self.globals.colors \
            and not (c in self.theme_alphas \
                     and "no" in self.theme_alphas[c]):
                alpha = self.globals.colors[a] * 256
                self.color_buttons[c].set_use_alpha(True)
                self.color_buttons[c].set_alpha(alpha)
            else:
                self.color_buttons[c].set_use_alpha(False)

        #Select action
        model = self.select_one_cg.get_model()
        for i in range(len(self.select_one_cg.get_model())):
                if model[i][0] == self.globals.settings['select_one_window'].lower():
                    self.select_one_cg.set_active(i)
                    break

        model = self.select_multiple_cg.get_model()
        for i in range(len(self.select_multiple_cg.get_model())):
                if model[i][0] == self.globals.settings['select_multiple_windows'].lower():
                    self.select_multiple_cg.set_active(i)
                    break

        model = self.select_workspace_cg.get_model()
        wso={
             "ignore":"Ignore windows on other workspaces",
             "switch":"Switch workspace when needed",
             "move":"Move windows from other workspaces"
            }
        for i in range(len(self.select_workspace_cg.get_model())):
                if model[i][0] == wso[self.globals.settings['workspace_behavior'].lower()]:
                    self.select_workspace_cg.set_active(i)
                    break

        # Themes
        model = self.theme_combo.get_model()
        for i in range(len(self.theme_combo.get_model())):
            if model[i][0].lower() == self.globals.settings['theme'].lower():
                self.theme_combo.set_active(i)
                break

        # Advanced page stuff
        self.preview_cb.set_active(self.globals.settings["preview"])
        self.remember_previews_cb.set_active(self.globals.settings["remember_previews"])
        self.remember_previews_cb.set_sensitive(self.globals.settings["preview"])
        self.preview_size_spin.set_value(self.globals.settings["preview_size"])
        self.preview_size_spin.set_sensitive(self.globals.settings["preview"])
        self.ignore_workspace_cb.set_active(self.globals.settings["show_only_current_desktop"])
        self.wine_apps_cb.set_active(self.globals.settings["separate_wine_apps"])
        self.ooo_apps_cb.set_active(self.globals.settings["separate_ooo_apps"])



    def dialog_close (self,par1,par2):
        self.dialog.destroy()
        gtk.main_quit()

    def rb_toggled (self,button,par1):
        # Read the value of the toggled radio button and write to gconf
        rb1_toggled = False
        rb2_toggled = False
        rb3_toggled = False

        if par1 == 'rb1_blink' and button.get_active():
            value = 'blink'
            rb1_toggled = True
        if par1 == 'rb1_compwater' and button.get_active():
            value = 'compwater'
            rb1_toggled = True
        if par1 == 'rb1_red' and button.get_active():
            value = 'red'
            rb1_toggled = True
        if par1 == 'rb1_nothing' and button.get_active():
            value = 'nothing'
            rb1_toggled = True

        if rb1_toggled and value != self.globals.settings["groupbutton_attention_notification_type"]:
            GCONF_CLIENT.set_string(GCONF_DIR+'/groupbutton_attention_notification_type', value)

        if par1 == 'rb3_left' and button.get_active():
            value = 'left'
            rb3_toggled = True
        if par1 == 'rb3_center' and button.get_active():
            value = 'center'
            rb3_toggled = True
        if par1 == 'rb3_right' and button.get_active():
            value = 'right'
            rb3_toggled = True

        if rb3_toggled and value != self.globals.settings["popup_align"]:
            GCONF_CLIENT.set_string(GCONF_DIR+'/popup_align', value)

    def checkbutton_toggled (self,button,name):
        # Read the value of the toggled check button/box and write to gconf
        if button.get_active() != self.globals.settings[name]:
            GCONF_CLIENT.set_bool(GCONF_DIR+'/'+name, button.get_active())


    def cb_changed(self, combobox):
        # Read the value of the combo box and write to gconf
        # Groupbutton settings
        for name, cb in self.gb_combos.items():
            if cb == combobox:
                setting_name = self.gb_labels_and_settings[name]
                value = combobox.get_active_text()
                if value == None:
                    return
                if value != self.globals.settings[setting_name]:
                    GCONF_CLIENT.set_string(GCONF_DIR+'/'+setting_name, value)

        # Windowbutton settings
        for name, cb in self.wb_combos.items():
            if cb == combobox:
                setting_name = self.wb_labels_and_settings[name]
                value = combobox.get_active_text()
                if value == None:
                    return
                if value != self.globals.settings[setting_name]:
                    GCONF_CLIENT.set_string(GCONF_DIR+'/'+setting_name, value)

        if combobox == self.theme_combo:
            value = combobox.get_active_text()
            if value == None:
                return
            if value != self.globals.settings['theme']:
                GCONF_CLIENT.set_string(GCONF_DIR+'/theme', value)

        if combobox == self.select_one_cg:
            value = combobox.get_active_text()
            if value == None:
                return
            if value != self.globals.settings['select_one_window']:
                GCONF_CLIENT.set_string(GCONF_DIR+'/select_one_window', value)

        if combobox == self.select_multiple_cg:
            value = combobox.get_active_text()
            if value == None:
                return
            if value != self.globals.settings['select_multiple_windows']:
                GCONF_CLIENT.set_string(GCONF_DIR+'/select_multiple_windows', value)

        if combobox == self.select_workspace_cg:
            value = combobox.get_active_text()
            wso={
                 "Ignore windows on other workspaces":"ignore",
                 "Switch workspace when needed":"switch",
                 "Move windows from other workspaces":"move"
                }
            if value == None:
                return
            if value != self.globals.settings['workspace_behavior']:
                GCONF_CLIENT.set_string(GCONF_DIR+'/workspace_behavior', wso[value])

    def adjustment_changed(self, widget, setting):
        # Read the value of the adjustment and write to gconf
        value = int(widget.get_value())
        if value != self.globals.settings[setting]:
            GCONF_CLIENT.set_int(GCONF_DIR+'/'+setting, value)

    def color_set(self, button, c):
        # Read the value from color (and aplha) and write
        # it as 8-bit/channel hex string for gconf.
        # (Alpha is written like int (0-255).)
        if not self.theme:
            return
        color_string = self.globals.colors[c]
        color = button.get_color()
        cs = color.to_string()
        # cs has 16-bit per color, we want 8.
        new_color = cs[0:3] + cs[5:7] + cs[9:11]
        theme_name = self.theme.get_name().replace(' ', '_').encode()
        try:
            theme_name = theme_name.translate(None, '!?*()/#"@')
        except:
            pass
        color_dir = GCONF_DIR + '/themes/' + theme_name
        if new_color != color_string:
            GCONF_CLIENT.set_string(color_dir+'/'+c, new_color)
        if button.get_use_alpha():
            if self.globals.colors.has_key(c+"_alpha"):
                alpha = self.globals.colors[c+"_alpha"]
            else:
                alpha = None
            new_alpha = min(int(float(button.get_alpha()) / 256 + 0.5), 255)
            if new_alpha != alpha:
                GCONF_CLIENT.set_int(color_dir+'/'+c+"_alpha", new_alpha)

    def color_reset(self, button, c):
        # Reset gconf color setting to default.
        if not self.theme:
            return
        if self.theme_colors.has_key(c):
            color_string = self.theme_colors[c]
        else:
            color_string = self.globals.DEFAULT_COLORS[c]
        theme_name = self.theme.get_name().replace(' ', '_').encode()
        try:
            theme_name = theme_name.translate(None, '!?*()/#"@')
        except:
            pass
        color_dir = GCONF_DIR + '/themes/' + theme_name
        GCONF_CLIENT.set_string(color_dir+'/'+c, color_string)
        if self.theme_alphas.has_key(c):
            if 'no' in self.theme_alphas[c]:
                return
            alpha = int(int(self.theme_alphas[c]) * 2.55 + 0.4)
        elif self.globals.DEFAULT_COLORS.has_key(c+"_alpha"):
            alpha = self.globals.DEFAULT_COLORS[c+"_alpha"]
        else:
            return
        GCONF_CLIENT.set_int(color_dir+'/'+c+"_alpha", alpha)

    def set_theme(self, button=None):
        value = self.theme_combo.get_active_text()
        if value == None:
            return
        if value != self.globals.settings['theme']:
            GCONF_CLIENT.set_string(GCONF_DIR+'/theme', value)
        else:
            # Check if the theme list
            # has changed anyway.
            self.load_theme()
            self.theme_combo.get_model().clear()
            theme_names = self.themes.keys()
            theme_names.sort()
            for theme in theme_names:
                    self.theme_combo.append_text(theme)
            # Color labels
            color_names = self.theme.get_color_names()
            for i in range(1, 9):
                c = 'color%s'%i
                if color_names.has_key(c):
                    text = color_names[c].capitalize()
                else:
                    text = self.default_color_names[c]
                self.color_labels[c].set_text(text)
                self.color_buttons[c].set_title(text)

    def on_theme_changed(self, arg):
        self.load_theme()
        self.theme_combo.get_model().clear()
        theme_names = self.themes.keys()
        theme_names.sort()
        for theme in theme_names:
                self.theme_combo.append_text(theme)
        # Color labels
        color_names = self.theme.get_color_names()
        for i in range(1, 9):
            c = 'color%s'%i
            if color_names.has_key(c):
                text = color_names[c].capitalize()
            else:
                text = self.default_color_names[c]
            self.color_labels[c].set_text(text)
            self.color_buttons[c].set_title(text)

PrefDialog()
gtk.main()
