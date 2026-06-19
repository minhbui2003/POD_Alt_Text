from typing import List, Callable
from graphql_client import TeeInBlueGraphQLClient

class AltService:
    def __init__(self, graphql_client: TeeInBlueGraphQLClient):
        self.graphql_client = graphql_client

    def process_batch(self, update_tasks: List[dict]):
        # update_tasks: [{"mockup_id": ..., "new_alt": ..., "progress_cb": ..., "error_cb": ...}]
        for task in update_tasks:
            mid = task['mockup_id']
            alt = task['new_alt']
            progress_cb = task['progress_cb']
            error_cb = task['error_cb']
            
            try:
                progress_cb("Cập nhật Alt...")
                self.graphql_client.update_alt_text(mid, alt)
                progress_cb("Alt updated")
            except Exception as e:
                error_cb(str(e))
                progress_cb("Cập nhật Alt lỗi")
