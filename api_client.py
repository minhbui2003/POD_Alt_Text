import requests
import time
import logging

logger = logging.getLogger(__name__)

class APIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class TeeInBlueAPIClient:
    def __init__(self, token: str):
        self.token = token
        self.rest_base = "https://portal-api.teeinblue.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def _handle_response(self, response):
        if response.status_code >= 400:
            msg = f"Lỗi {response.status_code}"
            if response.status_code in [401, 403]:
                msg = "Token không hợp lệ hoặc đã hết hạn."
            elif response.status_code == 404:
                msg = "Không tìm thấy dữ liệu (404)."
            elif response.status_code == 429:
                msg = "Gửi quá nhiều yêu cầu (Rate Limit - 429)."
            elif response.status_code >= 500:
                msg = f"Lỗi server ({response.status_code})."
            
            try:
                err_data = response.json()
                if "message" in err_data:
                    msg += f" Chi tiết: {err_data['message']}"
            except Exception:
                pass
            
            raise APIError(msg, response.status_code)
        
        # 204 No Content
        if not response.text:
            return {}
        
        return response.json()

    def check_token(self):
        url = f"{self.rest_base}/api/mockup-layers"
        params = {"page": 1, "per_page": 1}
        resp = self.session.get(url, params=params)
        self._handle_response(resp)
        return True

    def get_campaign_detail(self, campaign_id: int):
        url = f"{self.rest_base}/api/campaigns/{campaign_id}"
        resp = self.session.get(url)
        return self._handle_response(resp)

    def create_upload_url(self, user_id: int, filename: str, filesize: int, mimetype: str):
        url = f"{self.rest_base}/api/users/{user_id}/temporary-files/upload-url"
        payload = {
            "filename": filename,
            "filesize": filesize,
            "mimetype": mimetype
        }
        resp = self.session.post(url, json=payload)
        return self._handle_response(resp)

    def upload_file_binary(self, signed_url: str, file_path: str, mimetype: str):
        headers = {
            "Content-Type": mimetype
        }
        with open(file_path, "rb") as f:
            resp = requests.put(signed_url, headers=headers, data=f)
            status = resp.status_code
            text = resp.text[:300]
            if status not in [200, 201, 204]:
                raise APIError(f"Upload thất bại ({status}): {text}", status)
            return status, text

    def create_mockup_layer_from_temporary(self, temp_file_id: str, name: str, width: int, height: int):
        url = f"{self.rest_base}/api/mockup-layers/by-temporary-file"
        payload = {
            "temporary_file_id": temp_file_id,
            "name": name,
            "filewidth": width,
            "fileheight": height,
            "category_id": None
        }
        resp = self.session.post(url, json=payload)
        return self._handle_response(resp)

    def poll_mockup_layer(self, layer_name: str, user_id: int, upload_start_time: float, progress_cb, timeout_sec: int = 120, allow_fallback: bool = False):
        url = f"{self.rest_base}/api/mockup-layers"
        params = {
            "page": 1,
            "per_page": 50,
            "sort": "created_at",
            "sort_type": "desc"
        }
        start_time = time.time()
        import datetime
        import re
        
        progress_cb(f"Bắt đầu poll... (Tên cần tìm: {layer_name}, upload_start_time: {upload_start_time})")
        
        while time.time() - start_time < timeout_sec:
            try:
                resp = self.session.get(url, params=params)
                data = self._handle_response(resp)
                
                items = data.get("data", []) if isinstance(data, dict) and "data" in data else data
                if isinstance(items, dict) and "data" in items:
                    items = items["data"]
                
                if isinstance(items, list) and items:
                    # Log top 10 layers for debugging every 5s roughly
                    top_10_names = [f"[{it.get('id')}] {it.get('name')} ({it.get('created_at')}) url:{bool(it.get('url'))} thumb:{bool(it.get('thumbnail'))}" for it in items[:10]]
                    progress_cb(f"Polling top 10:\n  " + "\n  ".join(top_10_names))
                    
                    valid_items = [it for it in items if it.get("url") and it.get("thumbnail")]
                    
                    if valid_items:
                        # Priority 1: Exact match
                        for it in valid_items:
                            if it.get("name") == layer_name:
                                return it
                        
                        # Priority 2: Startswith
                        for it in valid_items:
                            name = it.get("name", "")
                            if name and name.startswith(layer_name):
                                progress_cb(f"Fallback P2 (Startswith): Chọn {name}")
                                return it
                                
                        # Priority 3: Contains normalized name
                        norm_expected = re.sub(r'[^a-zA-Z0-9]', '', layer_name).lower()
                        for it in valid_items:
                            name = it.get("name", "")
                            norm_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
                            if norm_expected and norm_expected in norm_name:
                                progress_cb(f"Fallback P3 (Contains Norm): Chọn {name}")
                                return it
                                
                        # Priority 4: Time window & Newest fallback
                        if allow_fallback and (time.time() - start_time > 20):
                            for it in valid_items:
                                c_at = it.get("created_at")
                                if c_at and it.get("user_id") == user_id:
                                    try:
                                        c_at_iso = c_at.replace("Z", "+00:00")
                                        dt = datetime.datetime.fromisoformat(c_at_iso)
                                        if dt.timestamp() >= upload_start_time:
                                            progress_cb(f"Fallback P4 (Newest > 20s): Chọn {it.get('name')}")
                                            return it
                                    except Exception:
                                        pass
                                    
            except Exception as e:
                progress_cb(f"Polling lỗi: {e}")
                
            time.sleep(5)
        raise APIError(f"Không tìm thấy layer '{layer_name}' sau {timeout_sec}s")

    def add_mockup_to_campaign(self, campaign_product_id: int, mockup_layer_id: int):
        url = f"{self.rest_base}/api/campaign-products/{campaign_product_id}/campaign-mockups"
        payload = {
            "mockup_layer_ids": [mockup_layer_id]
        }
        resp = self.session.post(url, json=payload)
        return self._handle_response(resp)

    def update_campaign_mockup(self, campaign_product_id: int, mockup_id: int, payload: dict):
        url = f"{self.rest_base}/api/campaign-products/{campaign_product_id}/campaign-mockups/{mockup_id}"
        resp = self.session.put(url, json=payload)
        return self._handle_response(resp)
