import tensorflow as tf
from tensorflow.contrib.rnn import DropoutWrapper, RNNCell, LSTMCell, LSTMStateTuple
from tensorflow.python.ops import variable_scope as vs
from tensorflow.contrib.rnn.python.ops.core_rnn_cell_impl import _linear

import numpy as np
from six.moves import xrange  # pylint: disable=redefined-builtin

class MatchLSTMCell(LSTMCell):

    def __init__(self, num_units, h_q, p_len, q_len, batch_size, scope=None):
        super(MatchLSTMCell, self).__init__(num_units)
        self._cell = LSTMCell(num_units)
        self.p_len = p_len
        self.q_len = q_len
        self._output_size = num_units
        self.batch_size = batch_size
        self.Hq = tf.reshape(h_q, [-1, num_units])

    @property
    def state_size(self):
        return self._state_size

    @property
    def output_size(self):
        return self._output_size

    def __call__(self, inputs, state, scope=None):

        with tf.variable_scope(scope or self.__class__.__name__, 
                    initializer=tf.contrib.layers.xavier_initializer()):
            hp, h_r = inputs, state.h
            Wq = tf.get_variable('Wq', shape=(self._num_units, self._num_units))
        
            # None, 200, 45
            fixed_WH = tf.reshape(tf.matmul(self.Hq, Wq), [-1, 
                self._num_units, self.p_len])

            # Use same weights for fw/bw linear
            with vs.variable_scope('inner'):
                x = _linear([hp, h_r], self._num_units, True)
            x = tf.reshape(tf.tile(tf.expand_dims(x, 0), [self.batch_size,
                1, self.p_len]), [-1,  self._num_units, self.p_len])
            G = tf.reshape(tf.tanh(fixed_WH + x), [-1, self._num_units])

            # Use same weights for fw/bw linear
            with vs.variable_scope('outer'):
                attn = tf.nn.softmax(_linear(G, self._output_size, True)) # 1 x Q
            z = tf.concat([hp, tf.matmul(attn, self.Hq)], 0)

        return self._cell(z, state)

class AnsPtrLSTMCell(LSTMCell):

    def __init__(self, Hr, num_units, batch_size, p_len):
        super(AnsPtrLSTMCell, self).__init__(num_units)
        self._cell = LSTMCell(num_units)   #  200
        self._output_size = p_len
        self.batch_size = batch_size
        self.H = Hr

    @property
    def state_size(self):
        return self._state_size

    @property
    def output_size(self):
        return self._output_size

    def __call__(self, inputs, state, scope=None):

        with tf.variable_scope(scope or self.__class__.__name__,
            initializer=tf.contrib.layers.xavier_initializer()):

            V = tf.get_variable('V', shape=(self._num_units, 2 * self._num_units))
            fixed_VH = tf.reshape(tf.matmul(tf.reshape(self.H, [-1, self._num_units]), V), 
                [-1, self._num_units, self._output_size])

            with vs.variable_scope('linear'):
                x = _linear(state, self._num_units, True)

            x = tf.tile(tf.expand_dims(x, 2), [-1, 1, self._output_size])
            F = tf.tanh(fixed_VH + x)   # None, 200, 750
            F = tf.reshape(F, [-1, self._num_units]) # None, 200

            with vs.variable_scope('f_linear'):
                b_k = tf.nn.softmax(_linear(F, self._output_size, True))

            m = tf.matmul(tf.reshape(self.H, [-1, self._output_size]), tf.reshape(b_k, [self._output_size, -1]))
            m = tf.reshape(m, [-1, 2 * self._num_units])  # None, 200

        #TODO: Make sure totally correct
        return b_k, self._cell(m, state)[1]
