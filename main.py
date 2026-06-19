import sys
import logging
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

def main():
    app = QApplication(sys.argv)
    
    # Modern Light Mode Style
    app.setStyle("Fusion")
    style_sheet = """
    QWidget {
        background-color: #f8f9fa;
        color: #212529;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 14px;
    }
    QGroupBox {
        font-weight: bold;
        border: 1px solid #dee2e6;
        border-radius: 5px;
        margin-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 3px 0 3px;
        color: #0d6efd;
    }
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 6px;
    }
    QLineEdit:focus {
        border: 1px solid #86b7fe;
    }
    QPushButton {
        background-color: #6c757d;
        color: #ffffff;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #5a6268;
    }
    QPushButton:pressed {
        background-color: #545b62;
    }
    QPushButton:disabled {
        background-color: #adb5bd;
    }
    QTableWidget {
        background-color: #ffffff;
        alternate-background-color: #f8f9fa;
        gridline-color: #dee2e6;
        selection-background-color: #e9ecef;
        selection-color: #000000;
        border: 1px solid #dee2e6;
    }
    QHeaderView::section {
        background-color: #e9ecef;
        padding: 6px;
        border: 1px solid #dee2e6;
        font-weight: bold;
    }
    QPlainTextEdit {
        background-color: #212529;
        color: #f8f9fa;
        border: 1px solid #ced4da;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 12px;
    }
    QCheckBox {
        spacing: 5px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
    }
    """
    app.setStyleSheet(style_sheet)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
