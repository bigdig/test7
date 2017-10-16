'''machine learning utility functions and classes'''
import datetime
import os
import sys
import typing
import pdb

import configuration


class Logger(object):
    # ref: stack overflow: how do i duplicat sys stdout to a log file in python
    def __init__(self, logfile_path=None, logfile_mode='w', base_name=None):
        def path(s):
            return directory('log') + s + '-' + datetime.datetime.now().isoformat('T') + '.log'
        self.terminal = sys.stdout
        if os.name == 'posix':
            clean_path = logfile_path.replace(':', '-') if base_name is None else path(base_name)
        else:
            clean_path = logfile_path
        self.log = open(clean_path, logfile_mode)

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        pass

    
def main(
        argv: typing.List[str],
        program: str,
        unittest,
        do_work,
        out_log='out_log',
):
    config = configuration.make(
        program=program,
        argv=argv[1:],
        )
    print('started %s with configuration' % program)
    print(str(config))
    # echo print statement to the log file
    sys.stdout = Logger(config.get(out_log))
    print(str(config))
    if config.get('debug', False):
        # enter pdb if run-time error
        # (useful during development)
        import debug
        if False:
            debug.info
    unittest(config)
    do_work(config)


if False:
    # usage example
    sys.stdout = Logger('path/to/log/file')
    pdb
    # now print statements write on both stdout and the log file
