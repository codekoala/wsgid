#encoding: utf-8

__all__ = ['StartResponse', 'StartResponseCalledTwice', 'Plugin', 'run_command', 'get_main_logger', 'validate_input_params', 'Wsgid']

import sys
import logging
import plugnplay
from command import ICommand
import parser
import re
import os
from wsgid import __version__
from wsgid import conf
from cStringIO import StringIO
import urllib
from message import Message
import zmq
from glob import glob


Plugin = plugnplay.Plugin


class StartResponse(object):

    def __init__(self):
        self.headers = []
        self.status = ''
        self.body = ''
        self.called = False
        self.body_written = False

    def __call__(self, status, response_headers, exec_info=None):
        if self.called and not exec_info:
            raise StartResponseCalledTwice()

        if exec_info and self.body_written:
            try:
                raise exec_info[0], exec_info[1], exec_info[2]
            finally:
                exec_info = None  # Avoid circular reference (PEP-333)

        self.headers = response_headers
        self.status = status

        self.called = True
        return self._write

    def _write(self, body):
        self.body_written = True
        self.body += body


class StartResponseCalledTwice(Exception):
    pass


log = logging.getLogger('wsgid')


def get_main_logger():
    return log


def set_main_logger(logger):
    log = logger


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
        self.log = get_main_logger()

    def serve(self):
        '''
        Start serving requests.
        '''
        recv_sock = self.ctx.socket(zmq.PULL)
        recv_sock.connect(self.recv)
        self.log.debug("Using PULL socket %s" % self.recv)

        send_sock = self.ctx.socket(zmq.PUB)
        send_sock.connect(self.send)
        self.log.debug("Using PUB socket %s" % self.send)

        self.log.info("All set, ready to serve requests...")
        while True:
            m2message = Message(recv_sock.recv())

            if m2message.is_disconnect():
                self.log.debug("Disconnect message received, id=%s" % m2message.client_id)
                continue

            if m2message.is_upload_start():
                self.log.debug("Starting async upload, file will be at: {0}".format(m2message.async_upload_path))
                continue

            # Call the app and send the response back to mongrel2
            self._call_wsgi_app(m2message, send_sock)

    def _call_wsgi_app(self, m2message, send_sock):
        environ = self._create_wsgi_environ(m2message.headers, m2message.body)
        upload_path = conf.settings.mongrel2_chroot or '/'

        if m2message.is_upload_done():
            self.log.debug("Async upload done, reading from {0}".format(m2message.async_upload_path))
            parts = m2message.async_upload_path.split('/')
            upload_path = os.path.join(upload_path, *parts)
            environ['wsgi.input'] = open(upload_path)

        start_response = StartResponse()

        server_id = m2message.server_id
        client_id = m2message.client_id
        response = None
        try:
            body = ''
            response = self.app(environ, start_response)

            if start_response.body_written:
                body = start_response.body
            else:
                for data in response:
                    body += data

            status = start_response.status
            headers = start_response.headers
            send_sock.send(str(self._reply(server_id, client_id, status, headers, body)))
        except Exception, e:
            # Internal Server Error
            send_sock.send(self._reply(server_id, client_id, '500 Internal Server Error', headers=[]))
            self.log.exception(e)
        finally:
            if hasattr(response, 'close'):
                response.close()
            if m2message.is_upload_done():
                self._remove_tmp_file(upload_path)

    def _remove_tmp_file(self, filepath):
        try:
            os.unlink(filepath)
        except OSError, o:
            self.log.exception(o)

    def _reply(self, uuid, conn_id, status, headers=[], body=''):
        '''
        Constructs a mongrel2 response message based on the
        WSGI app response values.
        @uuid, @conn_id comes from Wsgid itself
        @headers, @body comes from the executed application

        @body is the raw content of the response and not [body]
        as returned by the WSGI app
        @headers is a list of tuples
        '''
        RAW_HTTP = "HTTP/1.1 %(status)s\r\n%(headers)s\r\n%(body)s"
        msg = "%s %d:%s, " % (uuid, len(conn_id), conn_id)
        params = {'status': status, 'body': body}

        headers += [('Content-Length', len(body))]
        raw_headers = ""
        for h, v in headers:
            if not h.lower() == x_wsgid_header_name:
                raw_headers += "%s: %s\r\n" % (h, v)

        params['headers'] = raw_headers + X_WSGID_HEADER
        return msg + RAW_HTTP % params

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
        self._set(environ, 'wsgi.url_scheme', "http")

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
        self._set(environ, 'PATH_INFO', urllib.unquote(path_info))

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
        for (header, value) in json_headers.iteritems():
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
