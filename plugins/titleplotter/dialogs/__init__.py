# -*- coding: utf-8 -*-
"""
Dialogs package for Title Plotter - Philippine Land Titles plugin.
"""

from .title_plotter_dialog import TitlePlotterPhilippineLandTitlesDialog
from .tie_point_selector_dialog import TiePointSelectorDialog
from .report_correction_dialog import ReportCorrectionDialog
from .llm_ocr_dialog import LLMOCRDialog

__all__ = [
    'TitlePlotterPhilippineLandTitlesDialog',
    'TiePointSelectorDialog',
    'ReportCorrectionDialog',
    'LLMOCRDialog'
]
