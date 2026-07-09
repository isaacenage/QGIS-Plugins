import sys
import os
import unittest
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtCore import Qt

# Add the plugin directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from title_plotter_dialog import TitlePlotterPhilippineLandTitlesDialog

class TestTitlePlotter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize QGIS application
        cls.app = QApplication(sys.argv)
        QgsApplication.setPrefixPath("C:/OSGeo4W64/apps/qgis", True)
        QgsApplication.initQgis()
        
    def setUp(self):
        self.dialog = TitlePlotterPhilippineLandTitlesDialog()
        
    def test_parse_bearing_distance(self):
        test_input = """N 69 16 E - 100.00M
S 20 44 E - 150.00M
S 69 16 W - 100.00M
N 20 44 W - 150.00M"""
        
        self.dialog.bearingInput.setPlainText(test_input)
        result = self.dialog._parse_bearing_distance(test_input)
        
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]['direction1'], 'N')
        self.assertEqual(result[0]['degrees'], 69)
        self.assertEqual(result[0]['minutes'], 16)
        self.assertEqual(result[0]['direction2'], 'E')
        self.assertEqual(result[0]['distance'], 100.00)
        
    def test_calculate_azimuth(self):
        bearing = {
            'direction1': 'N',
            'degrees': 69,
            'minutes': 16,
            'direction2': 'E',
            'distance': 100.00
        }
        
        azimuth = self.dialog._calculate_azimuth(bearing)
        self.assertAlmostEqual(azimuth, 69.2667, places=4)
        
    def test_calculate_coordinates(self):
        start_point = QgsPointXY(100, 100)
        bearing = {
            'direction1': 'N',
            'degrees': 69,
            'minutes': 16,
            'direction2': 'E',
            'distance': 100.00
        }
        
        new_point = self.dialog._calculate_coordinates(start_point, bearing, 100)
        self.assertIsNotNone(new_point)
        self.assertIsInstance(new_point, QgsPointXY)
        
    @classmethod
    def tearDownClass(cls):
        QgsApplication.exitQgis()
        cls.app.quit()

if __name__ == '__main__':
    unittest.main() 