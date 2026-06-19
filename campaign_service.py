import urllib.parse
from api_client import TeeInBlueAPIClient

class CampaignService:
    def __init__(self, api_client: TeeInBlueAPIClient):
        self.api_client = api_client

    def parse_url(self, url: str):
        try:
            parsed = urllib.parse.urlparse(url)
            path_parts = parsed.path.split('/')
            
            campaign_id = None
            if 'campaigns' in path_parts:
                idx = path_parts.index('campaigns')
                campaign_id = int(path_parts[idx+1])
            
            qs = urllib.parse.parse_qs(parsed.query)
            product_id = None
            if 'product-id' in qs:
                product_id = int(qs['product-id'][0])
                
            if not campaign_id or not product_id:
                raise ValueError("Không tìm thấy campaign_id hoặc product_id trong URL")
                
            return campaign_id, product_id
        except Exception as e:
            raise ValueError(f"URL không hợp lệ: {str(e)}")

    def load_campaign(self, campaign_id: int, product_id: int):
        data = self.api_client.get_campaign_detail(campaign_id)
        
        target_cp = None
        for cp in data.get('campaign_products', []):
            if cp.get('product_id') == product_id:
                target_cp = cp
                break
                
        if not target_cp:
            raise ValueError(f"Không tìm thấy campaign_product cho product_id {product_id}")
            
        campaign_product_id = target_cp['id']
        mockups = target_cp.get('campaign_mockups', [])
        
        # Sort by position ASC
        mockups.sort(key=lambda x: x.get('position', 0))
        
        # Extract user_id from first mockup if possible
        user_id = None
        for m in mockups:
            preview_url = m.get('preview_url', '')
            if preview_url.startswith('users/'):
                parts = preview_url.split('/')
                if len(parts) > 1 and parts[1].isdigit():
                    user_id = int(parts[1])
                    break
                    
        return {
            "campaign_product_id": campaign_product_id,
            "mockups": mockups,
            "user_id": user_id
        }
