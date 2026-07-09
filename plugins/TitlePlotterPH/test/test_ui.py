import sys
import os
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtCore import Qt

# Add the plugin directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from title_plotter_dialog import TitlePlotterPhilippineLandTitlesDialog

def test_ui():
    app = QApplication(sys.argv)
    
    # Create and show the dialog
    dialog = TitlePlotterPhilippineLandTitlesDialog()
    dialog.show()
    
    # Test tie point input
    dialog.tiePointNorthingInput.setText("100.0")
    dialog.tiePointEastingInput.setText("200.0")
    
    # Test bearing input
    test_input = """N 69 16 E - 100.00M
S 20 44 E - 150.00M
S 69 16 W - 100.00M
N 20 44 W - 150.00M"""
    dialog.bearingInput.setPlainText(test_input)
    
    # Simulate button clicks
    QTest.mouseClick(dialog.generateWKTButton, Qt.LeftButton)
    
    # Print the generated WKT
    print("Generated WKT:")
    print(dialog.wktOutput.toPlainText())
    
    # Keep the dialog open for manual inspection
    return app.exec()

if __name__ == '__main__':
    sys.exit(test_ui()) 