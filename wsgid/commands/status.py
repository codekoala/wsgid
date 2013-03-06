

from wsgid.core.command import ICommand
from wsgid.core import Plugin
from wsgid.core import WsgidApp
import sys
import os


class CommandStatus(Plugin):

    implements = [ICommand]

    def command_name(self):
        return 'status'

    def name_matches(self, name):
        return name == 'status'

    def run(self, options, **kwargs):
        app = WsgidApp(options.app_path)
        status = {True: 'Running', False: 'Stopped'}
        sys.stdout.write("Status: {status}\n".format(status=status[self._any_running(app.worker_pids())]))
        sys.stdout.write("Master pid(s): {pids}\n".format(pids=", ".join([str(p) for p in app.master_pids()])))
        sys.stdout.write("Worker pid(s): {pids}\n".format(pids=", ".join([self._prepare_pid(p) for p in app.worker_pids()])))

    def _any_running(self, pids):
        '''
        Return True if at least one of the passed pids is running
        '''
        return len(list(filter(self._pid_exists, pids))) > 0

    def _pid_exists(self, pid):
        '''
        True id the given pid is running, False otherwise
        '''
        try:
            os.kill(pid, 0)
            return True
        except:
            return False

    def _prepare_pid(self, pid):
        '''
        Prepare a "status string" for this pid
        '''
        if self._pid_exists(pid):
            return str(pid)
        else:
            return "{0}(dead)".format(pid)

    def extra_options(self):
        return []
