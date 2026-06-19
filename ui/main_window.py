import os
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QPlainTextEdit, QMessageBox,
    QGroupBox, QFormLayout, QCheckBox, QAbstractItemView, QSplitter, QListWidget, QListWidgetItem, QDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QBrush, QIcon

from ui.workers import CheckTokenWorker, LoadCampaignWorker, ImageLoaderWorker, RunPlanWorker
from ui.auto_gen_dialog import AutoGenDialog
from ui.settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("POD Alt text")
        self.setWindowIcon(QIcon("podsoftware.ico"))
        self.resize(1300, 800)
        
        self.existing_mockups = [] 
        self.current_user_id = None
        
        self._init_ui()
        
    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # --- Top Section: Cấu hình ---
        input_group = QGroupBox("Cấu hình")
        form_layout = QFormLayout()
        
        token_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Nhập Bearer Token")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.check_token_btn = QPushButton("Kiểm tra Token")
        self.check_token_btn.clicked.connect(self.check_token)
        token_layout.addWidget(self.token_input)
        token_layout.addWidget(self.check_token_btn)
        
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://portal.teeinblue.com/campaigns/966343/edit?product-id=334658")
        self.load_camp_btn = QPushButton("Load Campaign")
        self.load_camp_btn.clicked.connect(self.load_campaign)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.load_camp_btn)
        
        self.user_id_input = QLineEdit()
        self.user_id_input.setPlaceholderText("Tự động phát hiện hoặc nhập thủ công")
        
        form_layout.addRow("Token TeeInBlue:", token_layout)
        form_layout.addRow("Link Campaign:", url_layout)
        form_layout.addRow("User ID:", self.user_id_input)
        
        input_group.setLayout(form_layout)
        main_layout.addWidget(input_group)
        
        # --- Action Plan Table & Toolbar ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0,0,0,0)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        self.btn_select_files = QPushButton("Chọn ảnh")
        self.btn_select_files.clicked.connect(self.select_files)
        
        self.btn_auto_gen = QPushButton("Auto Gen Name + Alt")
        self.btn_auto_gen.clicked.connect(self.auto_generate)
        
        self.btn_clear_changes = QPushButton("Clear Changes")
        self.btn_clear_changes.clicked.connect(self.clear_changes)
        
        self.btn_tick_all = QPushButton("Tick All")
        self.btn_tick_all.clicked.connect(lambda: self.set_all_ticks(Qt.Checked))
        
        self.btn_untick_all = QPushButton("Untick All")
        self.btn_untick_all.clicked.connect(lambda: self.set_all_ticks(Qt.Unchecked))
        
        self.btn_settings = QPushButton("Cài đặt")
        self.btn_settings.clicked.connect(self.open_settings)
        
        toolbar_layout.addWidget(self.btn_select_files)
        toolbar_layout.addWidget(self.btn_auto_gen)
        toolbar_layout.addWidget(self.btn_clear_changes)
        toolbar_layout.addWidget(self.btn_tick_all)
        toolbar_layout.addWidget(self.btn_untick_all)
        
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_settings)
        
        right_layout.addLayout(toolbar_layout)
        
        # Table with Drag and Drop
        class DropTableWidget(QTableWidget):
            def __init__(self, main_win, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.main_win = main_win
                self.setAcceptDrops(True)

            def dragEnterEvent(self, event):
                if event.mimeData().hasUrls():
                    event.accept()
                else:
                    event.ignore()
                    
            def dragMoveEvent(self, event):
                if event.mimeData().hasUrls():
                    event.accept()
                else:
                    event.ignore()
                    
            def dropEvent(self, event):
                if event.mimeData().hasUrls():
                    event.accept()
                    files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
                    if files:
                        self.main_win.add_images_to_plan(files)
                else:
                    event.ignore()

        self.table = DropTableWidget(self, 0, 12)
        self.table.setHorizontalHeaderLabels([
            "Chọn", "Pos", "Current Preview", "New Preview", "Mockup ID", 
            "Current Name", "Tên file khi upload", "Current Alt", "New Alt", "Action", "Status", "FilePath"
        ])
        self.table.setColumnHidden(11, True) # Ẩn FilePath
        header_item = QTableWidgetItem("Tên file khi upload")
        header_item.setToolTip("Chỉ áp dụng cho ảnh mới. Ảnh cũ chưa hỗ trợ rename.")
        self.table.setHorizontalHeaderItem(6, header_item)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.Stretch) # Action
        
        self.table.itemChanged.connect(self.on_table_item_changed)
        
        right_layout.addWidget(self.table)
        
        # Run Button
        self.btn_run = QPushButton("RUN ACTION PLAN")
        self.btn_run.setStyleSheet("background-color: #198754; color: white; font-size: 16px; padding: 10px;")
        self.btn_run.clicked.connect(self.run_plan)
        right_layout.addWidget(self.btn_run)
        
        main_layout.addWidget(right_widget)
        
        # --- Log Section ---
        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumHeight(100)
        main_layout.addWidget(self.log_panel)
        
        self.setCentralWidget(main_widget)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"[{timestamp}] {message}")

    def check_token(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập Token")
            return
        self.check_token_btn.setEnabled(False)
        self.log("Đang kiểm tra token...")
        self.tk_worker = CheckTokenWorker(token)
        self.tk_worker.result.connect(self.on_check_token_result)
        self.tk_worker.start()

    def on_check_token_result(self, success, message):
        self.check_token_btn.setEnabled(True)
        if success:
            self.log(message)
        else:
            self.log(message)
            QMessageBox.critical(self, "Lỗi", message)

    def load_campaign(self):
        token = self.token_input.text().strip()
        url = self.url_input.text().strip()
        if not token or not url:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập Token và URL Campaign")
            return
        self.load_camp_btn.setEnabled(False)
        self.log("Đang load campaign...")
        self.lc_worker = LoadCampaignWorker(token, url)
        self.lc_worker.result.connect(self.on_load_campaign_result)
        self.lc_worker.start()

    def on_load_campaign_result(self, success, message, data):
        self.load_camp_btn.setEnabled(True)
        if success:
            self.log(f"{message} (Sản phẩm ID: {data.get('campaign_product_id')})")
            self.existing_mockups = data.get('mockups', [])
            if not self.user_id_input.text() and data.get('user_id'):
                self.user_id_input.setText(str(data.get('user_id')))
                self.current_user_id = data.get('user_id')
            self.log(f"Tìm thấy {len(self.existing_mockups)} mockups.")
            self._populate_table_with_mockups()
        else:
            self.log(message)

    def _populate_table_with_mockups(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        image_tasks = []
        for idx, m in enumerate(self.existing_mockups):
            self.table.insertRow(idx)
            
            chk_widget = QWidget()
            chk_widget.setStyleSheet("background-color: #e9ecef;")
            layout = QHBoxLayout(chk_widget)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox()
            chk.setChecked(True)
            chk.setStyleSheet("QCheckBox::indicator { width: 18px; height: 18px; }")
            layout.addWidget(chk)
            self.table.setCellWidget(idx, 0, chk_widget)
            
            self.table.setItem(idx, 1, QTableWidgetItem(str(m.get('position', 0))))
            self.table.setItem(idx, 2, QTableWidgetItem("Đang tải..."))
            self.table.setItem(idx, 3, QTableWidgetItem("")) # New Image
            self.table.setItem(idx, 4, QTableWidgetItem(str(m.get('id', ''))))
            
            layers = m.get('layers', [])
            c_name = layers[0].get('name', '') if layers else ''
            self.table.setItem(idx, 5, QTableWidgetItem(c_name))
            
            new_name_item = QTableWidgetItem("")
            self.table.setItem(idx, 6, new_name_item)
            
            self.table.setItem(idx, 7, QTableWidgetItem(m.get('alt', '')))
            
            new_alt_item = QTableWidgetItem("")
            self.table.setItem(idx, 8, new_alt_item)
            
            self.table.setItem(idx, 9, QTableWidgetItem("No Change"))
            self.table.setItem(idx, 10, QTableWidgetItem("Sẵn sàng"))
            self.table.setItem(idx, 11, QTableWidgetItem("")) # FilePath
            
            # Make columns readonly except 6 and 8
            for col in [1, 2, 3, 4, 5, 7, 9, 10, 11]:
                it = self.table.item(idx, col)
                if it: it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            
            thumb_url = m.get('preview_thumbnail') or m.get('preview_url', '')
            if thumb_url:
                image_tasks.append((idx, thumb_url))
                
        self.table.blockSignals(False)
        self.preview_plan() # Colorize
        
        if image_tasks:
            self.img_loader = ImageLoaderWorker(image_tasks)
            self.img_loader.image_loaded.connect(self.on_image_loaded)
            self.img_loader.start()

    def on_image_loaded(self, row, img_bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(img_bytes):
            scaled = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(scaled)
            self.table.setCellWidget(row, 2, label)
        else:
            self.table.setItem(row, 2, QTableWidgetItem("Lỗi"))

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh", "", "Image Files (*.webp *.png *.jpg *.jpeg)")
        if files:
            self.add_images_to_plan(files)

    def add_images_to_plan(self, items):
        if not items: return
        
        self.table.blockSignals(True)
        start_idx = self.table.rowCount()
        for idx, file_path in enumerate(items):
            row = start_idx + idx
            self.table.insertRow(row)
            
            chk_widget = QWidget()
            chk_widget.setStyleSheet("background-color: #e9ecef;")
            layout = QHBoxLayout(chk_widget)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox()
            chk.setChecked(True)
            chk.setStyleSheet("QCheckBox::indicator { width: 18px; height: 18px; }")
            layout.addWidget(chk)
            self.table.setCellWidget(row, 0, chk_widget)
            
            self.table.setItem(row, 1, QTableWidgetItem("")) # Pos
            self.table.setItem(row, 2, QTableWidgetItem("")) # Current preview
            
            # New Preview
            pixmap = QPixmap(file_path).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(pixmap)
            self.table.setCellWidget(row, 3, label)
            
            self.table.setItem(row, 4, QTableWidgetItem("")) # Mockup ID
            self.table.setItem(row, 5, QTableWidgetItem("")) # Current Name
            
            name = os.path.splitext(os.path.basename(file_path))[0]
            self.table.setItem(row, 6, QTableWidgetItem(name)) # New Name
            self.table.setItem(row, 7, QTableWidgetItem("")) # Current alt
            self.table.setItem(row, 8, QTableWidgetItem("")) # New alt
            self.table.setItem(row, 9, QTableWidgetItem("Append New Image"))
            self.table.setItem(row, 10, QTableWidgetItem("Sẵn sàng"))
            self.table.setItem(row, 11, QTableWidgetItem(file_path))
            
            # Make columns readonly except 6, 8
            for col in [1, 2, 4, 5, 7, 9, 10, 11]:
                it = self.table.item(row, col)
                if it: it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            
        self.table.blockSignals(False)
        self.preview_plan()

    def on_table_item_changed(self, item):
        # Tránh trigger nhiều lần
        if item.column() in [6, 8]: # New Name, New Alt changed
            self.preview_plan()

    def calculate_action(self, row):
        cur_alt_item = self.table.item(row, 7)
        new_alt_item = self.table.item(row, 8)
        file_path_item = self.table.item(row, 11)
        mid_item = self.table.item(row, 4)
        
        cur_alt = cur_alt_item.text().strip() if cur_alt_item else ""
        new_alt = new_alt_item.text().strip() if new_alt_item else ""
        file_path = file_path_item.text().strip() if file_path_item else ""
        mid = mid_item.text().strip() if mid_item else ""
        
        has_new_img = bool(file_path)
        alt_changed = bool(new_alt) and (new_alt != cur_alt)
        
        cur_name = self.table.item(row, 5).text().strip()
        new_name = self.table.item(row, 6).text().strip()
        name_changed = bool(new_name) and (new_name != cur_name)
        
        if has_new_img:
            if mid:
                return "Replace Pending" # Chưa hỗ trợ replace
            if alt_changed and name_changed:
                return "Upload + Update Alt & Name"
            if alt_changed:
                return "Upload + Update Alt"
            if name_changed:
                return "Upload + Update Name"
            return "Append New Image"
        else:
            if alt_changed and name_changed:
                return "Update Name & Alt"
            if name_changed:
                return "Update Name"
            if alt_changed:
                return "Update Alt"
            return "No Change"

    def preview_plan(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            action = self.calculate_action(row)
            action_item = QTableWidgetItem(action)
            action_item.setFlags(action_item.flags() & ~Qt.ItemIsEditable)
            
            # Tô màu
            color = QColor("#f8f9fa") # gray
            if action == "No Change":
                color = QColor("#e9ecef")
            elif action in ["Update Alt", "Update Name", "Update Name & Alt"]:
                color = QColor("#cce5ff") # light blue
            elif action == "Append New Image":
                color = QColor("#d4edda") # light green
            elif action in ["Upload + Update Alt", "Upload + Update Name", "Upload + Update Alt & Name"]:
                color = QColor("#e2d9f3") # light purple
            elif action == "Replace Pending":
                color = QColor("#fff3cd") # light yellow
                
            status_item = self.table.item(row, 10)
            if status_item and "Lỗi" in status_item.text():
                color = QColor("#f8d7da") # light red
                
            for col in range(11):
                it = self.table.item(row, col)
                if it: it.setBackground(QBrush(color))
                
            self.table.setItem(row, 9, action_item)
        self.table.blockSignals(False)

    def set_all_ticks(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                chk = widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(state == Qt.Checked)
        self.table.blockSignals(False)

    def clear_changes(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText("")
            self.table.item(row, 8).setText("")
        self.table.blockSignals(False)
        self.preview_plan()

    def auto_generate(self):
        items = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if not widget: continue
            chk = widget.findChild(QCheckBox)
            if not chk or not chk.isChecked(): continue
            
            pos = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            mid = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
            file_path = self.table.item(row, 11).text() if self.table.item(row, 11) else ""
            
            source_type = ""
            preview_pixmap = None
            url = ""
            
            if file_path:
                source_type = "Local"
                lbl = self.table.cellWidget(row, 3)
                if lbl and isinstance(lbl, QLabel):
                    preview_pixmap = lbl.pixmap()
            else:
                source_type = "TeeInBlue"
                lbl = self.table.cellWidget(row, 2)
                if lbl and isinstance(lbl, QLabel):
                    preview_pixmap = lbl.pixmap()
                    
                # Find url
                for m in self.existing_mockups:
                    if str(m.get('id', '')) == mid:
                        url = m.get('preview_url') or m.get('preview_thumbnail', '')
                        if not url and m.get('layers'):
                            url = m.get('layers')[0].get('url', '')
                        break
            
            items.append({
                'row_index': row,
                'pos': pos,
                'mockup_id': mid,
                'file_path': file_path,
                'url': url,
                'source_type': source_type,
                'pixmap': preview_pixmap
            })
            
        if not items:
            QMessageBox.information(self, "Info", "Chưa chọn dòng nào để generate.")
            return
            
        dialog = AutoGenDialog(items, self)
        if dialog.exec():
            results = dialog.get_results()
            if results:
                self.table.blockSignals(True)
                for row_index, data in results.items():
                    name_item = self.table.item(row_index, 6)
                    if name_item:
                        name_item.setText(data.get('name', ''))
                    
                    alt_item = self.table.item(row_index, 8)
                    if alt_item: alt_item.setText(data.get('alt', ''))
                self.table.blockSignals(False)
                self.preview_plan()
                self.log(f"Đã cập nhật Name và Alt từ AI cho {len(results)} mockups.")

    def run_plan(self):
        token = self.token_input.text().strip()
        url = self.url_input.text().strip()
        uid_str = self.user_id_input.text().strip()
        
        if not token or not url or not uid_str:
            QMessageBox.warning(self, "Lỗi", "Vui lòng kiểm tra lại Token, URL Campaign và User ID.")
            return
            
        tasks = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if not widget: continue
            chk = widget.findChild(QCheckBox)
            if not chk or not chk.isChecked(): continue
            
            action = self.table.item(row, 9).text()
            if action in ["No Change", "Replace Pending"]: continue
            
            file_path = self.table.item(row, 11).text()
            layer_name = self.table.item(row, 6).text()
            mockup_id = self.table.item(row, 4).text()
            new_alt = self.table.item(row, 8).text()
            
            tasks.append({
                "row_index": row,
                "file_path": file_path,
                "layer_name": layer_name,
                "mockup_id": mockup_id,
                "new_alt": new_alt,
                "action": action
            })
            
        if not tasks:
            QMessageBox.information(self, "Info", "Không có Action nào cần thực thi.")
            return
            
        reply = QMessageBox.question(self, "Xác nhận RUN", f"Thực thi {len(tasks)} actions?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return

        self._set_ui_enabled(False)
        self.run_worker = RunPlanWorker(token, url, int(uid_str), tasks)
        self.run_worker.log_msg.connect(self.log)
        self.run_worker.progress.connect(self.update_row_status)
        self.run_worker.campaign_refreshed.connect(self.on_campaign_refreshed)
        self.run_worker.finished_run.connect(self._on_worker_finished)
        self.run_worker.start()

    def update_row_status(self, row_index, msg):
        self.table.setItem(row_index, 10, QTableWidgetItem(msg))
        self.preview_plan() # colorize if error

    def on_campaign_refreshed(self, new_mockups):
        self.existing_mockups = new_mockups
        self._populate_table_with_mockups()
        self.log("Bảng đã được cập nhật với dữ liệu mới từ TeeInBlue.")

    def _set_ui_enabled(self, enabled):
        self.btn_run.setEnabled(enabled)
        self.btn_select_files.setEnabled(enabled)
        self.btn_auto_gen.setEnabled(enabled)
        self.btn_clear_changes.setEnabled(enabled)
        self.load_camp_btn.setEnabled(enabled)
        self.btn_tick_all.setEnabled(enabled)
        self.btn_untick_all.setEnabled(enabled)

    def _on_worker_finished(self):
        self._set_ui_enabled(True)
        self.preview_plan()
