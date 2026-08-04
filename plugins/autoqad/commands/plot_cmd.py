# -*- coding: utf-8 -*-
"""Plotting commands — PLOT, PAGESETUP, PLOTSTYLE, PLOTTHEME.

Model space is black; paper is white. Everything here exists to bridge that,
and the three commands cover the three ways a user can want to cross it:

``PLOT``
    Open AutoQAD's own plot sheet and send the drawing to PDF, an image, a
    printer, or a fresh QGIS layout.
``PLOTSTYLE``
    Set the plot style table from the command line, no dialog — the fast path
    when only the CTB needs changing.
``PLOTTHEME``
    Publish the paper style as a QGIS **map theme**, so QGIS's own layout
    designer can produce a correct plot with no AutoQAD involvement at all.

None of them modify the drawing, so all three declare ``modifies = False`` and
none needs an undo transaction.
"""

from ..engine.command import Command
from ..engine.prompt import KeywordPrompt
from ..style import plot_render, plotstyle


class PlotCommand(Command):
    """Open the plot sheet."""

    name = "PLOT"
    aliases = ("PRINT", "PLT")
    description = "Plot the drawing to PDF, an image, a printer or a layout."
    group = "tools"
    modifies = False

    def run(self):
        opener = getattr(self.context, "open_dialog", None)
        if opener is None:
            self.write("PLOT needs the AutoQAD user interface.")
        else:
            opener("plot")
        return
        yield        # noqa: unreachable - keeps run() a generator


class PageSetupCommand(Command):
    """AutoCAD keeps page setup separate; AutoQAD folds it into the plot sheet.

    Sheet size, orientation, margin, scale and plot style are all remembered in
    the PLOT* system variables, so setting them up and plotting are the same
    dialog — there is nothing left for a separate one to hold.
    """

    name = "PAGESETUP"
    aliases = ("PAGESET",)
    description = "Set the sheet, scale and plot style (the plot sheet)."
    group = "tools"
    modifies = False

    def run(self):
        opener = getattr(self.context, "open_dialog", None)
        if opener is None:
            self.write("PAGESETUP needs the AutoQAD user interface.")
        else:
            opener("plot")
        return
        yield        # noqa: unreachable - keeps run() a generator


class PlotStyleCommand(Command):
    """Choose the plot style table from the command line."""

    name = "PLOTSTYLE"
    aliases = ("CTB",)
    description = "Set the plot style table: Normal, Monochrome or Grayscale."
    group = "tools"
    modifies = False

    def run(self):
        current = plotstyle.normalise(self.var("PLOTSTYLE"))
        options = [plotstyle.label_for(key) for key in plotstyle.MODE_KEYS]

        answer = yield KeywordPrompt(
            "Plot style table",
            options=options,
            default=plotstyle.label_for(current))

        if self.is_cancelled(answer):
            return
        if self.is_finished(answer):
            answer = plotstyle.label_for(current)

        chosen = self._match(answer, current)
        self.set_var("PLOTSTYLE", chosen)
        self.write("Plot style table: {0} — {1}".format(
            plotstyle.label_for(chosen), plotstyle.describe(chosen)))

        # A published theme is a snapshot of the style, so it goes stale the
        # moment the table changes. Refresh it if the user has one.
        if plot_render.theme_exists(self.document.project):
            plot_render.register_plot_theme(
                self.document, plotstyle.PlotStyle.from_variables(
                    self.variables))
            self.write("Map theme '{0}' updated.".format(
                plot_render.PLOT_THEME_NAME))

    @staticmethod
    def _match(answer, fallback):
        """Resolve a typed answer to a mode key, by key or by label prefix."""
        text = str(answer or "").strip().lower()
        if not text:
            return fallback
        if text in plotstyle.MODE_KEYS:
            return text
        for key in plotstyle.MODE_KEYS:
            if key.startswith(text) or plotstyle.label_for(key).lower(
            ).startswith(text):
                return key
        return fallback


class PlotThemeCommand(Command):
    """Publish the paper style as a QGIS map theme.

    The one command that makes QGIS's *built-in* layout designer able to plot
    the drawing correctly: it registers a named ``AutoQAD Plot`` style on each
    drawing table and a map theme selecting it, so a map frame set to "follow
    map theme" renders black-on-white whatever the canvas is doing.

    Neither the styles nor the theme are removed when the session ends. A user
    who has wired the theme into a layout of their own would find it silently
    broken next time they opened it, and a stale theme is a far smaller problem
    than a broken layout.
    """

    name = "PLOTTHEME"
    aliases = ("PLOTPREP",)
    description = ("Publish the plot style as a QGIS map theme for the "
                   "built-in Layout designer.")
    group = "tools"
    modifies = False

    def run(self):
        if not self.document.is_open:
            self.write("No drawing is open.")
            return

        style = plotstyle.PlotStyle.from_variables(self.variables)
        if not plot_render.register_plot_theme(self.document, style):
            self.write("Could not register the plot map theme.")
            return

        self.write(
            "Map theme '{0}' registered ({1} plot style). In the QGIS Layout "
            "designer, tick 'Follow map theme' on the map frame and choose it "
            "to plot the drawing black on white.".format(
                plot_render.PLOT_THEME_NAME,
                plotstyle.label_for(style.mode).lower()))
        return
        yield        # noqa: unreachable - keeps run() a generator


PLOT_COMMANDS = (PlotCommand, PageSetupCommand, PlotStyleCommand,
                 PlotThemeCommand)
