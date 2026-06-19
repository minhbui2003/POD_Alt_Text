from PySide6.QtCore import QThread, Signal
import os
import json
import requests

from api_client import TeeInBlueAPIClient
from graphql_client import TeeInBlueGraphQLClient
from campaign_service import CampaignService
from upload_service import UploadService
from alt_service import AltService

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except:
        return {"max_workers": 3}

def save_config(config_data):
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    with open(config_path, "w") as f:
        json.dump(config_data, f, indent=4)

class CheckTokenWorker(QThread):
    result = Signal(bool, str) # success, message

    def __init__(self, token):
        super().__init__()
        self.token = token

    def run(self):
        try:
            client = TeeInBlueAPIClient(self.token)
            client.check_token()
            self.result.emit(True, "Token hợp lệ.")
        except Exception as e:
            self.result.emit(False, f"Lỗi Token: {str(e)}")

class LoadCampaignWorker(QThread):
    result = Signal(bool, str, dict) # success, message, data

    def __init__(self, token, url):
        super().__init__()
        self.token = token
        self.url = url

    def run(self):
        try:
            client = TeeInBlueAPIClient(self.token)
            service = CampaignService(client)
            campaign_id, product_id = service.parse_url(self.url)
            data = service.load_campaign(campaign_id, product_id)
            self.result.emit(True, "Load campaign thành công.", data)
        except Exception as e:
            self.result.emit(False, f"Lỗi load campaign: {str(e)}", {})

class ImageLoaderWorker(QThread):
    image_loaded = Signal(int, bytes)

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def run(self):
        for row, url in self.tasks:
            if not url:
                continue
            
            if not url.startswith('http'):
                url = f"https://teeinblue-cdn.nyc3.digitaloceanspaces.com/{url}"
                
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    self.image_loaded.emit(row, resp.content)
            except Exception:
                pass



class RunPlanWorker(QThread):
    log_msg = Signal(str)
    progress = Signal(int, str) # row_index, status_text
    finished_run = Signal()
    campaign_refreshed = Signal(list) # updated mockups list

    def __init__(self, token, url, user_id, tasks):
        # tasks is list of dict: { row_index, file_path, layer_name, mockup_id, new_alt, action }
        super().__init__()
        self.token = token
        self.url = url
        self.user_id = user_id
        self.tasks = tasks

    def run(self):
        try:
            config = load_config()
            max_workers = config.get("max_workers", 3)

            client = TeeInBlueAPIClient(self.token)
            gql_client = TeeInBlueGraphQLClient(self.token)
            camp_service = CampaignService(client)
            upload_service = UploadService(client, max_workers)
            alt_service = AltService(gql_client)
            
            campaign_id, product_id = camp_service.parse_url(self.url)
            camp_data = camp_service.load_campaign(campaign_id, product_id)
            campaign_product_id = camp_data['campaign_product_id']
            
            # Phân tách task upload
            upload_tasks = []
            for t in self.tasks:
                if t['action'] in ["Append New Image", "Upload + Update Alt"]:
                    row_idx = t['row_index']
                    def make_prog_cb(idx):
                        return lambda msg: self.progress.emit(idx, msg)
                    def make_err_cb(idx):
                        return lambda msg: self.log_msg.emit(f"Lỗi dòng {idx+1}: {msg}")
                    
                    upload_tasks.append({
                        "file_path": t['file_path'],
                        "layer_name": t['layer_name'],
                        "progress_cb": make_prog_cb(row_idx),
                        "error_cb": make_err_cb(row_idx),
                        "row_index": row_idx
                    })

            upload_results = []
            if upload_tasks:
                self.log_msg.emit(f"Tiến hành upload {len(upload_tasks)} ảnh với {max_workers} luồng...")
                upload_results = upload_service.process_batch(self.user_id, campaign_product_id, upload_tasks)
            
            # Refresh campaign if we uploaded anything, or just to be safe
            self.log_msg.emit("Làm mới Campaign để lấy Mockup ID mới nhất...")
            updated_camp_data = camp_service.load_campaign(campaign_id, product_id)
            new_mockups = updated_camp_data['mockups']
            
            self.campaign_refreshed.emit(new_mockups)
            
            # Phân tách task update metadata
            update_tasks = []
            for t in self.tasks:
                if t['action'] in ["Update Alt", "Upload + Update Alt", "Update Name", "Upload + Update Name", "Update Name & Alt", "Upload + Update Alt & Name"]:
                    row_idx = t['row_index']
                    mid = t['mockup_id']
                    
                    # Nếu là ảnh mới upload, mockup_id ban đầu là rỗng, cần tìm ID mới từ new_mockups
                    if not mid:
                        up_res = next((res for res in upload_results if res.get('row_index') == row_idx), None)
                        if up_res and up_res.get('success'):
                            s_name = up_res.get('selected_layer_name')
                            s_url = up_res.get('selected_layer_url')
                            
                            # 1. Map bằng Name
                            if s_name:
                                for m in new_mockups:
                                    layers = m.get('layers', [])
                                    if any(l.get('name') == s_name for l in layers):
                                        mid = m.get('id')
                                        self.log_msg.emit(f"Dòng {row_idx+1}: Đã map Mockup ID {mid} bằng Name ({s_name})")
                                        break
                                        
                            # 2. Map bằng URL
                            if not mid and s_url:
                                for m in new_mockups:
                                    layers = m.get('layers', [])
                                    if any(l.get('url') == s_url for l in layers):
                                        mid = m.get('id')
                                        self.log_msg.emit(f"Dòng {row_idx+1}: Đã map Mockup ID {mid} bằng URL")
                                        break
                                        
                            # 3. Map bằng Position lớn nhất
                            if not mid and new_mockups:
                                max_pos_mockup = max(new_mockups, key=lambda x: x.get('position', 0))
                                mid = max_pos_mockup.get('id')
                                self.log_msg.emit(f"Dòng {row_idx+1}: Đã map Mockup ID {mid} bằng Position cao nhất")
                    
                    if mid:
                        update_tasks.append({
                            "mockup_id": int(mid),
                            "new_alt": t.get('new_alt', ''),
                            "new_name": t.get('layer_name', ''),
                            "action": t['action'],
                            "row_index": row_idx
                        })
                    else:
                        self.log_msg.emit(f"Không tìm thấy Mockup ID cho dòng {row_idx+1} để cập nhật.")
            
            if update_tasks:
                self.log_msg.emit(f"Tiến hành cập nhật thông tin cho {len(update_tasks)} mockups...")
                
                for task in update_tasks:
                    mid = task['mockup_id']
                    action = task['action']
                    row_idx = task['row_index']
                    
                    def make_prog_cb(idx):
                        return lambda msg: self.progress.emit(idx, msg)
                    prog_cb = make_prog_cb(row_idx)
                    
                    # Cập nhật Alt (qua GraphQL)
                    if "Alt" in action:
                        try:
                            prog_cb("Cập nhật Alt...")
                            alt_service.graphql_client.update_alt_text(mid, task['new_alt'])
                            prog_cb("Alt updated")
                        except Exception as e:
                            self.log_msg.emit(f"Lỗi cập nhật Alt dòng {row_idx+1}: {e}")
                            prog_cb("Lỗi Alt")
                            
                    # Cập nhật Name (qua REST)
                    if "Name" in action:
                        try:
                            prog_cb("Cập nhật Name...")
                            target_mockup = next((m for m in new_mockups if m.get('id') == mid), None)
                            if target_mockup:
                                layers = target_mockup.get('layers', [])
                                if layers and isinstance(layers, list) and len(layers) > 0:
                                    layers[0]['name'] = task['new_name']
                                
                                payload = {
                                    "width": target_mockup.get('width'),
                                    "height": target_mockup.get('height'),
                                    "color_as_variant": target_mockup.get('color_as_variant', False),
                                    "default_background_color": target_mockup.get('default_background_color'),
                                    "layers": layers
                                }
                                client.update_campaign_mockup(campaign_product_id, mid, payload)
                                prog_cb("Name updated")
                                self.log_msg.emit(f"Dòng {row_idx+1}: Đã cập nhật tên layer thành '{task['new_name']}'")
                            else:
                                self.log_msg.emit(f"Dòng {row_idx+1}: Không tìm thấy data mockup để cập nhật tên.")
                                prog_cb("Lỗi Name")
                        except Exception as e:
                            self.log_msg.emit(f"Lỗi cập nhật Name dòng {row_idx+1}: {e}")
                            prog_cb("Lỗi Name")
            
            self.log_msg.emit("Hoàn tất Action Plan!")
            self.finished_run.emit()
            
        except Exception as e:
            self.log_msg.emit(f"Lỗi quá trình RUN: {str(e)}")
            self.finished_run.emit()
