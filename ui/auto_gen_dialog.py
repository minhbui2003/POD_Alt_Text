import time
import json
import io
import requests
from PIL import Image

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QPlainTextEdit, QMessageBox, QCheckBox, QAbstractItemView,
    QGroupBox, QFormLayout, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QColor

from google import genai

from ui.workers import load_config, save_config

DEFAULT_PROMPT = """You will receive multiple product images.

Analyze each image independently.

Return ONLY valid JSON:

{
  "images": [
    {
      "image_index": 1,
      "image_name": "",
      "alt_text": ""
    }
  ]
}

Rules:
- image_index must match the input image order, starting from 1
- describe only visible content
- do not mention brand names
- do not mention personalization unless visible
- image_name lowercase, hyphen-separated, no extension
- alt_text natural English, max 125 characters
- return one item per image
- return JSON only
"""

class AutoGenGeminiWorker(QThread):
    log_msg = Signal(str)
    progress = Signal(int, str) # task_index, status
    result_ready = Signal(int, str, str) # row_index, name, alt
    finished_run = Signal()

    def __init__(self, api_key, model_name, prompt_text, tasks):
        super().__init__()
        self.api_key = api_key
        self.model_name = model_name
        self.prompt_text = prompt_text
        self.tasks = tasks
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def _load_image(self, item, task_idx):
        file_path = item['file_path']
        url = item['url']
        source = item['source_type']
        pixmap = item['pixmap']
        
        img = None
        if source == "Local" and file_path:
            try:
                img = Image.open(file_path)
            except Exception as e:
                self.log_msg.emit(f"[{item['pos']}] Lỗi đọc local file: {e}")
        
        elif source == "TeeInBlue" and url:
            if not url.startswith('http'):
                url = f"https://teeinblue-cdn.nyc3.digitaloceanspaces.com/{url}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content))
                else:
                    self.log_msg.emit(f"[{item['pos']}] Lỗi tải ảnh: HTTP {resp.status_code}")
            except Exception as e:
                self.log_msg.emit(f"[{item['pos']}] Lỗi tải ảnh: {e}")
        
        # Fallback to thumbnail
        if not img and pixmap:
            self.log_msg.emit(f"[{item['pos']}] Dùng Thumbnail Fallback...")
            buffer = QBuffer()
            buffer.open(QIODevice.ReadWrite)
            pixmap.save(buffer, "PNG")
            try:
                img = Image.open(io.BytesIO(buffer.data()))
            except Exception as e:
                self.log_msg.emit(f"[{item['pos']}] Lỗi đọc thumbnail: {e}")
                
        if not img:
            self.log_msg.emit(f"[{item['pos']}] Không thể tải ảnh để gửi AI.")
            self.progress.emit(task_idx, "Lỗi ảnh")
        return img

    def _process_single(self, client, item, img, task_idx):
        self.progress.emit(task_idx, "Đang gửi đơn...")
        success = False
        for attempt in range(1, 4):
            if self._is_stopped: break
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=[self.prompt_text, img],
                )
                
                text = response.text.strip()
                if text.startswith("```json"): text = text[7:]
                if text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                text = text.strip()
                
                data = json.loads(text)
                if "images" in data and isinstance(data["images"], list) and len(data["images"]) > 0:
                    res = data["images"][0]
                    name = res.get("image_name", "")
                    alt = res.get("alt_text", "")
                    self.result_ready.emit(item['row_index'], name, alt)
                    self.progress.emit(task_idx, "Thành công")
                    self.log_msg.emit(f"[{item['pos']}] Xong (Đơn): {name}")
                    success = True
                    break
                else:
                    raise Exception("Không tìm thấy images trong JSON.")
            except Exception as e:
                err = str(e)
                if "503" in err or "UNAVAILABLE" in err or "high demand" in err.lower() or "429" in err:
                    self.log_msg.emit(f"[{item['pos']}] Quá tải/Rate limit (Lần {attempt}/3). Chờ 5s...")
                    time.sleep(5)
                else:
                    self.log_msg.emit(f"[{item['pos']}] Lỗi AI: {err}")
                    break
        if not success:
            self.progress.emit(task_idx, "Thất bại")

    def run(self):
        try:
            client = genai.Client(api_key=self.api_key)
            BATCH_SIZE = 5
            
            for i in range(0, len(self.tasks), BATCH_SIZE):
                if self._is_stopped:
                    self.log_msg.emit("Đã dừng bởi người dùng.")
                    break
                    
                batch = self.tasks[i:i+BATCH_SIZE]
                valid_items = []
                images = []
                
                for idx_in_batch, item in enumerate(batch):
                    task_idx = i + idx_in_batch
                    self.progress.emit(task_idx, "Đang chuẩn bị ảnh...")
                    img = self._load_image(item, task_idx)
                    if img:
                        valid_items.append((item, task_idx, img))
                        images.append(img)
                        
                if not valid_items:
                    continue
                    
                self.log_msg.emit(f"Đang gửi Batch {len(valid_items)} ảnh...")
                for item, task_idx, _ in valid_items:
                    self.progress.emit(task_idx, "Đang gửi Batch...")
                    
                batch_success = False
                for attempt in range(1, 4):
                    if self._is_stopped: break
                    try:
                        response = client.models.generate_content(
                            model=self.model_name,
                            contents=[self.prompt_text] + images,
                        )
                        
                        text = response.text.strip()
                        if text.startswith("```json"): text = text[7:]
                        if text.startswith("```"): text = text[3:]
                        if text.endswith("```"): text = text[:-3]
                        text = text.strip()
                        
                        data = json.loads(text)
                        if "images" in data and isinstance(data["images"], list):
                            for res in data["images"]:
                                img_idx = res.get("image_index", 0) - 1
                                if 0 <= img_idx < len(valid_items):
                                    item, task_idx, _ = valid_items[img_idx]
                                    name = res.get("image_name", "")
                                    alt = res.get("alt_text", "")
                                    self.result_ready.emit(item['row_index'], name, alt)
                                    self.progress.emit(task_idx, "Thành công")
                                    self.log_msg.emit(f"[{item['pos']}] Xong (Batch): {name}")
                            batch_success = True
                            break
                        else:
                            raise Exception("Invalid JSON structure (missing 'images')")
                            
                    except Exception as e:
                        err = str(e)
                        if "503" in err or "UNAVAILABLE" in err or "high demand" in err.lower() or "429" in err:
                            self.log_msg.emit(f"Batch bị Quá tải/Rate limit (Lần {attempt}/3). Chờ 5s...")
                            time.sleep(5)
                        else:
                            self.log_msg.emit(f"Lỗi Batch AI: {err}")
                            break
                            
                # Fallback to 1-by-1 if batch fails
                if not batch_success:
                    self.log_msg.emit("Batch thất bại, chuyển sang chạy từng ảnh...")
                    for item, task_idx, img in valid_items:
                        if self._is_stopped: break
                        self._process_single(client, item, img, task_idx)
                        time.sleep(1.5)
                        
                # Rate limit giữa các batch
                if not self._is_stopped and i + BATCH_SIZE < len(self.tasks):
                    time.sleep(2)
                    
        except Exception as e:
            self.log_msg.emit(f"Lỗi Worker: {str(e)}")
            
        finally:
            self.finished_run.emit()


class AutoGenDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto Generate Name & Alt with AI")
        self.resize(1000, 700)
        self.items = items # list of dicts from main table
        self.results = {} # row_index -> {name, alt}
        self.worker = None
        
        self.config = load_config()
        self._init_ui()
        self._populate_table()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        

        # Table Header & Selection
        table_top_layout = QHBoxLayout()
        table_top_layout.addWidget(QLabel("<b>Danh sách ảnh:</b>"))
        table_top_layout.addStretch()
        
        self.btn_tick_all = QPushButton("Tick All")
        self.btn_tick_all.clicked.connect(lambda: self.set_all_ticks(Qt.Checked))
        self.btn_untick_all = QPushButton("Untick All")
        self.btn_untick_all.clicked.connect(lambda: self.set_all_ticks(Qt.Unchecked))
        table_top_layout.addWidget(self.btn_tick_all)
        table_top_layout.addWidget(self.btn_untick_all)
        
        layout.addLayout(table_top_layout)
        
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Chọn", "Pos", "Mockup ID", "Preview", "Source", "Status", "Tên file khi upload", "New Alt"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        # Log
        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumHeight(100)
        layout.addWidget(self.log_panel)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Generate")
        self.btn_start.setStyleSheet("background-color: #0d6efd; color: white; padding: 8px;")
        self.btn_start.clicked.connect(self.start_generation)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white; padding: 8px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_generation)
        
        self.btn_apply = QPushButton("Apply Results to Main Table")
        self.btn_apply.setStyleSheet("background-color: #198754; color: white; padding: 8px;")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_results)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_layout)

    def _populate_table(self):
        self.table.setRowCount(0)
        for idx, item in enumerate(self.items):
            self.table.insertRow(idx)
            
            chk_widget = QWidget()
            chk_widget.setStyleSheet("background-color: #e9ecef;")
            layout = QHBoxLayout(chk_widget)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox()
            chk.setChecked(item.get('source_type') == 'Local')
            chk.setStyleSheet("QCheckBox::indicator { width: 18px; height: 18px; }")
            # Save original list index in the widget
            chk_widget.row_idx = item['row_index']
            layout.addWidget(chk)
            self.table.setCellWidget(idx, 0, chk_widget)
            
            self.table.setItem(idx, 1, QTableWidgetItem(str(item.get('pos', ''))))
            self.table.setItem(idx, 2, QTableWidgetItem(str(item.get('mockup_id', ''))))
            
            # Preview
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            if item.get('pixmap'):
                scaled = item['pixmap'].scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl.setPixmap(scaled)
            else:
                lbl.setText("No Img")
            self.table.setCellWidget(idx, 3, lbl)
            
            self.table.setItem(idx, 4, QTableWidgetItem(item.get('source_type', '')))
            self.table.setItem(idx, 5, QTableWidgetItem("Sẵn sàng"))
            self.table.setItem(idx, 6, QTableWidgetItem(""))
            self.table.setItem(idx, 7, QTableWidgetItem(""))
            
            # Make columns readonly except 6 and 7
            for col in [1, 2, 4, 5]:
                it = self.table.item(idx, col)
                if it: it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            
            # Original list index is already saved in the widget's row_idx

    def set_all_ticks(self, state):
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                chk = widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(state == Qt.Checked)

    def log(self, msg):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"[{ts}] {msg}")

    def start_generation(self):
        config = load_config()
        api_key = config.get("gemini_api_key", "")
        model = config.get("gemini_model", "gemini-2.5-flash")
        
        if not api_key:
            QMessageBox.warning(self, "Lỗi", "Chưa có Gemini API Key. Vui lòng vào 'Cài đặt' ở màn hình chính để cấu hình.")
            return
            
        prompt_txt = DEFAULT_PROMPT
        
        # Collect tasks
        tasks = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if not widget: continue
            chk = widget.findChild(QCheckBox)
            if not chk or not chk.isChecked(): continue
            orig_row_index = getattr(widget, 'row_idx', None)
            # find item
            item_data = next((x for x in self.items if x['row_index'] == orig_row_index), None)
            if item_data:
                # attach local table index so we can update status
                task = item_data.copy()
                task['dialog_row'] = row
                tasks.append(task)
                    
        if not tasks:
            QMessageBox.information(self, "Info", "Chưa chọn dòng nào để generate.")
            return
            
        self.btn_start.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log(f"Bắt đầu xử lý {len(tasks)} ảnh...")
        
        self.worker = AutoGenGeminiWorker(api_key, model, prompt_txt, tasks)
        self.worker.log_msg.connect(self.log)
        self.worker.progress.connect(self.update_status)
        self.worker.result_ready.connect(self.on_result_ready)
        self.worker.finished_run.connect(self.on_worker_finished)
        self.worker.start()

    def stop_generation(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.log("Đang dừng...")

    def update_status(self, task_idx, msg):
        if not self.worker: return
        try:
            task = self.worker.tasks[task_idx]
            d_row = task['dialog_row']
            self.table.setItem(d_row, 5, QTableWidgetItem(msg))
        except:
            pass

    def on_result_ready(self, row_index, name, alt):
        self.results[row_index] = {"name": name, "alt": alt}
        # Update UI Table
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 0)
            if widget and getattr(widget, 'row_idx', None) == row_index:
                self.table.setItem(r, 6, QTableWidgetItem(name))
                self.table.setItem(r, 7, QTableWidgetItem(alt))
                break

    def on_worker_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_apply.setEnabled(True)
        self.log("Hoàn tất quy trình AI.")

    def apply_results(self):
        self.accept()
        
    def get_results(self):
        return self.results
