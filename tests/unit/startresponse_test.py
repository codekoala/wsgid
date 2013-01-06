#encoding: utf-8


import unittest
from wsgid.core import StartResponse, StartResponseCalledTwice, Wsgid
from wsgid.core.message import Message
from wsgid import __version__
from mock import patch, Mock, call, ANY

class StartResponseTest(unittest.TestCase):



  def setUp(self):
    self.wsgid = Wsgid()
    self.socket = Mock()
    self.socket.send.return_value = None
    self.wsgid.send_sock = self.socket
    message = Message('1 2 / 22:{"VERSION":"HTTP/1.0"},0:,')
    self.start_response = StartResponse(message, self.wsgid)


  def test_start_response_app_return_iterable(self):
    headers = [('Header', 'Value'), ('Other-Header', 'More-Value')]
    self.start_response('200 OK', headers)
    self.assertEquals(headers, self.start_response.headers)
    self.assertEquals('200 OK', self.start_response.status)

  # start_response no longer accumulates the body
  #def test_acumulate_body_data(self):
  #  write_fn = self.start_response('200 OK', [])
  #  write_fn('First Line\n')
  #  write_fn('Second One\n')
  #  self.assertEquals('First Line\nSecond One\n', self.start_response.body)

  '''
   Ensure that it's possible to change the status/headers values if the write callable
   was called yet
  '''
  def test_change_status_value(self):
    self.start_response('200 OK', [('Header', 'Value')])
    self.assertEquals('200 OK', self.start_response.status)
    self.assertEquals([('Header', 'Value')], self.start_response.headers)
    import sys
    self.start_response('500 Internal Server Error', [('More-Header', 'Other-Value')], sys.exc_info())
    self.assertEquals('500 Internal Server Error', self.start_response.status)
    self.assertEquals([('More-Header', 'Other-Value')], self.start_response.headers)

  '''
   start_response should re-raise the exception raise by the app
  '''
  def test_call_start_response_after_called_write(self):
    write_fn = self.start_response('200 OK', [])
    write_fn('Body\n') # Response sent to client
    try:
      raise Exception()
    except:
      import sys
      exec_info = sys.exc_info()
      self.assertRaises(exec_info[0], self.start_response, '500 Server Error', [], exec_info)

  def test_call_start_response_twice_without_exec_info(self):
    self.start_response('200 OK', [])
    self.assertRaises(StartResponseCalledTwice, self.start_response, '500 OK', [])


  def test_should_close(self):
    message = Message('1 2 / 22:{"VERSION":"HTTP/1.0"},0:,')
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, True)

    headers = '{"VERSION":"HTTP/1.0", "connection":"close"}'
    message = Message('1 2 / %d:%s,0:,' %(len(headers),headers))
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, True)

    headers = '{"VERSION":"HTTP/1.0", "connection":"keep-alive"}'
    message = Message('1 2 / %d:%s,0:,' %(len(headers),headers))
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, False)

    message = Message('1 2 / 22:{"VERSION":"HTTP/1.1"},0:,')
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, False)

    headers = '{"VERSION":"HTTP/1.1", "connection":"close"}'
    message = Message('1 2 / %d:%s,0:,' %(len(headers),headers))
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, True)

    headers = '{"VERSION":"HTTP/1.1", "connection":"keep-alive"}'
    message = Message('1 2 / %d:%s,0:,' %(len(headers),headers))
    start_response = StartResponse(message, self.wsgid)
    self.assertEquals(start_response.should_close, False)

  def test_finalize_headers(self):
    headers = []
    message = Message('1 2 / 22:{"VERSION":"HTTP/1.0"},0:,')
    start_response = StartResponse(message, self.wsgid)
    write_fn = start_response("200 OK", headers)        
    start_response._finalize_headers()
    headers = start_response.headers[:]
    expected_headers = [('X-Wsgid', __version__), ('Date', ANY)]
    self.assertEquals(headers, expected_headers)
    self.assertEquals(start_response.chunked, False)
    self.assertEquals(start_response.should_close, True)

    headers = []
    headers_str = '{"VERSION":"HTTP/1.0","te":"chunked"}'
    message = Message('1 2 / %d:%s,0:,' %(len(headers_str),headers_str))
    start_response = StartResponse(message, self.wsgid)
    write_fn = start_response("200 OK", headers)        
    start_response._finalize_headers()
    headers = start_response.headers[:]
    expected_headers = [('X-Wsgid', __version__),('Date', ANY), ('Transfer-Encoding','chunked')]
    self.assertEquals(headers, expected_headers)
    self.assertEquals(start_response.chunked, True)
    self.assertEquals(start_response.should_close, True)

    headers = []
    message = Message('1 2 / 22:{"VERSION":"HTTP/1.1"},0:,')
    start_response = StartResponse(message, self.wsgid)
    write_fn = start_response("200 OK", headers)        
    start_response._finalize_headers()
    headers = start_response.headers[:]
    expected_headers = [('X-Wsgid', __version__),('Date', ANY), ('Transfer-Encoding','chunked')]
    self.assertEquals(headers, expected_headers)
    self.assertEquals(start_response.chunked, True)
    self.assertEquals(start_response.should_close, False)

    headers = [('content-length','42')]
    message = Message('1 2 / 22:{"VERSION":"HTTP/1.1"},0:,')
    start_response = StartResponse(message, self.wsgid)
    write_fn = start_response("200 OK", headers)        
    start_response._finalize_headers()
    headers = start_response.headers[:]
    expected_headers = [('content-length','42'), ('X-Wsgid', __version__), ('Date', ANY)]
    self.assertEquals(headers, expected_headers)
    self.assertEquals(start_response.chunked, False)
    self.assertEquals(start_response.should_close, False)
    
    

