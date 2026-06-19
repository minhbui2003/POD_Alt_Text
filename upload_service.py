import os
import concurrent.futures
from typing import List, Callable
from api_client import TeeInBlueAPIClient

class UploadService:
    def __init__(self, api_client: TeeInBlueAPIClient, max_workers: int = 3):
        self.api_client = api_client
        self.max_workers = min(max_workers, 5) # Capped at 5 as per user request

    def process_single_upload(self, user_id: int, campaign_product_id: int, file_path: str, layer_name: str, 
                              progress_cb: Callable, error_cb: Callable, row_index: int, allow_fallback: bool = False):
        try:
            import time
            from PIL import Image
            
            filesize = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            mimetype = "image/webp" if ext == ".webp" else "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
            filename = layer_name + ext
            
            with Image.open(file_path) as img:
                width, height = img.size
            
            # 1. Create upload url
            progress_cb("Lấy link upload...")
            upload_res = self.api_client.create_upload_url(user_id, filename, filesize, mimetype)
            signed_url = upload_res.get('meta', {}).get('signed_url')
            
            # Extract data for logging
            temp_file_id = upload_res.get('data', {}).get('id')
            temp_path = upload_res.get('data', {}).get('path')
            progress_cb(f"Created Upload URL: file={filename}, id={temp_file_id}, path={temp_path}, signed_url_exists={bool(signed_url)}")
            
            if not signed_url:
                raise Exception("Không lấy được signed_url")
                
            upload_start_time = time.time()
            
            # 2. Upload binary
            progress_cb("Đang upload file (PUT)...")
            status, text = self.api_client.upload_file_binary(signed_url, file_path, mimetype)
            progress_cb(f"PUT Status: {status}. Response: {text[:100]}")
            
            # 3. Create mockup layer from temporary file
            progress_cb("Tạo Mockup Layer từ Temporary File...")
            created_layer = self.api_client.create_mockup_layer_from_temporary(temp_file_id, layer_name, width, height)
            progress_cb(f"Đã tạo layer tạm: ID={created_layer.get('id')}")
            
            # 4. Poll layer until url and thumbnail are generated
            progress_cb("Chờ Server xử lý ảnh (Sinh URL)...")
            layer_data = self.api_client.poll_mockup_layer(
                layer_name=layer_name, 
                user_id=user_id, 
                upload_start_time=upload_start_time,
                progress_cb=progress_cb,
                timeout_sec=120,
                allow_fallback=allow_fallback
            )
            layer_id = layer_data['id']
            layer_name_matched = layer_data.get('name')
            layer_url_matched = layer_data.get('url')
            
            progress_cb(f"Tìm thấy layer: {layer_name_matched} (ID: {layer_id})")
            
            # 4. Add mockup
            progress_cb("Gán vào campaign...")
            self.api_client.add_mockup_to_campaign(campaign_product_id, layer_id)
            
            progress_cb("Upload thành công")
            return {
                "row_index": row_index,
                "layer_name": layer_name,
                "success": True,
                "selected_layer_id": layer_id,
                "selected_layer_name": layer_name_matched,
                "selected_layer_url": layer_url_matched
            }
            
        except Exception as e:
            error_cb(str(e))
            progress_cb("Upload lỗi")
            return {
                "row_index": row_index,
                "layer_name": layer_name,
                "success": False
            }

    def process_batch(self, user_id: int, campaign_product_id: int, upload_tasks: List[dict]):
        # upload_tasks: [{"file_path": ..., "layer_name": ..., "progress_cb": ..., "error_cb": ...}]
        results = []
        allow_fb = (len(upload_tasks) == 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.process_single_upload, 
                    user_id, 
                    campaign_product_id, 
                    task['file_path'], 
                    task['layer_name'], 
                    task['progress_cb'], 
                    task['error_cb'],
                    task['row_index'],
                    allow_fb
                ): task for task in upload_tasks
            }
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    # Catch-all
                    task = futures[future]
                    task['error_cb'](f"Lỗi thread: {str(e)}")
                    task['progress_cb']("Upload lỗi")
                    
        return results
