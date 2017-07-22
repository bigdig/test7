'''make targets from trace prints

Copyright 2017 Roy E. Lowrance, roy.lowrance@gmail.com

You may not use this file except in compliance with a License.
'''
import collections
import numpy as np
import pandas as pd
import pdb

import seven.feature_makers


class TargetMaker(seven.feature_makers.FeatureMaker):
    def __init__(self):
        super(TargetMaker, self).__init__('TargetMaker')
        self.interarrivaltime = seven.feature_makers.TracerecordInterarrivalTime()
        self.targets = pd.DataFrame()  # build this up row by row, its part of the API
        return  # OLD BELOW ME
        self.interarrivaltime = collections.defaultdict(lambda: seven.InterarrivalTime.InterarrivalTime())
        self.targets = pd.DataFrame()  # build this up row by row; its part of the API

    def make_features(self, trace_index, trace_record):
        'return (features, err) and append features to self.targets'
        interarrival_features, err = self.interarrivaltime(trace_index, trace_record)
        if err is not None:
            return (None, '%s: %s' % (interarrival_features.name, err))

        oasspread = trace_record['oasspread']
        if np.isnan(oasspread):
            return None, 'oasspread is NaN'

        trade_type = trace_record['trade_type']
        assert trade_type in ('B', 'D', 'S')

        result = {
            'id_trace_index': trace_index,
            'id_trade_type': trade_type,
            'id_oasspread': oasspread,
            'id_effectivedatetime': trace_record['effectivedatetime'],
            'id_effectivedate': trace_record['effectivedate'].date(),
            'id_effectivetime': trace_record['effectivetime'],
            'id_quantity': trace_record['quantity'],
            'target_oasspread': oasspread,
            'target_interarrival_seconds': interarrival_features['p_interrarival_seconds_size'],
            # 'target_interarrival_seconds': interarrival_seconds,  # from prrior trade of any trade_type
        }
        return result, None        

    def append_targets(self, trace_index, trace_record):
        'append info to self.data and self.indices; return None (if successful) or err'
        def append_to_data(targets_values):
            for target, value in targets_values.iteritems():
                self.data[target]. append(value)
            return None

        def append_to_indices(trace_index):
            self.indices.append(trace_index)

        target_values, err = self._make_targets_values(trace_index, trace_record)
        if err is not None:
            return err

        new_row = pd.DataFrame(
            data=target_values,
            index=pd.Index(
                data=[trace_index],
                name='trace_index',
            ),
        )
        self.targets = self.targets.append(new_row)

        return None

    def _make_targets_values(self, trace_index, trace_record):
        'return (dict, err)'
        iat = self.interarrivaltime[trace_record['cusip']]
        interarrival_seconds, err = iat.interarrival_seconds(trace_index, trace_record)
        if err is not None:
            return None, 'interarrivaltime: %s' % err

        oasspread = trace_record['oasspread']
        if np.isnan(oasspread):
            return None, 'oasspread is NaN'

        trade_type = trace_record['trade_type']
        assert trade_type in ('B', 'D', 'S')

        result = {
            'id_trace_index': trace_index,
            'id_trade_type': trade_type,
            'id_oasspread': oasspread,
            'id_effectivedatetime': trace_record['effectivedatetime'],
            'id_effectivedate': trace_record['effectivedate'].date(),
            'id_effectivetime': trace_record['effectivetime'],
            'id_quantity': trace_record['quantity'],
            'target_oasspread': oasspread,
            'target_interarrival_seconds': interarrival_seconds,  # from prrior trade of any trade_type
        }
        return result, None


if False:
    pdb
