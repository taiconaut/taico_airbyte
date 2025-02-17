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
    def cursor_field(self) -> str:
        """
        TODO
        Override to return the cursor field used by this stream e.g: an API entity might always use created_at as the cursor field. This is
        usually id or date based. This field's presence tells the framework this in an incremental stream. Required for incremental.

        :return str: The name of the cursor field.
        """
        return []

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Override to determine the latest state after reading the latest record. This typically compared the cursor_field from the latest record and
        the current state and picks the 'most' recent cursor. This is how a stream's state is determined. Required for incremental.
        """
        return {}


class Employees(IncrementalAdformStream):
    """
    TODO: Change class name to match the table/data source this stream corresponds to.
    """

    # TODO: Fill in the cursor_field. Required.
    cursor_field = "start_date"

    # TODO: Fill in the primary key. Required. This is usually a unique field in the stream, like an ID or a timestamp.
    primary_key = "employee_id"

    def path(self, **kwargs) -> str:
        """
        TODO: Override this method to define the path this stream corresponds to. E.g. if the url is https://example-api.com/v1/employees then this should
        return "single". Required.
        """
        return "employees"

    def stream_slices(self, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, any]]]:
        """
        TODO: Optionally override this method to define this stream's slices. If slicing is not needed, delete this method.

        Slices control when state is saved. Specifically, state is saved after a slice has been fully read.
        This is useful if the API offers reads by groups or filters, and can be paired with the state object to make reads efficient. See the "concepts"
        section of the docs for more information.

        The function is called before reading any records in a stream. It returns an Iterable of dicts, each containing the
        necessary data to craft a request for a slice. The stream state is usually referenced to determine what slices need to be created.
        This means that data in a slice is usually closely related to a stream's cursor_field and stream_state.

        An HTTP request is made for each returned slice. The same slice can be accessed in the path, request_params and request_header functions to help
        craft that specific request.

        For example, if https://example-api.com/v1/employees offers a date query params that returns data for that particular day, one way to implement
        this would be to consult the stream state object for the last synced date, then return a slice containing each date from the last synced date
        till now. The request_params function would then grab the date from the stream_slice and make it part of the request by injecting it into
        the date query param.
        """
        raise NotImplementedError("Implement stream slices or delete this method!")


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