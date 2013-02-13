WSGID Internals
===============


Plugin system
:::::::::::::

wsgid internal plugin system is implemented by plugnplay. This means that all plugins must inherit one same base class, in this case this class is *wsgid.core.Plugin*.

For now, wsgid only declares custom AppLoaders. But any other interface declared in the future will have to be implemented subclassing *wsgid.core.Plugin*.

.. versionadded:: 0.7.0

Wsgid has support for request filters. This way you can inject code in the HTTP request flow. Read more at :ref:`requestfilters`.

.. _commands-implementation:

WSGID commands internal implementation
::::::::::::::::::::::::::::::::::::::

.. versionadded:: 0.3.0

Now wsgid ships with custom commands and you can implement new ones if you need. Again, this capability is implemented through plugnplay. 

To create a new command you just have to implement the :py:class:`wsgid.core.command.ICommand` interface. This interface have 4 methods:

 * `def command_name(self):`
   This method returns the name of your new command. This is the name showed on the help screen, if you command adds any extra option to wsgid CLI.

 * `def name_matches(self, name):`
   This method is used when wsgid is trying to find the right implementation for a command. The `name` parameter is the command name that wsgid is searching. Usually this is the first parameter that was just passed to wsgid CLI.
 
 * `def run(self, options, command_name = None):`
   This is your implementation's main method. The `options` parameter is a special object containing all options passed to wsgid CLI and you can access these options by the name, eg: `options.debug` or `options.app_path`.
   The optional parameter ``command_name`` is useful when you have the same implementation for two different commands, eg: The same python class is used to implement thw commands ``stop`` and ``restart``.
 
 * `def extra_options(sefl):`
   This is where you return the extra options that you want to add. You must return an array of :py:class:`wsgid.core.parser.CommandLineOption`.

Note that when wsgid finds an implementation for a command, it exits just after the run() method returns.

.. _wsgidapp-object:

WsgidApp Object
:::::::::::::::

.. versionadded:: 0.4.0

The `wsgid.core.WsgidApp` object is an abstraction around the wsgidapp folder on disk. With this object you don't need to know what is the internal structure 
of a wsgid app folder.

To instantiate a WsgidApp object, just pass the fullpath of your wsgidapp, eg: ::

    from wsgid.core import WsgidApp

    app = WsgidApp(fullpath)

and then you can get information about your wsgid app, eg: ::

    app.is_valid()
    app.master_pids()

For now we have these method implemented:

 * `def is_valid():` 
    Returns True if the path conforms with the right internal structure (see :doc:`appstructure`).
 * `def master_pids():`
    Returns the pid number of all master processes, as a list of integers
 * `def worker_pids():`
    Returns the pid number of all worker processes, as a list of integers

