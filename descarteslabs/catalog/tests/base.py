import re
import unittest

import responses
import json
from six import ensure_str

from descarteslabs.client.auth import Auth
from ..catalog_base import CatalogClient


public_token = "header.e30.signature"


class ClientTestCase(unittest.TestCase):
    def setUp(self):
        self.url = "https://example.com/catalog/v2"
        self.client = CatalogClient(
            url=self.url, auth=Auth(jwt_token=public_token, token_info_path=None)
        )
        self.match_url = re.compile(self.url)

    def mock_response(self, method, json, status=200, **kwargs):
        responses.add(method, self.match_url, json=json, status=status, **kwargs)

    def get_request(self, index):
        r = responses.calls[index].request
        r.body = ensure_str(r.body)
        return r

    def get_request_body(self, index):
        return json.loads(ensure_str(responses.calls[index].request.body))
