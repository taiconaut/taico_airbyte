"""
Adform API Source Connector for Airbyte

This module contains the implementation of a custom source connector for the Adform API using the Airbyte CDK.
It consists of two main stream classes: ReportCreationStream for creating reports, and ReportDataStream for
fetching the report data.

Classes:
    ReportCreationStream: Handles the creation of reports via the Adform API.
    ReportDataStream: Fetches and processes the data from created reports.

Usage:
    This connector is designed to be used with the Airbyte platform to sync data from the Adform API
    to various destinations.

Configuration:
    The connector requires the following configuration parameters:
    - api_key: Your Adform API key
    - filter: Filter criteria for the report
    - metrics: Metrics to include in the report
    - dimensions: Dimensions to include in the report

Note:
    This connector implements pagination and handles rate limiting as per Adform API specifications.
    It uses a parent-child stream relationship where ReportCreationStream is the parent and
    ReportDataStream is the child.

Dependencies:
    - airbyte_cdk
    - requests

For more information on developing custom source connectors for Airbyte, please refer to:
https://docs.airbyte.com/connector-development/
"""

import time
import requests
from datetime import date

from typing import Any, Iterable, List, Mapping, Optional, Tuple, Union
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream, HttpSubStream
from airbyte_cdk.sources.streams.http.requests_native_auth import Oauth2Authenticator

DATE_FORMAT = "%Y-%m-%d"
POLLING_IN_SECONDS = 30
DEFAULT_START_DATE = "2016-01-01"

class ReportCreationStream(HttpStream):
    # Implementation for creating the report and getting the report ID
    # ...
    http_method = "POST"
    url_base = "https://api.adform.com"
    page_size = 100
    # max_pages = 100
    
    def __init__(self, authenticator, name, path, config, primary_key=None):
        self._name = name
        self._path = path
        self.config = config
        self._primary_key = primary_key
        self._offset = 0
        self._total_rows = None
        self._current_report_id = None
        super().__init__(authenticator=authenticator)
    
    @property
    def name(self) -> str:
        return self._name

    @property
    def primary_key(self) -> Optional[Union[str, List[str], List[List[str]]]]:
        return self._primary_key
    
    def stream_slices(self, sync_mode, cursor_field: List[str] = None, stream_state: Mapping[str, Any] = None) -> Iterable[Optional[Mapping[str, Any]]]:
        self.logger.info(f"Generating stream slice with offset: {self._offset}")
        yield {"offset": self._offset}

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None
    
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        headers = response.headers
        self._current_report_id = headers['Location']
        self.logger.info(f"Parsed response, got report_path: {self._current_report_id}")
        yield {'report_path': self._current_report_id, 'offset': self._offset}

    def path(
        self,
        *,
        stream_state: Optional[Mapping[str, Any]] = None,
        stream_slice: Optional[Mapping[str, Any]] = None,
        next_page_token: Optional[Mapping[str, Any]] = None,
    ) -> str:
        return self._path
    
    def request_body_json(
        self,
        stream_state: Optional[Mapping[str, Any]],
        stream_slice: Optional[Mapping[str, Any]] = None,
        next_page_token: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Mapping[str, Any]]:
        
        today: date = date.today()

        start_date = self.config.get("start_date", today.strftime(DATE_FORMAT))
        end_date = self.config.get("end_date", DEFAULT_START_DATE) 

        request_payload = {
            "filter": {
                "date": {
                    "From": start_date,
                    "To": end_date
                }
            },
            "metrics": self.config["metrics"],
            "dimensions": self.config["dimensions"],
            "paging": {
                "offset": self._offset,
                "limit": self.page_size,
            },
            "includeRowCount": True
        }
        return request_payload
    
    def backoff_time(self, response: requests.Response) -> Optional[float]:
        if isinstance(response, Exception):
            self.logger.warning(f"Back off due to {type(response)}.")
            return POLLING_IN_SECONDS * 2
        if response.status_code == 429:
            self.logger.warning(f"API calls quota exceeded, maximum admitted 10 per minute")
            return POLLING_IN_SECONDS * 2
        return super().backoff_time(response)
    
    def should_retry(self, response: requests.Response) -> bool:
        return response.status_code in [429]

    def get_json_schema(self):
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "report_path": {
                    "type": "string"
                }
            }
        }

class ReportDataStream(HttpSubStream):
    http_method = "GET"
    url_base = "https://api.adform.com"
    def __init__(self, name, authenticator, parent, config, primary_key = None):
        self._name = name
        self.config = config
        self._primary_key = primary_key
        self._has_more_data = True
        super().__init__(parent=parent, authenticator=authenticator)

    @property
    def name(self) -> str:
        return self._name

    @property
    def primary_key(self) -> Optional[Union[str, List[str], List[List[str]]]]:
        return self._primary_key
    
    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None
    ) -> str:
        return stream_slice['report_path']
   
    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None
    
    def stream_slices(self, sync_mode, cursor_field: List[str] = None, stream_state: Mapping[str, Any] = None) -> Iterable[Optional[Mapping[str, Any]]]:
        while self._has_more_data:
            parent_slice = next(self.parent.stream_slices(sync_mode=sync_mode, cursor_field=cursor_field, stream_state=stream_state), None)
            if parent_slice is None:
                break
            
            parent_records = list(self.parent.read_records(sync_mode=sync_mode, stream_slice=parent_slice))
            if not parent_records:
                break
           
            report_location = parent_records[0]['report_path']
            offset = parent_records[0]['offset']
           
            time.sleep(POLLING_IN_SECONDS)
            yield {"report_path": report_location, "offset": offset}
    
    def parse_response(self, response: requests.Response, stream_slice: Mapping[str, Any] = None, stream_state: Mapping[str, Any] = None, *kwargs) -> Iterable[Mapping]:
        response_json = response.json()
        report_data = response_json['reportData']
        columns = report_data['columnHeaders']
        rows = report_data['rows']

        self.logger.info(f"Reading report data")

        for row in rows:
            yield dict(zip(columns, row))
        
        # Check if we've reached the end of the data
        if len(rows) < self.parent.page_size:
            self.logger.info("Reached end of data")
            self._has_more_data = False
        else:
            # Update the parent's offset for the next iteration
            self.parent._offset += self.parent.page_size
    
    def backoff_time(self, response: requests.Response) -> Optional[float]:
        if isinstance(response, Exception):
            self.logger.warning(f"Back off due to {type(response)}.")
            return POLLING_IN_SECONDS * 2
        if response.status_code == 404:
            self.logger.warning(f"Query results are not ready yet! Retrying in {POLLING_IN_SECONDS*2} seconds...")
            return POLLING_IN_SECONDS * 2
        return super().backoff_time(response)

    def should_retry(self, response: requests.Response) -> bool:
        return response.status_code in [404]

# Source
class SourceAdform(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        TODO: Implement a connection check to validate that the user-provided config can be used to connect to the underlying API

        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        try:
            Oauth2Authenticator(
                token_refresh_endpoint="https://id.adform.com/sts/connect/token",
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                refresh_token=None,
                scopes=config["scope"],
                token_expiry_date=None,
                grant_type="client_credentials",
                refresh_request_body={
                    "grant_type": "client_credentials",
                    "client_id": config['client_id'],
                    "client_secret": config['client_secret'],
                    "scope": config['scope']
                }
            )
        except Exception as e:
            return False, e
        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        TODO: Replace the streams below with your own streams.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        auth = Oauth2Authenticator(
            token_refresh_endpoint="https://id.adform.com/sts/connect/token",
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            refresh_token=None,
            scopes=config["scope"],
            token_expiry_date=None,
            grant_type="client_credentials",
            refresh_request_body={
                "grant_type": "client_credentials",
                "client_id": config['client_id'],
                "client_secret": config['client_secret'],
                "scope": config['scope']
            }
        )
        report_creation = ReportCreationStream(
            authenticator=auth,
            name="report_creation",
            path="/v1/buyer/stats/data",
            config=config
        )
        return [
            ReportDataStream(
                name="report_data",
                authenticator=auth,
                parent=report_creation,
                config=config
           )
        ]