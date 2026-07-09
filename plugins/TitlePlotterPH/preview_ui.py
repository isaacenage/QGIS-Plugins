import sys
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtWidgets import QApplication

def main():
    app = QApplication(sys.argv)
    
    # Load the UI file
    ui_file = 'Title Plotter - Philippine Land Titles_dialog_base.ui'
    form_class, base_class = uic.loadUiType(ui_file)
    
    # Create the dialog
    dialog = base_class()
    form = form_class()
    form.setupUi(dialog)
    
    # Show the dialog
    dialog.show()
    
    # Start the event loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 