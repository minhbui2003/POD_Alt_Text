import requests
import logging

logger = logging.getLogger(__name__)

class GraphQLError(Exception):
    pass

class TeeInBlueGraphQLClient:
    def __init__(self, token: str):
        self.token = token
        self.graphql_base = "https://graphql.teeinblue.com/v1/graphql"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        })

    def update_alt_text(self, campaign_mockup_id: int, alt_text: str):
        query = """
        mutation update($id: bigint!, $objects: campaign_mockups_set_input!) {
            update_campaign_mockups(where: {id: {_eq: $id}}, _set: $objects) {
                returning {
                    id
                    __typename
                }
                __typename
            }
        }
        """
        payload = {
            "operationName": "update",
            "variables": {
                "id": campaign_mockup_id,
                "objects": {
                    "alt": alt_text
                }
            },
            "query": query
        }
        
        resp = self.session.post(self.graphql_base, json=payload)
        
        if resp.status_code >= 400:
            raise GraphQLError(f"GraphQL HTTP Error {resp.status_code}: {resp.text}")
            
        data = resp.json()
        if "errors" in data:
            err_msg = ", ".join([err.get("message", "Unknown error") for err in data["errors"]])
            raise GraphQLError(f"GraphQL update lỗi: {err_msg}")
            
        return data
