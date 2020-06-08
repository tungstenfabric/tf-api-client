from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import range
import platform
from . import test_common
import json
import httpretty
from urllib.parse import urlparse
from requests.exceptions import ConnectionError

from testtools.matchers import Contains
from testtools import ExpectedException

from vnc_api.gen.vnc_api_client_gen import all_resource_type_tuples
from vnc_api import vnc_api
from vnc_api.utils import OP_GET


def _auth_request_status(request, url, status_code):
    ret_headers = {'server': '127.0.0.1'}
    try:
        ret_headers.update(request.headers.dict)
    except AttributeError:
        ret_headers.update(dict(request.headers.items()))
        del ret_headers['Content-Length']
    ret_body = {'access': {'token': {'id': 'foo'}}}
    return (status_code, ret_headers, json.dumps(ret_body))


class TestVncApi(test_common.TestCase):
    def test_retry_after_auth_success(self):
        uri_with_auth = '/try-after-auth'
        url_with_auth = 'http://127.0.0.1:8082/try-after-auth'
        httpretty.register_uri(
                httpretty.GET, url_with_auth,
                responses=[httpretty.Response(status=401, body='""'),
                           httpretty.Response(status=200, body='""')])

        auth_url = "http://127.0.0.1:35357/v2.0/tokens"

        def _auth_request_success(request, url, *args):
            return _auth_request_status(request, url, 200)

        httpretty.register_uri(
                httpretty.POST, auth_url, body=_auth_request_success)

        self._vnc_lib._request_server(OP_GET, url=uri_with_auth)
    # end test_retry_after_auth_success

    def test_retry_after_auth_failure(self):
        uri_with_auth = '/try-after-auth'
        url_with_auth = 'http://127.0.0.1:8082/try-after-auth'
        httpretty.register_uri(
                httpretty.GET, url_with_auth,
                responses=[httpretty.Response(status=401, body='""')])

        auth_url = "http://127.0.0.1:35357/v2.0/tokens"

        def _auth_request_failure(request, url, *args):
            return _auth_request_status(request, url, 401)

        httpretty.register_uri(
                httpretty.POST, auth_url, body=_auth_request_failure)

        with ExpectedException(RuntimeError):
            self._vnc_lib._request_server(OP_GET, url=uri_with_auth)
    # end test_retry_after_auth_failure

    def test_contrail_useragent_header(self):
        def _check_header(uri, headers=None, query_params=None):
            useragent = headers['X-Contrail-Useragent']
            hostname = platform.node()
            self.assertThat(useragent, Contains(hostname))
            return (200, json.dumps({}))

        orig_http_get = self._vnc_lib._http_get
        try:
            self._vnc_lib._http_get = _check_header
            self._vnc_lib._request_server(OP_GET, url='/')
        finally:
            self._vnc_lib._http_get = orig_http_get
    # end test_contrail_useragent_header

    def test_server_has_more_types_than_client(self):
        links = [
            {"link": {
                "href": "http://localhost:8082/foos",
                "name": "foo",
                "rel": "collection"
            }
            },
            {"link": {
                "href": "http://localhost:8082/foo",
                "name": "foo",
                "rel": "resource-base"
            }
            },
        ]
        httpretty.register_uri(
                httpretty.GET, "http://127.0.0.1:8082/",
                body=json.dumps({'href': "http://127.0.0.1:8082",
                                 'links': links}))

        vnc_api.VncApi(conf_file='/tmp/fake-config-file')
    # end test_server_has_more_types_than_client

    def test_supported_auth_strategies(self):
        uri_with_auth = '/try-after-auth'
        url_with_auth = 'http://127.0.0.1:8082%s' % uri_with_auth
        httpretty.register_uri(
            httpretty.GET, url_with_auth,
            responses=[httpretty.Response(status=401, body='""'),
                       httpretty.Response(status=200, body='""')],
        )
        auth_url = "http://127.0.0.1:35357/v2.0/tokens"
        keystone_api_called = [False]

        def keytone_api_request(request, url, *args):
            keystone_api_called[0] = True
            return _auth_request_status(request, url, 200)

        httpretty.register_uri(httpretty.POST, auth_url,
                               body=keytone_api_request)

        # Verify auth strategy is Keystone if not provided and check Keystone
        # API is requested
        self.assertEqual(self._vnc_lib._authn_strategy, 'keystone')
        self._vnc_lib._request_server(OP_GET, url=uri_with_auth)
        self.assertTrue(keystone_api_called[0])

        # Validate we can use 'noauth' auth strategy and check Keystone API is
        # not requested
        keystone_api_called = [False]
        self._vnc_lib = vnc_api.VncApi(conf_file='/tmp/fake-config-file',
                                       auth_type='noauth')
        self.assertEqual(self._vnc_lib._authn_strategy, 'noauth')
        self._vnc_lib._request_server(OP_GET, url=uri_with_auth)
        self.assertFalse(keystone_api_called[0])

        # Validate we cannot use unsupported authentication strategy
        with ExpectedException(NotImplementedError):
            self._vnc_lib = vnc_api.VncApi(auth_type='fake-auth')

    def test_multiple_server_roundrobin_session(self):
        httpretty.register_uri(
                httpretty.GET, "http://127.1.0.1:8082/",
                body=json.dumps({'href': "http://127.1.0.1:8082",
                                 'links': []}))
        httpretty.register_uri(
                httpretty.GET, "http://127.1.0.2:8082/",
                body=json.dumps({'href': "http://127.1.0.2:8082",
                                 'links': []}))
        api_servers = ['127.1.0.3', '127.1.0.2', '127.1.0.1']
        vnclib = vnc_api.VncApi(
                api_server_host=api_servers)

        # Try connecting to api-server with one node(127.1.0.3) down
        # Expected the connection to round robin between
        # 127.1.0.2 and 127.1.0.1
        response = vnclib._request_server(OP_GET, url='/')
        index = api_servers.index(urlparse(response['href']).hostname)
        for i in range(6):
            if index < (len(api_servers) - 1):
                index += 1
            else:
                index = 1
            response = vnclib._request_server(OP_GET, url='/')
            self.assertEqual(
                    response['href'], 'http://%s:8082' % api_servers[index])
    # end test_multiple_server_active_session

    def test_multiple_server_all_servers_down(self):
        httpretty.register_uri(
                httpretty.GET, "http://127.2.0.1:8082/",
                body=json.dumps({'href': "http://127.2.0.1:8082",
                                 'links': []}))
        httpretty.register_uri(
                httpretty.GET, "http://127.2.0.2:8082/",
                body=json.dumps({'href': "http://127.2.0.2:8082",
                                 'links': []}))
        httpretty.register_uri(
                httpretty.GET, "http://127.2.0.3:8082/",
                body=json.dumps({'href': "http://127.2.0.3:8082",
                                 'links': []}))
        vnclib = vnc_api.VncApi(
                api_server_host=['127.2.0.3', '127.2.0.2', '127.2.0.1'])
        # Connect to a server
        # Expected to connect to first server
        response = vnclib._request_server(OP_GET, url='/')
        self.assertEqual(
                response['href'], 'http://127.2.0.2:8082')

        # Bring down all fake servers
        httpretty.disable()

        # Connect to a server
        # Expected to connect to second server
        # first server will used during authenticate
        with ExpectedException(ConnectionError):
            vnclib._request_server(OP_GET, url='/', retry_on_error=False)

        # Bring up all fake servers
        httpretty.enable()

        # Connect to a server
        # Expected to connect to first server
        response = vnclib._request_server(OP_GET, url='/')
        self.assertEqual(
                response['href'], 'http://127.2.0.3:8082')
        # Connect to a server
        # Expected to connect to second server
        response = vnclib._request_server(OP_GET, url='/')
        self.assertEqual(
                response['href'], 'http://127.2.0.2:8082')
        # Expected to connect to third server
        response = vnclib._request_server(OP_GET, url='/')
        self.assertEqual(
                response['href'], 'http://127.2.0.1:8082')
        # Expected to connect to first server
        response = vnclib._request_server(OP_GET, url='/')
        self.assertEqual(
                response['href'], 'http://127.2.0.3:8082')
    # end test_multiple_server_all_servers_down

    def test_only_security_resources_have_read_draft_method(self):
        for object_type, resource_type in all_resource_type_tuples:
            method_name = '%s_read_draft' % object_type
            if object_type in self._vnc_lib._SECURITY_OBJECT_TYPES:
                self.assertTrue(hasattr(self._vnc_lib, method_name))
            else:
                self.assertFalse(hasattr(self._vnc_lib, method_name))

# end class TestVncApi
