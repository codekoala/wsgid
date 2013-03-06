#encoding: utf8

import os


class FakeOptions(object):
    def __init__(self, **kwargs):
        for k, v in list(kwargs.items()):
            setattr(self, k, v)


def fullpath(path):
    '''
    Returns the full absolute path
    of the path received.

    Useful when you want to know the full
    path of the current file, eg:

    full_path(__file__)
    '''
    return os.path.dirname(os.path.abspath(os.path.expanduser(path)))
