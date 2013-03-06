#encoding: utf-8

__all__ = ['StartResponse', 'StartResponseCalledTwice', 'Plugin',
           'run_command', 'validate_input_params', 'Wsgid']

from glob import glob
from io import StringIO
import logging
import os
import re
import sys

try:
    from urllib import unquote
except ImportError:
    from urllib.parse import unquote

import plugnplay
import zmq

from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time

from wsgid import conf, __version__
from wsgid.core import parser
from wsgid.core.command import ICommand
from wsgid.core.message import Message
from wsgid.interfaces.filters import IPreRequestFilter, IPostRequestFilter

Plugin = plugnplay.Plugin
log = logging.getLogger('wsgid')


if sys.version_info >= (3, 0, 0):
    def _raise(*exc_info):
        raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])
else:
    # wish I knew of a cleaner way to not product a SyntaxError in Python 3
    eval(compile('def _raise(*exc): raise exc[0], exc[1], exc[2]'))


class StartResponse(object):

    def __init__(self, message, server):
        self.headers = []
        self.status = ''
        self.called = False
        self.headers_sent = False
        self.message = message
        self.server = server

        # this may go away once the environ is built
        self.version = message.headers['VERSION']
        self._filtered_finish = self._finish
        self._filtered_write = self._reply
        self.chunked = False

        _c = message.headers.get('connection', '').lower()
        if self.version == 'HTTP/1.1':
            self.should_close = (_c == 'close')
        else:
            self.should_close = (_c != 'keep-alive')

        server.log.debug("Should close: %s", self.should_close)

    def __call__(self, status, response_headers, exc_info=None):
        if self.called and not exc_info:
            raise StartResponseCalledTwice()

        if exc_info and self.headers_sent:
            try:
                _raise(exc_info[0], exc_info[1], exc_info[2])
            finally:
                exc_info = None  # Avoid circular reference (PEP-333)

        self.headers = response_headers
        self.status = status

        self.called = True
        return self.write

    @property
    def log(self):
        global log
        return log

    @property
    def has_content_length(self):
        #content-length generally at the end, so search backwards
        return 'content-length' in (header[0].lower() for header in reversed(self.headers))

    @property
    def supports_chunked(self):
        if self.version == 'HTTP/1.1':
            return True
        if 'te' in self.message.headers:
            te = self.message.headers['te']
            return ('chunked' in (v.strip().lower() for v in te.split(',')))
        return False

    def finish(self):
        if not self.headers_sent:
            self._finalize_headers()
        trailer = self._filtered_finish()
        if trailer:
            self._reply_internal(trailer)

        if self.chunked or not self.headers_sent:
            self._reply_internal("")


        if self.should_close:
            self.close()

    def close(self):
        self.chunked = False
        self._reply_internal("")

    def write(self, body):
        if not self.headers_sent:
            self._finalize_headers()
        return self._filtered_write(body)

    def _finalize_headers(self):
        header_set = frozenset(header.lower() for (header,value) in self.headers)

        if x_wsgid_header_name not in header_set:
            self.headers.append((X_WSGID_HEADER_NAME, __version__))
        if 'date' not in header_set:
            self.headers.append(("Date", format_date_time(mktime(datetime.now().timetuple())) ))
        if 'content-length' not in header_set:
            if self.supports_chunked:
                if 'transfer-encoding' not in header_set:
                    self.chunked = True
                    self.headers.append(("Transfer-Encoding", "chunked"))
            else:
                self.should_close = True

        if 'connection' not in header_set:
            if self.version == 'HTTP/1.1':
                if self.should_close:
                    self.headers.append(('Connection','close'))
            else:
                if not self.should_close:
                    self.headers.append(('Connection','Keep-Alive'))
        else:
            #should set should_close to the value of 'connection' in headers
            pass


        self._run_post_filters(IPostRequestFilter.implementors())

    def _finish(self):
        return ""

    def _reply(self, body):
        if body is None:
            return None
        else:
            return self._reply_internal(body)

    def _reply_internal(self, body):
        '''
        Constructs a mongrel2 response message
        '''
        if self.chunked:
            body = "%s\r\n%s\r\n" % (hex(len(body))[2:], body)

        if not self.headers_sent:
            self.headers_sent = True
            return self.server._reply(self.message, self.status, self.headers, body)
        return self.server._reply(self.message, None, None, body)

    def error(self, status):
        if not self.headers_sent:
            self(status,[],True)
            self.write("")
        self.close()

    '''
     Run post request filters
     This method is separated because the post request filter should return a value that will
     be passed to the next filter in the execution chain
    '''
    def _run_post_filters(self, filters):
        self.log.debug("Calling PostRequest filters...")
        status, headers, write, finish = self.status, self.headers, self._reply, self._finish
        for f in filters:
            try:
                self.log.debug("Calling {0} filter".format(f.__class__.__name__))
                status, headers, write, finish = f.process(self.message, status, headers, write, finish)
            except Exception as e:
                from wsgid.core import log
                log.exception(e)
        self.status = status
        self.headers = headers
        self._filtered_write = write
        self._filtered_finish = finish

class StartResponseCalledTwice(Exception):
    pass


def run_command():
    '''
    Extract the first command line argument (if it exists)
    and tries to find a ICommand implementor for it.
    If found, run it. If not does nothing.
    '''
    command_implementors = ICommand.implementors()
    if command_implementors and len(sys.argv) > 1:
        cname = sys.argv[1]  # get the command name
        for command in command_implementors:
            if command.name_matches(cname):
                # Remove the command name, since it's not defined
                # in the parser options
                sys.argv.remove(cname)
                command.run(parser.parse_options(use_config=False), command_name=cname)
                return True
    return False


ZMQ_SOCKET_SPEC = re.compile("(?P<proto>inproc|ipc|tcp|pgm|epgm)://(?P<address>.*)$")
TCP_SOCKET_SPEC = re.compile("(?P<adress>.*):(?P<port>[0-9]+)")


def _is_valid_socket(sockspec):
    generic_match = ZMQ_SOCKET_SPEC.match(sockspec)
    if generic_match:
        proto = generic_match.group('proto')
        if proto == "tcp":
            return TCP_SOCKET_SPEC.match(generic_match.group('address'))
        else:
            return True
    return False


def validate_input_params(app_path=None, recv=None, send=None):
    if app_path and not os.path.exists(app_path):
        raise Exception("path {0} does not exist.\n".format(app_path))
    if not recv or not _is_valid_socket(recv):
        raise Exception("Recv socket is mandatory, value received: {0}\n".format(recv))
    if not send or not _is_valid_socket(send):
        raise Exception("Send socker is mandatory, value received: {0}\n".format(send))


X_WSGID_HEADER_NAME = 'X-Wsgid'
x_wsgid_header_name = X_WSGID_HEADER_NAME.lower()
X_WSGID_HEADER = '{header}: {version}\r\n'.format(header=X_WSGID_HEADER_NAME, version=__version__)


class Wsgid(object):

    def __init__(self, app=None, recv=None, send=None):
        self.app = app
        self.recv = recv
        self.send = send

        self.ctx = zmq.Context()
        self.log = log

    def _setup_zmq_endpoints(self):
        recv_sock = self.ctx.socket(zmq.PULL)
        recv_sock.connect(self.recv)
        self.log.debug("Using PULL socket %s" % self.recv)

        send_sock = self.ctx.socket(zmq.PUB)
        send_sock.connect(self.send)
        self.log.debug("Using PUB socket %s" % self.send)
        return (send_sock, recv_sock)

    def serve(self):
        '''
        Start serving requests.
        '''
        self.log.debug("Setting up ZMQ endpoints")
        send_sock, recv_sock = self._setup_zmq_endpoints()
        self.send_sock = send_sock
        self.log.info("All set, ready to serve requests...")
        while self._should_serve():
            self.log.debug("Serving requests...")
            m2message = Message(recv_sock.recv())
            self.log.debug("Request arrived... headers={0}".format(m2message.headers))

            if m2message.is_disconnect():
                self.log.debug("Disconnect message received, id=%s" % m2message.client_id)
                continue

            if m2message.is_upload_start():
                self.log.debug("Starting async upload, file will be at: {0}".format(m2message.async_upload_path))
                continue

            # Call the app and send the response back to mongrel2
            self._call_wsgi_app(m2message)

    '''
     This method exists just to me mocked in the tests.
     It is simply too unpredictable to mock the True object
    '''
    def _should_serve(self):
        return True

    def _call_wsgi_app(self, m2message):
        start_response = StartResponse(m2message, self)
        environ = self._create_wsgi_environ(m2message.headers, m2message.body)
        upload_path = conf.settings.mongrel2_chroot or '/'

        if m2message.is_upload_done():
            self.log.debug("Async upload done, reading from {0}".format(m2message.async_upload_path))
            parts = m2message.async_upload_path.split('/')
            upload_path = os.path.join(upload_path, *parts)
            environ['wsgi.input'] = open(upload_path)

        response = None
        try:
            body = ''
            self.log.debug("Calling PreRequest filters...")
            self._run_simple_filters(IPreRequestFilter.implementors(), self._filter_process_callback, m2message, environ)

            self.log.debug("Waiting for the WSGI app to return...")
            response = self.app(environ, start_response)
            self.log.debug("WSGI app finished running... status={0}, headers={1}".format(start_response.status, start_response.headers))

            if response is None:
                return start_response.finish()

            if (not start_response.headers_sent and not start_response.has_content_length):
                #try to guess content-length. Works if the result from the app is [body]
                try:
                    n = len(response)
                except TypeError:
                    pass
                else:
                    if n == 1:
                        data = next(iter(response))
                        start_response.headers.append(('Content-Length', str(len(data))))
                        start_response.write(data)
                        return start_response.finish()
            for data in response:
                start_response.write(data)
            return start_response.finish()

        except Exception as e:
            # Internal Server Error
            self._run_simple_filters(IPostRequestFilter.implementors(),
                                     self._filter_exception_callback,
                                     m2message, e)
            start_response.error('500 Internal Server Error')
            self.log.exception("Internal server error")
        finally:
            if hasattr(response, 'close'):
                response.close()
            if m2message.is_upload_done():
                self._remove_tmp_file(upload_path)

    def _filter_exception_callback(self, f, *args):
        f.exception(*args)

    def _filter_process_callback(self, f, *args):
        return f.process(*args)

    '''
     Run pre request filters
    '''
    def _run_simple_filters(self, filters, callback, m2message, *filter_args):
        for f in filters:
            try:
                self.log.debug("Calling {0} filter".format(f.__class__.__name__))
                callback(f, m2message, *filter_args)
            except Exception as e:
                from wsgid.core import log
                log.exception(e)

    def _remove_tmp_file(self, filepath):
        try:
            os.unlink(filepath)
        except OSError:
            self.log.exception("Error removing tmp file")

    def _reply(self, message,  status, headers, body):
        conn_id = message.client_id
        uuid = message.server_id

        body_list = [uuid, " ", str(len(conn_id)), ":", conn_id, ", "]
        if status:
            body_list.append("HTTP/1.1 ")
            body_list.append(status)
            body_list.append("\r\n")
        if headers:
            body_list.extend( ("%s: %s\r\n" % items for items in headers ) )
            body_list.append("\r\n")
        body_list.append(body)
        self.log.debug("Returning to mongrel2")
        data = "".join(body_list)
        self.log.debug("Data: (%d) %s", len(data), data)
        try:
            self.send_sock.send(data, flags = zmq.NOBLOCK )
        except zmq.EAGAIN:
            #eat or propogate?
            log.warn("Discarding response to {} due to full send queue".format((uuid,)))
            return False
        return True

    def _create_wsgi_environ(self, json_headers, body=None):
        '''
        Creates a complete WSGI environ from the JSON encoded headers
        reveived from mongrel2.
        @json_headers should be an already parsed JSON string
        '''
        environ = {}
        #Not needed
        json_headers.pop('URI', None)

        #First, some fixed values
        environ['wsgi.multithread'] = False
        environ['wsgi.multiprocess'] = True
        environ['wsgi.run_once'] = True
        environ['wsgi.errors'] = sys.stderr
        environ['wsgi.version'] = (1, 0)
        self._set(environ, 'wsgi.url_scheme', json_headers.get('URL_SCHEME', "http"))

        if body:
            environ['wsgi.input'] = StringIO(body)
        else:
            environ['wsgi.input'] = StringIO('')

        self._set(environ, 'REQUEST_METHOD', json_headers.pop('METHOD'))
        self._set(environ, 'SERVER_PROTOCOL', json_headers.pop('VERSION'))
        self._set(environ, 'SCRIPT_NAME', json_headers.pop('PATTERN').rstrip('/'))
        self._set(environ, 'QUERY_STRING', json_headers.pop('QUERY', ""))

        script_name = environ['SCRIPT_NAME']
        path_info = json_headers.pop('PATH')[len(script_name):]
        self._set(environ, 'PATH_INFO', unquote(path_info))

        server_port = '80'
        host_header = json_headers.pop('host')
        if ':' in host_header:
            server_name, server_port = host_header.split(':')
        else:
            server_name = host_header

        self._set(environ, 'HTTP_HOST', host_header)
        self._set(environ, 'SERVER_PORT', server_port)
        self._set(environ, 'SERVER_NAME', server_name)

        self._set(environ, 'REMOTE_ADDR', json_headers['x-forwarded-for'])

        self._set(environ, 'CONTENT_TYPE', json_headers.pop('content-type', ''))
        environ['content-type'] = environ['CONTENT_TYPE']

        self._set(environ, 'CONTENT_LENGTH', json_headers.pop('content-length', ''))
        environ['content-length'] = environ['CONTENT_LENGTH']

        #Pass the other headers
        for (header, value) in json_headers.items():
            if header[0] in ('X', 'x'):
                environ[header] = str(value)
            else:
                # Change HTTP_ headers to CGI-like formatting
                header = header.upper()
                environ['HTTP_%s' % header] = str(value)

        return environ

    def _set(self, environ, key, value):
        '''
        Sets a value in the environ object
        '''
        environ[key] = str(value)


class WsgidApp(object):

    REGEX_PIDFILE = re.compile("[0-9]+\.pid")

    def __init__(self, fullpath):
        self.fullpath = fullpath

    def is_valid(self):
        return os.path.exists(os.path.join(self.fullpath, 'app')) \
            and os.path.exists(os.path.join(self.fullpath, 'logs')) \
            and os.path.exists(os.path.join(self.fullpath, 'plugins')) \
            and os.path.exists(os.path.join(self.fullpath, 'pid')) \
            and os.path.exists(os.path.join(self.fullpath, 'pid/master')) \
            and os.path.exists(os.path.join(self.fullpath, 'pid/worker'))

    def master_pids(self):
        return sorted(self._get_pids(self.fullpath, 'pid/master/'))

    def worker_pids(self):
        return sorted(self._get_pids(self.fullpath, 'pid/worker/'))

    @property
    def pluginsdir(self):
        return os.path.join(self.fullpath, 'plugins')

    def _get_pids(self, base_path, pids_path):
        final_path = os.path.join(base_path, pids_path, '*.pid')
        pid_files = glob(final_path)
        pids = [int(os.path.basename(pid_file).split('.')[0]) for pid_file in pid_files if self._is_pidfile(pid_file)]
        return pids

    def _is_pidfile(self, filename):
        return self.REGEX_PIDFILE.match(os.path.basename(filename))
