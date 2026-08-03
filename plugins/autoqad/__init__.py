# -*- coding: utf-8 -*-
"""AutoQAD — CAD-style drawing tools for QGIS.

Copyright (C) 2026 Isaac Enage (byZenterra)
Licensed under the GNU General Public License v3.0 or later.

This is an original implementation. It is not derived from, and shares no
source with, any other CAD plugin.
"""


def classFactory(iface):            # pylint: disable=invalid-name
    """Load the AutoQAD plugin class.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .main_plugin import AutoQadPlugin
    return AutoQadPlugin(iface)
