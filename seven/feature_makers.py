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
'''

from __future__ import division

import collections
import datetime
import numbers
import pandas as pd
import pdb
from pprint import pprint


from applied_data_science.timeseries import FeatureMaker

import seven.OrderImbalance4
import seven.read_csv


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


class Skipped(object):
    def __init__(self):
        self.counter = collections.Counter()
        self.n_skipped = 0

    def skip(self, reason):
        self.counter[reason] += 1
        self.n_skipped += 1


class AllFeatures(object):
    'create features for a single CUSIP for a specfied ticker'
    def __init__(self, ticker):
        self.ticker = ticker
        self.all_feature_makers = (
            FeatureMakerEtf(
                df=seven.read_csv.input(ticker, 'etf agg'),
                name='agg',
            ),
            FeatureMakerEtf(
                df=seven.read_csv.input(ticker, 'etf lqd'),
                name='lqd',
            ),
            FeatureMakerFund(
                df=seven.read_csv.input(ticker, 'fund'),
            ),
            FeatureMakerTradeId(),
            FeatureMakerOhlc(
                df_ticker=seven.read_csv.input(ticker, 'ohlc ticker'),
                df_spx=seven.read_csv.input(ticker, 'ohlc spx'),
            ),
            FeatureMakerSecurityMaster(
                df=seven.read_csv.input(ticker, 'security master'),
            ),
            FeatureMakerTrace(
                order_imbalance4_hps={
                    'lookback': 10,
                    'typical_bid_offer': 2,
                    'proximity_cutoff': 20,
                },
            ),
        )
        self.skipped = collections.Counter()
        # NOTE: callers rely on the definitions of self.d and self.trace_indices
        self.d = collections.defaultdict(list)  # Dict[feature_name, [feature_value]]
        self.trace_indices = []  # [trace_index]
        self.cusip = None

    def append_features(self, trace_index, trace_record, verbose=False):
        'return True (in which case, we created features from the trace_record) or False (we did not)'
        # assure all the trace_records are for the same CUSIP
        if self.cusip is None:
            self.cusip = trace_record['cusip']
        else:
            assert self.cusip == trace_record['cusip'], (self.cusip, trace_record)

        # accumulate features from the feature makers
        # stop on the first error from a feature maker
        any_skipped = False
        trace_index_features = {}  # Dict[feature_name, feature_value]
        trace_index_feature_names = set()
        for feature_maker in self.all_feature_makers:
            # Maybe: make the error codes explicit by returning (True, Dict) or (False, Str)
            features_dict_or_error_message = feature_maker.make_features(trace_index, trace_record)
            if isinstance(features_dict_or_error_message, str):
                self.skipped[features_dict_or_error_message] += 1
                any_skipped = True
                if verbose:
                    print 'no features appended for %s %s %s %s: %s' % (
                        trace_index,
                        trace_record['cusip'],
                        trace_record['trade_type'],
                        trace_record['oasspread'],
                        features_dict_or_error_message,
                    )
                break
            for feature_name, feature_value in features_dict_or_error_message.iteritems():
                # check that no feture names just created are unique across all feature makers
                assert feature_name not in trace_index_feature_names, (feature_name, trace_index_feature_names)
                # check that we are creating no NaN (missing) feature values
                if feature_value != feature_value:
                    # feature value is NaN; should not happen
                    print 'NaN feature value', feature_name, feature_maker.name
                    pdb.set_trace()
                # append to the to-be DataFrame

                trace_index_feature_names.add(feature_name)
                trace_index_features[feature_name] = feature_value
        if any_skipped:
            return False  # created no features from the trace_record
        else:
            if verbose:
                print 'features appended for %s %s %s %s' % (
                    trace_index,
                    trace_record['cusip'],
                    trace_record['trade_type'],
                    trace_record['oasspread'],
                )
            self.trace_indices.append(trace_index)
            for feature_name, feature_value in trace_index_features.iteritems():
                self.d[feature_name].append(feature_value)
            return True  # creted all features from the trace_record

    def get_by_effectivedatetime(self, effectivedatetime):
        'return dictionary of an arbitrarily-chosen record at the effective datetime or None'
        pdb.set_trace()

    def get_by_index(self, index):
        'return dict or None'
        if index in self.d:
            return self.d[index]
        else:
            return None

    def get_all_features(self):
        'return DataFrame'
        result = pd.DataFrame(data=self.d, index=self.trace_indices)
        return result


class FeatureMakerEtf(FeatureMaker):
    def __init__(self, df=None, name=None):
        # the df comes from a CSV file for the ticker and etf name
        # df format
        #  each row is a date as specified in the index
        #  each column is an isin as specified in the column names
        #  each df[date, isin] is the weight in an exchanged trade fund
        def invalid(isin):
            'return Bool'
            # the input files appear to duplicate the isin, by having two columns for each
            # the second column ends in ".1"
            # there are also some unnamed colums
            return isin.endswith('.1') or isin.startswith('Unnamed:')

        self.short_name = name
        super(FeatureMakerEtf, self).__init__('etf_' + name)
        self.df = df.copy(deep=True)
        return


    def make_features(self, ticker_index, ticker_record):
        'return Dict[feature_name, feature_value] or str (if error)'
        date = ticker_record['effectivedate']
        isin = ticker_record['isin']  # international security identification number'
        try:
            weight = self.df.loc[date, isin]
            assert 0.0 <= weight <= 1.0, (weight, date, isin)
            return {
                'p_weight_etf_%s_size' % self.short_name: weight,
            }
        except KeyError:
            msg = '.loc[date: %s, isin: %s] not in eff file %s' % (date, isin, self.name)
            return msg


class FeatureMakerFund(FeatureMaker):
    def __init__(self, df=None):
        super(FeatureMakerFund, self).__init__('fund')
        # precompute all the features
        # convert the Excel date in column "Date" to a python.datetime
        # create Dict[date: datetime.date, features: Dict[name:str, value]]
        self.sorted_df = df.sort_values('date', ascending=False)
        self.sorted_df.index = self.sorted_df['date']
        return

    def make_features(self, ticker_index, ticker_record):
        'return error_msg:str or Dict[feature_name, feature_value]'
        # find correct date for the fundamentals
        # this code assumes there is no lag in reporting the values
        ticker_record_effective_date = ticker_record['effectivedate']
        for reported_date, row in self.sorted_df.iterrows():
            if reported_date <= ticker_record_effective_date:
                return {
                    'p_debt_to_market_cap': row['total_debt'] / row['mkt_cap'],
                    'p_debt_to_ltm_ebitda': row['total_debt'] / row['LTM_EBITDA'],
                    'p_gross_leverage': row['total_assets'] / row['total_debt'],
                    'p_interest_coverage': row['interest_coverage'],
                    'p_ltm_ebitda': row['LTM_EBITDA'],  # not a size, since could be negative
                    # OLD VERSION (note: different column names; some features were precomputed)
                    # 'p_debt_to_market_cap': series['Total Debt BS'] / series['Market capitalization'],
                    # 'p_debt_to_ltm_ebitda': series['Debt / LTM EBITDA'],
                    # 'p_gross_leverage': series['Debt / Mkt Cap'],
                    # 'p_interest_coverage': series['INTEREST_COVERAGE_RATIO'],
                    # 'p_ltm_ebitda_size': series['LTM EBITDA'],
                }
        msg = 'date %s not found in fundamentals files %s' % (ticker_record['effectivedate'], self.name)
        return msg


class FeatureMakerTradeId(FeatureMaker):
    def __init__(self, input_file_name=None):
        assert input_file_name is None
        super(FeatureMakerTradeId, self).__init__('trade id')

    def make_features(self, ticker_index, ticker_record):
        'return error_msg:str or Dict[feature_name, feature_value]'
        return {
            'id_ticker_index': ticker_index,
            'id_cusip': ticker_record['cusip'],
            'id_cusip1': ticker_record['cusip1'],
            'id_effectivedatetime': ticker_record['effectivedatetime'],
            'id_effectivedate': ticker_record['effectivedate'],
            'id_effectivetime': ticker_record['effectivetime'],
        }


def adjust_date(dates_list, days_back):
    'return date if its in valid_dates, else None'
    try:
        return dates_list[-days_back]
    except:
        return None


def ratio_day(prices_spx, prices_ticker, start, stop):
    delta_ticker = prices_ticker[start] * 1.0 / prices_ticker[stop]
    delta_spx = prices_spx[start] * 1.0 / prices_spx[stop]
    ratio_day = delta_ticker * 1.0 / delta_spx
    return ratio_day


class FeatureMakerOhlc(FeatureMaker):
    'ratio_days of delta ticker / delta spx for closing prices'
    def __init__(self, df_ticker=None, df_spx=None, verbose=False):
        'precompute all results'
        super(FeatureMakerOhlc, self).__init__('ohlc')

        self.df_ticker = df_ticker
        self.df_spx = df_spx
        self.skipped_reasons = collections.Counter()

        self.days_back = [
            1 + days_back
            for days_back in xrange(30)
        ]
        self.ratio_day = self._make_ratio_day(df_ticker, df_spx)

    def make_features(self, ticker_index, ticker_record):
        'return Dict[feature_name: str, feature_value: number] or error_msg:str'
        date = ticker_record.effectivedatetime.date()
        result = {}
        feature_name_template = 'p_price_delta_ratio_back_%s_%02d'
        for days_back in self.days_back:
            key = (date, days_back)
            if key not in self.ratio_day:
                return 'missing key %s in self.ratio_date' % key
            feature_name = feature_name_template % ('days', days_back)
            result[feature_name] = self.ratio_day[key]
        return result

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
                stop_date = adjust_date(dates_list, 2)
                start_date = adjust_date(dates_list, 2 + days_back)
                if stop_date is None or start_date is None:
                    msg = 'no valid date for trade date %s days_back %d' % (date, days_back)
                    if verbose:
                        print msg
                    self.skipped_reasons[msg] += 1
                    continue
                ratio[(date, days_back)] = ratio_day(
                    closing_price_spx,
                    closing_price_ticker,
                    start_date,
                    stop_date,
                )
                if verbose:
                    print 'ratio', days_back, start_date, stop_date, date, ratio[(date, days_back)]
        return ratio


def months_from_until(a, b):
    'return months from date a to date b'
    delta_days = (b - a).days
    return delta_days / 30.0


class FeatureMakerSecurityMaster(FeatureMaker):
    def __init__(self, df):
        super(FeatureMakerSecurityMaster, self).__init__('securitymaster')
        self.df = df

    def make_features(self, ticker_index, ticker_record):
        'return Dict[feature_name: str, feature_value: number] or error_msg:str'
        cusip = ticker_record.cusip
        if cusip not in self.df.index:
            return 'cusip %s not in security master' % cusip
        row = self.df.loc[cusip]

        # check the we have coded all the discrete values that will occur
        def make_coupon_types(value):
            expected_values = ('Fixed rate', 'Floating rate')
            result = {}
            if value not in expected_values:
                print 'error: unexpected value:', value
                print 'expected values:', expected_values
                pdb.set_trace()
            result = {}
            for expected_value in expected_values:
                feature_name = 'p_coupon_type_is_%s' % expected_value.lower().replace(' ', '_')
                result[feature_name] = 1 if value == expected_value else 0
            return result

        assert row.curr_cpn >= 0.0
        assert row.is_callable in (False, True)
        assert row.is_puttable in (False, True)
        if not isinstance(row.issue_amount, numbers.Number):
            print 'not a number', row.issue_amount
            pdb.set_trace()
        if not row.issue_amount > 0:
            print 'not positive', row.issue_amount
            pdb.set_trace()

        result = {
            'p_amount_issued_size': row.issue_amount,
            'p_coupon_current_size': row.curr_cpn,
            'p_is_callable': 1 if row.is_callable else 0,
            'p_is_puttable': 1 if row.is_puttable else 0,
            'p_months_to_maturity_size': months_from_until(ticker_record.effectivedate, row.maturity_date)
        }
        result.update(make_coupon_types(row.coupon_type))
        return result


class TickertickerContextCusip(object):
    'accumulate running info from trace prints for a specific CUSIP'
    def __init__(self, lookback=None, typical_bid_offer=None, proximity_cutoff=None):
        self.order_imbalance4_object = seven.OrderImbalance4.OrderImbalance4(
            lookback=lookback,
            typical_bid_offer=typical_bid_offer,
            proximity_cutoff=proximity_cutoff,
        )
        self.order_imbalance4 = None

        self.prior_oasspread = {}
        self.prior_price = {}
        self.prior_quantity = {}

        self.all_trade_types = ('B', 'D', 'S')

    def update(self, trace_record, verbose=False):
        'update self.* using current trace record; return (True, None) or (False, error_message)'
        oasspread = trace_record['oasspread']
        price = trace_record['price']
        quantity = trace_record['quantity']
        trade_type = trace_record['trade_type']

        if verbose:
            print 'context', trace_record['cusip'], trade_type, oasspread

        assert trade_type in self.all_trade_types
        # check for NaN values
        if oasspread != oasspread:
            return (False, 'oasspread is NaN')
        if price != price:
            return (False, 'price is NaN')
        if quantity != quantity:
            return (False, 'quantity is NaN')

        self.order_imbalance4 = self.order_imbalance4_object.imbalance(
            trade_type=trade_type,
            trade_quantity=quantity,
            trade_price=price,
        )
        # the updated values could be missing, in which case, they are np.nan values
        self.prior_oasspread[trade_type] = oasspread
        self.prior_price[trade_type] = price
        self.prior_quantity[trade_type] = quantity
        return (True, None)

    def missing_any_prior_oasspread(self):
        'return (True, msg) or (False, None)'
        for trade_type in self.all_trade_types:
            if trade_type not in self.prior_oasspread:
                return (True, 'missing prior oasspread for trade type %s' % trade_type)
        return (False, None)


class FeatureMakerTrace(FeatureMaker):
    def __init__(self, order_imbalance4_hps=None):
        super(FeatureMakerTrace, self).__init__('trace')
        assert order_imbalance4_hps is not None

        self.contexts = {}  # Dict[cusip, TickertickerContextCusip]
        self.order_imbalance4_hps = order_imbalance4_hps

    def make_features(self, ticker_index, ticker_record):
        'return Dict[feature_name: string, feature_value: number] or error:str'
        cusip = ticker_record['cusip']
        if cusip not in self.contexts:
            self.contexts[cusip] = TickertickerContextCusip(
                lookback=self.order_imbalance4_hps['lookback'],
                typical_bid_offer=self.order_imbalance4_hps['typical_bid_offer'],
                proximity_cutoff=self.order_imbalance4_hps['proximity_cutoff'],
            )
        cusip_context = self.contexts[cusip]
        ok, msg = cusip_context.update(ticker_record)
        if not ok:
            return msg
        any_missing, msg = cusip_context.missing_any_prior_oasspread()
        if any_missing:
            return msg
        else:
            return {
                'p_oasspread': ticker_record['oasspread'],   # can be negative, so not a size
                'p_order_imbalance4': cusip_context.order_imbalance4,
                'p_prior_oasspread_B': cusip_context.prior_oasspread['B'],
                'p_prior_oasspread_D': cusip_context.prior_oasspread['D'],
                'p_prior_oasspread_S': cusip_context.prior_oasspread['S'],
                'p_prior_quantity_B_size': cusip_context.prior_quantity['B'],
                'p_prior_quantity_D_size': cusip_context.prior_quantity['D'],
                'p_prior_quantity_S_size': cusip_context.prior_quantity['S'],
                'p_quantity_size': ticker_record['quantity'],
                'p_trade_type_is_B': 1 if ticker_record['trade_type'] == 'B' else 0,
                'p_trade_type_is_D': 1 if ticker_record['trade_type'] == 'D' else 0,
                'p_trade_type_is_S': 1 if ticker_record['trade_type'] == 'S' else 0,
            }


if False:
    # avoid errors from linter
    pdb
    pprint
