import os
import sys

try:
    import simplejson as json
except ImportError:
    import json

from wsgid.loaders.default import IAppLoader
from wsgid.core import Plugin, log
import wsgid.conf


class DjangoAppLoader(Plugin):
    implements = [IAppLoader]

    def _not_hidden_folder(self, name):
        return not name.startswith('.')

    def _valid_dirs(self, app_path):
        return sorted(filter(self._not_hidden_folder, os.listdir(app_path)))

    def _first_djangoproject_dir(self, app_path):
        dirs = self._valid_dirs(app_path)
        log.debug("{0} Possible valid djangoapp folders: {1}".format(len(dirs), dirs))
        for d in dirs:
            settings_path = os.path.join(app_path, d, 'settings.py')
            init_path = os.path.join(app_path, d, '__init__.py')
            if os.path.exists(settings_path) and os.path.exists(init_path):
                return d
        return None

    def can_load(self, app_path):
        return wsgid.conf.settings.django or self._first_djangoproject_dir(app_path) is not None

    def _load_django_extra_options(self, path):
        parsed = {}
        conf_file = os.path.join(path, 'django.json')
        log.debug("Reading {0}".format(conf_file))
        if os.path.exists(conf_file):
            try:
                parsed = json.load(open(conf_file))
            except:
                log.exception("Error parsing {file}".format(file=conf_file))
        return parsed

    def load_app(self, app_path, app_full_name=None):
        logger = log
        # Since we receive here --app-path + app/, we need to remove the last part
        # because django.json lives in --app-path
        wsgidapp_path = os.path.dirname(app_path)

        extra = self._load_django_extra_options(wsgidapp_path)

        site_name = self._first_djangoproject_dir(app_path)
        os.environ['DJANGO_SETTINGS_MODULE'] = '{0}.settings'.format(site_name)
        logger.debug("Using DJANGO_SETTINGS_MODULE = {0}".format(os.environ['DJANGO_SETTINGS_MODULE']))

        new_syspath = os.path.join(app_path, site_name)

        logger.debug("Adding {0} to sys.path".format(app_path))
        sys.path.append(app_path)
        logger.debug("Adding {0} to sys.path".format(new_syspath))
        sys.path.append(new_syspath)

        try:
            from django.conf import settings
        except ImportError:
            log.exception('Failed to import Django project settings')

        # Here we force django to load the app settings
        settings._some_value = True
        # Clean up
        del settings._some_value

        for k, v in list(extra.items()):
            setting_value = None
            if hasattr(settings, k):
                setting_value = getattr(settings, k)

            if isinstance(v, dict) and setting_value and isinstance(setting_value, dict):
                for k2, v2 in list(v.items()):
                    getattr(settings, k)[k2] = v2
            elif isinstance(v, list) and setting_value and isinstance(setting_value, list):
                setting_value += v
            elif isinstance(v, list) and setting_value and isinstance(setting_value, tuple):
                #Since we cannot modify the original tuple, we must re-create it
                setattr(settings, k, setting_value + tuple(v))
            else:
                setattr(settings, k, v)

        import django.core.handlers.wsgi
        return django.core.handlers.wsgi.WSGIHandler()

    def _is_all_instance(self, instance_of, *args):
        '''
        Check if isinstance(args[0], instance_of) returns True for *all*
        members of *args
        '''
        for a in args:
            if not isinstance(a, instance_of):
                return False
        return True
