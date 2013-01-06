#encoding: utf-8

import unittest
from wsgid.core import Wsgid
from wsgid.test import FakeOptions
import wsgid.conf
import urllib2
import time
import logging
logging.basicConfig(level=logging.DEBUG)
import multiprocessing
logger = multiprocessing.log_to_stderr()
logger.setLevel(multiprocessing.SUBDEBUG)

class WsgidServeTest(unittest.TestCase):

    def setUp(self):
        wsgid.conf.settings = FakeOptions(mongrel2_chroot=None)

    def test_app_return_body(self):
        def app(environ, start_response):
            start_response('200 OK', [('Some-Header', 'Some-Value')])
            return ['Body content']
        pid = self._run_wsgid(app)
        try:
            r = urllib2.urlopen('http://127.0.0.1:8888/py/abc/')
            body = r.read()
            self.assertEquals(body, 'Body content')
        finally:
            self._kill_wsgid(pid)

    def test_app_return_body_with_more_than_one_item(self):
        '''
        Ensure that when the WSGI app returns ['Line1', 'Line2', ...]
        Wsgid joins all parts to build the complete body
        '''
        def app(env, start_response):
            start_response('200 OK', [])
            return ['More Lines\n', 'And more...\n']
        pid = self._run_wsgid(app)
        try:
            r = urllib2.urlopen('http://127.0.0.1:8888/py/abc/')
            self.assertEquals('More Lines\nAnd more...\n', r.read())
        finally:
            self._kill_wsgid(pid)

    def test_app_use_write_callable(self):
        def app(env, start_response):
            write = start_response('200 OK', [])
            write('One Line\n')
            write('Two Lines\n')
            return None
        pid = self._run_wsgid(app)
        try:
            r = urllib2.urlopen('http://127.0.0.1:8888/py/abc/')
            self.assertEquals('One Line\nTwo Lines\n', r.read())
        finally:
            self._kill_wsgid(pid)

    def test_app_return_an_iterable(self):
        '''
            Instead of returnin a list, a app can return an object that is iterable
        '''
        def app(environ, start_response):
            class Body(object):
                def __init__(self, parts):
                    self.parts = parts

                def __iter__(self):
                    for a in self.parts:
                        yield a

            start_response('200 OK', [])
            return Body(['Line One\n', 'Line Two\n'])

        pid = self._run_wsgid(app)
        try:
            r = urllib2.urlopen('http://127.0.0.1:8888/py/abc/')
            self.assertEquals('Line One\nLine Two\n', r.read())
        finally:
            self._kill_wsgid(pid)

    def test_app_receives_a_post_request(self):
        '''
        A Simple POST that do not use mongrel2's async upload
        '''
        def app(environ, start_response):
            start_response('200 OK', [])
            if environ['REQUEST_METHOD'] == 'POST':
                return [environ['wsgi.input'].read()]

        pid = self._run_wsgid(app)
        try:
            r = urllib2.urlopen('http://127.0.0.1:8888/py/post', data='Some post data')
            self.assertEquals('Some post data', r.read())
        finally:
            self._kill_wsgid(pid)

    def _run_wsgid(self, app):
        def _serve(app):
            import multiprocessing
            w = Wsgid(app,
                'tcp://127.0.0.1:8889',
                'tcp://127.0.0.1:8890')
            w.log = multiprocessing.get_logger()
            w.log.setLevel(logging.DEBUG)
            w.serve()
        import multiprocessing
        p = multiprocessing.Process(target=_serve, args=(app,))

        p.start()
        time.sleep(1)
        return p.pid

    def _kill_wsgid(self, pid):
        import os
        os.kill(pid, 15)
