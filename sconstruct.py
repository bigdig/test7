# invocations:
#   scons -f sconstruct.py /
#   scons -n -f sconstruct.py /
#   scons --debug=explain -f sconstruct.py /
#   scons -j <nprocesses> -f sconstruct.py /

# where / means to build everything (not just stuff in the current working directory .)
import os
import pdb
import pprint

import seven.build
pp = pprint.pprint
pdb

dir_home = os.path.join('C:', r'\Users', 'roylo')
dir_dropbox = os.path.join(dir_home, 'Dropbox')
dir_working = os.path.join(dir_dropbox, 'data', '7chord', '7chord-01', 'working')
dir_midpredictor_data = os.path.join(dir_dropbox, 'MidPredictor', 'data')

env = Environment(
    ENV=os.environ,
)

env.Decider('MD5-timestamp')  # if timestamp out of date, examine MD5 checksum


def command(*args):
    make_paths = args[0]
    other_args = args[1:]
    scons = seven.build.make_scons(make_paths(*other_args))
    env.Command(
        scons['targets'],
        scons['sources'],
        scons['commands'],
    )


# main program
tickers = ['ORCL']
# all dates in November 2016
# weekends: 5, 6, 12, 13, 19, 20, 26, 27
# thanksgiving: 24
dates_selected = 'nov 2016'
dates_selected = 'kristina 170528'
if dates_selected == 'nov 2016':
    dates = [ 
        '%d-%02d-%02d' % (2016, 11, day + 1)
        for day in xrange(30)  # 30 days in November
    ]
else:
    # all dates for 68389XAS4
    days_in_month = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    years = (2013, 2014, 2015, 2016, 2017)
    dates = []
    for year in years:
        # see cusips-ORCL for the range of trade dates for cusip 68389XAS4
        if year == 2013:
            months = (7, 8, 9, 10, 11, 12)
        elif year == 2017:
            months = (1, 2, 3)
        else:
            months = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
        for month in months:
            for day in xrange(days_in_month[month]):
                dates.append('%d-%02d-%02d' % (year, month, day + 1))

for ticker in tickers:
    command(seven.build.cusips, ticker)
    for cusip in ['68389XAS4']:  # just one cusip, for now
        for hpset in ['grid3']:
            for effective_date in dates:
                command(seven.build.fit_predict, ticker, cusip, hpset, effective_date)
            command(seven.build.report03_compare_models, ticker, cusip, hpset)

