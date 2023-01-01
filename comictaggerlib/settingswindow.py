"""A PyQT4 dialog to enter app settings"""
#
# Copyright 2012-2014 Anthony Beville
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import argparse
import html
import logging
import os
import pathlib
import platform
from typing import Any

import settngs
from PyQt5 import QtCore, QtGui, QtWidgets, uic

from comicapi import utils
from comicapi.genericmetadata import md_test
from comictaggerlib.ctversion import version
from comictaggerlib.filerenamer import FileRenamer, Replacement, Replacements
from comictaggerlib.imagefetcher import ImageFetcher
from comictaggerlib.ui import ui_path
from comictalker.comiccacher import ComicCacher
from comictalker.talkerbase import ComicTalker

logger = logging.getLogger(__name__)

windowsRarHelp = """
                <html><head/><body><p>To write to CBR/RAR archives,
                you will need to have the tools from
                <span style=" text-decoration: underline; color:#0000ff;">
                <a href="http://www.win-rar.com/download.html">WINRar</a></span>
                installed. (ComicTagger only uses the command-line rar tool.)
                </p></body></html>
                """

linuxRarHelp = """
                <html><head/><body><p>To write to CBR/RAR archives,
                you will need to have the shareware rar tool from RARLab installed.
                Your package manager should have rar (e.g. "apt-get install rar"). If not, download it
                <span style=" text-decoration: underline; color:#0000ff;">
                <a href="https://www.rarlab.com/download.htm">here</a></span>,
                and install in your path. </p></body></html>
                """

macRarHelp = """
                <html><head/><body><p>To write to CBR/RAR archives,
                you will need the rar tool.  The easiest way to get this is
                to install <span style=" text-decoration: underline; color:#0000ff;">
                <a href="https://brew.sh/">homebrew</a></span>.
                </p>Once homebrew is installed, run: <b>brew install caskroom/cask/rar</b></body></html>
                """


template_tooltip = """
The template for the new filename. Uses python format strings https://docs.python.org/3/library/string.html#format-string-syntax
Accepts the following variables:
{is_empty}         (boolean)
{tag_origin}       (string)
{series}           (string)
{issue}            (string)
{title}            (string)
{publisher}        (string)
{month}            (integer)
{year}             (integer)
{day}              (integer)
{issue_count}      (integer)
{volume}           (integer)
{genre}            (string)
{language}         (string)
{comments}         (string)
{volume_count}     (integer)
{critical_rating}  (float)
{country}          (string)
{alternate_series} (string)
{alternate_number} (string)
{alternate_count}  (integer)
{imprint}          (string)
{notes}            (string)
{web_link}         (string)
{format}           (string)
{manga}            (string)
{black_and_white}  (boolean)
{page_count}       (integer)
{maturity_rating}  (string)
{story_arc}        (string)
{series_group}     (string)
{scan_info}        (string)
{characters}       (string)
{teams}            (string)
{locations}        (string)
{credits}          (list of dict({'role': string, 'person': string, 'primary': boolean}))
{writer}           (string)
{penciller}        (string)
{inker}            (string)
{colorist}         (string)
{letterer}         (string)
{cover artist}     (string)
{editor}           (string)
{tags}             (list of str)
{pages}            (list of dict({'Image': string(int), 'Type': string, 'Bookmark': string, 'DoublePage': boolean}))

CoMet-only items:
{price}            (float)
{is_version_of}    (string)
{rights}           (string)
{identifier}       (string)
{last_mark}        (string)
{cover_image}      (string)

Examples:

{series} {issue} ({year})
Spider-Geddon 1 (2018)

{series} #{issue} - {title}
Spider-Geddon #1 - New Players; Check In
"""


class SettingsWindow(QtWidgets.QDialog):
    def __init__(
        self, parent: QtWidgets.QWidget, options: settngs.Config, talker_api: ComicTalker, talker_plugins: dict
    ) -> None:
        super().__init__(parent)

        uic.loadUi(ui_path / "settingswindow.ui", self)

        self.setWindowFlags(
            QtCore.Qt.WindowType(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        )

        self.options = options
        self.talker_api = talker_api
        self.talker_plugins = talker_plugins
        self.name = "Settings"

        if platform.system() == "Windows":
            self.lblRarHelp.setText(windowsRarHelp)

        elif platform.system() == "Linux":
            self.lblRarHelp.setText(linuxRarHelp)

        elif platform.system() == "Darwin":
            self.leRarExePath.setReadOnly(False)

            self.lblRarHelp.setText(macRarHelp)
            self.name = "Preferences"

        self.setWindowTitle("ComicTagger " + self.name)
        self.lblDefaultSettings.setText("Revert to default " + self.name.casefold())
        self.btnResetSettings.setText("Default " + self.name)

        nmit_tip = """<html>The <b>Name Match Ratio Threshold: Auto-Identify</b> is for eliminating automatic
                search matches that are too long compared to your series name search. The lower
                it is, the more likely to have a good match, but each search will take longer and
                use more bandwidth. Too high, and only the very closest matches will be explored.</html>"""
        nmst_tip = """<html>The <b>Name Match Ratio Threshold: Search</b> is for reducing the total
                number of results that are returned from a search. The lower it is, the more pages will
                be returned (max 5 pages or 500 results)</html>"""

        self.sbNameMatchIdentifyThresh.setToolTip(nmit_tip)
        self.sbNameMatchSearchThresh.setToolTip(nmst_tip)

        pbl_tip = """<html>
            The <b>Publisher Filter</b> is for eliminating automatic matches to certain publishers
            that you know are incorrect. Useful for avoiding international re-prints with same
            covers or series names. Enter publisher names separated by commas.
            </html>"""
        self.tePublisherFilter.setToolTip(pbl_tip)

        validator = QtGui.QIntValidator(1, 4, self)
        self.leIssueNumPadding.setValidator(validator)

        self.leRenameTemplate.setToolTip(f"<pre>{html.escape(template_tooltip)}</pre>")
        self.settings_to_form()
        self.rename_error: Exception | None = None
        self.rename_test()
        self.dir_test()

        self.btnBrowseRar.clicked.connect(self.select_rar)
        self.btnClearCache.clicked.connect(self.clear_cache)
        self.btnResetSettings.clicked.connect(self.reset_settings)
        # self.btnTestKey.clicked.connect(self.test_api_key)
        self.btnTemplateHelp.clicked.connect(self.show_template_help)
        self.cbxMoveFiles.clicked.connect(self.dir_test)
        self.leDirectory.textEdited.connect(self.dir_test)
        self.cbxComplicatedParser.clicked.connect(self.switch_parser)

        self.btnAddLiteralReplacement.clicked.connect(self.addLiteralReplacement)
        self.btnAddValueReplacement.clicked.connect(self.addValueReplacement)
        self.btnRemoveLiteralReplacement.clicked.connect(self.removeLiteralReplacement)
        self.btnRemoveValueReplacement.clicked.connect(self.removeValueReplacement)

        self.leRenameTemplate.textEdited.connect(self.rename_test)
        self.cbxMoveFiles.clicked.connect(self.rename_test)
        self.cbxRenameStrict.clicked.connect(self.rename_test)
        self.cbxSmartCleanup.clicked.connect(self.rename_test)
        self.cbxChangeExtension.clicked.connect(self.rename_test)
        self.leIssueNumPadding.textEdited.connect(self.rename_test)
        self.twLiteralReplacements.cellChanged.connect(self.rename_test)
        self.twValueReplacements.cellChanged.connect(self.rename_test)

        self.sources: dict = {}
        self.generate_source_option_tabs()

    def generate_source_option_tabs(self) -> None:
        # Add source sub tabs to Comic Sources tab
        for source_name, source_cls in self.talker_plugins.items():

            # Add source to general tab dropdown list
            self.cobxInfoSource.addItem(source_name, source_name)

            # Use a dict to make a var name from var
            source_info = {}
            tab_name = source_name
            source_info[tab_name] = {"tab": QtWidgets.QWidget(), "widgets": {}}
            layout_grid = QtWidgets.QGridLayout()
            row = 0

            # Add logo and web link if available
            """if source.static_options.website:
                source_label_logo = QtGui.QPixmap(source.source_details.logo)

                source_website_icon_link = QtWidgets.QPushButton()
                source_website_icon_link.clicked.connect(
                    lambda state, w=source.static_options.website: open_web_link(w)
                )
                source_website_icon_link.setToolTip(f"Click to visit website: {source.static_options.website}")
                source_website_icon_link.setMaximumSize(250, 100)

                if source_label_logo.isNull():
                    source_website_icon_link.setFont(QtGui.QFont("Arial", 14, 3))
                    source_website_icon_link.setText(source.source_details.name)
                else:
                    if source_label_logo.height() > 100 or source_label_logo.width() > 250:
                        source_label_logo = source_label_logo.scaled(
                            250, 100, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                        )

                    source_website_icon_link.setIconSize(QtCore.QSize(source_label_logo.rect().size()))
                    source_website_icon_link.setFixedSize(QtCore.QSize(source_label_logo.rect().size()))
                    source_website_icon_link.setIcon(QtGui.QIcon(source_label_logo))
                    source_website_icon_link.setFlat(True)

                layout_grid.addWidget(source_website_icon_link, row, 0, 1, -1)
                row += 1"""

            for option in self.options[1][source_name].values():
                current_widget = None
                if option.action is not None and isinstance(option.action, type(argparse.BooleanOptionalAction)):
                    # bool equals a checkbox (QCheckBox)
                    current_widget = QtWidgets.QCheckBox(option.internal_name)
                    # Set widget status
                    current_widget.setChecked(getattr(self.options[0], option.internal_name))
                    # Add widget and span all columns
                    layout_grid.addWidget(current_widget, row, 0, 1, -1)
                elif isinstance(option.type, type(int)):
                    # int equals a spinbox (QSpinBox)
                    lbl = QtWidgets.QLabel(option.internal_name)
                    # Create a label
                    layout_grid.addWidget(lbl, row, 0)
                    current_widget = QtWidgets.QSpinBox()
                    current_widget.setRange(0, 9999)
                    current_widget.setValue(getattr(self.options[0], option.internal_name))
                    layout_grid.addWidget(current_widget, row, 1, alignment=QtCore.Qt.AlignLeft)
                elif isinstance(option.type, type(float)):
                    # float equals a spinbox (QDoubleSpinBox)
                    lbl = QtWidgets.QLabel(option.internal_name)
                    # Create a label
                    layout_grid.addWidget(lbl, row, 0)
                    current_widget = QtWidgets.QDoubleSpinBox()
                    current_widget.setRange(0, 9999.99)
                    current_widget.setValue(getattr(self.options[0], option.internal_name))
                    layout_grid.addWidget(current_widget, row, 1, alignment=QtCore.Qt.AlignLeft)
                # type of None should be string
                elif option.type is None or isinstance(option.type, type(str)):
                    # str equals a text field (QLineEdit)
                    lbl = QtWidgets.QLabel(option.internal_name)
                    # Create a label
                    layout_grid.addWidget(lbl, row, 0)
                    current_widget = QtWidgets.QLineEdit()
                    # Set widget status
                    current_widget.setText(getattr(self.options[0], option.internal_name))
                    layout_grid.addWidget(current_widget, row, 1)
                    # Special case for api_key, make a test button
                    if option.internal_name.endswith("api_key"):
                        btn = QtWidgets.QPushButton("Test Key")
                        layout_grid.addWidget(btn, row, 2)
                        btn.clicked.connect(lambda state, sn=source_name: self.test_api_key(sn))
                row += 1

                if current_widget:
                    # Add tooltip text
                    current_widget.setToolTip(option.help)

                    source_info[tab_name]["widgets"][option.internal_name] = current_widget
                else:
                    # An empty current_widget implies an unsupported type
                    logger.info(f"Unsupported talker option found. Name: {option.internal_name} Type: {option.type}")

            # Add vertical spacer
            vspacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
            layout_grid.addItem(vspacer, row, 0)
            # Display the new widgets
            source_info[tab_name]["tab"].setLayout(layout_grid)

            # Add new sub tab to Comic Source tab
            self.tTalkerTabs.addTab(source_info[tab_name]["tab"], source_name)
            self.sources.update(source_info)

        # Select active source in dropdown
        self.cobxInfoSource.setCurrentIndex(self.cobxInfoSource.findData(self.options[0].talkers_general_source))

        # Set General as start tab
        self.tabWidget.setCurrentIndex(0)

    def addLiteralReplacement(self) -> None:
        self.insertRow(self.twLiteralReplacements, self.twLiteralReplacements.rowCount(), Replacement("", "", False))

    def addValueReplacement(self) -> None:
        self.insertRow(self.twValueReplacements, self.twValueReplacements.rowCount(), Replacement("", "", False))

    def removeLiteralReplacement(self) -> None:
        if self.twLiteralReplacements.currentRow() >= 0:
            self.twLiteralReplacements.removeRow(self.twLiteralReplacements.currentRow())

    def removeValueReplacement(self) -> None:
        if self.twValueReplacements.currentRow() >= 0:
            self.twValueReplacements.removeRow(self.twValueReplacements.currentRow())

    def insertRow(self, table: QtWidgets.QTableWidget, row: int, replacement: Replacement) -> None:
        find, replace, strict_only = replacement
        table.insertRow(row)
        table.setItem(row, 0, QtWidgets.QTableWidgetItem(find))
        table.setItem(row, 1, QtWidgets.QTableWidgetItem(replace))
        tmp = QtWidgets.QTableWidgetItem()
        if strict_only:
            tmp.setCheckState(QtCore.Qt.Checked)
        else:
            tmp.setCheckState(QtCore.Qt.Unchecked)
        table.setItem(row, 2, tmp)

    def rename_test(self, *args: Any, **kwargs: Any) -> None:
        self._rename_test(self.leRenameTemplate.text())

    def dir_test(self) -> None:
        self.lblDir.setText(
            str(pathlib.Path(self.leDirectory.text().strip()).resolve()) if self.cbxMoveFiles.isChecked() else ""
        )

    def _rename_test(self, template: str) -> None:
        fr = FileRenamer(
            md_test,
            platform="universal" if self.cbxRenameStrict.isChecked() else "auto",
            replacements=self.get_replacemnts(),
        )
        fr.move = self.cbxMoveFiles.isChecked()
        fr.set_template(template)
        fr.set_issue_zero_padding(int(self.leIssueNumPadding.text()))
        fr.set_smart_cleanup(self.cbxSmartCleanup.isChecked())
        try:
            self.lblRenameTest.setText(fr.determine_name(".cbz"))
            self.rename_error = None
        except Exception as e:
            self.rename_error = e
            self.lblRenameTest.setText(str(e))

    def switch_parser(self) -> None:
        complicated = self.cbxComplicatedParser.isChecked()

        self.cbxRemoveC2C.setEnabled(complicated)
        self.cbxRemoveFCBD.setEnabled(complicated)
        self.cbxRemovePublisher.setEnabled(complicated)

    def settings_to_form(self) -> None:
        # Copy values from settings to form
        self.leRarExePath.setText(self.options[0].general_rar_exe_path)
        self.sbNameMatchIdentifyThresh.setValue(self.options[0].identifier_series_match_identify_thresh)
        self.sbNameMatchSearchThresh.setValue(self.options[0].comicvine_series_match_search_thresh)
        self.tePublisherFilter.setPlainText("\n".join(self.options[0].identifier_publisher_filter))

        self.cbxCheckForNewVersion.setChecked(self.options[0].general_check_for_new_version)

        self.cbxComplicatedParser.setChecked(self.options[0].filename_complicated_parser)
        self.cbxRemoveC2C.setChecked(self.options[0].filename_remove_c2c)
        self.cbxRemoveFCBD.setChecked(self.options[0].filename_remove_fcbd)
        self.cbxRemovePublisher.setChecked(self.options[0].filename_remove_publisher)
        self.switch_parser()

        self.cbxUseSeriesStartAsVolume.setChecked(self.options[0].comicvine_cv_use_series_start_as_volume)
        self.cbxClearFormBeforePopulating.setChecked(self.options[0].talkers_general_clear_form_before_populating)
        # self.cbxRemoveHtmlTables.setChecked(self.options[0].comicvine_cv_remove_html_tables)

        self.cbxUseFilter.setChecked(self.options[0].talkers_general_always_use_publisher_filter)
        self.cbxSortByYear.setChecked(self.options[0].talkers_general_sort_series_by_year)
        self.cbxExactMatches.setChecked(self.options[0].talkers_general_exact_series_matches_first)

        self.cbxAssumeLoneCreditIsPrimary.setChecked(self.options[0].cbl_assume_lone_credit_is_primary)
        self.cbxCopyCharactersToTags.setChecked(self.options[0].cbl_copy_characters_to_tags)
        self.cbxCopyTeamsToTags.setChecked(self.options[0].cbl_copy_teams_to_tags)
        self.cbxCopyLocationsToTags.setChecked(self.options[0].cbl_copy_locations_to_tags)
        self.cbxCopyStoryArcsToTags.setChecked(self.options[0].cbl_copy_storyarcs_to_tags)
        self.cbxCopyNotesToComments.setChecked(self.options[0].cbl_copy_notes_to_comments)
        self.cbxCopyWebLinkToComments.setChecked(self.options[0].cbl_copy_weblink_to_comments)
        self.cbxApplyCBLTransformOnCVIMport.setChecked(self.options[0].cbl_apply_transform_on_import)
        self.cbxApplyCBLTransformOnBatchOperation.setChecked(self.options[0].cbl_apply_transform_on_bulk_operation)

        self.leRenameTemplate.setText(self.options[0].rename_template)
        self.leIssueNumPadding.setText(str(self.options[0].rename_issue_number_padding))
        self.cbxSmartCleanup.setChecked(self.options[0].rename_use_smart_string_cleanup)
        self.cbxChangeExtension.setChecked(self.options[0].rename_set_extension_based_on_archive)
        self.cbxMoveFiles.setChecked(self.options[0].rename_move_to_dir)
        self.leDirectory.setText(self.options[0].rename_dir)
        self.cbxRenameStrict.setChecked(self.options[0].rename_strict)

        for table, replacments in zip(
            (self.twLiteralReplacements, self.twValueReplacements), self.options[0].rename_replacements
        ):
            table.clearContents()
            for i in reversed(range(table.rowCount())):
                table.removeRow(i)
            for row, replacement in enumerate(replacments):
                self.insertRow(table, row, replacement)

    def get_replacemnts(self) -> Replacements:
        literal_replacements = []
        value_replacements = []
        for row in range(self.twLiteralReplacements.rowCount()):
            if self.twLiteralReplacements.item(row, 0).text():
                literal_replacements.append(
                    Replacement(
                        self.twLiteralReplacements.item(row, 0).text(),
                        self.twLiteralReplacements.item(row, 1).text(),
                        self.twLiteralReplacements.item(row, 2).checkState() == QtCore.Qt.Checked,
                    )
                )
        for row in range(self.twValueReplacements.rowCount()):
            if self.twValueReplacements.item(row, 0).text():
                value_replacements.append(
                    Replacement(
                        self.twValueReplacements.item(row, 0).text(),
                        self.twValueReplacements.item(row, 1).text(),
                        self.twValueReplacements.item(row, 2).checkState() == QtCore.Qt.Checked,
                    )
                )
        return Replacements(literal_replacements, value_replacements)

    def accept(self) -> None:
        self.rename_test()
        if self.rename_error is not None:
            if isinstance(self.rename_error, ValueError):
                logger.exception("Invalid format string: %s", self.options[0].rename_template)
                QtWidgets.QMessageBox.critical(
                    self,
                    "Invalid format string!",
                    "Your rename template is invalid!"
                    f"<br/><br/>{self.rename_error}<br/><br/>"
                    "Please consult the template help in the "
                    "settings and the documentation on the format at "
                    "<a href='https://docs.python.org/3/library/string.html#format-string-syntax'>"
                    "https://docs.python.org/3/library/string.html#format-string-syntax</a>",
                )
                return
            else:
                logger.exception(
                    "Formatter failure: %s metadata: %s", self.options[0].rename_template, self.renamer.metadata
                )
                QtWidgets.QMessageBox.critical(
                    self,
                    "The formatter had an issue!",
                    "The formatter has experienced an unexpected error!"
                    f"<br/><br/>{type(self.rename_error).__name__}: {self.rename_error}<br/><br/>"
                    "Please open an issue at "
                    "<a href='https://github.com/comictagger/comictagger'>"
                    "https://github.com/comictagger/comictagger</a>",
                )

        # Copy values from form to settings and save
        self.options[0].general_rar_exe_path = str(self.leRarExePath.text())

        # make sure rar program is now in the path for the rar class
        if self.options[0].general_rar_exe_path:
            utils.add_to_path(os.path.dirname(self.options[0].general_rar_exe_path))

        if not str(self.leIssueNumPadding.text()).isdigit():
            self.leIssueNumPadding.setText("0")

        self.options[0].general_check_for_new_version = self.cbxCheckForNewVersion.isChecked()

        self.options[0].identifier_series_match_identify_thresh = self.sbNameMatchIdentifyThresh.value()
        self.options[0].comicvine_cv_series_match_search_thresh = self.sbNameMatchSearchThresh.value()
        self.options[0].identifier_publisher_filter = [
            x.strip() for x in str(self.tePublisherFilter.toPlainText()).splitlines() if x.strip()
        ]

        self.options[0].filename_complicated_parser = self.cbxComplicatedParser.isChecked()
        self.options[0].filename_remove_c2c = self.cbxRemoveC2C.isChecked()
        self.options[0].filename_remove_fcbd = self.cbxRemoveFCBD.isChecked()
        self.options[0].filename_remove_publisher = self.cbxRemovePublisher.isChecked()

        self.options[0].comicvine_cv_use_series_start_as_volume = self.cbxUseSeriesStartAsVolume.isChecked()
        self.options[0].talkers_general_clear_form_before_populating = self.cbxClearFormBeforePopulating.isChecked()
        # self.options[0].comicvine_cv_remove_html_tables = self.cbxRemoveHtmlTables.isChecked()

        self.options[0].talkers_general_always_use_publisher_filter = self.cbxUseFilter.isChecked()
        self.options[0].talkers_general_sort_series_by_year = self.cbxSortByYear.isChecked()
        self.options[0].talkers_general_exact_series_matches_first = self.cbxExactMatches.isChecked()
        self.options[0].talkers_general_source = str(self.cobxInfoSource.itemData(self.cobxInfoSource.currentIndex()))

        self.options[0].cbl_assume_lone_credit_is_primary = self.cbxAssumeLoneCreditIsPrimary.isChecked()
        self.options[0].cbl_copy_characters_to_tags = self.cbxCopyCharactersToTags.isChecked()
        self.options[0].cbl_copy_teams_to_tags = self.cbxCopyTeamsToTags.isChecked()
        self.options[0].cbl_copy_locations_to_tags = self.cbxCopyLocationsToTags.isChecked()
        self.options[0].cbl_copy_storyarcs_to_tags = self.cbxCopyStoryArcsToTags.isChecked()
        self.options[0].cbl_copy_notes_to_comments = self.cbxCopyNotesToComments.isChecked()
        self.options[0].cbl_copy_weblink_to_comments = self.cbxCopyWebLinkToComments.isChecked()
        self.options[0].cbl_apply_transform_on_import = self.cbxApplyCBLTransformOnCVIMport.isChecked()
        self.options[0].cbl_apply_transform_on_bulk_operation = self.cbxApplyCBLTransformOnBatchOperation.isChecked()

        self.options[0].rename_template = str(self.leRenameTemplate.text())
        self.options[0].rename_issue_number_padding = int(self.leIssueNumPadding.text())
        self.options[0].rename_use_smart_string_cleanup = self.cbxSmartCleanup.isChecked()
        self.options[0].rename_set_extension_based_on_archive = self.cbxChangeExtension.isChecked()
        self.options[0].rename_move_to_dir = self.cbxMoveFiles.isChecked()
        self.options[0].rename_dir = self.leDirectory.text()

        self.options[0].rename_strict = self.cbxRenameStrict.isChecked()
        self.options[0].rename_replacements = self.get_replacemnts()

        # Read settings from sources tabs and generate self.settings.config data
        for tab in self.sources.items():
            for name, widget in tab[1]["widgets"].items():
                widget_value = None
                if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                    widget_value = widget.value()
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget_value = widget.text().strip()
                elif isinstance(widget, QtWidgets.QCheckBox):
                    widget_value = widget.isChecked()

                setattr(self.options[0], name, widget_value)

                # Update talker options in object
                if widget_value is not None and tab[0] == self.options[0].talkers_general_source:
                    # TODO Special case for url and api key. If empty str reset to default. Not required if reloaded.
                    setattr(self.talker_api, name, widget_value)

        settngs.save_file(self.options, self.options[0].runtime_config.user_config_dir / "settings.json")
        self.parent().options = self.options
        QtWidgets.QDialog.accept(self)

        # TODO Reload talkerapi with selected talker

    def select_rar(self) -> None:
        self.select_file(self.leRarExePath, "RAR")

    def clear_cache(self) -> None:
        ImageFetcher(self.options[0].runtime_config.user_cache_dir).clear_cache()
        ComicCacher(self.options[0].runtime_config.user_cache_dir, version).clear_cache()
        QtWidgets.QMessageBox.information(self, self.name, "Cache has been cleared.")

    def test_api_key(self, source_id) -> None:
        # Only allow testing of active talker
        # TODO Make classmethod to allow testing of all?
        if source_id == self.options[0].talkers_general_source:
            # Find URL and API key
            for tab in self.sources.items():
                for name, widget in tab[1]["widgets"].items():
                    if tab[0] == source_id:
                        if name.endswith("api_key"):
                            key = widget.text().strip()
                        if name.endswith("url"):
                            url = widget.text().strip()

            if self.talker_api.check_api_key(key, url):
                QtWidgets.QMessageBox.information(self, "API Key Test", "Key is valid!")
            else:
                QtWidgets.QMessageBox.warning(self, "API Key Test", "Key is NOT valid!")
        else:
            QtWidgets.QMessageBox.warning(self, "API Key Test", "Unable to test inactive sources!")

    def reset_settings(self) -> None:
        self.options = settngs.Config(settngs.defaults(self.options[1]), self.options[1])
        self.settings_to_form()
        QtWidgets.QMessageBox.information(self, self.name, self.name + " have been returned to default values.")

    def select_file(self, control: QtWidgets.QLineEdit, name: str) -> None:

        dialog = QtWidgets.QFileDialog(self)
        dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)

        if platform.system() == "Windows":
            if name == "RAR":
                flt = "Rar Program (Rar.exe)"
            else:
                flt = "Libraries (*.dll)"
            dialog.setNameFilter(flt)
        else:
            dialog.setFilter(QtCore.QDir.Filter.Files)

        dialog.setDirectory(os.path.dirname(str(control.text())))
        if name == "RAR":
            dialog.setWindowTitle(f"Find {name} program")
        else:
            dialog.setWindowTitle(f"Find {name} library")

        if dialog.exec():
            file_list = dialog.selectedFiles()
            control.setText(str(file_list[0]))

    def show_rename_tab(self) -> None:
        self.tabWidget.setCurrentIndex(5)

    def show_template_help(self) -> None:
        template_help_win = TemplateHelpWindow(self)
        template_help_win.setModal(False)
        template_help_win.show()


class TemplateHelpWindow(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)

        uic.loadUi(ui_path / "TemplateHelp.ui", self)
