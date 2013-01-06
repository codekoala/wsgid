import plugnplay


class IPreRequestFilter(plugnplay.Interface):

    '''
     Receives the already parsed mongrel2 message object (wsgid.core.Message)
     and the WSGI environ
    '''
    def process(self, m2Message, environ):
        pass


class IPostRequestFilter(plugnplay.Interface):

    '''
     Should always return a tuple of the form: (status, headers, write, finish)
     even if it does not modify any of the values
    '''
    def process(self, m2message, status, write, finish):
        pass

    def exception(self, m2message, exception):
        pass
