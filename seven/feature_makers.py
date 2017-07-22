'''class to create features from the input files

Rules for FeatureMakers
1. Each FeatureMaker is a class associated with one input file
2. Calling its update method with an input record returns a dictionary of features. The dictionary
   has as keys strings, which are the feature names, and floating point values, the values
   of the features.
3. The feature names from each feature maker must be unique across all feature makers.
4. Any string can be a feature name. However, features names ending in "_size" are transformed
   if the model_spec.transform_x value is True.
5. If a feature name begins with "id_", its not actually a feature name that is put into the
   models. Its just an identifier.
6. If a feature name begins with "p_", its a feature for the print (the trade).
7. If a feature name begins with "otr1", its a feature name for the closest on-the-run bond.

Copyright 2017 Roy E. Lowrance, roy.lowrance@gmail.com

You may not use this file except in compliance with a license.
'''
from __future__ import division

from abc import ABCMeta, abstractmethod
import collections
import datetime
import math
import pandas as pd
import pdb
from pprint import pprint
import unittest

# imports from seven/
# import Fundamentals
import OrderImbalance4
import read_csv


def make_effectivedatetime(df, effectivedate_column='effectivedate', effectivetime_column='effectivetime'):
    '''create new column that combines the effectivedate and effective time

    example:
    df['effectivedatetime'] = make_effectivedatetime(df)
    '''
    values = []
    for the_date, the_time in zip(df[effectivedate_column], df[effectivetime_column]):
        values.append(datetime.datetime(
            the_date.year,
            the_date.month,
            the_date.day,
            the_time.hour,
            the_time.minute,
            the_time.second,
        ))
    return pd.Series(values, index=df.index)


class FeatureMaker(object):
    __metaclass__ = ABCMeta

    def __init__(self, name=None):
        print 'constructing FeatureMaker', name
        self.name = name  # used in error message; informal name of the feature maker

    @abstractmethod
    def make_features(trace_index, trace_record, extra):
        'return (dict, None) or (None, err) or (None, errs)'
        # type:
        #  trace_index: identifier from the trace print file (an integer)
        #  trace_record: pd.Series
        #  extra: dict[value_name:str, value:obj] (extra info to derive features)
        # where
        #  dict:Dict[feature_name:str, feature_value:float]
        #  err:Str
        #  errs:List[Str]
        # The prefix of each feature_name str has info used in fitting and predicting:
        #  'id_{suffix}' is simply identifying information
        #  '{prefix}_size' a feature value that is non-negative (so that log1p() make sense)
        #  '{other}'  is a feature value, possibly negative, never NaN
        pass


class Etf(FeatureMaker):
    def __init__(self, df=None, name=None):
        'construct'
        # name is "weight {security_kind} {etf_name}"
        assert df is not None
        assert name is not None
        super(Etf, self).__init__('etf ' + name)  # sets self.name
        table = collections.defaultdict(dict)
        for index, row in df.iterrows():
            timestamp, cusip = index
            date = timestamp.date()
            weight = row['weight_of_cusip_pct']
            assert 0 <= weight <= 100.0
            table[date][cusip] = weight
        df.table = table
        self.security_kind, self.security_id, self.etf_name = name.split(' ')[1:]
        self.second_index_name = None  # overridden by subclass

    def make_features(self, trace_index, trace_record):
        'return (None, err) or (DataFrame, None)'
        date = trace_record['effectivedate']
        second_index_value = trace_record[self.second_index_name]
        pdb.set_trace()
        if date not in self.table:
            return None, 'date %d not in input file for %s' % (date, self.name)
        table_date = self.table[date]
        if second_index_value not in table_date:
            return None, 'security id %s not in input file %s for date %s' % (second_index_value, self.name, date)
        weight = table_date[second_index_value]
        features = {
            'p_weight_etf_pct_%s_%s_size' % (self.security_kind, self.etf_name): weight,
        }
        return features, None


class EtfCusip(Etf):
    def __init__(self, df=None, name=None):
        print 'construction FeatureMakerEtfCusip'
        super(EtfCusip, self). __init__(df=df, name=name)
        self.second_index_name = 'cusip'


class EtfCusipTest(unittest.TestCase):
    def test(self):
        return  # for now, unstub when testing the EFT feature makers
        Test = collections.namedtuple('Test', 'logical_name cusip date, expected_featurename, expected_weight')
        tests = (
            Test('weight cusip agg', '00184AAG0', datetime.date(2010, 1, 29), 'p_weight_etf_pct_cusip_agg_size', 0.152722039314371),
        )
        for test in tests:
            fm = EtfCusip(
                df=read_csv.input(issuer=None, logical_name=test.logical_name),
                name=test.logical_name,
            )
            trace_record = {
                'effectivedate': test.date,
                'cusip': test.cusip
            }
            features, err = fm.make_features(0, trace_record)
            self.assertIsNone(err)
            self.assertEqual(1, len(features))
            for k, v in features.iteritems():
                self.assertEqual(test.expected_featurename, k)
                self.assertAlmostEqual(test.expected_weight, v)


class Fundamentals(FeatureMaker):
    def __init__(self, issuer):
        super(Fundamentals, self).__init__('Fundamentals(issuer=%s)' % issuer)
        self.issuer = issuer
        self.file_logical_names = (  # feature names are the same as the logical names
            'expected_interest_coverage',
            'gross_leverage',
            'LTM_EBITDA',
            'mkt_cap',
            'mkt_gross_leverage',
            'reported_interest_coverage',
            'total_assets',
            'total_debt',
        )
        # create Dict[content_name: str, Dict[datetime.date, content_value:float]]
        self.data = self._read_files()
        return

    def _read_file(self, logical_name):
        'return the contents of the CSV file as a pd.DataFrame'
        df = read_csv.input(issuer=self.issuer, logical_name=logical_name)
        if len(df) == 0:
            print 'df has zero length', logical_name
            pdb.set_trace()
        result = {}
        for timestamp, row in df.iterrows():
            result[timestamp.date()] = row[0]
        return result

    def _read_files(self):
        'return Dict[datetime.date, Dict[content_name:str, content_value:float]]'
        result = {}
        for logical_name in self.file_logical_names:
            result[logical_name] = self._read_file(logical_name)
        return result

    def _get(self, date, logical_name):
            'return (value on or just before the specified date, None) or (None, err)'
            # a logical name and feature name are the same thing for this function
            data = self.data[logical_name]
            for sorted_date in sorted(data.keys(), reverse=True):
                if date >= sorted_date:
                    result = data[sorted_date]
                    return (result, None)
            return (
                None,
                'date %s not in fundamentals for issuer %s content %s' % (
                    date,
                    self.issuer,
                    logical_name))

    def make_features(self, trace_index, trace_record, extra):
        'return Dict[feature_name, feature_value], errs'
        def check_no_negatives(d):
            for k, v in d.iteritems():
                assert v >= 0.0

        date = trace_record['effectivedate'].date()

        # build basic features directly from the fundamentals file data
        result = {}
        errors = []
        for feature_name in self.file_logical_names:
            value, err = self._get(date, feature_name)
            if err is not None:
                errors.append(err)
            else:
                result['%s_size' % feature_name] = value

        # add in derived features, which for now are ratios of the basic features
        # all of the basic features are in the result dict

        def maybe_add_ratio(feature_name, numerator_name, denominator_name):
            numerator = result[numerator_name]
            denominator = result[denominator_name]
            if denominator is 0:
                errors.append('feature %s had zero denominator' % feature_name)
            value = numerator * 1.0 / denominator
            if value != value:
                errors.append('feature %s was NaN' % feature_name)
            else:
                result[feature_name] = value

        maybe_add_ratio('debt_to_market_cap_size', 'total_debt_size', 'mkt_cap_size')
        maybe_add_ratio('debt_to_ltm_ebitda_size', 'total_debt_size', 'LTM_EBITDA_size')
        if len(errors) is not None:
            return (None, errors)

        check_no_negatives(result)
        if len(errors) == 0:
            return (result, None)
        else:
            return (None, errors)


class InterarrivalTime(FeatureMaker):
    def __init__(self):
        super(InterarrivalTime, self).__init__('InterarrivalTime')
        self.last_effectivedatetime = None

    def make_features(self, trace_index, trace_record):
        'return (features, err)'
        def accumulate_history():
            self.last_effectivedatetime = trace_record['effectivedatetime']

        if self.last_effectivedatetime is None:
            accumulate_history()
            return (None, 'no prior trace record')
        else:
            interval = trace_record['effectivedatetime'] - self.last_effectivedatetime
            # interval: Timedelta, a subclass of datetime.timedelta
            # attributes of a datetime.timedelta are days, seconds, microseconds
            interarrival_seconds = (interval.days * 24.0 * 60.0 * 60.0) + (interval.seconds * 1.0)
            assert interarrival_seconds >= 0.0  # trace print file not sorted in ascending datetime order
            features = {
                'interarrival_seconds_size': interarrival_seconds,
            }
            accumulate_history()
            return (features, None)


class InterarrivalTimeTest(unittest.TestCase):
    def test1(self):
        Test = collections.namedtuple('Test', 'minute second expected_interval')
        tests = (  # (minute, second, expected_interval)
            Test(10, 0, None),
            Test(10, 0, 0),
            Test(10, 1, 1),
            Test(10, 20, 19),
            Test(10, 20, 0),
        )
        iat = InterarrivalTime()
        for test in tests:
            trace_record = {}
            trace_record['effectivedatetime'] = datetime.datetime(2016, 11, 3, 6, test.minute, test.second)
            features, err = iat.make_features(
                trace_index=None,
                trace_record=trace_record,
            )
            if test.expected_interval is None:
                self.assertTrue(features is None)
                self.assertTrue(isinstance(err, str))  # it contains an error message
            else:
                self.assertEqual(test.expected_interval, features['interarrival_seconds_size'])
                self.assertTrue(err is None)


class OasspreadHistory(FeatureMaker):
    'create historic oasspread features'

    # The caller will want to create these additional features:
    #  p_reclassified_trade_type_is_{B|C} with value 0 or 1
    #  p_oasspread with the value in the trace_record
    def __init__(self, k):
        super(OasspreadHistory, self).__init__('TracerecordOasspreadHistory(k=%s)' % k)
        self.k = k  # number of historic B and S oasspreads in the feature vector
        self.recognized_trade_types = ('B', 'S')

        self.history = {}
        for trade_type in self.recognized_trade_types:
            self.history[trade_type] = collections.deque(maxlen=k)

    def make_features(self, trace_index, trace_record, reclassified_trade_type):
        'return (features, err)'
        def accumulate_history():
            self.history[reclassified_trade_type].append(trace_record['oasspread'])

        if reclassified_trade_type not in self.recognized_trade_types:
            return (None, 'no history is created for reclassified trade types %s' % reclassified_trade_type)

        # determine whether we have enough history to build the features
        for trade_type in self.recognized_trade_types:
            if len(self.history[trade_type]) < self.k:
                err = 'history for trade type %s has length less than %s' % (
                    trade_type,
                    self.k,
                )
                accumulate_history()
                return (None, err)

        # create the features, if we have enough history to do so
        features = {}
        for trade_type in self.recognized_trade_types:
            for k in range(self.k):
                key = 'p_oasspread_%s_back_%02d' % (
                    trade_type,
                    self.k - k,  # the user-visible index is the number of trades back
                )
                features[key] = self.history[trade_type][k]
        accumulate_history()
        return (features, None)


class OasspreadHistoryTest(unittest.TestCase):
    def test_1(self):
        verbose = False
        Test = collections.namedtuple(
            'Test',
            'reclassified_trade_type oasspread b02 b01 s02 s01',
        )

        def has_nones(seq):
            for item in seq:
                if item is None:
                    return True
            return False

        def make_trace_record(trace_index, test):
            'return a pandas.Series with the bare minimum fields set'
            return pd.Series(
                data={
                    'oasspread': test.oasspread,
                },
            )

        tests = (
            Test('B', 100, None, None, None, None),
            Test('S', 103, 100, None, None, None),
            Test('S', 104, 100, None, 103, None),
            Test('B', 101, 100, None, 103, 104),
            Test('B', 102, 100, 101, 103, 104),
            Test('S', 105, 101, 102, 103, 104),
            Test('S', 106, 101, 102, 104, 105),
            Test('B', 103, 101, 102, 105, 106),
            Test('B', 105, 102, 103, 105, 106),
        )
        feature_maker = OasspreadHistory(k=2)
        for trace_index, test in enumerate(tests):
            if verbose:
                print 'TestOasSpreads.test_1: trace_index', trace_index
                print 'TestOasSpreads.test_1: test', test
            features, err = feature_maker.make_features(
                trace_index,
                make_trace_record(trace_index, test),
                test.reclassified_trade_type,
            )
            if has_nones(test):
                self.assertTrue(features is None)
                self.assertTrue(err is not None)
            else:
                self.assertTrue(features is not None)
                self.assertTrue(err is None)
                self.assertEqual(features['p_oasspread_B_back_01'], test.b01)
                self.assertEqual(features['p_oasspread_B_back_02'], test.b02)
                self.assertEqual(features['p_oasspread_S_back_01'], test.s01)
                self.assertEqual(features['p_oasspread_S_back_02'], test.s02)


class Ohlc(FeatureMaker):
    'ratio_days of delta ticker / delta spx for closing prices'
    def __init__(self, df_ticker=None, df_spx=None, verbose=False):
        'precompute all results'
        pdb.set_trace()
        super(Ohlc, self).__init__('ohlc')

        self.df_ticker = df_ticker  # a DataFreame
        self.df_spx = df_spx        # a DataFrame
        self.skipped_reasons = collections.Counter()

        self.days_back = [
            1 + days_back
            for days_back in xrange(30)
        ]
        self.ratio_day, self.dates_list = self._make_ratio_day(df_ticker, df_spx)
        self.dates_set = set(self.dates_list)

    def make_features(self, trace_index, trace_record, extra):
        'return Dict[feature_name, feature_value], err'
        pdb.set_trace()
        date = trace_record['effectivedatetime'].date()
        if date not in self.dates_set:
            return False, 'ohlc: date %s not in ticker and spx input files' % date
        result = {}
        feature_name_template = 'p_price_delta_ratio_back_%s_%02d'
        for days_back in self.days_back:
            key = (date, days_back)
            if key not in self.ratio_day:
                return False, 'ohlc: missing date %s days_back %s in ticker and spx input files' % (
                    date,
                    days_back,
                )
            feature_name = feature_name_template % ('days', days_back)
            result[feature_name] = self.ratio_day[key]
        return result, None

    def _make_ratio_day(self, df_ticker, df_spx):
        'return Dict[date, ratio]'
        verbose = False

        closing_price_spx = {}         # Dict[date, closing_price]
        closing_price_ticker = {}
        dates_list = []
        ratio = {}
        for timestamp in sorted(df_ticker.index):
            ticker = df_ticker.loc[timestamp]
            if timestamp.date() not in df_spx.index:
                msg = 'FeatureMakerOhlc: skipping index %s is in ticker but not spx' % timestamp
                self.skipped_reasons[msg] += 1
                continue
            spx = df_spx.loc[timestamp]

            date = timestamp.date()
            dates_list.append(date)
            closing_price_spx[date] = spx.Close
            closing_price_ticker[date] = ticker.Close
            if verbose:
                print 'trades', date, 'ticker', ticker.Close, 'spx', spx.Close
            for days_back in self.days_back:
                # detemine for calendar days (which might fail)
                # assume that the calendar dates are a subset of the market dates
                stop_date = self._adjust_date(dates_list, 2)
                start_date = self._adjust_date(dates_list, 2 + days_back)
                if stop_date is None or start_date is None:
                    msg = 'no valid date for trade date %s days_back %d' % (date, days_back)
                    if verbose:
                        print msg
                    self.skipped_reasons[msg] += 1
                    continue
                ratio[(date, days_back)] = self._ratio_day(
                    closing_price_spx,
                    closing_price_ticker,
                    start_date,
                    stop_date,
                )
                if verbose:
                    print 'ratio', days_back, start_date, stop_date, date, ratio[(date, days_back)]
        return ratio, dates_list

    def _adjust_date(self, dates_list, days_back):
        'return date if its in valid_dates, else None'
        try:
            return dates_list[-days_back]
        except:
            return None

    def _ratio_day(self, prices_spx, prices_ticker, start, stop):
        delta_ticker = prices_ticker[start] * 1.0 / prices_ticker[stop]
        delta_spx = prices_spx[start] * 1.0 / prices_spx[stop]
        ratio_day = delta_ticker * 1.0 / delta_spx
        return ratio_day


class OrderImbalance(FeatureMaker):
    'features related to the order imbalance'
    def __init__(self, lookback=None, typical_bid_offer=None, proximity_cutoff=None):
        super(OrderImbalance, self).__init__(
            'OrderImbalance(lookback=%s, typical_bid_offer=%s, proximity_cutff=%s)' % (
                lookback,
                typical_bid_offer,
                proximity_cutoff,
            ))
        self.order_imbalance4_object = OrderImbalance4.OrderImbalance4(
            lookback=lookback,
            typical_bid_offer=typical_bid_offer,
            proximity_cutoff=proximity_cutoff,
        )
        self.order_imbalance4 = None
        self.all_trade_type = ('B', 'D', 'S')

    def make_features(self, trace_index, trace_record, verbose=False):
        'return (Dict, err)'
        'return None or error message'
        pdb.set_trace()
        oasspread = trace_record['oasspread']
        price = trace_record['price']
        quantity = trace_record['quantity']
        trade_type = trace_record['trade_type']

        assert trade_type in self.all_trade_types
        # check for NaN values
        if oasspread != oasspread:
            return (None, 'oasspread is NaN')
        if price != price:
            return (None, 'price is NaN')
        if quantity != quantity:
            return (None, 'quantity is NaN')
        if trade_type not in self.all_trade_type:
            return (None, 'unexpected trade type %d for trace print %s' % (
                trade_type,
                trace_index,
                ))

        order_imbalance4_result = self.order_imbalance4_object.imbalance(
            trade_type='trade_type',
            trade_quantity='quantity',
            trade_price='price',
        )
        order_imbalance, reclassified_trade_type, err = order_imbalance4_result
        if err is not None:
            return (None, 'trade type not reclassfied: ' + err)

        features = {
            'orderimbalance': order_imbalance,
            'id_reclassified_trade_type': reclassified_trade_type,
            'reclassified_trade_type_is_B': 1 if reclassified_trade_type is 'B' else 0,
            'reclassified_trade_type_is_S': 1 if reclassified_trade_type is 'S' else 0,
        }
        return (features, None)


class SecurityMaster(FeatureMaker):
    def __init__(self, df):
        super(SecurityMaster, self).__init__('SecurityMaster')
        self.df = df  # the security master records

    def make_features(self, trace_index, trace_record, extra):
        'return (Dict[feature_name, feature_value], None) or (None, err)'
        cusip = trace_record['cusip']
        if cusip not in self.df.index:
            return (None, 'cusip %s not in security master' % cusip)
        security = self.df.loc[cusip]

        result = {
            'coupon_type_is_fixed_rate': 1 if security['coupon_type'] == 'Fixed rate' else 0,
            'coupon_type_is_floating_rate': 1 if security['coupon_type'] == 'Floating rate' else 0,
            'original_amount_issued_size': security['original_amount_issued'],
            'months_to_maturity_size': self._months_from_until(trace_record['effectivedate'], security['maturity_date']),
            'months_of_life_size': self._months_from_until(security['issue_date'], security['maturity_date']),
            'is_callable': 1 if security['is_callable'] else 0,
            'is_puttable': 1 if security['is_puttable'] else 0,
        }
        return result, None

    def _months_from_until(self, a, b):
        'return months from date a to date b'
        delta_days = (b - a).days
        return delta_days / 30.0


class TimeVolumeWeightedAverage(object):
    def __init__(self, k):
        assert k > 0
        self.k = k
        self.history = collections.deque([], k)

    def weighted_average(self, amount, volume, timestamp):
        'accumulate amount and volume and return (weighted_average: float, err)'
        def as_days(timedelta):
            'convert pandas Timedelta to number of days'
            seconds_per_day = 24.0 * 60.0 * 60.0
            return (
                timedelta.components.days +
                timedelta.components.hours / 24.0 +
                timedelta.components.minutes / (24.0 * 60.0) +
                timedelta.components.seconds / seconds_per_day +
                timedelta.components.milliseconds / (seconds_per_day * 1e3) +
                timedelta.components.microseconds / (seconds_per_day * 1e6) +
                timedelta.components.nanoseconds / (seconds_per_day * 1e9)
            )

        self.history.append((amount, volume, timestamp))
        if len(self.history) != self.k:
            return None, 'not yet k=%d observations' % self.k
        weighted_amount_sum = 0.0
        weighted_volume_sum = 0.0
        for amount, volume, ts in self.history:
            days_back = as_days((ts - timestamp))  # in fractions of a day
            assert days_back <= 0.0
            weight = math.exp(days_back)
            weighted_amount_sum += amount * volume * weight
            weighted_volume_sum += volume * weight
        if weighted_volume_sum == 0.0:
            return None, 'time-weighted volumes sum to zero'
        return weighted_amount_sum / weighted_volume_sum, None


class TimeVolumeWeightedAverageTest(unittest.TestCase):
    def test(self):
        def t(hour, minute):
            'return datetime.date'
            return pd.Timestamp(2016, 11, 1, hour, minute, 0)

        TestCase = collections.namedtuple('TestCase', 'k spreads_quantities expected')
        data = ((t(10, 00), 100, 10), (t(10, 25), 200, 20), (t(10, 30), 300, 30))  # [(time, value, quantity)]
        tests = (
            TestCase(1, data, 300),
            TestCase(2, data, 240.06),
            TestCase(3, data, (100 * 10 * 0.979 + 200 * 20 * 0.996 + 300 * 30) / (10 * 0.979 + 20 * 0.996 + 30)),
            TestCase(4, data, None),
        )
        for test in tests:
            if test.k != 3:
                continue
            rwa = TimeVolumeWeightedAverage(test.k)
            for spread_quantity in test.spreads_quantities:
                time, spread, quantity = spread_quantity
                actual, err = rwa.weighted_average(spread, quantity, time)
                # we check only the last result
            if test.expected is None:
                self.assertEqual(actual, None)
                self.assertTrue(err is not None)
            else:
                self.assertAlmostEqual(test.expected, actual, 1)
                self.assertTrue(err is None)


class TraceIndex(FeatureMaker):
    def __init__(self):
        super(TraceIndex, self).__init__('TraceIndex')

    def make_features(self, trace_index, trace_record, extra):
        'return Dict[feature_name, feature_value], err'
        return {
            'id_trace_index': trace_index,
            'id_cusip': trace_record['cusip'],
            'id_effectivedatetime': trace_record['effectivedatetime'],
            'id_effectivedate': trace_record['effectivedate'],
            'id_effectivetime': trace_record['effectivetime'],
            'id_trade_type': trace_record['trade_type'],
            'id_issuepriceid': trace_record['issuepriceid'],  # unique identifier of the trace print
        }, None


class TraceTradetypeContext(object):
    'accumulate running info from trace prints for each trade type'
    def __init__(self, lookback=None, typical_bid_offer=None, proximity_cutoff=None):
        print 'deprecated: use OrderImbalance, PriceHistory, QuantityHistory instead'
        self.order_imbalance4_object = OrderImbalance4.OrderImbalance4(
            lookback=lookback,
            typical_bid_offer=typical_bid_offer,
            proximity_cutoff=proximity_cutoff,
        )
        self.order_imbalance4 = None

        # each has type Dict[trade_type, number]
        self.prior_oasspread = {}
        self.prior_price = {}
        self.prior_quantity = {}

        self.all_trade_types = ('B', 'D', 'S')

    def update(self, trace_record, verbose=False):
        'return (Dict, err)'
        'return None or error message'
        oasspread = trace_record['oasspread']
        price = trace_record['price']
        quantity = trace_record['quantity']
        trade_type = trace_record['trade_type']

        if verbose:
            print 'context', trace_record['cusip'], trade_type, oasspread

        assert trade_type in self.all_trade_types
        # check for NaN values
        if oasspread != oasspread:
            return (None, 'oasspread is NaN')
        if price != price:
            return (None, 'price is NaN')
        if quantity != quantity:
            return (None, 'quantity is NaN')

        order_imbalance4_result = self.order_imbalance4_object.imbalance(
            trade_type=trade_type,
            trade_quantity=quantity,
            trade_price=price,
        )
        order_imbalance, reclassified_trade_type, err = order_imbalance4_result
        if err is not None:
            return (None, 'trace print not reclassfied: ' + err)

        assert order_imbalance is not None
        assert reclassified_trade_type in ('B', 'S')
        # the updated values could be missing, in which case, they are np.nan values
        self.prior_oasspread[trade_type] = oasspread
        self.prior_price[trade_type] = price
        self.prior_quantity[trade_type] = quantity

        # assure that we know the prior values the caller is looking for
        for trade_type in self.all_trade_types:
            if trade_type not in self.prior_oasspread:
                return (None, 'no prior oasspread for trade type %s' % trade_type)
            if trade_type not in self.prior_price:
                return (None, 'no prior price for trade type %s' % trade_type)
            if trade_type not in self.prior_quantity:
                return (None, 'no prior quantity for trade type %s' % trade_type)

        d = {
            'orderimbalance': order_imbalance,
            'reclassified_trade_type': reclassified_trade_type,
            'prior_price': self.prior_price,
            'prior_quantity': self.prior_quantity,
        }
        return (d, None)

    def missing_any_prior_oasspread(self):
        'return None or error'
        missing = []
        for trade_type in self.all_trade_types:
            if trade_type not in self.prior_oasspread:
                missing.append(trade_type)
        return (
            None if len(missing) == 0 else
            'missing prior oasspread for trade type %s' % missing
        )


class VolumeWeightedAverage(object):
    def __init__(self, k):
        assert k > 0
        self.k = k
        self.history = collections.deque([], k)

    def weighted_average(self, amount, volume):
        'accumulate amount and volume and return (weighted_average: float, err)'
        self.history.append((amount, volume))
        if len(self.history) != self.k:
            return None, 'not yet k=%d observations' % self.k
        weighted_amount_sum = 0.0
        weighted_volume_sum = 0.0
        for amount, volume in self.history:
            weighted_amount_sum += amount * volume
            weighted_volume_sum += volume
        if weighted_volume_sum == 0.0:
            return None, 'volums sum to zero'
        return weighted_amount_sum / weighted_volume_sum, None


class VolumeWeightedAverageTest(unittest.TestCase):
    def test(self):
        TestCase = collections.namedtuple('TestCase', 'k spreads_quantities expected')
        data = ((100, 10), (200, 20), (300, 30))  # [(value, quantity)]
        tests = (
            TestCase(1, data, 300),
            TestCase(2, data, 260),
            TestCase(3, data, 233.33),
            TestCase(4, data, None),
        )
        for test in tests:
            rwa = VolumeWeightedAverage(test.k)
            for spread_quantity in test.spreads_quantities:
                spread, quantity = spread_quantity
                actual, err = rwa.weighted_average(spread, quantity)
                # we check only the last result
            if test.expected is None:
                self.assertEqual(actual, None)
                self.assertTrue(err is not None)
            else:
                self.assertAlmostEqual(test.expected, actual, 2)
                self.assertTrue(err is None)


class TraceRecord(FeatureMaker):
    # possibly deprecated, at least some functionality to be put into more focused classes
    def __init__(self, order_imbalance4_hps=None):
        assert order_imbalance4_hps is not None
        super(TraceRecord, self).__init__('TraceRecord')

        self.trace_record_feature_makers = (
            InterarrivalTime(),
            OrderImbalance(**order_imbalance4_hps),
        )
        print 'move other trace-record feature makers to here'

        return  # OLD BELWO ME
        self.contexts = {}  # Dict[cusip, TraceTradetypeContext]
        self.order_imbalance4_hps = order_imbalance4_hps
        self.oasspread_history = OasspreadHistory(10)

        self.ks = (1, 2, 5, 10)  # num trades of weighted average spreads
        self.volume_weighted_average = {}
        self.time_volume_weighted_average = {}
        for k in self.ks:
                self.volume_weighted_average[k] = VolumeWeightedAverage(k)
                self.time_volume_weighted_average[k] = TimeVolumeWeightedAverage(k)

        self.interarrivaltimes = collections.defaultdict(lambda: InterarrivalTime.InterarrivalTime())  # key = cusip

    def make_features(self, trace_index, trace_record):
        'return Dict[feature_name, feature_value], err'
        pdb.set_trace()
        all_features = {}
        xtra = {}
        propagated_fields = ('reclassified_trade_type',)
        for feature_maker in self.trace_record_feature_makers:
            new_features, err = feature_maker.make_features(trace_index, trace_record, xtra)
            if err is not None:
                return (None, '%s: %s' % (feature_maker.name, err))
            all_features.update(new_features)
            for propagated_field in propagated_fields:
                if propagated_field in new_features:
                    xtra[propagated_field] = new_features[propagated_fields]

        return (all_features, None)

        # OLD BELOW ME
        cusip = trace_record['cusip']

        # interarrival time are the time difference since the last trace print for the same cusip
        interarrival_seconds, err = self.interarrivaltimes[cusip].interarrival_seconds(trace_index, trace_record)
        if err is not None:
            return (None, 'interarrivaltime: %s' % err)

        # other info from prior trades of this cusip
        if cusip not in self.contexts:
            self.contexts[cusip] = TraceTradetypeContext(
                lookback=self.order_imbalance4_hps['lookback'],
                typical_bid_offer=self.order_imbalance4_hps['typical_bid_offer'],
                proximity_cutoff=self.order_imbalance4_hps['proximity_cutoff'],
            )
        cusip_context = self.contexts[cusip]

        cc, err = cusip_context.update(trace_record)
        if err is not None:
            return (None, 'cusip context not created: ' + err)

        # trade history
        reclassified_trade_type = cc['reclassified_trade_type']
        if reclassified_trade_type == 'D':
            err = 'trade type reclassified as D'
            return (None, err)

        pdb.set_trace()
        oasspread_history_features, err = self.oasspread_history(
            trace_index,
            trace_record,
            reclassified_trade_type,
        )
        if err is not None:
            return (None, err)

        # weighted average spreads
        oasspread = trace_record['oasspread']
        quantity = trace_record['quantity']
        effectivedatetime = trace_record['effectivedatetime']
        volume_weighted_average_spread = {}
        time_volume_weighted_average_spread = {}
        for k in self.ks:
            volume_weighted_spread, err = self.volume_weighted_average[k].weighted_average(
                oasspread,
                quantity,
            )
            if err is not None:
                return None, 'volume weighted average: ' + err
            volume_weighted_average_spread[k] = volume_weighted_spread

            time_volume_weighted_spread, err = self.time_volume_weighted_average[k].weighted_average(
                oasspread,
                quantity,
                effectivedatetime,
            )
            if err is not None:
                return None, 'time volume weighted average: ' + err
            time_volume_weighted_average_spread[k] = time_volume_weighted_spread

        weighted_spread_features = {}
        for k in self.ks:
            feature_name = 'p_volume_weighted_oasspread_%02d_back' % k
            weighted_spread_features[feature_name] = volume_weighted_average_spread[k]

            feature_name = 'p_time_volume_weighted_oasspread_%02d_back' % k
            weighted_spread_features[feature_name] = time_volume_weighted_average_spread[k]

        other_features = {
            'id_event_source': 'trace_print',
            'p_interarrival_seconds_size': interarrival_seconds,
            'p_order_imbalance4': cc['orderimbalance'],
            'id_reclassified_trade_type': cc['reclassified_trade_type'],
            'p_reclassified_trade_type_is_B': 1 if cc['reclassified_trade_type'] == 'B' else 0,
            'p_reclassified_trade_type_is_S': 1 if cc['reclassified_trade_type'] == 'S' else 0,
            'p_quantity_size': trace_record['quantity'],
            'p_oasspread': trace_record['oasspread'],
        }
        # add in trade_type related features
        tt_features = {}  # features dependent on the trade date
        for trade_type in ('B', 'D', 'S'):
            tt_features['p_prior_oasspread_%s' % trade_type] = cc['prior_oasspread'][trade_type]
            tt_features['p_prior_price_%s' % trade_type] = cc['prior_price'][trade_type]
            tt_features['p_prior_quantity_%s_size' % trade_type] = cc['prior_quantity'][trade_type]
            tt_features['p_trade_type_is_%s' % trade_type] = 1 if trace_record['trade_type'] == trade_type else 0

        all_features = oasspread_history_features
        all_features.update(weighted_spread_features)
        all_features.update(other_features)
        all_features.update(tt_features)
        return all_features, None


if __name__ == '__main__':
    unittest.main()


if False:
    # avoid errors from linter
    pdb
    pprint
