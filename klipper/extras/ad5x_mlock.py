# Klippy's memory kept in RAM (docs/memory.md)
#
# Once per klippy process, at the first config read: mlockall(MCL_CURRENT |
# MCL_FUTURE | MCL_ONFAULT). Each page klippy touches then stays resident:
# the kernel neither swaps it to zram (the 256 MiB board) nor drops it from
# the page cache (libpython, the C helper), so page reclaim can't stall
# klippy mid-print. MCL_ONFAULT locks pages as they are touched, so the
# lock costs no more RAM than klippy already uses.
# The kernel counts a locked mapping's whole size against RLIMIT_MEMLOCK,
# and with MCL_FUTURE a mapping past it fails (malloc then fails):
# S61klipper raises the limit to unlimited for klippy. With any lower
# limit only the current mappings are locked (MCL_CURRENT | MCL_ONFAULT,
# no MCL_FUTURE), so a later allocation never fails because of the lock.
# A lock refused (EPERM, ENOMEM: limit below klippy's size) is logged and
# klippy runs on unlocked. The lock stays across RESTART and
# FIRMWARE_RESTART (same process). Processes klippy starts (fork, exec,
# multiprocessing) are not locked: the kernel doesn't pass the lock on.
# /data/ad5x/klipper-mlock.disable: no lock (at klippy's next start).
# Not in batch mode (klippy -o, the laptop tests).
# Loaded by ad5x_log (no config section, so a Klipper package without this
# file still reads ad5x.cfg).
# printer.ad5x_mlock: locked (bool), flags ("current,future,onfault"),
#   limit (RLIMIT_MEMLOCK in bytes, null: unlimited), error (null or text)
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import ctypes
import errno
import logging
import os
import resource

# The same values on MIPS (arch/mips/include/uapi/asm/mman.h) as in
# asm-generic
MCL_CURRENT = 1
MCL_FUTURE = 2
MCL_ONFAULT = 4
DISABLE_FILE = "/data/ad5x/klipper-mlock.disable"

# Per process (the module stays imported across RESTART): None until tried
RESULT = None


def flag_names(flags):
    return ",".join(n for b, n in ((MCL_CURRENT, "current"),
                                   (MCL_FUTURE, "future"),
                                   (MCL_ONFAULT, "onfault")) if flags & b)


def _libc():
    return ctypes.CDLL(None, use_errno=True)


def lock(libc=None, disable_file=None):
    """mlockall() for this process; returns the result dict"""
    if disable_file is None:
        disable_file = DISABLE_FILE
    try:
        limit = resource.getrlimit(resource.RLIMIT_MEMLOCK)[0]
    except (OSError, ValueError):
        limit = 0
    res = {'locked': False, 'flags': "",
           'limit': None if limit == resource.RLIM_INFINITY else limit,
           'error': None}
    if os.path.exists(disable_file):
        res['error'] = "off (%s)" % (disable_file,)
        return res
    flags = MCL_CURRENT | MCL_ONFAULT
    if limit == resource.RLIM_INFINITY:
        flags |= MCL_FUTURE
    res['flags'] = flag_names(flags)
    try:
        if libc is None:
            libc = _libc()
        ret = libc.mlockall(flags)
        err = ctypes.get_errno() if ret != 0 else 0
    except Exception as e:
        res['error'] = "mlockall unavailable: %s" % (e,)
        return res
    if ret == 0:
        res['locked'] = True
    else:
        res['error'] = "%s (%s)" % (errno.errorcode.get(err, str(err)),
                                    os.strerror(err))
    return res


def describe(res):
    if res['locked']:
        lim = ("unlimited" if res['limit'] is None
               else "%d KiB" % (res['limit'] // 1024,))
        return "memory locked (%s; RLIMIT_MEMLOCK %s)" % (res['flags'], lim)
    return "memory not locked: %s" % (res['error'],)


class MemoryLock:
    def __init__(self, config):
        global RESULT
        printer = config.get_printer()
        again = RESULT is not None
        if not again:
            if printer.get_start_args().get('debugoutput') is not None:
                RESULT = {'locked': False, 'flags': "", 'limit': None,
                          'error': "batch mode"}
            else:
                RESULT = lock()
        self.result = dict(RESULT)
        logging.info("ad5x_mlock: %s%s", describe(self.result),
                     " (since klippy started)" if again else "")

    def get_status(self, eventtime):
        return dict(self.result)


def load_config(config):
    return MemoryLock(config)
