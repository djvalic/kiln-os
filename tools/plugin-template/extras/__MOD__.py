# __NAME__: Klipper part. __MACRO___GREET [NAME=] prints the greeting;
# printer.__MOD__ has greeting and count.
#
# This file may be distributed under the terms of the GNU GPLv3 license.


class __CLASS__:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.greeting = config.get('greeting', 'Hello')
        self.count = 0
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('__MACRO___GREET', self.cmd_GREET,
                               desc="Print the __NAME__ greeting")

    def cmd_GREET(self, gcmd):
        self.count += 1
        gcmd.respond_info("%s, %s!" % (self.greeting,
                                       gcmd.get('NAME', 'world')))

    def get_status(self, eventtime):
        return {'greeting': self.greeting, 'count': self.count}


def load_config(config):
    return __CLASS__(config)
