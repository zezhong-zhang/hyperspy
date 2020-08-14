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

import copy
import importlib
import logging
import os
import tempfile
import warnings
from contextlib import contextmanager
from distutils.version import LooseVersion
from functools import partial

import dill
import numpy as np
import scipy
import scipy.odr as odr
from IPython.display import display, display_pretty
from scipy.linalg import svd
from scipy.optimize import (
    differential_evolution,
    leastsq,
    least_squares,
    minimize,
    OptimizeResult
)

from hyperspy.component import Component
from hyperspy.defaults_parser import preferences
from hyperspy.docstrings.model import FIT_PARAMETERS_ARG
from hyperspy.docstrings.signal import (MAX_WORKERS_ARG, PARALLEL_ARG,
                                        SHOW_PROGRESSBAR_ARG)
from hyperspy.events import Event, Events, EventSuppressor
from hyperspy.exceptions import VisibleDeprecationWarning
from hyperspy.extensions import ALL_EXTENSIONS
from hyperspy.external.mpfit.mpfit import mpfit
from hyperspy.external.progressbar import progressbar
from hyperspy.misc.export_dictionary import (export_to_dictionary,
                                             load_from_dictionary,
                                             parse_flag_string,
                                             reconstruct_object)
from hyperspy.misc.model_tools import current_model_values
from hyperspy.misc.slicing import copy_slice_from_whitelist
from hyperspy.misc.utils import (dummy_context_manager, shorten_name, slugify,
                                 stash_active_state)
from hyperspy.signal import BaseSignal
from hyperspy.ui_registry import add_gui_method

_logger = logging.getLogger(__name__)

_COMPONENTS = ALL_EXTENSIONS["components1D"]
_COMPONENTS.update(ALL_EXTENSIONS["components1D"])


def _check_deprecated_optimizer(optimizer):
    """Can be removed in HyperSpy 2.0"""
    deprecated_optimizer_dict = {
        "fmin": "Nelder-Mead",
        "fmin_cg": "CG",
        "fmin_ncg": "Newton-CG",
        "fmin_bfgs": "BFGS",
        "fmin_l_bfgs_b": "L-BFGS-B",
        "fmin_tnc": "TNC",
        "fmin_powell": "Powell",
        "mpfit": "lm",
        "leastsq": "lm",
    }
    check_optimizer = deprecated_optimizer_dict.get(optimizer, None)

    if check_optimizer:
        warnings.warn(
            f"`{optimizer}` has been deprecated and will be removed "
            f"in HyperSpy 2.0. Please use `{check_optimizer}` instead.",
            VisibleDeprecationWarning,
        )
        optimizer = check_optimizer

    return optimizer

def reconstruct_component(comp_dictionary, **init_args):
    _id = comp_dictionary['_id_name']
    if _id in _COMPONENTS:
        _class = getattr(
            importlib.import_module(
                _COMPONENTS[_id]["module"]), _COMPONENTS[_id]["class"])
    elif "_class_dump" in comp_dictionary:
        # When a component is not registered using the extension mechanism,
        # it is serialized using dill.
        _class = dill.loads(comp_dictionary['_class_dump'])
    else:
        raise ImportError(
            f'Loading the {comp_dictionary["class"]} component ' +
            'failed because the component is provided by the ' +
            f'{comp_dictionary["package"]} Python package, but ' +
            f'{comp_dictionary["package"]} is not installed.')
    return _class(**init_args)


class ModelComponents(object):

    """Container for model components.

    Useful to provide tab completion when running in IPython.

    """

    def __init__(self, model):
        self._model = model

    def __repr__(self):
        signature = "%4s | %19s | %19s | %19s"
        ans = signature % ('#',
                           'Attribute Name',
                           'Component Name',
                           'Component Type')
        ans += "\n"
        ans += signature % ('-' * 4, '-' * 19, '-' * 19, '-' * 19)
        if self._model:
            for i, c in enumerate(self._model):
                ans += "\n"
                name_string = c.name
                variable_name = slugify(name_string, valid_variable_name=True)
                component_type = c.__class__.__name__

                variable_name = shorten_name(variable_name, 19)
                name_string = shorten_name(name_string, 19)
                component_type = shorten_name(component_type, 19)

                ans += signature % (i,
                                    variable_name,
                                    name_string,
                                    component_type)
        return ans


@add_gui_method(toolkey="hyperspy.Model")
class BaseModel(list):

    """Model and data fitting tools applicable to signals of both one and two
    dimensions.

    Models of one-dimensional signals should use the
    :py:class:`~hyperspy.models.model1d` and models of two-dimensional signals
    should use the :class:`~hyperspy.models.model2d`.

    A model is constructed as a linear combination of
    :py:mod:`~hyperspy._components` that are added to the model using the
    :py:meth:`~hyperspy.model.BaseModel.append` or
    :py:meth:`~hyperspy.model.BaseModel.extend`. There are many predefined
    components available in the in the :py:mod:`~hyperspy._components`
    module. If needed, new components can be created easily using the code of
    existing components as a template.

    Once defined, the model can be fitted to the data using :meth:`fit` or
    :py:meth:`~hyperspy.model.BaseModel.multifit`. Once the optimizer reaches
    the convergence criteria or the maximum number of iterations the new value
    of the component parameters are stored in the components.

    It is possible to access the components in the model by their name or by
    the index in the model. An example is given at the end of this docstring.

    Attributes
    ----------

    signal : BaseSignal instance
        It contains the data to fit.
    chisq : A BaseSignal of floats
        Chi-squared of the signal (or np.nan if not yet fit)
    dof : A BaseSignal of integers
        Degrees of freedom of the signal (0 if not yet fit)
    red_chisq : BaseSignal instance
        Reduced chi-squared.
    components : `ModelComponents` instance
        The components of the model are attributes of this class. This provides
        a convenient way to access the model components when working in IPython
        as it enables tab completion.

    Methods
    -------

    append
        Append one component to the model.
    extend
        Append multiple components to the model.
    remove
        Remove component from model.
    as_signal
        Generate a BaseSignal instance (possible multidimensional)
        from the model.
    store_current_values
        Store the value of the parameters at the current position.
    fetch_stored_values
        Fetch stored values of the parameters.
    update_plot
        Force a plot update. (In most cases the plot should update
        automatically.)
    set_signal_range, remove_signal range, reset_signal_range,
    add signal_range.
        Customize the signal range to fit.
    fit, multifit
        Fit the model to the data at the current position or the
        full dataset.
    save_parameters2file, load_parameters_from_file
        Save/load the parameter values to/from a file.
    plot
        Plot the model and the data.
    enable_plot_components, disable_plot_components
        Plot each component separately. (Use after `plot`.)
    set_current_values_to
        Set the current value of all the parameters of the given component as
        the value for all the dataset.
    export_results
        Save the value of the parameters in separate files.
    plot_results
        Plot the value of all parameters at all positions.
    print_current_values
        Print the value of the parameters at the current position.
    enable_adjust_position, disable_adjust_position
        Enable/disable interactive adjustment of the position of the components
        that have a well defined position. (Use after `plot`).
    fit_component
        Fit just the given component in the given signal range, that can be
        set interactively.
    set_parameters_not_free, set_parameters_free
        Fit the `free` status of several components and parameters at once.
    set_parameters_value
        Set the value of a parameter in components in a model to a specified
        value.
    as_dictionary
        Exports the model to a dictionary that can be saved in a file.

    See also
    --------

    :py:class:`~hyperspy.models.model1d.Model1D`
    :py:class:`~hyperspy.models.model2d.Model2D`

    """

    def __init__(self):

        self.events = Events()
        self.events.fitted = Event("""
            Event that triggers after fitting changed at least one parameter.

            The event triggers after the fitting step was finished, and only of
            at least one of the parameters changed.

            Arguments
            ---------
            obj : Model
                The Model that the event belongs to
            """, arguments=['obj'])

    def __hash__(self):
        # This is needed to simulate a hashable object so that PySide does not
        # raise an exception when using windows.connect
        return id(self)

    def store(self, name=None):
        """Stores current model in the original signal

        Parameters
        ----------
            name : {None, str}
                Stored model name. Auto-generated if left empty
        """
        if self.signal is None:
            raise ValueError("Cannot store models with no signal")
        s = self.signal
        s.models.store(self, name)

    def save(self, file_name, name=None, **kwargs):
        """Saves signal and its model to a file

        Parameters
        ----------
            file_name : str
                Name of the file
            name : {None, str}
                Stored model name. Auto-generated if left empty
            **kwargs :
                Other keyword arguments are passed onto `BaseSignal.save()`
        """
        if self.signal is None:
            raise ValueError("Currently cannot save models with no signal")
        else:
            self.store(name)
            self.signal.save(file_name, **kwargs)

    def _load_dictionary(self, dic):
        """Load data from dictionary.

        Parameters
        ----------
        dic : dict
            A dictionary containing at least the following fields:

            * _whitelist: a dictionary with keys used as references of save
              attributes, for more information, see
              :py:func:`~hyperspy.misc.export_dictionary.load_from_dictionary`
            * components: a dictionary, with information about components of
              the model (see
              :py:meth:`~hyperspy.component.Parameter.as_dictionary`
              documentation for more details)
            * any field from _whitelist.keys()
        """

        if 'components' in dic:
            while len(self) != 0:
                self.remove(self[0])
            id_dict = {}

            for comp in dic['components']:
                init_args = {}
                for k, flags_str in comp['_whitelist'].items():
                    if not len(flags_str):
                        continue
                    if 'init' in parse_flag_string(flags_str):
                        init_args[k] = reconstruct_object(flags_str, comp[k])

                self.append(reconstruct_component(comp, **init_args))
                id_dict.update(self[-1]._load_dictionary(comp))
            # deal with twins:
            for comp in dic['components']:
                for par in comp['parameters']:
                    for tw in par['_twins']:
                        id_dict[tw].twin = id_dict[par['self']]

        if '_whitelist' in dic:
            load_from_dictionary(self, dic)

    def __repr__(self):
        title = self.signal.metadata.General.title
        class_name = str(self.__class__).split("'")[1].split('.')[-1]

        if len(title):
            return "<%s, title: %s>" % (
                class_name, self.signal.metadata.General.title)
        else:
            return "<%s>" % class_name

    def _get_component(self, thing):
        if isinstance(thing, int) or isinstance(thing, str):
            thing = self[thing]
        elif np.iterable(thing):
            thing = [self._get_component(athing) for athing in thing]
            return thing
        elif not isinstance(thing, Component):
            raise ValueError("Not a component or component id.")
        if thing in self:
            return thing
        else:
            raise ValueError("The component is not in the model.")

    def insert(self, **kwargs):
        raise NotImplementedError

    def append(self, thing):
        """Add component to Model.

        Parameters
        ----------
        thing: `Component` instance.
        """
        if not isinstance(thing, Component):
            raise ValueError(
                "Only `Component` instances can be added to a model")
        # Check if any of the other components in the model has the same name
        if thing in self:
            raise ValueError("Component already in model")
        component_name_list = [component.name for component in self]
        if thing.name:
            name_string = thing.name
        else:
            name_string = thing.__class__.__name__

        if name_string in component_name_list:
            temp_name_string = name_string
            index = 0
            while temp_name_string in component_name_list:
                temp_name_string = name_string + "_" + str(index)
                index += 1
            name_string = temp_name_string
        thing.name = name_string

        thing._axes_manager = self.axes_manager
        thing._create_arrays()
        list.append(self, thing)
        thing.model = self
        setattr(self.components, slugify(name_string,
                                         valid_variable_name=True), thing)
        if self._plot_active is True:
            self._connect_parameters2update_plot(components=[thing])
        self.update_plot()

    def extend(self, iterable):
        for object in iterable:
            self.append(object)

    def __delitem__(self, thing):
        thing = self.__getitem__(thing)
        self.remove(thing)

    def remove(self, thing):
        """Remove component from model.

        Examples
        --------

        >>> s = hs.signals.Signal1D(np.empty(1))
        >>> m = s.create_model()
        >>> g = hs.model.components1D.Gaussian()
        >>> m.append(g)

        You could remove `g` like this

        >>> m.remove(g)

        Like this:

        >>> m.remove("Gaussian")

        Or like this:

        >>> m.remove(0)

        """
        thing = self._get_component(thing)
        if not np.iterable(thing):
            thing = [thing, ]
        for athing in thing:
            for parameter in athing.parameters:
                # Remove the parameter from its twin _twins
                parameter.twin = None
                for twin in [twin for twin in parameter._twins]:
                    twin.twin = None

            list.remove(self, athing)
            athing.model = None
        if self._plot_active:
            self.update_plot()

    def as_signal(self, component_list=None, out_of_range_to_nan=True,
                  show_progressbar=None, out=None, parallel=None, max_workers=None):
        """Returns a recreation of the dataset using the model.
        The spectral range that is not fitted is filled with nans.

        Parameters
        ----------
        component_list : list of HyperSpy components, optional
            If a list of components is given, only the components given in the
            list is used in making the returned spectrum. The components can
            be specified by name, index or themselves.
        out_of_range_to_nan : bool
            If True the spectral range that is not fitted is filled with nans.
            Default True.
        %s
        out : {None, BaseSignal}
            The signal where to put the result into. Convenient for parallel
            processing. If None (default), creates a new one. If passed, it is
            assumed to be of correct shape and dtype and not checked.
        %s
        %s

        Returns
        -------
        BaseSignal : An instance of the same class as `BaseSignal`.

        Examples
        --------
        >>> s = hs.signals.Signal1D(np.random.random((10,100)))
        >>> m = s.create_model()
        >>> l1 = hs.model.components1D.Lorentzian()
        >>> l2 = hs.model.components1D.Lorentzian()
        >>> m.append(l1)
        >>> m.append(l2)
        >>> s1 = m.as_signal()
        >>> s2 = m.as_signal(component_list=[l1])

        """
        if show_progressbar is None:
            show_progressbar = preferences.General.show_progressbar
        if parallel is None:
            parallel = preferences.General.parallel

        if not isinstance(parallel, bool):
            warnings.warn(
                "Passing integer arguments to 'parallel' has been deprecated and will be removed "
                f"in HyperSpy 2.0. Please use 'parallel=True, max_workers={parallel}' instead.",
                VisibleDeprecationWarning,
            )
            max_workers = parallel
            parallel = True

        if out is None:
            data = np.empty(self.signal.data.shape, dtype='float')
            data.fill(np.nan)
            signal = self.signal.__class__(
                data,
                axes=self.signal.axes_manager._get_axes_dicts())
            signal.metadata.General.title = (
                self.signal.metadata.General.title + " from fitted model")
            signal.metadata.Signal.binned = self.signal.metadata.Signal.binned
        else:
            signal = out
            data = signal.data

        if out_of_range_to_nan is True:
            channel_switches_backup = copy.copy(self.channel_switches)
            self.channel_switches[:] = True

        # We set this value to equal cpu_count, with a maximum
        # of 32 cores, since the earlier default value was inappropriate
        # for many-core machines.
        if max_workers is None:
            max_workers = min(32, os.cpu_count())

        # Avoid any overhead of additional threads
        if max_workers < 2:
            parallel = False

        if not parallel:
            self._as_signal_iter(component_list=component_list,
                                 show_progressbar=show_progressbar, data=data)
        else:
            am = self.axes_manager
            nav_shape = am.navigation_shape
            if len(nav_shape):
                ind = np.argmax(nav_shape)
                size = nav_shape[ind]
            if not len(nav_shape) or size < 4:
                # no or not enough navigation, just run without threads
                return self.as_signal(component_list=component_list,
                                      show_progressbar=show_progressbar,
                                      out=signal, parallel=False)
            max_workers = min(max_workers, size / 2)
            splits = [len(sp) for sp in np.array_split(np.arange(size),
                                                       max_workers)]
            models = []
            data_slices = []
            slices = [slice(None), ] * len(nav_shape)
            for sp, csm in zip(splits, np.cumsum(splits)):
                slices[ind] = slice(csm - sp, csm)
                models.append(self.inav[tuple(slices)])
                array_slices = self.signal._get_array_slices(tuple(slices),
                                                             True)
                data_slices.append(data[array_slices])

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as exe:
                _map = exe.map(
                    lambda thing: thing[0]._as_signal_iter(
                        data=thing[1],
                        component_list=component_list,
                        show_progressbar=thing[2] + 1 if show_progressbar else False),
                    zip(models, data_slices, range(int(max_workers))))

            _ = next(_map)

        if out_of_range_to_nan is True:
            self.channel_switches[:] = channel_switches_backup

        return signal

    as_signal.__doc__ %= (SHOW_PROGRESSBAR_ARG, PARALLEL_ARG, MAX_WORKERS_ARG)

    def _as_signal_iter(self, component_list=None, show_progressbar=None,
                        data=None):
        # Note that show_progressbar can be an int to determine the progressbar
        # position for a thread-friendly bars. Otherwise race conditions are
        # ugly...
        if data is None:
            raise ValueError('No data supplied')
        if show_progressbar is None:
            show_progressbar = preferences.General.show_progressbar

        with stash_active_state(self if component_list else []):
            if component_list:
                component_list = [self._get_component(x)
                                  for x in component_list]
                for component_ in self:
                    active = component_ in component_list
                    if component_.active_is_multidimensional:
                        if active:
                            continue    # Keep active_map
                        component_.active_is_multidimensional = False
                    component_.active = active
            maxval = self.axes_manager.navigation_size
            enabled = show_progressbar and (maxval > 0)
            pbar = progressbar(total=maxval, disable=not enabled,
                               position=show_progressbar, leave=True)
            for index in self.axes_manager:
                self.fetch_stored_values(only_fixed=False)
                data[self.axes_manager._getitem_tuple][
                    np.where(self.channel_switches)] = self.__call__(
                    non_convolved=not self.convolved, onlyactive=True).ravel()
                pbar.update(1)

    @property
    def _plot_active(self):
        if self._plot is not None and self._plot.is_active:
            return True
        else:
            return False

    def _connect_parameters2update_plot(self, components):
        if self._plot_active is False:
            return
        for i, component in enumerate(components):
            component.events.active_changed.connect(
                self._model_line._auto_update_line, [])
            for parameter in component.parameters:
                parameter.events.value_changed.connect(
                    self._model_line._auto_update_line, [])

    def _disconnect_parameters2update_plot(self, components):
        if self._model_line is None:
            return
        for component in components:
            component.events.active_changed.disconnect(
                self._model_line._auto_update_line)
            for parameter in component.parameters:
                parameter.events.value_changed.disconnect(
                    self._model_line._auto_update_line)

    def update_plot(self, *args, **kwargs):
        """Update model plot.

        The updating can be suspended using `suspend_update`.

        See Also
        --------
        suspend_update

        """
        if self._plot_active is True and self._suspend_update is False:
            try:
                if self._model_line is not None:
                    self._model_line.update()
                for component in [component for component in self if
                                  component.active is True]:
                    self._update_component_line(component)
            except BaseException:
                self._disconnect_parameters2update_plot(components=self)

    @contextmanager
    def suspend_update(self, update_on_resume=True):
        """Prevents plot from updating until 'with' clause completes.

        See Also
        --------
        update_plot
        """

        es = EventSuppressor()
        es.add(self.axes_manager.events.indices_changed)
        if self._model_line:
            f = self._model_line._auto_update_line
            for c in self:
                es.add(c.events, f)
                for p in c.parameters:
                    es.add(p.events, f)
        for c in self:
            if hasattr(c, '_model_plot_line'):
                f = c._model_plot_line._auto_update_line
                es.add(c.events, f)
                for p in c.parameters:
                    es.add(p.events, f)

        old = self._suspend_update
        self._suspend_update = True
        with es.suppress():
            yield
        self._suspend_update = old

        if update_on_resume is True:
            self.update_plot()

    def _close_plot(self):
        if self._plot_components is True:
            self.disable_plot_components()
        self._disconnect_parameters2update_plot(components=self)
        self._model_line = None

    @staticmethod
    def _connect_component_line(component):
        if hasattr(component, "_model_plot_line"):
            f = component._model_plot_line._auto_update_line
            component.events.active_changed.connect(f, [])
            for parameter in component.parameters:
                parameter.events.value_changed.connect(f, [])

    @staticmethod
    def _disconnect_component_line(component):
        if hasattr(component, "_model_plot_line"):
            f = component._model_plot_line._auto_update_line
            component.events.active_changed.disconnect(f)
            for parameter in component.parameters:
                parameter.events.value_changed.disconnect(f)

    def _connect_component_lines(self):
        for component in self:
            if component.active:
                self._connect_component_line(component)

    def _disconnect_component_lines(self):
        for component in self:
            if component.active:
                self._disconnect_component_line(component)

    @staticmethod
    def _update_component_line(component):
        if hasattr(component, "_model_plot_line"):
            component._model_plot_line.update()

    def _disable_plot_component(self, component):
        self._disconnect_component_line(component)
        if hasattr(component, "_model_plot_line"):
            component._model_plot_line.close()
            del component._model_plot_line
        self._plot_components = False

    def enable_plot_components(self):
        if self._plot is None or self._plot_components:
            return
        self._plot_components = True
        for component in [component for component in self if
                          component.active]:
            self._plot_component(component)

    def disable_plot_components(self):
        if self._plot is None:
            return
        for component in self:
            self._disable_plot_component(component)
        self._plot_components = False

    def _set_p0(self):
        self.p0 = ()
        for component in self:
            if component.active:
                for parameter in component.free_parameters:
                    self.p0 = (self.p0 + (parameter.value,)
                               if parameter._number_of_elements == 1
                               else self.p0 + parameter.value)

    def set_boundaries(self, bounded=True):
        warnings.warn(
            "`set_boundaries()` has been deprecated and "
            "will be made private in HyperSpy 2.0.",
            VisibleDeprecationWarning,
        )
        self._set_boundaries(bounded=bounded)

    def _set_boundaries(self, bounded=True):
        """Generate the boundary list.

        Necessary before fitting with a boundary aware optimizer.

        Parameters
        ----------
        bounded : bool, default True
            If True, loops through the model components and
            populates the free parameter boundaries.

        Returns
        -------
        None

        """
        if not bounded:
            self.free_parameters_boundaries = None
        else:
            self.free_parameters_boundaries = []
            for component in self:
                if component.active:
                    for param in component.free_parameters:
                        if param._number_of_elements == 1:
                            self.free_parameters_boundaries.append((param._bounds))
                        else:
                            self.free_parameters_boundaries.extend((param._bounds))

    def _bounds_as_tuple(self):
        """Converts parameter bounds to tuples for least_squares()"""
        if self.free_parameters_boundaries is None:
            return (-np.inf, np.inf)

        return tuple(
            (a if a is not None else -np.inf, b if b is not None else np.inf)
            for a, b in self.free_parameters_boundaries
        )

    def set_mpfit_parameters_info(self, bounded=True):
        warnings.warn(
            "`set_mpfit_parameters_info()` has been deprecated and "
            "will be made private in HyperSpy 2.0.",
            VisibleDeprecationWarning,
        )
        self._set_mpfit_parameters_info(bounded=bounded)

    def _set_mpfit_parameters_info(self, bounded=True):
        """Generate the boundary list for mpfit.

        Parameters
        ----------
        bounded : bool, default True
            If True, loops through the model components and
            populates the free parameter boundaries.

        Returns
        -------
        None

        """
        if not bounded:
            self.mpfit_parinfo = None
        else:
            self.mpfit_parinfo = []
            for component in self:
                if component.active:
                    for param in component.free_parameters:
                        limited = [False, False]
                        limits = [0, 0]
                        if param.bmin is not None:
                            limited[0] = True
                            limits[0] = param.bmin
                        if param.bmax is not None:
                            limited[1] = True
                            limits[1] = param.bmax
                        if param._number_of_elements == 1:
                            self.mpfit_parinfo.append(
                                {"limited": limited, "limits": limits}
                            )
                        else:
                            self.mpfit_parinfo.extend(
                                ({"limited": limited, "limits": limits},)
                                * param._number_of_elements
                            )

    def ensure_parameters_in_bounds(self):
        """For all active components, snaps their free parameter values to
        be within their boundaries (if bounded). Does not touch the array of
        values.
        """
        for component in self:
            if component.active:
                for param in component.free_parameters:
                    bmin = -np.inf if param.bmin is None else param.bmin
                    bmax = np.inf if param.bmax is None else param.bmax
                    if param._number_of_elements == 1:
                        if not bmin <= param.value <= bmax:
                            min_d = np.abs(param.value - bmin)
                            max_d = np.abs(param.value - bmax)
                            if min_d < max_d:
                                param.value = bmin
                            else:
                                param.value = bmax
                    else:
                        values = np.array(param.value)
                        if param.bmin is not None:
                            minmask = values < bmin
                            values[minmask] = bmin
                        if param.bmax is not None:
                            maxmask = values > bmax
                            values[maxmask] = bmax
                        param.value = tuple(values)

    def store_current_values(self):
        """ Store the parameters of the current coordinates into the
        parameters array.

        If the parameters array has not being defined yet it creates it filling
        it with the current parameters."""
        for component in self:
            if component.active:
                component.store_current_parameters_in_map()

    def fetch_stored_values(self, only_fixed=False):
        """Fetch the value of the parameters that has been previously stored.

        Parameters
        ----------
        only_fixed : bool, optional
            If True, only the fixed parameters are fetched.

        See Also
        --------
        store_current_values

        """
        cm = self.suspend_update if self._plot_active else dummy_context_manager
        with cm(update_on_resume=True):
            for component in self:
                component.fetch_stored_values(only_fixed=only_fixed)

    def fetch_values_from_array(self, array, array_std=None):
        """Fetch the parameter values from the given array, optionally also
        fetching the standard deviations.

        Parameters
        ----------
        array : array
            array with the parameter values
        array_std : {None, array}
            array with the standard deviations of parameters
        """
        self.p0 = array
        self._fetch_values_from_p0(p_std=array_std)

    def _fetch_values_from_p0(self, p_std=None):
        """Fetch the parameter values from the output of the optimizer `self.p0`

        Parameters
        ----------
        p_std : array, optional
            array containing the corresponding standard deviation.

        """
        comp_p_std = None
        counter = 0
        for component in self:  # Cut the parameters list
            if component.active is True:
                if p_std is not None:
                    comp_p_std = p_std[
                        counter: counter +
                        component._nfree_param]
                component.fetch_values_from_array(
                    self.p0[counter: counter + component._nfree_param],
                    comp_p_std, onlyfree=True)
                counter += component._nfree_param

    def _model2plot(self, axes_manager, out_of_range2nans=True):
        old_axes_manager = None
        if axes_manager is not self.axes_manager:
            old_axes_manager = self.axes_manager
            self.axes_manager = axes_manager
            self.fetch_stored_values()
        s = self.__call__(non_convolved=False, onlyactive=True)
        if old_axes_manager is not None:
            self.axes_manager = old_axes_manager
            self.fetch_stored_values()
        if out_of_range2nans is True:
            ns = np.empty(self.axis.axis.shape)
            ns.fill(np.nan)
            ns[np.where(self.channel_switches)] = s
            s = ns
        return s

    def _model_function(self, param):
        self.p0 = param
        self._fetch_values_from_p0()
        to_return = self.__call__(non_convolved=False, onlyactive=True)
        return to_return

    def _errfunc_sq(self, param, y, weights=None):
        if weights is None:
            weights = 1.0
        return ((weights * self._errfunc(param, y)) ** 2).sum()

    def _errfunc4mpfit(self, p, fjac=None, x=None, y=None, weights=None):
        if fjac is None:
            errfunc = self._model_function(p).ravel() - y
            if weights is not None:
                errfunc *= weights.ravel()
            status = 0
            return [status, errfunc]
        else:
            return [0, self._jacobian(p, y).T]

    def _get_variance(self, only_current=True):
        """Return the variance taking into account the `channel_switches`.
        If only_current=True, the variance for the current navigation indices
        is returned, otherwise the variance for all navigation indices is
        returned.
        """
        variance = self.signal.get_noise_variance()
        if variance is not None:
            if isinstance(variance, BaseSignal):
                if only_current:
                    variance = variance.data.__getitem__(
                        self.axes_manager._getitem_tuple
                        )[np.where(self.channel_switches)]
                else:
                    variance = variance.data[..., np.where(
                        self.channel_switches)[0]]
        else:
            variance = 1.0
        return variance

    def _calculate_chisq(self):
        variance = self._get_variance()
        d = self(onlyactive=True).ravel() - self.signal()[np.where(
            self.channel_switches)]
        d *= d / (1. * variance)  # d = difference^2 / variance.
        self.chisq.data[self.signal.axes_manager.indices[::-1]] = d.sum()

    def _set_current_degrees_of_freedom(self):
        self.dof.data[self.signal.axes_manager.indices[::-1]] = len(self.p0)

    @property
    def red_chisq(self):
        """Reduced chi-squared. Calculated from self.chisq and self.dof
        """
        tmp = self.chisq / (- self.dof + self.channel_switches.sum() - 1)
        tmp.metadata.General.title = self.signal.metadata.General.title + \
            ' reduced chi-squared'
        return tmp

    def _calculate_parameter_std(self, pcov, cost, ysize):
        warn_cov = False

        if pcov is None:  # Indeterminate covariance
            p_var = np.zeros(len(self.p0), dtype=float)
            p_var.fill(np.nan)
            warn_cov = True
        elif isinstance(pcov, np.ndarray):
            p_var = np.diag(pcov).astype(float) if pcov.ndim > 1 else pcov.astype(float)

            if p_var.min() < 0 or np.any(np.isnan(p_var)) or np.any(np.isinf(p_var)):
                # Numerical overflow on diagonal
                p_var.fill(np.nan)
                warn_cov = True
            elif ysize > self.p0.size:
                p_var *= cost / (ysize - self.p0.size)
                p_var = np.sqrt(p_var)
            else:
                p_var.fill(np.nan)
                warn_cov = True
        else:
            raise ValueError(f"pcov should be None or np.ndarray, got {type(pcov)}")

        if warn_cov:
            _logger.warning(
                "Covariance of the parameters could not be estimated. "
                "Estimated parameter standard deviations will be np.nan."
            )

        return p_var

    def _convert_variance_to_weights(self):
        weights = None
        variance = self.signal.get_noise_variance()

        if variance is not None:
            if isinstance(variance, BaseSignal):
                variance = variance.data.__getitem__(self.axes_manager._getitem_tuple)[
                    np.where(self.channel_switches)
                ]

            _logger.info("Setting weights to 1/variance of signal noise")

            # Note that we square this later in self._errfunc_sq()
            weights = 1.0 / np.sqrt(variance)

        return weights

    def fit(
        self,
        optimizer="lm",
        loss_function="ls",
        grad="fd",
        bounded=False,
        update_plot=False,
        print_info=False,
        return_info=True,
        fd_scheme="2-point",
        **kwargs,
    ):
        """Fits the model to the experimental data.

        Read more in the :ref:`User Guide <model.fitting>`.

        Parameters
        ----------
        %s

        Returns
        -------
        None

        Notes
        -----
        The chi-squared and reduced chi-squared statistics, and the
        degrees of freedom, are computed automatically when fitting,
        only when `loss_function="ls"`. They are stored as signals:
        ``chisq``, ``red_chisq`` and ``dof``.

        If the attribute ``metada.Signal.Noise_properties.variance``
        is defined as a ``Signal`` instance with the same
        ``navigation_dimension`` as the signal, and ``loss_function``
        is ``"ls"`` or ``"huber"``, then a weighted fit is performed,
        using the inverse of the noise variance as the weights.

        Note that for both homoscedastic and heteroscedastic noise, if
        ``metadata.Signal.Noise_properties.variance`` does not contain
        an accurate estimation of the variance of the data, then the
        chi-squared and reduced chi-squared statistics will not be be
        computed correctly. See the :ref:`Setting the noise properties
        <signal.noise_properties>` in the User Guide for more details.

        See Also
        --------
        * :py:meth:`~hyperspy.model.BaseModel.multifit`
        * :py:meth:`~hyperspy.model.EELSModel.fit`

        """
        cm = (
            self.suspend_update
            if (update_plot != self._plot_active) and not update_plot
            else dummy_context_manager
        )

        # ---------------------------------------------
        # Deprecated arguments (remove in HyperSpy 2.0)
        # ---------------------------------------------

        # Deprecate "fitter" argument
        check_fitter = kwargs.pop("fitter", None)
        if check_fitter:
            warnings.warn(
                f"`fitter='{check_fitter}'` has been deprecated and will be removed "
                f"in HyperSpy 2.0. Please use `optimizer='{check_fitter}'` instead.",
                VisibleDeprecationWarning,
            )
            optimizer = check_fitter

        # Deprecated optimization algorithms
        optimizer = _check_deprecated_optimizer(optimizer)

        # Deprecate loss_function
        if loss_function == "ml":
            warnings.warn(
                "`loss_function='ml'` has been deprecated and will be removed in "
                "HyperSpy 2.0. Please use `loss_function='ML-poisson'` instead.",
                VisibleDeprecationWarning,
            )
            loss_function = "ML-poisson"

        # Deprecate grad=True/False
        if isinstance(grad, bool):
            alt_grad = "analytical" if grad else None
            warnings.warn(
                f"`grad={grad}` has been deprecated and will be removed in "
                f"HyperSpy 2.0. Please use `grad={alt_grad}` instead.",
                VisibleDeprecationWarning,
            )
            grad = alt_grad

        # Deprecate ext_bounding
        ext_bounding = kwargs.pop("ext_bounding", False)
        if ext_bounding:
            warnings.warn(
                "`ext_bounding=True` has been deprecated and will be removed "
                "in HyperSpy 2.0. Please use `bounded=True` instead.",
                VisibleDeprecationWarning,
            )

        # Deprecate custom min_function
        min_function = kwargs.pop("min_function", None)
        if min_function:
            warnings.warn(
                "`min_function` has been deprecated and will be removed "
                "in HyperSpy 2.0. Please use `loss_function` instead.",
                VisibleDeprecationWarning,
            )
            loss_function = min_function

        # Deprecate custom min_function
        min_function_grad = kwargs.pop("min_function_grad", None)
        if min_function_grad:
            warnings.warn(
                "`min_function_grad` has been deprecated and will be removed "
                "in HyperSpy 2.0. Please use `grad` instead.",
                VisibleDeprecationWarning,
            )
            grad = min_function_grad

        # ---------------------------
        # End of deprecated arguments
        # ---------------------------

        # Supported losses and optimizers
        _supported_global = {
            "Differential Evolution": differential_evolution,
        }

        if optimizer in ["Dual Annealing", "SHGO"]:
            if LooseVersion(scipy.__version__) < LooseVersion("1.2.0"):
                raise ValueError(f"`optimizer='{optimizer}'` requires scipy >= 1.2.0")

            from scipy.optimize import dual_annealing, shgo

            _supported_global.update({"Dual Annealing": dual_annealing, "SHGO": shgo})

        _supported_fd_schemes = ["2-point", "3-point", "cs"]
        _supported_losses = ["ls", "ML-poisson", "huber"]
        _supported_bounds = [
            "lm",
            "trf",
            "dogbox",
            "Powell",
            "TNC",
            "L-BFGS-B",
            "SLSQP",
            "trust-constr",
            "Differential Evolution",
            "Dual Annealing",
            "SHGO",
        ]
        _supported_deriv_free = [
            "Powell",
            "COBYLA",
            "Nelder-Mead",
            "SLSQP",
            "trust-constr",
        ]

        # Validate arguments
        if bounded:
            if optimizer not in _supported_bounds:
                raise ValueError(
                    f"Bounded optimization is only supported by "
                    f"'{_supported_bounds}', not '{optimizer}'."
                )

            # This has to be done before setting p0
            self.ensure_parameters_in_bounds()

        # Check validity of loss_function argument
        if callable(loss_function):
            loss_function = partial(loss_function, self)
        elif loss_function not in _supported_losses:
            raise ValueError(
                f"loss_function must be one of {_supported_losses} "
                f"or callable, not '{loss_function}'"
            )
        elif loss_function != "ls" and optimizer in ["lm", "trf", "dogbox", "odr"]:
            raise NotImplementedError(
                f"`optimizer='{optimizer}'` only supports "
                "least-squares fitting (`loss_function='ls'`)"
            )

        # Initialize print_info
        if print_info:
            to_print = [
                "Fit info:",
                f"  optimizer={optimizer}",
                f"  loss_function={loss_function}",
                f"  bounded={bounded}",
                f"  grad={grad}",
            ]

        # Don't let user pass "jac" kwarg since
        # it will clash with "grad" argument
        jac = kwargs.pop("jac", None)
        if jac:
            _logger.warning(
                f"`jac={jac}` keyword argument is not supported. "
                f"Please use `grad={jac}` instead."
            )
            grad = jac

        # Check validity of grad and fd_scheme arguments
        if grad == "analytical":
            _has_gradient, _jac_err_msg = self._check_analytical_jacobian()
            if not _has_gradient:
                # Alert the user that analytical gradients
                # are not supported (and the reason why)
                raise ValueError(f"`grad='analytical' is not supported: {_jac_err_msg}")
        elif callable(grad):
            grad = partial(grad, self)
        elif grad == "fd":
            if optimizer in ["lm", "odr"]:
                grad = None
            elif optimizer in _supported_deriv_free:
                # Setting it to None here avoids unnecessary warnings
                # from `scipy.optimize.minimize`
                grad = None
            else:
                if fd_scheme not in _supported_fd_schemes:
                    raise ValueError(
                        "`fd_scheme` must be one of "
                        f"{_supported_fd_schemes}, not '{fd_scheme}'"
                    )
                grad = fd_scheme
        elif grad is None:
            if optimizer in ["lm", "trf", "dogbox"]:
                # `scipy.optimize.least_squares` does not accept None as
                # an argument. `scipy.optimize.leastsq` will ALWAYS estimate
                # the Jacobian even if Dfun=None. `mpfit` can support no
                # differentiation, but for consistency across all three
                # we enforce estimation below, and raise an error here.
                raise ValueError(
                    f"`optimizer='{optimizer}'` does not support `grad=None`. "
                    f"Please use `grad='auto'` instead."
                )
        else:
            raise ValueError(
                "`grad` must be one of ['auto', 'analytical', "
                f"callable, None], not '{grad}'"
            )

        with cm(update_on_resume=True):
            self.p_std = None
            self._set_p0()
            old_p0 = self.p0

            if ext_bounding:
                self._enable_ext_bounding()

            # Get weights if metadata.Signal.Noise_properties.variance
            # has been set, otherwise this returns None
            weights = self._convert_variance_to_weights()

            if weights is not None and loss_function == "ML-poisson":
                # The attribute ``metadata.Signal.Noise_properties.variance`` is set,
                # but weighted fitting is not supported for `loss_function='ml_poisson'`.
                # Will proceed with unweighted fitting.
                weights = None

            args = (self.signal()[np.where(self.channel_switches)], weights)

            if optimizer == "lm":
                if bounded:
                    # Bounded Levenberg-Marquardt algorithm is supported
                    # using the `mpfit` function (bundled with HyperSpy)
                    self._set_mpfit_parameters_info(bounded=bounded)

                    # We enforce estimation of the Jacobian if no
                    # analytical gradients available for consistency
                    # with `scipy.optimize.leastsq`
                    auto_deriv = 0 if grad == "analytical" else 1

                    res = mpfit(
                        self._errfunc4mpfit,
                        self.p0[:],
                        parinfo=self.mpfit_parinfo,
                        functkw={
                            "y": self.signal()[self.channel_switches],
                            "weights": weights,
                        },
                        autoderivative=auto_deriv,
                        quiet=1,
                        **kwargs,
                    )

                    self.fit_output = OptimizeResult(
                        x=res.params,
                        covar=res.covar,
                        perror=res.perror,
                        nit=res.niter,
                        nfev=res.nfev,
                        success=(res.status > 0) and (res.status != 5),
                        status=res.status,
                        message=res.errmsg,
                        debug=res.debug,
                        dof=res.dof,
                        fnorm=res.fnorm,
                    )

                    self.p0 = self.fit_output.x
                    ysize = len(self.fit_output.x) + self.fit_output.dof
                    cost = self.fit_output.fnorm
                    pcov = self.fit_output.perror ** 2

                    # Calculate estimated parameter standard deviation
                    self.p_std = self._calculate_parameter_std(pcov, cost, ysize)

                else:
                    # Unbounded Levenberg-Marquardt algorithm is supported
                    # using the `scipy.optimize.leastsq` function. Note that
                    # Dfun=None means the gradient is always estimated here.
                    grad = self._jacobian if grad == "analytical" else None

                    res = leastsq(
                        self._errfunc,
                        self.p0[:],
                        Dfun=grad,
                        col_deriv=1,
                        args=args,
                        full_output=True,
                        **kwargs,
                    )

                    self.fit_output = OptimizeResult(
                        x=res[0],
                        covar=res[1],
                        fun=res[2]["fvec"],
                        nfev=res[2]["nfev"],
                        success=res[4] in [1, 2, 3, 4],
                        status=res[4],
                        message=res[3],
                    )

                    self.p0 = self.fit_output.x
                    ysize = len(self.fit_output.fun)
                    cost = np.sum(self.fit_output.fun ** 2)
                    pcov = self.fit_output.covar

                    # Calculate estimated parameter standard deviation
                    self.p_std = self._calculate_parameter_std(pcov, cost, ysize)

            elif optimizer in ["trf", "dogbox"]:
                self._set_boundaries(bounded=bounded)

                def _wrap_jac(*args, **kwargs):
                    # Our Jacobian function computes derivatives along
                    # columns, so we need the transpose instead here
                    return self._jacobian(*args, **kwargs).T

                grad = _wrap_jac if grad == "analytical" else grad

                self.fit_output = least_squares(
                    self._errfunc,
                    self.p0[:],
                    args=args,
                    bounds=self._bounds_as_tuple(),
                    jac=grad,
                    method=optimizer,
                    **kwargs,
                )

                self.p0 = self.fit_output.x
                ysize = len(self.fit_output.fun)
                jac = self.fit_output.jac
                cost = 2 * self.fit_output.cost

                # Do Moore-Penrose inverse, discarding zero singular values
                # to get pcov (as per scipy.optimize.curve_fit())
                _, s, VT = svd(jac, full_matrices=False)
                threshold = np.finfo(float).eps * max(jac.shape) * s[0]
                s = s[s > threshold]
                VT = VT[: s.size]
                pcov = np.dot(VT.T / s ** 2, VT)

                # Calculate estimated parameter standard deviation
                self.p_std = self._calculate_parameter_std(pcov, cost, ysize)

            elif optimizer == "odr":
                if not hasattr(self, "axis"):
                    raise NotImplementedError(
                        "`optimizer='odr'` is not implemented for Model2D"
                    )

                odr_jacobian = self._jacobian4odr if grad == "analytical" else None

                modelo = odr.Model(fcn=self._function4odr, fjacb=odr_jacobian)
                mydata = odr.RealData(
                    self.axis.axis[np.where(self.channel_switches)],
                    self.signal()[np.where(self.channel_switches)],
                    sx=None,
                    sy=(1.0 / weights if weights is not None else None),
                )
                myodr = odr.ODR(mydata, modelo, beta0=self.p0[:], **kwargs)
                res = myodr.run()

                dd = {
                    "x": res.beta,
                    "perror": res.sd_beta,
                    "covar": res.cov_beta,
                }
                if hasattr(res, "info"):
                    dd["status"] = res.info
                    dd["message"] = ", ".join(res.stopreason)
                    # Note that a value of 5 means maximum iterations reached
                    dd["success"] = (res.info >= 0) and (res.info < 4)

                self.fit_output = OptimizeResult(**dd)
                self.p0 = self.fit_output.x
                self.p_std = self.fit_output.perror

            else:
                # scipy.optimize.* functions
                if loss_function == "ls":
                    f_min = self._errfunc_sq
                    f_der = self._gradient_ls if grad == "analytical" else grad
                elif loss_function == "ML-poisson":
                    f_min = self._poisson_likelihood_function
                    f_der = self._gradient_ml if grad == "analytical" else grad
                elif loss_function == "huber":
                    f_min = self._huber_loss_function
                    f_der = self._gradient_huber if grad == "analytical" else grad
                    huber_delta = kwargs.pop("huber_delta", 1.0)
                    args = args + (huber_delta,)
                elif callable(loss_function):
                    f_min = loss_function
                    f_der = grad

                self._set_boundaries(bounded=bounded)

                if optimizer in _supported_global:
                    de_b = self._bounds_as_tuple()

                    if np.any(~np.isfinite(de_b)):
                        raise ValueError(
                            "Finite upper and lower bounds must be "
                            "specified for every free parameter when "
                            f"`optimizer='{optimizer}'`"
                        )

                    self.fit_output = _supported_global[optimizer](
                        f_min, de_b, args=args, **kwargs
                    )

                else:
                    self.fit_output = minimize(
                        f_min,
                        self.p0,
                        jac=f_der,
                        args=args,
                        method=optimizer,
                        bounds=self.free_parameters_boundaries,
                        **kwargs,
                    )

                self.p0 = self.fit_output.x

            if np.iterable(self.p0) == 0:
                self.p0 = (self.p0,)

            self._fetch_values_from_p0(p_std=self.p_std)
            self.store_current_values()
            self._calculate_chisq()
            self._set_current_degrees_of_freedom()

            if ext_bounding:
                self._disable_ext_bounding()

        if np.any(old_p0 != self.p0):
            self.events.fitted.trigger(self)

        # Print details about the fit we just performed
        if print_info:
            output_print = copy.copy(self.fit_output)
            # Drop these as they can be large (== size of data array)
            output_print.pop("fun", None)
            output_print.pop("jac", None)
            to_print.extend(["Fit result:", output_print])
            print("\n".join([str(pr) for pr in to_print]))

        # Check if the optimization actually succeeded
        success = self.fit_output.get("success", None)
        if success is False:
            message = self.fit_output.get("message", "Unknown reason")
            _logger.warning(f"`m.fit()` did not exit successfully. Reason: {message}")

        # Return info
        if return_info:
            return self.fit_output
        else:
            return None

    fit.__doc__ %= FIT_PARAMETERS_ARG

    def multifit(
        self,
        mask=None,
        fetch_only_fixed=False,
        autosave=False,
        autosave_every=10,
        show_progressbar=None,
        interactive_plot=False,
        iterpath=None,
        **kwargs,
    ):
        """Fit the data to the model at all positions of the navigation dimensions.

        Parameters
        ----------
        mask : np.ndarray, optional
            To mask (i.e. do not fit) at certain position, pass a boolean
            numpy.array, where True indicates that the data will NOT be
            fitted at the given position.
        fetch_only_fixed : bool, default False
            If True, only the fixed parameters values will be updated
            when changing the positon.
        autosave : bool, default False
            If True, the result of the fit will be saved automatically
            with a frequency defined by autosave_every.
        autosave_every : int, default 10
            Save the result of fitting every given number of spectra.
        %s
        interactive_plot : bool, default False
            If True, update the plot for every position as they are processed.
            Note that this slows down the fitting by a lot, but it allows for
            interactive monitoring of the fitting (if in interactive mode).
        iterpath : {None, "flyback", "serpentine"}, default None
            If "flyback":
                At each new row the index begins at the first column,
                in accordance with the way :py:class:`numpy.ndindex` generates indices.
            If "serpentine":
                Iterate through the signal in a serpentine, "snake-game"-like
                manner instead of beginning each new row at the first index.
                Works for n-dimensional navigation space, not just 2D.
            If None:
                Currently ``None -> "flyback"``. The default argument will use
                the ``"flyback"`` iterpath, but shows a warning that this will
                change to ``"serpentine"`` in version 2.0.
        **kwargs : keyword arguments
            Any extra keyword argument will be passed to the fit method.
            See the documentation for :py:meth:`~hyperspy.model.BaseModel.fit`
            for a list of valid arguments.

        Returns
        -------
        None

        See Also
        --------
        * :py:meth:`~hyperspy.model.BaseModel.fit`

        """
        if show_progressbar is None:
            show_progressbar = preferences.General.show_progressbar

        if autosave:
            fd, autosave_fn = tempfile.mkstemp(
                prefix="hyperspy_autosave-", dir=".", suffix=".npz"
            )
            os.close(fd)
            autosave_fn = autosave_fn[:-4]
            _logger.info(
                f"Autosaving every {autosave_every} pixels to {autosave_fn}.npz. "
                "When multifit finishes, this file will be deleted."
            )

        if mask is not None and (
            mask.shape != tuple(self.axes_manager._navigation_shape_in_array)
        ):
            raise ValueError(
                "The mask must be a numpy array of boolean type with "
                f"shape: {self.axes_manager._navigation_shape_in_array}"
            )

        masked_elements = 0 if mask is None else mask.sum()
        maxval = self.axes_manager.navigation_size - masked_elements
        show_progressbar = show_progressbar and (maxval > 0)

        if iterpath is None:
            self.axes_manager._iterpath = "flyback"
            warnings.warn(
                "The 'iterpath' default will change from 'flyback' to 'serpentine' "
                "in HyperSpy version 2.0. Change 'iterpath' to other than None to "
                "suppress this warning.",
                VisibleDeprecationWarning,
            )
        else:
            self.axes_manager._iterpath = iterpath

        i = 0
        with self.axes_manager.events.indices_changed.suppress_callback(
            self.fetch_stored_values
        ):
            if interactive_plot:
                outer = dummy_context_manager
                inner = self.suspend_update
            else:
                outer = self.suspend_update
                inner = dummy_context_manager

            with outer(update_on_resume=True):
                with progressbar(
                    total=maxval, disable=not show_progressbar, leave=True
                ) as pbar:
                    for index in self.axes_manager:
                        with inner(update_on_resume=True):
                            if mask is None or not mask[index[::-1]]:
                                self.fetch_stored_values(only_fixed=fetch_only_fixed)
                                self.fit(**kwargs)
                                i += 1
                                pbar.update(1)

                            if autosave and i % autosave_every == 0:
                                self.save_parameters2file(autosave_fn)

        if autosave is True:
            _logger.info(f"Deleting temporary file: {autosave_fn}.npz")
            os.remove(autosave_fn + ".npz")

    multifit.__doc__ %= (SHOW_PROGRESSBAR_ARG)

    def save_parameters2file(self, filename):
        """Save the parameters array in binary format.

        The data is saved to a single file in numpy's uncompressed ``.npz``
        format.

        Parameters
        ----------
        filename : str

        See Also
        --------
        load_parameters_from_file, export_results

        Notes
        -----
        This method can be used to save the current state of the model in a way
        that can be loaded back to recreate the it using `load_parameters_from
        file`. Actually, as of HyperSpy 0.8 this is the only way to do so.
        However, this is known to be brittle. For example see
        https://github.com/hyperspy/hyperspy/issues/341.

        """
        kwds = {}
        i = 0
        for component in self:
            cname = component.name.lower().replace(' ', '_')
            for param in component.parameters:
                pname = param.name.lower().replace(' ', '_')
                kwds['%s_%s.%s' % (i, cname, pname)] = param.map
            i += 1
        np.savez(filename, **kwds)

    def load_parameters_from_file(self, filename):
        """Loads the parameters array from  a binary file written with the
        'save_parameters2file' function.

        Parameters
        ---------
        filename : str

        See Also
        --------
        save_parameters2file, export_results

        Notes
        -----
        In combination with `save_parameters2file`, this method can be used to
        recreate a model stored in a file. Actually, before HyperSpy 0.8 this
        is the only way to do so.  However, this is known to be brittle. For
        example see https://github.com/hyperspy/hyperspy/issues/341.

        """
        f = np.load(filename)
        i = 0
        for component in self:  # Cut the parameters list
            cname = component.name.lower().replace(' ', '_')
            for param in component.parameters:
                pname = param.name.lower().replace(' ', '_')
                param.map = f['%s_%s.%s' % (i, cname, pname)]
            i += 1

        self.fetch_stored_values()

    def assign_current_values_to_all(self, components_list=None, mask=None):
        """Set parameter values for all positions to the current ones.

        Parameters
        ----------
        component_list : list of components, optional
            If a list of components is given, the operation will be performed
            only in the value of the parameters of the given components.
            The components can be specified by name, index or themselves.
        mask : boolean numpy array or None, optional
            The operation won't be performed where mask is True.

        """
        if components_list is None:
            components_list = []
            for comp in self:
                if comp.active:
                    components_list.append(comp)
        else:
            components_list = [self._get_component(x) for x in components_list]

        for comp in components_list:
            for parameter in comp.parameters:
                parameter.assign_current_value_to_all(mask=mask)

    def _enable_ext_bounding(self, components=None):
        """
        """
        if components is None:
            components = self
        for component in components:
            for parameter in component.parameters:
                parameter.ext_bounded = True

    def _disable_ext_bounding(self, components=None):
        """
        """
        if components is None:
            components = self
        for component in components:
            for parameter in component.parameters:
                parameter.ext_bounded = False

    def export_results(self, folder=None, format="hspy", save_std=False,
                       only_free=True, only_active=True):
        """Export the results of the parameters of the model to the desired
        folder.

        Parameters
        ----------
        folder : str or None
            The path to the folder where the file will be saved. If `None` the
            current folder is used by default.
        format : str
            The extension of the file format. It must be one of the
            fileformats supported by HyperSpy. The default is "hspy".
        save_std : bool
            If True, also the standard deviation will be saved.
        only_free : bool
            If True, only the value of the parameters that are free will be
            exported.
        only_active : bool
            If True, only the value of the active parameters will be exported.

        Notes
        -----
        The name of the files will be determined by each the Component and
        each Parameter name attributes. Therefore, it is possible to customise
        the file names modify the name attributes.

        """
        for component in self:
            if only_active is False or component.active:
                component.export(folder=folder, format=format,
                                 save_std=save_std, only_free=only_free)

    def plot_results(self, only_free=True, only_active=True):
        """Plot the value of the parameters of the model

        Parameters
        ----------

        only_free : bool
            If True, only the value of the parameters that are free will be
            plotted.
        only_active : bool
            If True, only the value of the active parameters will be plotted.

        Notes
        -----
        The name of the files will be determined by each the Component and
        each Parameter name attributes. Therefore, it is possible to customise
        the file names modify the name attributes.

        """
        for component in self:
            if only_active is False or component.active:
                component.plot(only_free=only_free)

    def print_current_values(self, only_free=False, only_active=False,
                             component_list=None, fancy=True):
        """Prints the current values of the parameters of all components.

        Parameters
        ----------
        only_free : bool
            If True, only components with free parameters will be printed. Within these,
            only parameters which are free will be printed.
        only_active : bool
            If True, only values of active components will be printed
        component_list : None or list of components.
            If None, print all components.
        fancy : bool
            If True, attempts to print using html rather than text in the notebook.
        """
        if fancy:
            display(current_model_values(
                model=self, only_free=only_free, only_active=only_active,
                component_list=component_list))
        else:
            display_pretty(current_model_values(
                model=self, only_free=only_free, only_active=only_active,
                component_list=component_list))

    def set_parameters_not_free(self, component_list=None,
                                parameter_name_list=None):
        """
        Sets the parameters in a component in a model to not free.

        Parameters
        ----------
        component_list : None, or list of hyperspy components, optional
            If None, will apply the function to all components in the model.
            If list of components, will apply the functions to the components
            in the list.  The components can be specified by name, index or
            themselves.
        parameter_name_list : None or list of strings, optional
            If None, will set all the parameters to not free.
            If list of strings, will set all the parameters with the same name
            as the strings in parameter_name_list to not free.

        Examples
        --------
        >>> v1 = hs.model.components1D.Voigt()
        >>> m.append(v1)
        >>> m.set_parameters_not_free()

        >>> m.set_parameters_not_free(component_list=[v1],
                                      parameter_name_list=['area','centre'])

        See also
        --------
        set_parameters_free
        hyperspy.component.Component.set_parameters_free
        hyperspy.component.Component.set_parameters_not_free
        """

        if not component_list:
            component_list = []
            for _component in self:
                component_list.append(_component)
        else:
            component_list = [self._get_component(x) for x in component_list]

        for _component in component_list:
            _component.set_parameters_not_free(parameter_name_list)

    def set_parameters_free(self, component_list=None,
                            parameter_name_list=None):
        """
        Sets the parameters in a component in a model to free.

        Parameters
        ----------
        component_list : None, or list of hyperspy components, optional
            If None, will apply the function to all components in the model.
            If list of components, will apply the functions to the components
            in the list. The components can be specified by name, index or
            themselves.

        parameter_name_list : None or list of strings, optional
            If None, will set all the parameters to not free.
            If list of strings, will set all the parameters with the same name
            as the strings in parameter_name_list to not free.

        Examples
        --------
        >>> v1 = hs.model.components1D.Voigt()
        >>> m.append(v1)
        >>> m.set_parameters_free()
        >>> m.set_parameters_free(component_list=[v1],
                                  parameter_name_list=['area','centre'])

        See also
        --------
        set_parameters_not_free
        hyperspy.component.Component.set_parameters_free
        hyperspy.component.Component.set_parameters_not_free
        """

        if not component_list:
            component_list = []
            for _component in self:
                component_list.append(_component)
        else:
            component_list = [self._get_component(x) for x in component_list]

        for _component in component_list:
            _component.set_parameters_free(parameter_name_list)

    def set_parameters_value(
            self,
            parameter_name,
            value,
            component_list=None,
            only_current=False):
        """
        Sets the value of a parameter in components in a model to a specified
        value

        Parameters
        ----------
        parameter_name : string
            Name of the parameter whose value will be changed
        value : number
            The new value of the parameter
        component_list : list of hyperspy components, optional
            A list of components whose parameters will changed. The components
            can be specified by name, index or themselves.
        only_current : bool, default False
            If True, will only change the parameter value at the current
            position in the model.
            If False, will change the parameter value for all the positions.

        Examples
        --------
        >>> v1 = hs.model.components1D.Voigt()
        >>> v2 = hs.model.components1D.Voigt()
        >>> m.extend([v1,v2])
        >>> m.set_parameters_value('area', 5)
        >>> m.set_parameters_value('area', 5, component_list=[v1])
        >>> m.set_parameters_value('area', 5, component_list=[v1],
                                   only_current=True)

        """

        if not component_list:
            component_list = []
            for _component in self:
                component_list.append(_component)
        else:
            component_list = [self._get_component(x) for x in component_list]

        for _component in component_list:
            for _parameter in _component.parameters:
                if _parameter.name == parameter_name:
                    if only_current:
                        _parameter.value = value
                        _parameter.store_current_value_in_array()
                    else:
                        _parameter.value = value
                        _parameter.assign_current_value_to_all()

    def as_dictionary(self, fullcopy=True):
        """Returns a dictionary of the model, including all components, degrees
        of freedom (dof) and chi-squared (chisq) with values.

        Parameters
        ----------
        fullcopy : bool (optional, True)
            Copies of objects are stored, not references. If any found,
            functions will be pickled and signals converted to dictionaries

        Returns
        -------
        dictionary : dict
            A dictionary including at least the following fields:

            * components: a list of dictionaries of components, one per
              component
            * _whitelist: a dictionary with keys used as references for saved
              attributes, for more information, see
              :py:func:`~hyperspy.misc.export_dictionary.export_to_dictionary`
            * any field from _whitelist.keys()

        Examples
        --------
        >>> s = signals.Signal1D(np.random.random((10,100)))
        >>> m = s.create_model()
        >>> l1 = components1d.Lorentzian()
        >>> l2 = components1d.Lorentzian()
        >>> m.append(l1)
        >>> m.append(l2)
        >>> d = m.as_dictionary()
        >>> m2 = s.create_model(dictionary=d)

        """
        dic = {'components': [c.as_dictionary(fullcopy) for c in self]}

        export_to_dictionary(self, self._whitelist, dic, fullcopy)

        def remove_empty_numpy_strings(dic):
            for k, v in dic.items():
                if isinstance(v, dict):
                    remove_empty_numpy_strings(v)
                elif isinstance(v, list):
                    for vv in v:
                        if isinstance(vv, dict):
                            remove_empty_numpy_strings(vv)
                        elif isinstance(vv, np.string_) and len(vv) == 0:
                            vv = ''
                elif isinstance(v, np.string_) and len(v) == 0:
                    del dic[k]
                    dic[k] = ''
        remove_empty_numpy_strings(dic)

        return dic

    def set_component_active_value(
            self, value, component_list=None, only_current=False):
        """
        Sets the component 'active' parameter to a specified value

        Parameters
        ----------
        value : bool
            The new value of the 'active' parameter
        component_list : list of hyperspy components, optional
            A list of components whose parameters will changed. The components
            can be specified by name, index or themselves.

        only_current : bool, default False
            If True, will only change the parameter value at the current
            position in the model.
            If False, will change the parameter value for all the positions.

        Examples
        --------
        >>> v1 = hs.model.components1D.Voigt()
        >>> v2 = hs.model.components1D.Voigt()
        >>> m.extend([v1,v2])
        >>> m.set_component_active_value(False)
        >>> m.set_component_active_value(True, component_list=[v1])
        >>> m.set_component_active_value(False, component_list=[v1],
                                         only_current=True)

        """

        if not component_list:
            component_list = []
            for _component in self:
                component_list.append(_component)
        else:
            component_list = [self._get_component(x) for x in component_list]

        for _component in component_list:
            _component.active = value
            if _component.active_is_multidimensional:
                if only_current:
                    _component._active_array[
                        self.axes_manager.indices[::-1]] = value
                else:
                    _component._active_array.fill(value)

    def __getitem__(self, value):
        """x.__getitem__(y) <==> x[y]"""
        if isinstance(value, str):
            component_list = []
            for component in self:
                if component.name:
                    if component.name == value:
                        component_list.append(component)
                elif component.__class__.__name__ == value:
                    component_list.append(component)
            if component_list:
                if len(component_list) == 1:
                    return component_list[0]
                else:
                    raise ValueError(
                        "There are several components with "
                        "the name \"" + str(value) + "\"")
            else:
                raise ValueError(
                    "Component name \"" + str(value) +
                    "\" not found in model")
        else:
            return list.__getitem__(self, value)

    def create_samfire(self, workers=None, setup=True, **kwargs):
        """Creates a SAMFire object.

        Parameters
        ----------
        workers : {None, int}
            the number of workers to initialise.
            If zero, all computations will be done serially.
            If None (default), will attempt to use (number-of-cores - 1),
            however if just one core is available, will use one worker.
        setup : bool
            if the setup should be run upon initialization.
        **kwargs
            Any that will be passed to the _setup and in turn SamfirePool.
        """
        from hyperspy.samfire import Samfire
        return Samfire(self, workers=workers,
                       setup=setup, **kwargs)


class ModelSpecialSlicers(object):

    def __init__(self, model, isNavigation):
        self.isNavigation = isNavigation
        self.model = model

    def __getitem__(self, slices):
        array_slices = self.model.signal._get_array_slices(
            slices,
            self.isNavigation)
        _signal = self.model.signal._slicer(slices, self.isNavigation)
        # TODO: for next major release, change model creation defaults to not
        # automate anything. For now we explicitly look for "auto_" kwargs and
        # disable them:
        import inspect
        pars = inspect.signature(_signal.create_model).parameters
        kwargs = {key: False for key in pars.keys() if key.startswith('auto_')}
        _model = _signal.create_model(**kwargs)

        dims = (self.model.axes_manager.navigation_dimension,
                self.model.axes_manager.signal_dimension)
        if self.isNavigation:
            _model.channel_switches[:] = self.model.channel_switches
        else:
            _model.channel_switches[:] = \
                np.atleast_1d(
                    self.model.channel_switches[
                        tuple(array_slices[-dims[1]:])])

        twin_dict = {}
        for comp in self.model:
            init_args = {}
            for k, v in comp._whitelist.items():
                if v is None:
                    continue
                flags_str, value = v
                if 'init' in parse_flag_string(flags_str):
                    init_args[k] = value
            _model.append(comp.__class__(**init_args))
        copy_slice_from_whitelist(self.model,
                                  _model,
                                  dims,
                                  (slices, array_slices),
                                  self.isNavigation,
                                  )
        for co, cn in zip(self.model, _model):
            copy_slice_from_whitelist(co,
                                      cn,
                                      dims,
                                      (slices, array_slices),
                                      self.isNavigation)
            if _model.axes_manager.navigation_size < 2:
                if co.active_is_multidimensional:
                    cn.active = co._active_array[array_slices[:dims[0]]]
            for po, pn in zip(co.parameters, cn.parameters):
                copy_slice_from_whitelist(po,
                                          pn,
                                          dims,
                                          (slices, array_slices),
                                          self.isNavigation)
                twin_dict[id(po)] = ([id(i) for i in list(po._twins)], pn)

        for k in twin_dict.keys():
            for tw_id in twin_dict[k][0]:
                twin_dict[tw_id][1].twin = twin_dict[k][1]

        _model.chisq.data = _model.chisq.data.copy()
        _model.dof.data = _model.dof.data.copy()
        _model.fetch_stored_values()  # to update and have correct values
        if not self.isNavigation:
            for _ in _model.axes_manager:
                _model._calculate_chisq()

        return _model

# vim: textwidth=80
