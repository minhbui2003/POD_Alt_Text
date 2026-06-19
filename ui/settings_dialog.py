from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QMessageBox
from ui.workers import load_config, save_config

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt chung")
        self.resize(400, 150)
        self.config = load_config()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setText(self.config.get("gemini_api_key", ""))
        
        form_layout.addRow("Gemini API Key:", self.api_key_input)
        
        layout.addLayout(form_layout)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Lưu cấu hình")
        btn_save.setStyleSheet("background-color: #198754; color: white;")
        btn_save.clicked.connect(self.save_settings)
        
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def save_settings(self):
        api_key = self.api_key_input.text().strip()
        
        self.config["gemini_api_key"] = api_key
        self.config["gemini_model"] = "gemini-2.5-flash"
            
        save_config(self.config)
        QMessageBox.information(self, "Thành công", "Đã lưu cấu hình!")
        self.accept()
