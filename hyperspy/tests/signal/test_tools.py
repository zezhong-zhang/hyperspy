# -*- coding: utf-8 -*-
# Copyright 2007-2020 The HyperSpy developers
#
# This file is part of  HyperSpy.
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.

import sys
from unittest import mock

import numpy as np
import pytest

from hyperspy import signals
from hyperspy.decorators import lazifyTestClass


def _verify_test_sum_x_E(self, s):
    np.testing.assert_array_equal(self.signal.data.sum(), s.data)
    assert s.data.ndim == 1
    # Check that there is still one signal axis.
    assert s.axes_manager.signal_dimension == 1


def _test_default_navigation_signal_operations_over_many_axes(self, op):
    s = getattr(self.signal, op)()
    ar = getattr(self.data, op)(axis=(0, 1))
    np.testing.assert_array_equal(ar, s.data)
    assert s.data.ndim == 1
    assert s.axes_manager.signal_dimension == 1
    assert s.axes_manager.navigation_dimension == 0


def test_signal_iterator():
    sig = signals.Signal1D(np.arange(3).reshape((3, 1)))
    for s in (sig, sig.as_lazy()):
        assert next(s).data[0] == 0
        # If the following fails it can be because the iteration index was not
        # restarted
        for i, signal in enumerate(s):
            assert i == signal.data[0]


@lazifyTestClass
class TestDerivative:
    def setup_method(self, method):
        offset = 3
        scale = 0.1
        x = np.arange(-offset, offset, scale)
        s = signals.Signal1D(np.sin(x))
        s.axes_manager[0].offset = x[0]
        s.axes_manager[0].scale = scale
        self.s = s

    def test_derivative_data(self):
        der = self.s.derivative(axis=0, order=4)
        np.testing.assert_allclose(
            der.data, np.sin(der.axes_manager[0].axis), atol=1e-2
        )


@lazifyTestClass
class TestOutArg:
    def setup_method(self, method):
        # Some test require consistent random data for reference to be correct
        np.random.seed(0)
        s = signals.Signal1D(np.random.rand(5, 4, 3, 6))
        for axis, name in zip(
            s.axes_manager._get_axes_in_natural_order(), ["x", "y", "z", "E"]
        ):
            axis.name = name
        self.s = s

    def _run_single(self, f, s, kwargs):
        m = mock.Mock()
        s1 = f(**kwargs)
        s1.events.data_changed.connect(m.data_changed)
        s.data = s.data + 2
        s2 = f(**kwargs)
        r = f(out=s1, **kwargs)
        m.data_changed.assert_called_with(obj=s1)
        assert r is None
        np.testing.assert_array_equal(s1.data, s2.data)

    def test_get_histogram(self):
        self._run_single(self.s.get_histogram, self.s, {})
        if self.s._lazy:
            self._run_single(self.s.get_histogram, self.s, {"rechunk": False})

    def test_sum(self):
        self._run_single(self.s.sum, self.s, dict(axis=("x", "z")))
        self._run_single(self.s.sum, self.s.get_current_signal(), dict(axis=0))

    def test_sum_return_1d_signal(self):
        self._run_single(self.s.sum, self.s, dict(axis=self.s.axes_manager._axes))
        self._run_single(self.s.sum, self.s.get_current_signal(), dict(axis=0))

    def test_mean(self):
        self._run_single(self.s.mean, self.s, dict(axis=("x", "z")))

    def test_max(self):
        self._run_single(self.s.max, self.s, dict(axis=("x", "z")))

    def test_min(self):
        self._run_single(self.s.min, self.s, dict(axis=("x", "z")))

    def test_std(self):
        self._run_single(self.s.std, self.s, dict(axis=("x", "z")))

    def test_var(self):
        self._run_single(self.s.var, self.s, dict(axis=("x", "z")))

    def test_diff(self):
        self._run_single(self.s.diff, self.s, dict(axis=0))

    def test_derivative(self):
        self._run_single(self.s.derivative, self.s, dict(axis=0))

    def test_integrate_simpson(self):
        self._run_single(self.s.integrate_simpson, self.s, dict(axis=0))

    def test_integrate1D(self):
        self._run_single(self.s.integrate1D, self.s, dict(axis=0))

    def test_indexmax(self):
        self._run_single(self.s.indexmax, self.s, dict(axis=0))

    def test_valuemax(self):
        self._run_single(self.s.valuemax, self.s, dict(axis=0))

    @pytest.mark.xfail(
        sys.platform == "win32", reason="sometimes it does not run lazily on windows"
    )
    def test_rebin(self):
        s = self.s
        scale = (1, 2, 1, 2)
        self._run_single(s.rebin, s, dict(scale=scale))

    def test_as_spectrum(self):
        s = self.s
        self._run_single(s.as_signal1D, s, dict(spectral_axis=1))

    def test_as_image(self):
        s = self.s
        self._run_single(
            s.as_signal2D, s, dict(image_axes=(s.axes_manager.navigation_axes[0:2]))
        )

    def test_inav(self):
        s = self.s
        self._run_single(
            s.inav.__getitem__,
            s,
            {"slices": (slice(2, 4, None), slice(None), slice(0, 2, None))},
        )

    def test_isig(self):
        s = self.s
        self._run_single(s.isig.__getitem__, s, {"slices": (slice(2, 4, None),)})

    def test_inav_variance(self):
        s = self.s
        s.metadata.set_item("Signal.Noise_properties.variance", s.deepcopy())
        s1 = s.inav[2:4, 0:2]
        s2 = s.inav[2:4, 1:3]
        s.inav.__getitem__(
            slices=(slice(2, 4, None), slice(1, 3, None), slice(None)), out=s1
        )
        np.testing.assert_array_equal(
            s1.metadata.Signal.Noise_properties.variance.data,
            s2.metadata.Signal.Noise_properties.variance.data,
        )

    def test_isig_variance(self):
        s = self.s
        s.metadata.set_item("Signal.Noise_properties.variance", s.deepcopy())
        s1 = s.isig[2:4]
        s2 = s.isig[1:5]
        s.isig.__getitem__(slices=(slice(1, 5, None)), out=s1)
        np.testing.assert_array_equal(
            s1.metadata.Signal.Noise_properties.variance.data,
            s2.metadata.Signal.Noise_properties.variance.data,
        )

    def test_histogram_axis_changes(self):
        s = self.s
        h1 = s.get_histogram(bins=4)
        h2 = s.get_histogram(bins=5)
        s.get_histogram(bins=5, out=h1)
        np.testing.assert_array_equal(h1.data, h2.data)
        assert h1.axes_manager[-1].size == h2.axes_manager[-1].size

    def test_masked_array_mean(self):
        s = self.s
        if s._lazy:
            pytest.skip("LazySignals do not support masked arrays")
        mask = s.data > 0.5
        s.data = np.arange(s.data.size).reshape(s.data.shape)
        s.data = np.ma.masked_array(s.data, mask=mask)
        sr = s.mean(axis=("x", "z",))
        np.testing.assert_array_equal(
            sr.data.shape, [ax.size for ax in s.axes_manager[("y", "E")]]
        )
        print(sr.data.tolist())
        ref = [
            [
                202.28571428571428,
                203.28571428571428,
                182.0,
                197.66666666666666,
                187.0,
                177.8,
            ],
            [
                134.0,
                190.0,
                191.27272727272728,
                170.14285714285714,
                172.0,
                209.85714285714286,
            ],
            [168.0, 161.8, 162.8, 185.4, 197.71428571428572, 178.14285714285714],
            [240.0, 184.33333333333334, 260.0, 229.0, 173.2, 167.0],
        ]
        np.testing.assert_array_equal(sr.data, ref)

    def test_masked_array_sum(self):
        s = self.s
        if s._lazy:
            pytest.skip("LazySignals do not support masked arrays")
        mask = s.data > 0.5
        s.data = np.ma.masked_array(np.ones_like(s.data), mask=mask)
        sr = s.sum(axis=("x", "z",))
        np.testing.assert_array_equal(sr.data.sum(), (~mask).sum())

    @pytest.mark.parametrize("mask", (True, False))
    def test_sum_no_navigation_axis(self, mask):
        s = signals.Signal1D(np.arange(100))
        if mask:
            s.data = np.ma.masked_array(s.data, mask=(s < 50))
        # Since s haven't any navigation axis, it returns the same signal as
        # default
        np.testing.assert_array_equal(s, s.sum())
        # When we specify an axis, it actually takes the sum.
        np.testing.assert_array_equal(s.data.sum(), s.sum(axis=0))

    def test_masked_arrays_out(self):
        s = self.s
        if s._lazy:
            pytest.skip("LazySignals do not support masked arrays")
        mask = s.data > 0.5
        s.data = np.ones_like(s.data)
        s.data = np.ma.masked_array(s.data, mask=mask)
        self._run_single(s.sum, s, dict(axis=("x", "z")))

    def test_wrong_out_shape(self):
        s = self.s
        ss = s.sum()  # Sum over navigation, data shape (6,)
        with pytest.raises(ValueError):
            s.sum(axis=s.axes_manager._axes, out=ss)

    def test_wrong_out_shape_masked(self):
        s = self.s
        s.data = np.ma.array(s.data)
        ss = s.sum()  # Sum over navigation, data shape (6,)
        with pytest.raises(ValueError):
            s.sum(axis=s.axes_manager._axes, out=ss)
