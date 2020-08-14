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

import os
import glob
import warnings
import logging
import importlib

import numpy as np
from natsort import natsorted

from hyperspy.drawing.marker import markers_metadata_dict_to_markers
from hyperspy.misc.io.tools import ensure_directory
from hyperspy.misc.io.tools import overwrite as overwrite_method
from hyperspy.misc.utils import strlist2enumeration
from hyperspy.misc.utils import stack as stack_method
from hyperspy.io_plugins import io_plugins, default_write_ext
from hyperspy.exceptions import VisibleDeprecationWarning
from hyperspy.ui_registry import get_gui
from hyperspy.extensions import ALL_EXTENSIONS

_logger = logging.getLogger(__name__)


# Utility string:
f_error_fmt = (
    "\tFile %d:\n"
    "\t\t%d signals\n"
    "\t\tPath: %s")


def _escape_square_brackets(text):
    """Escapes pairs of square brackets in strings for glob.glob().

    Parameters
    ----------
    text : str
        The text to escape

    Returns
    -------
    str
        The escaped string

    Example
    -------
    >>> # Say there are two files like this:
    >>> # /home/data/afile[1x1].txt
    >>> # /home/data/afile[1x2].txt
    >>>
    >>> path = "/home/data/afile[*].txt"
    >>> glob.glob(path)
    []
    >>> glob.glob(_escape_square_brackets(path))
    ['/home/data/afile[1x2].txt', '/home/data/afile[1x1].txt']

    """
    import re

    rep = dict((re.escape(k), v) for k, v in {"[": "[[]", "]": "[]]"}.items())
    pattern = re.compile("|".join(rep.keys()))
    return pattern.sub(lambda m: rep[re.escape(m.group(0))], text)


def load(filenames=None,
         signal_type=None,
         stack=False,
         stack_axis=None,
         new_axis_name="stack_element",
         lazy=False,
         convert_units=False,
         escape_square_brackets=False,
         **kwds):
    """
    Load potentially multiple supported file into an hyperspy structure.

    Supported formats: hspy (HDF5), msa, Gatan dm3, Ripple (rpl+raw),
    Bruker bcf and spx, FEI ser and emi, SEMPER unf, EMD, EDAX spd/spc,
    tif, and a number of image formats.

    Depending on the number of datasets to load in the file, this function will
    return a HyperSpy signal instance or list of HyperSpy signal instances.

    Any extra keyword is passed to the corresponding reader. For
    available options see their individual documentation.

    Parameters
    ----------
    filenames :  None, str or list of strings
        The filename to be loaded. If None, a window will open to select
        a file to load. If a valid filename is passed in that single
        file is loaded. If multiple file names are passed in
        a list, a list of objects or a single object containing the data
        of the individual files stacked are returned. This behaviour is
        controlled by the `stack` parameter (see bellow). Multiple
        files can be loaded by using simple shell-style wildcards,
        e.g. 'my_file*.msa' loads all the files that starts
        by 'my_file' and has the '.msa' extension.
    signal_type : {None, "EELS", "EDS_SEM", "EDS_TEM", "", str}
        The acronym that identifies the signal type.
        The value provided may determine the Signal subclass assigned to the
        data.
        If None the value is read/guessed from the file. Any other value
        overrides the value stored in the file if any.
        For electron energy-loss spectroscopy use "EELS".
        For energy dispersive x-rays use "EDS_TEM"
        if acquired from an electron-transparent sample — as it is usually
        the case in a transmission electron  microscope (TEM) —,
        "EDS_SEM" if acquired from a non electron-transparent sample
        — as it is usually the case in a scanning electron  microscope (SEM).
        If "" (empty string) the value is not read from the file and is
        considered undefined.
    stack : bool
        If True and multiple filenames are passed in, stacking all
        the data into a single object is attempted. All files must match
        in shape. If each file contains multiple (N) signals, N stacks will be
        created, with the requirement that each file contains the same number
        of signals.
    stack_axis : {None, int, str}
        If None, the signals are stacked over a new axis. The data must
        have the same dimensions. Otherwise the
        signals are stacked over the axis given by its integer index or
        its name. The data must have the same shape, except in the dimension
        corresponding to `axis`.
    new_axis_name : string
        The name of the new axis when `axis` is None.
        If an axis with this name already
        exists it automatically append '-i', where `i` are integers,
        until it finds a name that is not yet in use.
    lazy : {None, bool}
        Open the data lazily - i.e. without actually reading the data from the
        disk until required. Allows opening arbitrary-sized datasets. The default
        is `False`.
    convert_units : {bool}
        If True, convert the units using the `convert_to_units` method of
        the `axes_manager`. If False, does nothing. The default is False.
    escape_square_brackets : bool, default False
        If True, and ``filenames`` is a str containing square brackets,
        then square brackets are escaped before wildcard matching with
        ``glob.glob()``. If False, square brackets are used to represent
        character classes (e.g. ``[a-z]`` matches lowercase letters.
    print_info: bool
        For SEMPER unf- and EMD (Berkeley)-files, if True (default is False)
        additional information read during loading is printed for a quick
        overview.
    downsample : int (1–4095)
        For Bruker bcf files, if set to integer (>=2) (default 1)
        bcf is parsed into down-sampled size array by given integer factor,
        multiple values from original bcf pixels are summed forming downsampled
        pixel. This allows to improve signal and conserve the memory with the
        cost of lower resolution.
    cutoff_at_kV : {None, int, float}
        For Bruker bcf files, if set to numerical (default is None)
        bcf is parsed into array with depth cutoff at coresponding given energy.
        This allows to conserve the memory, with cutting-off unused spectra's
        tail, or force enlargement of the spectra size.
    select_type : {'spectrum_image', 'image', 'single_spectrum', None}
        If `None` (default), all data are loaded.
        For Bruker bcf and Velox emd files: if one of 'spectrum_image', 'image'
        or 'single_spectrum', the loader return single_spectrumns either only
        the spectrum image or only the images (including EDS map for Velox emd
        files) or only the single spectra (for Velox emd files).
    first_frame : int (default 0)
        Only for Velox emd files: load only the data acquired after the
        specified fname.
    last_frame : None or int (default None)
        Only for Velox emd files: load only the data acquired up to specified
        fname. If None, load up the data to the end.
    sum_frames : bool (default is True)
        Only for Velox emd files: if False, load each EDS frame individually.
    sum_EDS_detectors : bool (default is True)
        Only for Velox emd files: if True, the signal from the different
        detector are summed. If False, a distinct signal is returned for each
        EDS detectors.
    rebin_energy : int, a multiple of the length of the energy dimension (default 1)
        Only for Velox emd files: rebin the energy axis by the integer provided
        during loading in order to save memory space.
    SI_dtype : numpy.dtype
        Only for Velox emd files: set the dtype of the spectrum image data in
        order to save memory space. If None, the default dtype from the Velox emd
        file is used.
    load_SI_image_stack : bool (default False)
        Only for Velox emd files: if True, load the stack of STEM images
        acquired simultaneously as the EDS spectrum image.
    dataset_path : None, str or list of str, optional
        For filetypes which support several datasets in the same file, this
        will only load the specified dataset. Several datasets can be loaded
        by using a list of strings. Only for EMD (NCEM) and hdf5 (USID) files.
    stack_group : bool, optional
        Only for EMD NCEM. Stack datasets of groups with common name. Relevant
        for emd file version >= 0.5 where groups can be named 'group0000',
        'group0001', etc.
    ignore_non_linear_dims : bool, default is True
        Only for HDF5 USID. If True, parameters that were varied non-linearly
        in the desired dataset will result in Exceptions.
        Else, all such non-linearly varied parameters will be treated as
        linearly varied parameters and a Signal object will be generated.
    only_valid_data : bool, optional
        Only for FEI emi/ser file in case of series or linescan with the
        acquisition stopped before the end: if True, load only the acquired
        data. If False, fill empty data with zeros. Default is False and this
        default value will change to True in version 2.0.

    Returns
    -------
    Signal instance or list of signal instances

    Examples
    --------
    Loading a single file providing the signal type:

    >>> d = hs.load('file.dm3', signal_type="EDS_TEM")

    Loading multiple files:

    >>> d = hs.load('file1.dm3','file2.dm3')

    Loading multiple files matching the pattern:

    >>> d = hs.load('file*.dm3')

    Loading multiple files containing square brackets:

    >>> d = hs.load('file[*].dm3', escape_square_brackets=True)

    Loading (potentially larger than the available memory) files lazily and
    stacking:

    >>> s = hs.load('file*.blo', lazy=True, stack=True)

    """
    deprecated = ['mmap_dir', 'load_to_memory']
    warn_str = "'{}' argument is deprecated, please use 'lazy' instead"
    for k in deprecated:
        if k in kwds:
            lazy = True
            warnings.warn(warn_str.format(k), VisibleDeprecationWarning)
            del kwds[k]
    kwds['signal_type'] = signal_type
    kwds['convert_units'] = convert_units
    if filenames is None:
        from hyperspy.signal_tools import Load
        load_ui = Load()
        get_gui(load_ui, toolkey="hyperspy.load")
        if load_ui.filename:
            filenames = load_ui.filename
            lazy = load_ui.lazy
        if filenames is None:
            raise ValueError("No file provided to reader")

    if isinstance(filenames, str):
        if escape_square_brackets:
            filenames = _escape_square_brackets(filenames)

        filenames = natsorted([f for f in glob.glob(filenames)
                               if os.path.isfile(f)])

        if not filenames:
            raise ValueError('No filename matches this pattern')

    elif not isinstance(filenames, (list, tuple)):
        raise ValueError(
            'The filenames parameter must be a list, tuple, string or None')
    if not filenames:
        raise ValueError('No file provided to reader.')
    else:
        if len(filenames) > 1:
            _logger.info('Loading individual files')
        if stack is True:
            # We are loading a stack!
            # Note that while each file might contain several signals, all
            # files are required to contain the same number of signals. We
            # therefore use the first file to determine the number of signals.
            for i, filename in enumerate(filenames):
                obj = load_single_file(filename, 
                                        lazy=lazy,
                                       **kwds)
                if i == 0:
                    # First iteration, determine number of signals, if several:
                    if isinstance(obj, (list, tuple)):
                        n = len(obj)
                    else:
                        n = 1
                    # Initialize signal 2D list:
                    signals = [[] for j in range(n)]
                else:
                    # Check that number of signals per file doesn't change
                    # for other files:
                    if isinstance(obj, (list, tuple)):
                        if n != len(obj):
                            raise ValueError(
                                "The number of sub-signals per file does not "
                                "match:\n" +
                                (f_error_fmt % (1, n, filenames[0])) +
                                (f_error_fmt % (i, len(obj), filename)))
                    elif n != 1:
                        raise ValueError(
                            "The number of sub-signals per file does not "
                            "match:\n" +
                            (f_error_fmt % (1, n, filenames[0])) +
                            (f_error_fmt % (i, len(obj), filename)))
                # Append loaded signals to 2D list:
                if n == 1:
                    signals[0].append(obj)
                elif n > 1:
                    for j in range(n):
                        signals[j].append(obj[j])
            # Next, merge the signals in the `stack_axis` direction:
            # When each file had N signals, we create N stacks!
            objects = []
            for i in range(n):
                signal = signals[i]   # Sublist, with len = len(filenames)
                signal = stack_method(
                    signal, axis=stack_axis, new_axis_name=new_axis_name,
                    lazy=lazy)
                signal.metadata.General.title = os.path.split(
                    os.path.split(os.path.abspath(filenames[0]))[0])[1]
                _logger.info('Individual files loaded correctly')
                _logger.info(signal._summary())
                objects.append(signal)
        else:
            # No stack, so simply we load all signals in all files separately
            objects = [load_single_file(filename, lazy=lazy,
                                        **kwds)
                       for filename in filenames]

        if len(objects) == 1:
            objects = objects[0]
    return objects


def load_single_file(filename, **kwds):
    """
    Load any supported file into an HyperSpy structure
    Supported formats: netCDF, msa, Gatan dm3, Ripple (rpl+raw),
    Bruker bcf, FEI ser and emi, EDAX spc and spd, hspy (HDF5), and SEMPER unf.

    Parameters
    ----------

    filename : string
        File name (including the extension)
        

    """
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"File: {filename} not found!")

    extension = os.path.splitext(filename)[1][1:]
    i = 0
    
    while extension.lower() not in io_plugins[i].file_extensions and \
            i < len(io_plugins) - 1:
        i += 1

    if i == len(io_plugins):
        # Try to load it with the python imaging library
        try:
            from hyperspy.io_plugins import image
            reader = image
            return load_with_reader(filename, reader, **kwds)
        except BaseException:
            raise IOError('If the file format is supported'
                          ' please report this error')
    else:
        reader = io_plugins[i]
        return load_with_reader(filename=filename, reader=reader, **kwds)


def load_with_reader(filename, reader, signal_type=None, convert_units=False,
                     **kwds):
    lazy = kwds.get('lazy', False)
    file_data_list = reader.file_reader(filename,
                                        **kwds)
    objects = []

    for signal_dict in file_data_list:
        if 'metadata' in signal_dict:
            if "Signal" not in signal_dict["metadata"]:
                signal_dict["metadata"]["Signal"] = {}
            if signal_type is not None:
                signal_dict['metadata']["Signal"]['signal_type'] = signal_type
            objects.append(dict2signal(signal_dict, lazy=lazy))
            folder, filename = os.path.split(os.path.abspath(filename))
            filename, extension = os.path.splitext(filename)
            objects[-1].tmp_parameters.folder = folder
            objects[-1].tmp_parameters.filename = filename
            objects[-1].tmp_parameters.extension = extension.replace('.', '')
            if convert_units:
                objects[-1].axes_manager.convert_units()
        else:
            # it's a standalone model
            continue

    if len(objects) == 1:
        objects = objects[0]
    return objects


def assign_signal_subclass(dtype, signal_dimension, signal_type="", lazy=False):
    """Given dtype, signal_dimension and signal_type, return the matching Signal subclass.

    See `hs.print_known_signal_types()` for a list of known signal_types,
    and the developer guide for details on how to add new signal_types.

    Parameters
    ----------
    dtype : :class:`~.numpy.dtype`
        Signal dtype
    signal_dimension : int
        Signal dimension
    signal_type : str, default ""
        Signal type. Optional. Will log a warning if it is unknown to HyperSpy.
    lazy : bool, default False
        If True, returns the matching LazySignal subclass.

    Returns
    -------
    Signal or subclass

    """
    # Check if parameter values are allowed:
    if np.issubdtype(dtype, np.complexfloating):
        dtype = 'complex'
    elif ('float' in dtype.name or 'int' in dtype.name or
          'void' in dtype.name or 'bool' in dtype.name or
          'object' in dtype.name):
        dtype = 'real'
    else:
        raise ValueError(f'Data type "{dtype.name}" not understood!')
    if not isinstance(signal_dimension, int) or signal_dimension < 0:
        raise ValueError("signal_dimension must be a positive interger")

    signals = {key: value for key, value in ALL_EXTENSIONS["signals"].items()
               if value["lazy"] == lazy}
    dtype_matches = {key: value for key, value in signals.items()
                     if value["dtype"] == dtype}
    dtype_dim_matches = {key: value for key, value in dtype_matches.items()
                         if signal_dimension == value["signal_dimension"]}
    dtype_dim_type_matches = {key: value for key, value in dtype_dim_matches.items()
                              if signal_type == value["signal_type"] or
                              "signal_type_aliases" in value and
                              signal_type in value["signal_type_aliases"]}

    valid_signal_types = [v["signal_type"] for v in signals.values()]
    valid_signal_aliases = [
        v["signal_type_aliases"]
        for v in signals.values()
        if "signal_type_aliases" in v
    ]
    valid_signal_aliases = [i for j in valid_signal_aliases for i in j]
    valid_signal_types.extend(valid_signal_aliases)

    if dtype_dim_type_matches:
        # Perfect match found
        signal_dict = dtype_dim_type_matches
    else:
        if signal_type not in set(valid_signal_types):
            _logger.warning(
                f"`signal_type='{signal_type}'` not understood. "
                f"See `hs.print_known_signal_types()` for a list of known signal types, "
                f"and the developer guide for details on how to add new signal_types."
            )

        # If the following dict is not empty, only signal_dimension and dtype match.
        # The dict should contain a general class for the given signal
        # dimension.
        signal_dict = {key: value for key, value in dtype_dim_matches.items()
                       if value["signal_type"] == ""}
        if not signal_dict:
            # no signal_dimension match either, hence select the general subclass for
            # correct dtype
            signal_dict = {key: value for key, value in dtype_matches.items()
                           if value["signal_dimension"] == -1
                           and value["signal_type"] == ""}
    # Sanity check
    if len(signal_dict) > 1:
        _logger.warning(
            "There is more than one kind of signal that matches "
            "the current specifications. This is unexpected behaviour. "
            "Please report this issue to the HyperSpy developers."
        )

    # Regardless of the number of signals in the dict we assign one.
    # The following should only raise an error if the base classes
    # are not correctly registered.
    for key, value in signal_dict.items():
        signal_class = getattr(importlib.import_module(value["module"]), key)

        return signal_class

def dict2signal(signal_dict, lazy=False):
    """Create a signal (or subclass) instance defined by a dictionary

    Parameters
    ----------
    signal_dict : dictionary

    Returns
    -------
    s : Signal or subclass

    """
    if "package" in signal_dict and signal_dict["package"]:
        try:
            importlib.import_module(signal_dict["package"])
        except ImportError:
            _logger.warning(
                f"This file contains a signal provided by the " +
                f'{signal_dict["package"]} Python package that is not ' +
                f'currently installed. The signal will be loaded into a '
                f'generic HyperSpy signal. Consider installing ' +
                f'{signal_dict["package"]} to load this dataset into its '
                f'original signal class.')
    signal_dimension = -1  # undefined
    signal_type = ""
    if "metadata" in signal_dict:
        mp = signal_dict["metadata"]
        if "Signal" in mp and "record_by" in mp["Signal"]:
            record_by = mp["Signal"]['record_by']
            if record_by == "spectrum":
                signal_dimension = 1
            elif record_by == "image":
                signal_dimension = 2
            del mp["Signal"]['record_by']
        if "Signal" in mp and "signal_type" in mp["Signal"]:
            signal_type = mp["Signal"]['signal_type']
    if "attributes" in signal_dict and "_lazy" in signal_dict["attributes"]:
        lazy = signal_dict["attributes"]["_lazy"]
    # "Estimate" signal_dimension from axes. It takes precedence over record_by
    if ("axes" in signal_dict and
        len(signal_dict["axes"]) == len(
            [axis for axis in signal_dict["axes"] if "navigate" in axis])):
            # If navigate is defined for all axes
        signal_dimension = len(
            [axis for axis in signal_dict["axes"] if not axis["navigate"]])
    elif signal_dimension == -1:
        # If not defined, all dimension are categorised as signal
        signal_dimension = signal_dict["data"].ndim
    signal = assign_signal_subclass(signal_dimension=signal_dimension,
                                    signal_type=signal_type,
                                    dtype=signal_dict['data'].dtype,
                                    lazy=lazy)(**signal_dict)
    if signal._lazy:
        signal._make_lazy()
    if signal.axes_manager.signal_dimension != signal_dimension:
        # This may happen when the signal dimension couldn't be matched with
        # any specialised subclass
        signal.axes_manager.set_signal_dimension(signal_dimension)
    if "post_process" in signal_dict:
        for f in signal_dict['post_process']:
            signal = f(signal)
    if "mapping" in signal_dict:
        for opattr, (mpattr, function) in signal_dict["mapping"].items():
            if opattr in signal.original_metadata:
                value = signal.original_metadata.get_item(opattr)
                if function is not None:
                    value = function(value)
                if value is not None:
                    signal.metadata.set_item(mpattr, value)
    if "metadata" in signal_dict and "Markers" in mp:
        markers_dict = markers_metadata_dict_to_markers(
            mp['Markers'],
            axes_manager=signal.axes_manager)
        del signal.metadata.Markers
        signal.metadata.Markers = markers_dict
    return signal


def save(filename, signal, overwrite=None, **kwds):
    """
    Save hyperspy signal to a file.

    A list of plugins supporting file saving can be found here: 
    http://hyperspy.org/hyperspy-doc/current/user_guide/io.html#supported-formats

    Any extra keyword is passed to the corresponding save method in the
    io_plugin. 
    For available options see their individual documentation.

    Parameters
    ----------
    filename :  None or str
        The filename to save the signal to. 
    signal :  Hyperspy signal
        The signal to be saved to file     
    overwrite : None or Bool (default, None)
        If None and a file exists the user will be prompted to on whether to 
        overwrite. If False and a file exists the file will not be written.
        If True and a file exists the file will be overwritten without 
        prompting
    
    """
    extension = os.path.splitext(filename)[1][1:]
    if extension == '':
        extension = "hspy"
        filename = filename + '.' + extension
    writer = None
    for plugin in io_plugins:
        if extension.lower() in plugin.file_extensions:
            writer = plugin
            break

    if writer is None:
        raise ValueError(
            ('.%s does not correspond to any supported format. Supported ' +
             'file extensions are: %s') %
            (extension, strlist2enumeration(default_write_ext)))
    else:
        # Check if the writer can write
        sd = signal.axes_manager.signal_dimension
        nd = signal.axes_manager.navigation_dimension
        if writer.writes is False:
            raise ValueError('Writing to this format is not '
                             'supported, supported file extensions are: %s ' %
                             strlist2enumeration(default_write_ext))
        if writer.writes is not True and (sd, nd) not in writer.writes:
            yes_we_can = [plugin.format_name for plugin in io_plugins
                          if plugin.writes is True or
                          plugin.writes is not False and
                          (sd, nd) in plugin.writes]
            raise IOError('This file format cannot write this data. '
                          'The following formats can: %s' %
                          strlist2enumeration(yes_we_can))
        ensure_directory(filename)
        is_file = os.path.isfile(filename)
        if overwrite is None:
            write = overwrite_method(filename)  # Ask what to do
        elif overwrite is True or (overwrite is False and not is_file):
            write = True  # Write the file
        elif overwrite is False and is_file:
            write = False  # Don't write the file
        else:
            raise ValueError("`overwrite` parameter can only be None, True or "
                             "False.")
        if write:
            writer.file_writer(filename, signal, **kwds)
            _logger.info('The %s file was created' % filename)
            folder, filename = os.path.split(os.path.abspath(filename))
            signal.tmp_parameters.set_item('folder', folder)
            signal.tmp_parameters.set_item('filename',
                                           os.path.splitext(filename)[0])
            signal.tmp_parameters.set_item('extension', extension)
