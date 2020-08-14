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

import itertools

import numpy as np
import pytest

from hyperspy.components1d import GaussianHF
from hyperspy.signals import Signal1D
from hyperspy.utils import stack

sqrt2pi = np.sqrt(2 * np.pi)
sigma2fwhm = 2 * np.sqrt(2 * np.log(2))

TRUE_FALSE_2_TUPLE = [p for p in itertools.product((True, False), repeat=2)]


def test_function():
    g = GaussianHF()
    g.centre.value = 1
    g.fwhm.value = 2
    g.height.value = 3
    assert g.function(2) == 1.5
    assert g.function(1) == 3

def test_integral_as_signal():
    s = Signal1D(np.zeros((2, 3, 100)))
    g1 = GaussianHF(fwhm=3.33, centre=20.)
    h_ref = np.linspace(0.1, 3.0, s.axes_manager.navigation_size)
    for d, h in zip(s._iterate_signal(), h_ref):
        g1.height.value = h
        d[:] = g1.function(s.axes_manager.signal_axes[0].axis)
    m = s.create_model()
    g2 = GaussianHF()
    m.append(g2)
    g2.estimate_parameters(s, 0, 100, True)
    # HyperSpy 2.0: remove setting iterpath='serpentine'
    m.multifit(iterpath='serpentine')
    s_out = g2.integral_as_signal()
    ref = (h_ref * 3.33 * sqrt2pi / sigma2fwhm).reshape(s_out.data.shape)
    np.testing.assert_allclose(s_out.data, ref)

@pytest.mark.parametrize(("only_current", "binned"), TRUE_FALSE_2_TUPLE)
def test_estimate_parameters_binned(only_current, binned):
    s = Signal1D(np.empty((100,)))
    s.metadata.Signal.binned = binned
    axis = s.axes_manager.signal_axes[0]
    axis.scale = 2.
    axis.offset = -30
    g1 = GaussianHF(50015.156, 23, 10)
    s.data = g1.function(axis.axis)
    g2 = GaussianHF()
    factor = axis.scale if binned else 1
    assert g2.estimate_parameters(s, axis.low_value, axis.high_value,
                                  only_current=only_current)
    assert g2.binned == binned
    np.testing.assert_allclose(g1.height.value, g2.height.value * factor)
    assert abs(g2.centre.value - g1.centre.value) <= 1e-3
    assert abs(g2.fwhm.value - g1.fwhm.value) <= 0.1

@pytest.mark.parametrize(("binned"), (True, False))
def test_function_nd(binned):
    s = Signal1D(np.empty((100,)))
    axis = s.axes_manager.signal_axes[0]
    axis.scale = 2.
    axis.offset = -30
    g1 = GaussianHF(50015.156, 23, 10)
    s.data = g1.function(axis.axis)
    s.metadata.Signal.binned = binned

    s2 = stack([s] * 2)
    g2 = GaussianHF()
    factor = axis.scale if binned else 1
    g2.estimate_parameters(s2, axis.low_value, axis.high_value, False)
    assert g2.binned == binned
    # TODO: sort out while the rtol to be so high...
    np.testing.assert_allclose(g2.function_nd(axis.axis) * factor, s2.data, rtol=0.05)

def test_util_sigma_set():
    g1 = GaussianHF()
    g1.sigma = 1.0
    np.testing.assert_allclose(g1.fwhm.value, 1.0 * sigma2fwhm)

def test_util_sigma_get():
    g1 = GaussianHF()
    g1.fwhm.value = 1.0
    np.testing.assert_allclose(g1.sigma, 1.0 / sigma2fwhm)

def test_util_sigma_getset():
    g1 = GaussianHF()
    g1.sigma = 1.0
    np.testing.assert_allclose(g1.sigma, 1.0)

def test_util_fwhm_set():
    g1 = GaussianHF(fwhm=0.33)
    g1.A = 1.0
    np.testing.assert_allclose(g1.height.value, 1.0 * sigma2fwhm / (
                    0.33 * sqrt2pi))

def test_util_fwhm_get():
    g1 = GaussianHF(fwhm=0.33)
    g1.height.value = 1.0
    np.testing.assert_allclose(g1.A, 1.0 * sqrt2pi * 0.33 / sigma2fwhm)

def test_util_fwhm_getset():
    g1 = GaussianHF(fwhm=0.33)
    g1.A = 1.0
    np.testing.assert_allclose(g1.A, 1.0)
