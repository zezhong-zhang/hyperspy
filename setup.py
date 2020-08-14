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

from __future__ import print_function

import hyperspy.Release as Release
from distutils.errors import CompileError, DistutilsPlatformError
import distutils.ccompiler
import distutils.sysconfig
import itertools
import subprocess
import os
import warnings
from tempfile import TemporaryDirectory
from setuptools import setup, Extension, Command
import sys

v = sys.version_info
if v[0] != 3:
    error = "ERROR: From version 0.8.4 HyperSpy requires Python 3. " \
            "For Python 2.7 install Hyperspy 0.8.3 e.g. " \
            "$ pip install --upgrade hyperspy==0.8.3"
    print(error, file=sys.stderr)
    sys.exit(1)


# stuff to check presence of compiler:


setup_path = os.path.dirname(__file__)


install_req = ['scipy>=1.0.1',
               'matplotlib>=2.2.3',
               'numpy>=1.13.0',
               'traits>=4.5.0',
               'natsort',
               'requests',
               'tqdm>=4.9.0',
               'sympy',
               'dill',
               'h5py>=2.3',
               'python-dateutil>=2.5.0',
               'ipyparallel',
               'dask[array]>2.0',
               'scikit-image>=0.15',
               'pint>=0.10',
               'statsmodels',
               'numexpr',
               'sparse',
               'imageio',
               'pyyaml',
               'PTable',
               'tifffile[all]>=2018.10.18',
               'numba',
               ]

extras_require = {
    "learning": ['scikit-learn'],
    "gui-jupyter": ["hyperspy_gui_ipywidgets>=1.1.0"],
    "gui-traitsui": ["hyperspy_gui_traitsui>=1.1.0"],
    "mrcz": ["blosc>=1.5", 'mrcz>=0.3.6'],
    "speed": ["cython"],
    "usid": ["pyUSID>=0.0.7"],
    # bug in pip: matplotib is ignored here because it is already present in
    # install_requires.
    "tests": ["pytest>=3.6", "pytest-mpl", "matplotlib>=3.1"],
    "coverage":["pytest-cov", "codecov"],
    # required to build the docs
    "build-doc": ["sphinx>=1.7", "sphinx_rtd_theme"],
}

# Don't include "tests" and "docs" requirements since "all" is designed to be
# used for user installation.
runtime_extras_require = {x: extras_require[x] for x in extras_require.keys()
                          if x not in ["tests", "coverage", "build-doc"]}
extras_require["all"] = list(itertools.chain(*list(
    runtime_extras_require.values())))

extras_require["dev"] = list(itertools.chain(*list(extras_require.values())))


def update_version(version):
    release_path = "hyperspy/Release.py"
    lines = []
    with open(release_path, "r") as f:
        for line in f:
            if line.startswith("version = "):
                line = "version = \"%s\"\n" % version
            lines.append(line)
    with open(release_path, "w") as f:
        f.writelines(lines)


# Extensions. Add your extension here:
raw_extensions = [Extension("hyperspy.io_plugins.unbcf_fast",
                            [os.path.join('hyperspy', 'io_plugins', 'unbcf_fast.pyx')]),
                  ]

cleanup_list = []
for leftover in raw_extensions:
    path, ext = os.path.splitext(leftover.sources[0])
    if ext in ('.pyx', '.py'):
        cleanup_list.append(''.join([os.path.join(setup_path, path), '.c*']))
        if os.name == 'nt':
            bin_ext = '.cpython-*.pyd'
        else:
            bin_ext = '.cpython-*.so'
        cleanup_list.append(''.join([os.path.join(setup_path, path), bin_ext]))


def count_c_extensions(extensions):
    c_num = 0
    for extension in extensions:
        # if first source file with extension *.c or *.cpp exists
        # it is cythonised or pure c/c++ extension:
        sfile = extension.sources[0]
        path, ext = os.path.splitext(sfile)
        if os.path.exists(path + '.c') or os.path.exists(path + '.cpp'):
            c_num += 1
    return c_num


def cythonize_extensions(extensions):
    try:
        from Cython.Build import cythonize
        return cythonize(extensions)
    except ImportError:
        warnings.warn("""WARNING: cython required to generate fast c code is not found on this system.
Only slow pure python alternative functions will be available.
To use fast implementation of some functions writen in cython either:
a) install cython and re-run the installation,
b) try alternative source distribution containing cythonized C versions of fast code,
c) use binary distribution (i.e. wheels, egg).""")
        return []


def no_cythonize(extensions):
    for extension in extensions:
        sources = []
        for sfile in extension.sources:
            path, ext = os.path.splitext(sfile)
            if ext in ('.pyx', '.py'):
                if extension.language == 'c++':
                    ext = '.cpp'
                else:
                    ext = '.c'
                sfile = path + ext
            sources.append(sfile)
        extension.sources[:] = sources
    return extensions


# to cythonize, or not to cythonize... :
if len(raw_extensions) > count_c_extensions(raw_extensions):
    extensions = cythonize_extensions(raw_extensions)
else:
    extensions = no_cythonize(raw_extensions)


# to compile or not to compile... depends if compiler is present:
compiler = distutils.ccompiler.new_compiler()
assert isinstance(compiler, distutils.ccompiler.CCompiler)
distutils.sysconfig.customize_compiler(compiler)
try:
    with TemporaryDirectory() as tmpdir:
        compiler.compile([os.path.join(setup_path, 'hyperspy', 'misc', 'etc',
                                   'test_compilers.c')], output_dir=tmpdir)
except (CompileError, DistutilsPlatformError):
    warnings.warn("""WARNING: C compiler can't be found.
Only slow pure python alternative functions will be available.
To use fast implementation of some functions writen in cython/c either:
a) check that you have compiler (EXACTLY SAME as your python
distribution was compiled with) installed,
b) use binary distribution of hyperspy (i.e. wheels, egg, (only osx and win)).
Installation will continue in 5 sec...""")
    extensions = []
    from time import sleep
    sleep(5)  # wait 5 secs for user to notice the message


class Recythonize(Command):

    """cythonize all extensions"""
    description = "(re-)cythonize all changed cython extensions"

    user_options = []

    def initialize_options(self):
        """init options"""
        pass

    def finalize_options(self):
        """finalize options"""
        pass

    def run(self):
        # if there is no cython it is supposed to fail:
        from Cython.Build import cythonize
        global raw_extensions
        global extensions
        cythonize(extensions)


class update_version_when_dev:

    def __enter__(self):
        self.release_version = Release.version

        # Get the hash from the git repository if available
        self.restore_version = False
        if self.release_version.endswith(".dev"):
            p = subprocess.Popen(["git", "describe",
                                  "--tags", "--dirty", "--always"],
                                 stdout=subprocess.PIPE,
                                 shell=True)
            stdout = p.communicate()[0]
            if p.returncode != 0:
                # Git is not available, we keep the version as is
                self.restore_version = False
                self.version = self.release_version
            else:
                gd = stdout[1:].strip().decode()
                # Remove the tag
                gd = gd[gd.index("-") + 1:]
                self.version = self.release_version + "+git."
                self.version += gd.replace("-", ".")
                update_version(self.version)
                self.restore_version = True
        else:
            self.version = self.release_version
        return self.version

    def __exit__(self, type, value, traceback):
        if self.restore_version is True:
            update_version(self.release_version)


with update_version_when_dev() as version:
    setup(
        name="hyperspy",
        package_dir={'hyperspy': 'hyperspy'},
        version=version,
        ext_modules=extensions,
        packages=['hyperspy',
                  'hyperspy.datasets',
                  'hyperspy._components',
                  'hyperspy.datasets',
                  'hyperspy.io_plugins',
                  'hyperspy.docstrings',
                  'hyperspy.drawing',
                  'hyperspy.drawing._markers',
                  'hyperspy.drawing._widgets',
                  'hyperspy.learn',
                  'hyperspy._signals',
                  'hyperspy.utils',
                  'hyperspy.tests',
                  'hyperspy.tests.axes',
                  'hyperspy.tests.component',
                  'hyperspy.tests.datasets',
                  'hyperspy.tests.drawing',
                  'hyperspy.tests.io',
                  'hyperspy.tests.learn',
                  'hyperspy.tests.model',
                  'hyperspy.tests.samfire',
                  'hyperspy.tests.signal',
                  'hyperspy.tests.utils',
                  'hyperspy.tests.misc',
                  'hyperspy.models',
                  'hyperspy.misc',
                  'hyperspy.misc.eels',
                  'hyperspy.misc.eds',
                  'hyperspy.misc.io',
                  'hyperspy.misc.holography',
                  'hyperspy.misc.machine_learning',
                  'hyperspy.external',
                  'hyperspy.external.mpfit',
                  'hyperspy.external.astropy',
                  'hyperspy.samfire_utils',
                  'hyperspy.samfire_utils.segmenters',
                  'hyperspy.samfire_utils.weights',
                  'hyperspy.samfire_utils.goodness_of_fit_tests',
                  ],
        python_requires='~=3.6',
        install_requires=install_req,
        tests_require=["pytest>=3.0.2"],
        extras_require=extras_require,
        package_data={
            'hyperspy':
            [
                'tests/drawing/*.png',
                'tests/drawing/data/*.hspy',
                'tests/drawing/plot_signal/*.png',
                'tests/drawing/plot_signal1d/*.png',
                'tests/drawing/plot_signal2d/*.png',
                'tests/drawing/plot_markers/*.png',
                'tests/drawing/plot_model1d/*.png',
                'tests/drawing/plot_model/*.png',
                'tests/drawing/plot_roi/*.png',
                'misc/eds/example_signals/*.hdf5',
                'misc/holography/example_signals/*.hdf5',
                'tests/drawing/plot_mva/*.png',
                'tests/drawing/plot_signal/*.png',
                'tests/drawing/plot_signal1d/*.png',
                'tests/drawing/plot_signal2d/*.png',
                'tests/drawing/plot_markers/*.png',
                'tests/drawing/plot_widgets/*.png',
                'tests/drawing/plot_signal_tools/*.png',
                'tests/io/blockfile_data/*.blo',
                'tests/io/dens_data/*.dens',
                'tests/io/dm_stackbuilder_plugin/test_stackbuilder_imagestack.dm3',
                'tests/io/dm3_1D_data/*.dm3',
                'tests/io/dm3_2D_data/*.dm3',
                'tests/io/dm3_3D_data/*.dm3',
                'tests/io/dm4_1D_data/*.dm4',
                'tests/io/dm4_2D_data/*.dm4',
                'tests/io/dm4_3D_data/*.dm4',
                'tests/io/dm3_locale/*.dm3',
                'tests/io/FEI_new/*.emi',
                'tests/io/FEI_new/*.ser',
                'tests/io/FEI_new/*.npy',
                'tests/io/FEI_old/*.emi',
                'tests/io/FEI_old/*.ser',
                'tests/io/FEI_old/*.npy',
                'tests/io/msa_files/*.msa',
                'tests/io/hdf5_files/*.hdf5',
                'tests/io/hdf5_files/*.hspy',
                'tests/io/tiff_files/*.tif',
                'tests/io/tiff_files/*.dm3',
                'tests/io/npy_files/*.npy',
                'tests/io/unf_files/*.unf',
                'tests/io/bruker_data/*.bcf',
                'tests/io/bruker_data/*.json',
                'tests/io/bruker_data/*.npy',
                'tests/io/bruker_data/*.spx',
                'tests/io/ripple_files/*.rpl',
                'tests/io/ripple_files/*.raw',
                'tests/io/emd_files/*.emd',
                'tests/io/emd_files/fei_emd_files.zip',
                'tests/io/protochips_data/*.npy',
                'tests/io/protochips_data/*.csv',
                'tests/io/nexus_files/*.nxs',
                'tests/io/empad_data/*.xml',
                'tests/io/phenom_data/*.elid',
                'tests/io/sur_data/*.pro',
                'tests/io/sur_data/*.sur',
                'tests/signal/data/test_find_peaks1D_ohaver.hdf5',
                'tests/signal/data/*.hspy',
                'hyperspy_extension.yaml',
            ],
        },
        author=Release.authors['all'][0],
        description=Release.description,
        long_description=open('README.rst').read(),
        license=Release.license,
        platforms=Release.platforms,
        url=Release.url,
        project_urls=Release.PROJECT_URLS,
        keywords=Release.keywords,
        cmdclass={
            'recythonize': Recythonize,
        },
        classifiers=[
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Development Status :: 4 - Beta",
            "Environment :: Console",
            "Intended Audience :: Science/Research",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
            "Natural Language :: English",
            "Operating System :: OS Independent",
            "Topic :: Scientific/Engineering",
            "Topic :: Scientific/Engineering :: Physics",
        ],
    )
