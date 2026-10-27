# Keep the board fan (fan_generic pcb_fan, PA5, cools the TMC2209 drivers) on
# while the printer is busy, from a reactor timer (issue #17)
#
# This was a delayed_gcode. Those run through Klipper's G-code mutex, so a
# long macro such as bed leveling kept the fan from being switched on. A
# reactor timer runs whatever the G-code queue is doing.
#
# Copyright (C) 2026  ad5x-open contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.

class PCBFanWatch:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.fan_name = config.get('fan', 'pcb_fan')
        self.heater_names = config.getlist('heater',
                                           ('extruder', 'heater_bed'))
        self.idle_limit = config.getfloat('idle_timeout', 30., minval=0.)
        self.poll = config.getfloat('poll', 1., above=0.)
        self.printer.load_object(config, 'stepper_enable')
        self.printer.load_object(config, 'heaters')
        self.printer.register_event_handler("klippy:connect",
                                            self.handle_connect)
        self.printer.register_event_handler("klippy:ready",
                                            self.handle_ready)
        self.fan = self.stepper_enable = self.idle_obj = None
        self.heaters = []
        self.idle_start = None
    def handle_connect(self):
        # fan_generic wraps the real fan (fan.Fan) in .fan; set_speed and
        # get_status live on that inner object.
        self.fan = self.printer.lookup_object('fan_generic ' + self.fan_name).fan
        self.stepper_enable = self.printer.lookup_object('stepper_enable')
        self.idle_obj = self.printer.lookup_object('idle_timeout')
        pheaters = self.printer.lookup_object('heaters')
        self.heaters = [pheaters.lookup_heater(n) for n in self.heater_names]
    def handle_ready(self):
        self.reactor.register_timer(self.callback,
                                    self.reactor.monotonic() + self.poll)
    def is_busy(self, eventtime):
        se = self.stepper_enable
        motors = any(se.lookup_enable(n).is_motor_enabled()
                     for n in se.get_steppers())
        heat = any(h.get_temp(eventtime)[1] > 0 for h in self.heaters)
        printing = self.idle_obj.get_status(eventtime)['state'] == "Printing"
        return motors or heat or printing
    def callback(self, eventtime):
        if self.printer.is_shutdown():
            return self.reactor.NEVER
        speed = self.fan.get_status(eventtime)['speed']
        if self.is_busy(eventtime):
            self.idle_start = None
            if speed < 1.0:
                self.fan.set_speed(1.0)
        elif speed > 0.:
            if self.idle_start is None:
                self.idle_start = eventtime
            elif eventtime - self.idle_start >= self.idle_limit:
                self.idle_start = None
                self.fan.set_speed(0.)
        else:
            self.idle_start = None
        return eventtime + self.poll

def load_config(config):
    return PCBFanWatch(config)
