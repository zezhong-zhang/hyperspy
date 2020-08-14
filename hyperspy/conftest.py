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

# Configure mpl and traits to work in a headless system
from traits.etsconfig.api import ETSConfig
ETSConfig.toolkit = "null"

# pytest-mpl 0.7 already import pyplot, so setting the matplotlib backend to
# 'agg' as early as we can is useless for testing.
import matplotlib.pyplot as plt

import pytest
import numpy as np
import matplotlib
import hyperspy.api as hs


matplotlib.rcParams['figure.max_open_warning'] = 25
matplotlib.rcParams['interactive'] = False
hs.preferences.Plot.saturated_pixels = 0.0
hs.preferences.Plot.cmap_navigator = 'viridis'
hs.preferences.Plot.cmap_signal = 'viridis'

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "parallel: a test that is itself parallel and should be run serially."
    )

@pytest.fixture(autouse=True)
def add_np(doctest_namespace):
    doctest_namespace['np'] = np
    doctest_namespace['plt'] = plt
    doctest_namespace['hs'] = hs


@pytest.fixture
def pdb_cmdopt(request):
    return request.config.getoption("--pdb")


def setup_module(mod, pdb_cmdopt):
    if pdb_cmdopt:
        import dask
        dask.set_options(get=dask.local.get_sync)

from matplotlib.testing.conftest import mpl_test_settings
