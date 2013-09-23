import logging
import random
import os
import hy
import hy.importer
import traceback

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
                 nick='ppnx',
                 realname='xudd IRC Bot',
                 user='ppnx',
                 password=None):
        super(IRCBot, self).__init__(hive, id)

        self.nick = nick
        self.realname = realname
        self.user = user
        self.password = password

        self.message_routing.update({
            'handle_login': self.handle_login,
            'handle_line': self.handle_line,
        })
        self.modules = []
        self.module_directory = 'modules'

        self.load_modules()

    def load_modules(self):
        for f in os.listdir(self.module_directory):
            name, ext = os.path.splitext(f)
            self.modules.append(
                hy.importer.import_file_to_module(
                    '.'.join(['ppnx.modules', name]),
                    os.path.join(
                        self.module_directory,
                        f)))

    def handle_line(self, message):
        command = message.body['command']
        params = message.body['params']
        prefix = message.body['prefix']

        context = Context(
            command=command,
            params=params,
            prefix=prefix)

        in_channel = params.middle and params.middle[0] == '#'

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
        msg = 'USER {user} {hostname} {servername} :{realname}'.format(
                        user=self.user,
                        hostname='*',
                        servername='*',
                        realname=self.realname
                    )
        msg += '\r\n'
        msg += 'NICK {nick}'.format(nick=self.nick)

        message.reply(
            directive='reply',
            body={
                'line': msg
            })


def connect():
    logging.basicConfig(level=logging.DEBUG)

    hive = Hive()

    hive.create_actor(IRCBot, id='bot')
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
