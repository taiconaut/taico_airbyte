"""
Pubmatic API Source Connector for Airbyte

This module contains the implementation of a custom source connector for the Pubmatic API using the Airbyte CDK.
It consists of one main stream class: Analytics

Classes:
    Analytics: Executes a certain analytics report.

Usage:
    This connector is designed to be used with the Airbyte platform to sync data from the Pubmatic API
    to various destinations.

Configuration:
    The connector requires the following configuration parameters:
    - publisher_id: Your Pubmatic account ID
    - email: Your Pubmatic login email
    - password: Your Pubmatic login password

Dependencies:
    - airbyte_cdk
    - requests

For more information on developing custom source connectors for Airbyte, please refer to:
https://docs.airbyte.com/connector-development/
"""
import requests
from typing import Any, List, Mapping, Tuple, Optional, Iterable
from datetime import datetime, timedelta
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.auth import TokenAuthenticator

WINDOW_LENGTH = {
    "daily": 100,
    "monthly": 50*30
}
date_unit = {
    "daily": "date",
    "monthly": "month"
}
class AnalyticsStream(HttpStream):
    url_base = "https://api.pubmatic.com/"
    primary_key = None  # Define your primary key if applicable
    def __init__(self, config: Mapping[str, Any], authenticator, *kwargs):
        self.frquency = config["frequency"]
        self._name = "analytics"
        self.publisher_id = config["publisher_id"]
        today = datetime.now()
        self.end_date = today.strftime("%Y-%m-%d")
        self.window_length = WINDOW_LENGTH[config['frequency']]
        self.start_date = (today - timedelta(days=self.window_length)).strftime("%Y-%m-%d")
        self.config = config
        super().__init__(authenticator=authenticator)
        
    @property
    def name(self) -> str:
        return self._name
    
    def next_page_token(self, response: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        return None
    
    def path(
            self,
            *,
            stream_state: Optional[Mapping[str, Any]] = None,
            stream_slice: Optional[Mapping[str, Any]] = None,
            next_page_token: Optional[Mapping[str, Any]] = None,
        ) -> str:
        return f"/v1/analytics/data/publisher/{self.publisher_id}"
        
    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> Mapping[str, Any]:
        
        params = {  
            "toDate": self.end_date,
            "metrics": "ctr,clicks,paidImpressions,revenue,ecpm",
            "dateUnit": date_unit[self.frquency],
            "fromDate": self.start_date,
            "dimensions": f"{date_unit[self.frquency]},channelId,countryId,adFormatId,subAdFormatId,advertiserId",
            "currency": "EUR"
        }
        self.logger.info(f"Pulling {self.frquency} data from {self.start_date} to {self.end_date}")
        return params
        
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        response_json = response.json()
        display_value = response_json.get('displayValue', {})
        rows = response_json.pop("rows")
        columns = response_json.pop("columns")
        columns[0] = "date"
        for row in rows:
            record = dict(zip(columns, row))
            for field, id_value in record.items():
                if field in display_value and str(id_value) in display_value[field]:
                    record[field] = display_value[field][str(id_value)]
            yield record
   
class PubmaticAuthenticator(TokenAuthenticator):
   """
   Custom authenticator for Pubmatic API
   """
   def __init__(self, config: Mapping[str, Any]):
       self.config = config
       super().__init__(None)  # Initialize with None, we'll get the token later
       
   def get_auth_header(self) -> Mapping[str, str]:
       
       auth_url = "http://api.pubmatic.com/v1/developer-integrations/developer/token"
       auth_data = {
           "password": self.config["password"],
           "userName": self.config["email"],
           "apiProduct": "PUBLISHER"
       }
       
       response = requests.post(auth_url, json=auth_data)

       if response.status_code in [200, 201]:
           token_data = response.json()
           print(token_data)
           token = token_data.get("accessToken")
           return {"Authorization": f"Bearer {token}"}
       else:
           raise Exception(f"Failed to authenticate: {response.text}")
class SourcePubmatic(AbstractSource):
   def check_connection(self, logger, config) -> Tuple[bool, any]:
       try:
           authenticator = PubmaticAuthenticator(config)
           stream = AnalyticsStream(config=config, authenticator=authenticator)
           next(stream.read_records(sync_mode=None))
           return True, None
       except Exception as e:
           return False, f"Connection check failed: {e}"
       
   def streams(self, config: Mapping[str, Any]) -> List[Stream]:
       authenticator = PubmaticAuthenticator(config)
       return [AnalyticsStream(config=config, authenticator=authenticator)]