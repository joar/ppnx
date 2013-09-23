import logging
import random
import os
import sys
import traceback
import imp
import importlib

import hy
import hy.importer

# Watchdog is installed from git at the moment because of
# https://github.com/gorakhargosh/watchdog/issues/125
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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
        })

        self.modules = []
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

        name = self.namespace_module(str(name))

        if any(name == i.__name__ for i in self.modules):
            del sys.modules[name]
            _log.info('reloading {0}'.format(name))
            self.modules.append(self.import_module(name, path))
        else:
            _log.info('importing {0}'.format(name))
            self.modules.append(self.import_module(name, path))

    def import_module(self, name, path):
        return hy.importer.import_file_to_module(
            name,
            path)

    def namespace_module(self, module_name):
        return '{0}.modules.{1}'.format(
            __name__,
            module_name)

    def load_modules(self):
        if self.module_directory is None:
            _log.error('No module directory, will not load modules.')
            return

        for f in os.listdir(self.module_directory):
            name, ext = os.path.splitext(f)
            if not ext == '.hy':
                continue

            name = self.namespace_module(name)
            path = os.path.join(
                self.module_directory,
                str(f))

            mod = self.import_module(name, path)

            if hasattr(mod, 'trigger'):
                self.modules.append(mod)
                _log.info('Loaded {0}'.format(name))
            else:
                _log.error('{0} does not have a \'trigger\' method'.format(
                    name
                ))

    def handle_line(self, message):
        if not self.watcher_id:
            if True:  # NOT disabled
                self.watcher_id = self.hive.create_actor(ModuleChangeWatcher)
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

        for module in self.modules:
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

class ModuleChangeWatcher(Actor, FileSystemEventHandler):
    def __init__(self, hive, id):
        super(ModuleChangeWatcher, self).__init__(hive, id)
        self.message_routing = {
            'watch': self.watch,
        }
        self.watching_for = None
        self.path = None
        self.observer = None

    def on_created(self, event):
        name, ext = os.path.splitext(os.path.basename(event.src_path))
        if not ext == b'.hy':
            return

        _log.info('New module: {0}'.format(event.src_path))

        self.send_message(
            self.watching_for,
            'reload_module',
            body={
                'path': event.src_path
            }
        )

    def on_modified(self, event):
        name, ext = os.path.splitext(os.path.basename(event.src_path))
        if not ext == b'.hy':
            return

        _log.debug('Modified: {0}'.format(event.src_path))

        self.send_message(
            self.watching_for,
            'reload_module',
            body={
                'path': event.src_path
            }
        )

    def watch(self, message):
        self.watching_for = message.from_id
        self.path = message.body['path']

        self.observer = Observer()
        self.observer.schedule(self, path=self.path, recursive=True)
        self.observer.start()

        _log.info(u'Watching on behalf of {0} for changes in {1}'.format(
            self.watching_for,
            self.path))

def connect():
    logging.basicConfig(level=logging.DEBUG)

    hive = Hive()

    hive.create_actor(
        IRCBot, id='bot',
        module_directory=os.path.join(
            os.path.dirname(__file__),
            '..',
            'modules'))
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
