#encoding: utf-8


from collections import namedtuple
import unittest

from wsgid.core import Wsgid, Plugin
from wsgid.core.parser import parse_options
from wsgid.interfaces.filters import IPreRequestFilter, IPostRequestFilter
from wsgid.core.message import Message
import wsgid.conf as conf
from wsgid import __version__
import sys
import simplejson
import plugnplay

from mock import patch, Mock, call, ANY

class WsgidTest(unittest.TestCase):

  def setUp(self):
    self.wsgid = Wsgid()
    self.wsgid.send_sock = Mock()
    self.sample_headers = {
          'METHOD': 'GET',
          'VERSION': 'HTTP/1.1',
          'PATTERN': '/root',
          'URI': '/more/path/',
          'PATH': '/more/path',
          'QUERY': 'a=1&b=4&d=4',
          'host': 'localhost',
          'content-length': '42',
          'content-type': 'text/plain',
          'x-forwarded-for': '127.0.0.1'
        }
    sys.argv[1:] = []
    parse_options()

  def tearDown(self):
    self.sample_headers = {}
    conf.settings = None



  '''
   Creates the SCRIPT_NAME header from the mongrel2 PATTERN header.
   SCRIPT_NAME should be the PATTERN without any regex parts.
  '''
  def test_script_name_header_simple_path(self):
    self.sample_headers['PATTERN'] = "/py"
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("/py", environ['SCRIPT_NAME'])

  def test_environ_script_name_header_more_comples_header(self):
    self.sample_headers['PATTERN'] = '/some/more/path/'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("/some/more/path", environ['SCRIPT_NAME'])

  def test_environ_script_name_header_root(self):
    self.sample_headers['PATTERN'] = '/'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("", environ['SCRIPT_NAME'])


  '''
   PATH_INFO comes from (URI - SCRIPT_NAME) or (PATH - SCRIPT_NAME)
  '''
  def test_environ_path_info(self):

    self.sample_headers['PATTERN'] = '/py'
    self.sample_headers['PATH'] = '/py/some/py/path'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("/some/py/path", environ['PATH_INFO'])

  def test_environ_path_info_app_root(self):
    self.sample_headers['PATTERN'] = '/py'
    self.sample_headers['PATH'] = '/py'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("", environ['PATH_INFO'])


  def test_environ_unquoted_path_info(self):
    self.sample_headers['PATTERN'] = '/py/'
    self.sample_headers['PATH'] = '/py/so%20me/special%3f/user%40path'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('/so me/special?/user@path', environ['PATH_INFO'])

  '''
   Generates de REQUEST_METHOD variable
  '''
  def test_environ_request_method(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertTrue('REQUEST_METHOD' in environ)
    self.assertEquals('GET', environ['REQUEST_METHOD'])


  def test_environ_query_string(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("a=1&b=4&d=4", environ['QUERY_STRING'])

  def test_environ_no_query_string(self):
    #Not always we have a QUERY_STRING
    del self.sample_headers['QUERY']
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals("", environ['QUERY_STRING'])


  def test_environ_server_port(self):
    self.sample_headers['host'] = 'localhost:443'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('443', environ['SERVER_PORT'])

  def test_environ_server_port_default_port(self):
    self.sample_headers['host'] = 'localhost'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('80', environ['SERVER_PORT'])

  def test_environ_server_name(self):
    self.sample_headers['host'] = 'localhost:8080'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('localhost', environ['SERVER_NAME'])

  def test_environ_server_name_default_port(self):
    self.sample_headers['host'] = 'someserver'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('someserver', environ['SERVER_NAME'])

  '''
   HTTP_HOST must inclue the port, if present.
  '''
  def test_environ_http_host(self):
    self.sample_headers['host'] = 'localhost:8080'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('localhost:8080', environ['HTTP_HOST'])

  def test_environ_content_type(self):
    self.sample_headers['content-type'] = 'application/xml'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('application/xml', environ['CONTENT_TYPE'])

  def test_environ_no_content_type(self):
    del self.sample_headers['content-type']
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('', environ['CONTENT_TYPE'])

  def test_environ_content_length(self):
    self.sample_headers['content-length'] = '42'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('42', environ['CONTENT_LENGTH'])

  def test_environ_no_content_length(self):
    del self.sample_headers['content-length']
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('', environ['CONTENT_LENGTH'])

  '''
   Comes from mongrel2 VERSION header
  '''
  def test_environ_server_protocol(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertTrue('SERVER_PROTOCOL' in environ)
    self.assertEquals('HTTP/1.1', environ['SERVER_PROTOCOL'])


  def test_eviron_remote_addr(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('127.0.0.1', environ['REMOTE_ADDR'])


  '''
   Non Standard headers (X-) are passed untouched
  '''
  def test_environ_non_standart_headers(self):
    self.sample_headers['X-Some-Header'] = 'some-value'
    self.sample_headers['x-other-header'] = 'other-value'

    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('some-value', environ['X-Some-Header'])
    self.assertEquals('other-value', environ['x-other-header'])

  def test_environ_http_host_header(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('localhost', environ['HTTP_HOST'])

  '''
   All headers (but HTTP common headers and X- headers) must be HTTP_ prefixed
  '''
  def test_environ_other_headers(self):
    self.sample_headers['my_header'] = 'some-value'
    self.sample_headers['OTHER_HEADER'] = 'other-value'
    self.sample_headers['X-Some-Header'] = 'x-header'
    self.sample_headers['Accept'] = '*/*'
    self.sample_headers['Referer'] = 'http://www.someserver.com'

    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('some-value', environ['HTTP_MY_HEADER'])
    self.assertEquals('other-value', environ['HTTP_OTHER_HEADER'])
    self.assertEquals('x-header', environ['X-Some-Header'])
    self.assertEquals('*/*', environ['HTTP_ACCEPT'])
    self.assertEquals('http://www.someserver.com', environ['HTTP_REFERER'])


  '''
   Test a complete request, with all typed of headers.
  '''
  def test_eviron_complete_request(self):
    request = {
          'METHOD': 'GET',
          'VERSION': 'HTTP/1.1',
          'PATTERN': '/py',
          'URI': '/py/some/path',
          'PATH': '/py/some/path',
          'QUERY': 'a=1&b=4&d=4',
          'host': 'localhost',
          'Accept': '*/*',
          'CUSTOM_HEADER': 'value',
          'User-Agent': 'some user agent/1.0',
          'content-length': '42',
          'content-type': 'text/plain',
          'x-forwarded-for': '127.0.0.1'
        }

    environ = self.wsgid._create_wsgi_environ(request)
    self.assertEquals(24, len(environ))
    self.assertEquals('GET', environ['REQUEST_METHOD'])
    self.assertEquals('HTTP/1.1', environ['SERVER_PROTOCOL'])
    self.assertEquals('/py', environ['SCRIPT_NAME'])
    self.assertEquals('a=1&b=4&d=4', environ['QUERY_STRING'])
    self.assertEquals('/some/path', environ['PATH_INFO'])
    self.assertEquals('localhost', environ['SERVER_NAME'])
    self.assertEquals('80', environ['SERVER_PORT'])
    self.assertEquals('value', environ['HTTP_CUSTOM_HEADER'])
    self.assertEquals('*/*', environ['HTTP_ACCEPT'])
    self.assertEquals('some user agent/1.0', environ['HTTP_USER-AGENT'])
    self.assertEquals('42', environ['CONTENT_LENGTH'])
    self.assertEquals('42', environ['content-length'])
    self.assertEquals('text/plain', environ['CONTENT_TYPE'])
    self.assertEquals('text/plain', environ['content-type'])
    self.assertEquals('localhost', environ['HTTP_HOST'])
    self.assertEquals('127.0.0.1', environ['REMOTE_ADDR'])

  '''
   Some values are fixed:
    * wsgi.multithread = False
    * wsgi.multiprocess = True
    * wsgi.run_once = True
    * wsgi.version = (1,0)
  '''
  def test_environ_fixed_values(self):
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals(False, environ['wsgi.multithread'])
    self.assertEquals(True, environ['wsgi.multiprocess'])
    self.assertEquals(True, environ['wsgi.run_once'])
    self.assertEquals((1,0), environ['wsgi.version'])
    # url_scheme defaults to http
    self.assertEquals("http", environ['wsgi.url_scheme'])
    self.assertEquals(sys.stderr, environ['wsgi.errors'])

  def test_url_scheme_http(self):
    self.sample_headers['URL_SCHEME'] = 'http'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('http', environ['wsgi.url_scheme'])

  def test_url_scheme_https(self):
    self.sample_headers['URL_SCHEME'] = 'https'
    environ = self.wsgid._create_wsgi_environ(self.sample_headers)
    self.assertEquals('https', environ['wsgi.url_scheme'])

  def test_join_m2_chroot_to_async_upload_path(self):
      # The value in x-mongrel2-upload-{start,done} should be prepended with the
      # value of --m2-chroot, passed on the command line
      with patch('zmq.Context'):
          def _serve_request(wsgid, m2message, expected_final_path):
            with patch.object(wsgid, '_create_wsgi_environ'):
                wsgid._create_wsgi_environ.return_value = {}
                with patch("__builtin__.open") as mock_open:
                    with patch('os.unlink'):
                        wsgid._call_wsgi_app(message)
                        self.assertEquals(1, mock_open.call_count)
                        mock_open.assert_called_with(expected_final_path)

          self._reparse_options('--mongrel2-chroot=/var/mongrel2')
          wsgid = Wsgid(app = Mock(return_value=['body response']))
          wsgid.send_sock = Mock()
          message = self._create_fake_m2message('/uploads/m2.84Yet4')
          _serve_request(wsgid, message, '/var/mongrel2/uploads/m2.84Yet4')
          self._reparse_options()
          _serve_request(wsgid, message, '/uploads/m2.84Yet4')


  def test_remove_async_file_after_request_finishes_ok(self):
      # Since mongrel2 does not remove the originial temp file, wsgid
      # must remove it after the request was successfully (or not) handled.
      with patch('zmq.Context'):
          with patch('os.unlink') as mock_unlink:
            def _serve_request(wsgid, m2message):
                with patch.object(wsgid, '_create_wsgi_environ'):
                    wsgid._create_wsgi_environ.return_value = {}
                    with patch("__builtin__.open"):
                        wsgid._call_wsgi_app(message,)

            wsgid = Wsgid(app = Mock(return_value=['body response']))
            wsgid.send_sock = Mock()
            message = self._create_fake_m2message('/uploads/m2.84Yet4')
            _serve_request(wsgid, message)
            mock_unlink.assert_called_with('/uploads/m2.84Yet4')


  def test_remove_async_file_after_failed_request(self):
      # Even if the request failed, wsgid must remove the temporary file.
       with patch('zmq.Context'):
          with patch('os.unlink') as mock_unlink:
            def _serve_request(wsgid, m2message):
                with patch.object(wsgid, '_create_wsgi_environ'):
                    wsgid._create_wsgi_environ.return_value = {}
                    with patch("__builtin__.open"):
                        wsgid._call_wsgi_app(message)

            wsgid = Wsgid(app = Mock(side_effect = Exception("Failed")))
            wsgid.send_sock = Mock()
            wsgid.log = Mock()
            message = self._create_fake_m2message('/uploads/m2.84Yet4')
            _serve_request(wsgid, message)
            mock_unlink.assert_called_with('/uploads/m2.84Yet4')

  def test_protect_against_exception_on_file_removal(self):
        with patch('zmq.Context'):
          with patch('os.unlink') as mock_unlink:
            mock_unlink.side_effect = OSError("File does not exist")
            def _serve_request(wsgid, m2message):
                with patch.object(wsgid, '_create_wsgi_environ'):
                    wsgid._create_wsgi_environ.return_value = {}
                    with patch("__builtin__.open"):
                        wsgid._call_wsgi_app(message)

            wsgid = Wsgid(app = Mock(return_value = ['body response']))
            wsgid.send_sock = Mock()
            wsgid.log = Mock()
            message = self._create_fake_m2message('/uploads/m2.84Yet4')
            _serve_request(wsgid, message)
            self.assertEquals(1, wsgid.log.exception.call_count)

  def test_do_not_try_to_remove_if_not_upload_request(self):
         with patch('zmq.Context'):
          with patch('os.unlink') as mock_unlink:
            def _serve_request(wsgid, m2message):
                with patch.object(wsgid, '_create_wsgi_environ'):
                    wsgid._create_wsgi_environ.return_value = {}
                    with patch("__builtin__.open"):
                        wsgid._call_wsgi_app(message)

            wsgid = Wsgid(app = Mock(return_value = ['body response']))
            wsgid.send_sock = Mock()
            wsgid.log = Mock()
            message = Mock()
            message.headers = {'VERSION':'HTTP/1.1'} #It's not an upload message
            message.client_id = 'uuid'
            message.server_id = '1'
            message.is_upload_done.return_value = False
            _serve_request(wsgid, message)
            self.assertEquals(0, mock_unlink.call_count)

  def _reparse_options(self, *args):
      sys.argv[1:] = args
      conf.settings = None
      parse_options()

  def _create_fake_m2message(self, async_upload_path):
        message = Mock()
        message.headers = {'x-mongrel2-upload-start': async_upload_path,
                            'x-mongrel2-upload-done': async_upload_path,
                            'VERSION' : 'HTTP/1.0'}
        message.async_upload_path = async_upload_path
        message.server_id = 'uuid'
        message.client_id = '42'
        return message

class WsgidReplyTest(unittest.TestCase):

  def setUp(self):
    self.sample_uuid = 'bb3ce668-4528-11e0-94e3-001fe149503a'
    self.sample_conn_id = '42'
    self.message = Message('%s %s / 22:{"VERSION":"HTTP/1.0"},0:,' % (self.sample_uuid, self.sample_conn_id))


  def test_reply(self):
    wsgid = Wsgid()
    socket = Mock()
    socket.send.return_value = None
    wsgid.send_sock = socket


    headers = [('Header', 'Value'), ('X-Other-Header', 'Other-Value')]
    body = "Hello World\n"
    wsgid._reply(self.message, '200 OK', headers=headers, body=body)
    m2msg = socket.send.call_args[0][0]
    resp = "%s 2:42, HTTP/1.1 200 OK\r\n\
Header: Value\r\n\
X-Other-Header: Other-Value\r\n\
\r\n\
Hello World\n" % (self.sample_uuid, )
    self.assertEquals(resp, m2msg)

class WsgidContentLengthTest(unittest.TestCase):
  def setUp(self):
    self.sample_uuid = 'bb3ce668-4528-11e0-94e3-001fe149503a'
    self.sample_conn_id = '42'
    self.message = Message('%s %s / 22:{"VERSION":"HTTP/1.0"},0:,' % (self.sample_uuid, self.sample_conn_id))
  def test_content_length(self):
    def app(env, start):
        start("200 OK", [])
        return ["Hello"]

    wsgid = Wsgid(app)
    socket = Mock()
    socket.send.return_value = None
    wsgid.send_sock = socket
    with patch.object(wsgid, "_reply") as reply, \
          patch.object(wsgid, "_create_wsgi_environ") :
        wsgid._call_wsgi_app(self.message)
        headers = reply.call_args_list[0][0][2]
        self.assertEquals(headers, [('Content-Length', '5'), ('X-Wsgid', __version__),  ('Date', ANY) ])
  def test_no_cotent_length(self):
    def app(env, start):
        start("200 OK", [])
        return ["Hello", "There"]
    wsgid = Wsgid(app)
    socket = Mock()
    socket.send.return_value = None
    wsgid.send_sock = socket
    with patch.object(wsgid, "_reply") as reply, \
          patch.object(wsgid, "_create_wsgi_environ") :
        wsgid._call_wsgi_app(self.message)
        headers = reply.call_args_list[0][0][2]

        self.assertEquals(headers, [('X-Wsgid', __version__), ('Date', ANY)])


class AlmostAlwaysTrue(object):

    def __init__(self, total_iterations=1):
        self.total_iterations = total_iterations
        self.current_iteration = 0

    def __call__(self):
        if self.current_iteration < self.total_iterations:
            self.current_iteration += 1
            return bool(1)
        return bool(0)


class WsgidRequestFiltersTest(unittest.TestCase):

    def setUp(self):
        self.sample_headers = {
            'METHOD': 'GET',
            'VERSION': 'HTTP/1.0', #prevent chunking
            'PATTERN': '/root',
            'URI': '/more/path/',
            'PATH': '/more/path',
            'QUERY': 'a=1&b=4&d=4',
            'host': 'localhost',
            'content-length': '42',
            'content-type': 'text/plain',
            'x-forwarded-for': '127.0.0.1'
            }
        body = "Some body"
        headers_str = simplejson.dumps(self.sample_headers)
        self.raw_msg = "SID CID /path {len}:{h}:{lenb}:{b}".format(len=len(headers_str), h=headers_str, lenb=len(body), b=body)
        plugnplay.man.iface_implementors = {}
        conf.settings = namedtuple('object', 'mongrel2_chroot')
        self.start_response_mock = namedtuple('object', ['headers_sent', 'status', 'headers'], verbose=False)

    '''
     This also tests if the modified environ is passed to the WSGI app
    '''
    def test_call_pre_request_filter(self):
        class SimpleFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                environ['X-Added-Header'] = 'Value'

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)):

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            expected_environ = self.sample_headers
            expected_environ.update({'X-Added-Header': 'Value'})
            assert [call(expected_environ, ANY)] == app_mock.call_args_list

    def test_filter_raises_exception_but_app_still_called(self):
        class SimpleExceptionFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                raise Exception()

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)):

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            assert [call(self.sample_headers, ANY)] == app_mock.call_args_list

    def test_call_other_filters_if_one_raises_exception(self):
        class SimpleExceptionFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                raise Exception()

        class SimpleFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                environ['X-New'] = 'Other Value'

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)):

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            expected_environ = self.sample_headers
            expected_environ.update({'X-New': 'Other Value'})
            assert [call(expected_environ, ANY)] == app_mock.call_args_list

    def test_log_filter_exception(self):
        exception = Exception()
        class SimpleExceptionFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                raise exception

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)), \
                patch('wsgid.core.log') as mock_log:

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert [call(exception)] == mock_log.exception.call_args_list

    def test_pass_wsgi_environ_through_pre_request_filters(self):
        class AFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, messaage, environ):
                environ['X-A'] = 'Header A'

        class BFilter(Plugin):
            implements = [IPreRequestFilter, ]

            def process(self, message, environ):
                environ['X-B'] = 'Header B'

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)):

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            expected_environ = self.sample_headers
            expected_environ.update({'X-A': 'Header A', 'X-B': 'Header B'})
            assert [call(expected_environ, ANY)] == app_mock.call_args_list

    def test_call_post_request_filter(self):
        class PostRequestFilter(Plugin):
            implements = [IPostRequestFilter, ]

            def process(self, message, status, headers, write, finish):
                return ('200 OK from filter', headers + [('X-Post-Header', 'Value')], write, finish)

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        app_mock.return_value = ('Line1', 'Line2')  # Response body lines
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)), \
                patch.object(wsgid, '_reply') as reply_mock:

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            headers =  [('X-Wsgid', __version__), ('Date',ANY), ('X-Post-Header', 'Value')]
            self.assertEqual( [call(ANY, '200 OK from filter', headers, 'Line1'),
                              call(ANY, None, None, 'Line2'), ANY],
                         reply_mock.call_args_list)

    def test_call_post_request_exception(self):

        filter_mock = Mock()
        plugnplay.man.iface_implementors[IPostRequestFilter] = [filter_mock]

        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock(side_effect=Exception())
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)), \
                patch.object(wsgid, '_reply'):

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == filter_mock.exception.call_count

    def test_pass_app_response_through_post_request_filters(self):
        class APostRequestFilter(Plugin):
            implements = [IPostRequestFilter, ]

            def process(self, message, status, headers, write, finish):
                def new_finish():
                    return finish() + 'FA'
                return (status, headers, write, new_finish)

        class BPostRequestFilter(Plugin):
            implements = [IPostRequestFilter, ]

            def process(self, message, status, headers, write, finish):
                def new_finish():
                    return finish()  + 'FB'
                return (status, headers, write, new_finish)


        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        app_mock.return_value = ('Line1', 'Line2')  # Response body lines
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)), \
                patch.object(wsgid, '_reply') as reply_mock:

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            self.assertEquals( [call(ANY, '', [('X-Wsgid', __version__), ('Date', ANY)], 'Line1'),
                                call(ANY, None, None, 'Line2'),
                                call(ANY, None, None, 'FAFB'), ANY], reply_mock.call_args_list)

    def test_ensure_a_broken_post_request_filter_does_not_crash_a_sucessful_request(self):
        class APostRequestFilter(Plugin):
            implements = [IPostRequestFilter, ]

            def process(self, message, status, headers, write,finish):
                def new_finish():
                    return finish() + 'FA'
                return (status, headers,write,new_finish)

        class BPostRequestFilter(Plugin):
            implements = [IPostRequestFilter, ]

            def process(self, message, status, headers, write,finish):
                def new_finish():
                    return finish()  + 'FB'
                # Here we return a wrong tuple. wsgid must be able not to crash
                # the request because of this
                return (headers,write,new_finish)


        sock_mock = Mock()
        sock_mock.recv.return_value = self.raw_msg

        app_mock = Mock()
        app_mock.return_value = ('Line1', 'Line2')  # Response body lines
        wsgid = Wsgid(app=app_mock)
        with patch.object(wsgid, '_create_wsgi_environ') as environ_mock, \
                patch.object(wsgid, '_setup_zmq_endpoints', Mock(return_value=(sock_mock, sock_mock))), \
                patch.object(wsgid, '_should_serve', AlmostAlwaysTrue(1)), \
                patch.object(wsgid, '_reply') as reply_mock:

            environ_mock.return_value = self.sample_headers.copy()
            wsgid.serve()
            assert 1 == app_mock.call_count
            self.assertEqual( [call(ANY, '', [('X-Wsgid', __version__), ('Date', ANY)], 'Line1'),
                               call(ANY, None, None, 'Line2'),
                               call(ANY, None, None, 'FA'), ANY] , reply_mock.call_args_list)
