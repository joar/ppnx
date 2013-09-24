import logging
import random
import os
import sys
import traceback
import imp
import importlib

from functools import wraps

import hy
import hy.importer

import pyinotify

from xudd.lib.tcp import Client
from xudd.lib.irc import IRCClient
from xudd.hive import Hive
from xudd.actor import Actor

_log = logging.getLogger(__name__)

class Context(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class IRCBot(Actor):
    def __init__(self, hive, id,
                 administrator_nicknames=None,
                 autojoin_channels=None,
                 module_directory=None,
                 **kw):
        super(IRCBot, self).__init__(hive, id)

        self.nick = kw.get('nick', 'ppnx')
        self.realname = kw.get('realname', 'xudd IRC bot')
        self.user = kw.get('user', 'ppnx')
        self.password = kw.get('password')

        self.message_routing.update({
            'handle_login': self.handle_login,
            'handle_line': self.handle_line,
            'reload_module': self.reload_module,
            'on_authenticated': self.on_authenticated,
        })

        self.modules = {}
        self.module_directory = module_directory

        self.load_modules()

        self.administrator_nicknames = []

        if administrator_nicknames is not None:
            for nickname in administrator_nicknames.split(','):
                self.administrator_nicknames.append(nickname)

        self.autojoin_channels = []

        if autojoin_channels is not None:
            for channel in autojoin_channels.split(','):
                if not channel[0] == '#':
                    channel = '#{0}'.format(channel)

                self.autojoin_channels.append(channel)

        self.watcher_id = None

    def reload_module(self, message):
        # TODO:
        # 01:32:30 < paultag> it might also break when you have something
        # ref'ing the existing object
        #
        # Also, try not having threads in the mix, use
        # https://github.com/seb-m/pyinotify
        path = message.body.get('path')
        name, ext = os.path.splitext(os.path.basename(path))

        try:
            if name in self.modules:
                _log.info('reloading {0}'.format(name))
            else:
                _log.info('importing {0}'.format(name))

            self.import_module(name, path)
        except Exception as exc:
            _log.critical('Error while (re)loading: {0}'.format(
                traceback.format_exc()
            ))

    def on_authenticated(self, message):
        _log.debug('on_authenticated')

    def import_module(self, name, path):
        module = hy.importer.import_file_to_module(
            self.namespace_module(name),
            path)

        self.modules.update({
            name: module
        })

        return module

    def namespace_module(self, module_name):
        return 'ppnx_modules.{0}'.format(
            module_name)

    def load_modules(self):
        if self.module_directory is None:
            _log.error('No module directory, will not load modules.')
            return

        for f in os.listdir(self.module_directory):
            name, ext = os.path.splitext(f)
            if not ext == '.hy':
                continue

            path = os.path.join(
                self.module_directory,
                str(f))

            mod = self.import_module(name, path)

            if not hasattr(mod, 'trigger'):
                self.modules.pop(name)
                _log.error('{0} does not have a \'trigger\' method'.format(
                    name
                ))

            _log.info('Loaded {0}'.format(name))

    def handle_line(self, message):
        if not self.watcher_id:
            if True:  # NOT disabled
                self.watcher_id = self.hive.create_actor(
                    ModuleChangeWatcher,
                    id='watcher')
                self.send_message(
                    self.watcher_id,
                    'watch',
                    body={'path': self.module_directory}
                )

        command = message.body['command']
        params = message.body['params']
        prefix = message.body['prefix']

        in_channel = params.middle and params.middle[0] == '#'
        is_admin = prefix.nick in self.administrator_nicknames

        context = Context(
            command=command,
            params=params,
            prefix=prefix,
            is_admin=is_admin,
            in_channel=in_channel)

        for name, module in self.modules.items():
            try:
                if module.trigger(context):
                    result = module.act(context)

                    # Simply send the result as a message to the sender/channel
                    if isinstance(result, (str, bytes)):
                        line = 'PRIVMSG {0} :{1}'.format(
                            params.middle if in_channel else prefix.nick,
                            result)
                    # Assemble the line from a tuple
                    elif isinstance(result, (tuple, list)):
                        line = ' '.join(result)

                    message.reply(body={
                        'line': line
                    })
            except Exception as exc:
                _log.critical(traceback.format_exc())

    def handle_login(self, message):
        _log.info('Logging in')
        lines = [
            'USER {user} {hostname} {servername} :{realname}'.format(
                        user=self.user,
                        hostname='*',
                        servername='*',
                        realname=self.realname
            ),
            'NICK {nick}'.format(nick=self.nick)
        ]

        message.reply(
            directive='reply',
            body={
                'lines': lines
            })


def filter_filetype(func):
    @wraps(func)
    def wrapper(self, event, *args, **kw):
        path = event.pathname
        name, ext = os.path.splitext(os.path.basename(path))
        ext_short = ext[1:] if len(ext) else None
        included_exts = ['hy']

        if not ext_short in included_exts:
            _log.debug('{0} not in {1} ({2})'.format(
                ext_short,
                included_exts,
                path))
            return

        return func(self, event, path, *args, **kw)

    return wrapper


class ModuleChangeWatcher(Actor, pyinotify.ProcessEvent):
    def __init__(self, hive, id):
        super(ModuleChangeWatcher, self).__init__(hive, id)
        self.message_routing = {
            'watch': self.watch,
        }
        self.watching_for = None
        self.path = None
        self.observer = None

    @filter_filetype
    def process_IN_CREATE(self, event, path):
        _log.info('New module: {0}'.format(path))

        self.send_message(
            self.watching_for,
            'reload_module',
            body={
                'path': path
            }
        )

    @filter_filetype
    def process_IN_MODIFY(self, event, path):
        _log.debug('Modified: {0}'.format(path))

        self.send_message(
            self.watching_for,
            'reload_module',
            body={
                'path': path
            }
        )

    def watch(self, message):
        self.watching_for = message.from_id
        self.watch_manager = pyinotify.WatchManager()
        watch_mask = \
                pyinotify.IN_DELETE | pyinotify.IN_CREATE | pyinotify.IN_MODIFY
        self.path = message.body['path']

        self.watch_manager.add_watch(self.path, watch_mask, rec=True)

        notifier = pyinotify.Notifier(self.watch_manager, self, timeout=10)

        _log.info(u'Watching on behalf of {0} for changes in {1}'.format(
            self.watching_for,
            self.path))

        while True:
            if notifier._timeout is  None:
                raise AssertionError('Notifier must have a timeout')

            notifier.process_events()

            while notifier.check_events():
                _log.debug('Additional events found')
                notifier.read_events()
                notifier.process_events()

            yield self.wait_on_self()

def connect():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)08s %(threadName)s %(name)s: %(message)s')

    hive = Hive()

    hive.create_actor(
        IRCBot, id='bot',
        module_directory=os.path.join(
            os.path.dirname(__file__),
            '..',
            'modules'),
        administrator_nicknames='joar,paroneayea')
    irc_id = hive.create_actor(IRCClient, id='irc', message_handler='bot')
    client_id = hive.create_actor(Client, id='tcp_client',
                                  chunk_handler=irc_id)

    hive.send_message(
        to='tcp_client',
        directive='connect',
        body={'host': 'irc.freenode.net', 'port': 6667})


    hive.run()

if __name__ == '__main__':
    connect()
