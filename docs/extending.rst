
Extending Wsgid
***************

App Loaders
-----------

App loaders are classes that knows how to load an specific WSGI app. WSGID comes with some apploaders for some frameworks, for now django (http://djangoproject.com) and pyroutes (http://pyroutes.com).

As an app for each of this frameworks has a known structure, wsgid will try to discover the *best loader* for your app. The loaders are used in alphabetical order by the loader filename.

.. _app-loader:

Writing your App Loader
^^^^^^^^^^^^^^^^^^^^^^^

Writing your own AppLoader is very easy and simple. As said before every plugin must inherit *wsgid.core.Plugin* class, so it's not different with the AppLoaders.

To inform wsgid that your Plugin class implements the AppLoader interface (:py:class:`wsgid.loaders.IAppLoader`) you have to add one attribute to your class.::

  implements = [IAppLoader]

This is plugnplay specific, to know more about plugnplay go to: https://github.com/daltonmatos/plugnplay

Now, you need to fill the methods declared for the interface you are implementing, in this case are only two methods.

 * def can_load(self, app_path)
 * def load_app(self, app_path, app_full_name)

The first should return True/False if your loader, looking at the app_path directory, finds out that is can load this application. The second should return the WSGI application object for this app that is being loaded.

Now just save your loader into a .py file and pass --loader-dir=PATH_TO_LOADER to wsgid command line and your loader will be used to load your application. Feel free to write loader for other WSGI frameworks, see the :doc:`contributing` for more details.


.. _requestfilters:

Request Filters
---------------

.. versionadded:: 0.7.0

Request filters are extension points that Wsgid provides so you have an opportunity to inject custom code inside the flow of a Request. Currently you have two filters available: ``IPreRequestFilter`` and ``IPostRequestFilter``.

All Wsgid extension points are implemented through plugnplay (https://github.com/daltonmatos/plugnplay) project. To activate your custom filter, just drop your ``.py`` file inside your wsgidapp ``plugins/`` folder and restart your Wsgid process.


IPreRequestFilter
^^^^^^^^^^^^^^^^^

Invoked right before wsgid call to the running WSGI application. Since this call occurs after the mongrel2 message was parsed, this filter receives a copy of this message (``wsgid.core.Message``). Additionally it receives a copy of the WSGI environ that will be passes to the running application.

You can modify the WSGI environ freely. ::


    def IPreRequestFilter(plugnplay.Interface):

        def process(self, m2message, environ):
            pass


IPostRequestFilter
^^^^^^^^^^^^^^^^^^

Invoked after the WSGI application has returned its response. Receives also a copy of the raw mongrel2 message and additionally receives all values returned by the WSGI application. The HTTP status line, the headers (returned as a list of tuples, eg: ``[(<header-name>, <header-value>), ...]``) and the generated response body.

This filter should always return a tuple: (status, headers, body). Even if you don't modify any value you must return them. This tuple will be expanded and will be passed to the next filter in the running chain.

If the WSGI application raises any Exception, the ``exception()`` method will be called receiving the raw mongrel2 message and a the raised Exception. ::


    def IPostRequestFilter(plugnplay.Interface):

        def process(self, m2message, status, headers, body):
            pass

        def exception(self, m2message, e):
            pass
