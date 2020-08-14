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

"""Common docstring snippets for plot.

"""


BASE_PLOT_DOCSTRING_PARAMETERS = \
    """navigator : str, None, or :py:class:`~hyperspy.signal.BaseSignal` (or subclass)
        Allowed string values are ``'auto'``, ``'slider'``, and ``'spectrum'``.

        If ``'auto'``:

                - If `navigation_dimension` > 0, a navigator is
                  provided to explore the data.
                - If `navigation_dimension` is 1 and the signal is an image
                  the navigator is a sum spectrum obtained by integrating
                  over the signal axes (the image).
                - If `navigation_dimension` is 1 and the signal is a spectrum
                  the navigator is an image obtained by stacking all the
                  spectra in the dataset horizontally.
                - If `navigation_dimension` is > 1, the navigator is a sum
                  image obtained by integrating the data over the signal axes.
                - Additionally, if `navigation_dimension` > 2, a window
                  with one slider per axis is raised to navigate the data.
                - For example, if the dataset consists of 3 navigation axes `X`,
                  `Y`, `Z` and one signal axis, `E`, the default navigator will
                  be an image obtained by integrating the data over `E` at the
                  current `Z` index and a window with sliders for the `X`, `Y`,
                  and `Z` axes will be raised. Notice that changing the `Z`-axis
                  index changes the navigator in this case.

            If ``'slider'``:

                - If `navigation dimension` > 0 a window with one slider per
                  axis is raised to navigate the data.

            If ``'spectrum'``:

                - If `navigation_dimension` > 0 the navigator is always a
                  spectrum obtained by integrating the data over all other axes.

            If ``None``, no navigator will be provided.

            Alternatively a :py:class:`~hyperspy.signal.BaseSignal` (or subclass)
            instance can be provided. The `signal_dimension` must be 1 (for a
            spectrum navigator) or 2 (for a image navigator) and
            `navigation_shape` must be 0 (for a static navigator) or
            `navigation_shape` + `signal_shape` must be equal to the
            `navigator_shape` of the current object (for a dynamic navigator).
            If the signal `dtype` is RGB or RGBA this parameter has no effect and
            the value is always set to ``'slider'``.
        axes_manager : None or :py:class:`~hyperspy.axes.AxesManager`
            If None, the signal's `axes_manager` attribute is used.
        plot_markers : bool, default True
            Plot markers added using s.add_marker(marker, permanent=True).
            Note, a large number of markers might lead to very slow plotting.
        navigator_kwds : dict
            Only for image navigator, additional keyword arguments for
            :py:func:`matplotlib.pyplot.imshow`.
        """


BASE_PLOT_DOCSTRING = \
    """Plot the signal at the current coordinates.

        For multidimensional datasets an optional figure,
        the "navigator", with a cursor to navigate that data is
        raised. In any case it is possible to navigate the data using
        the sliders. Currently only signals with signal_dimension equal to
        0, 1 and 2 can be plotted.

        Parameters
        ----------
        """


PLOT1D_DOCSTRING = \
    """norm : str, optional
            The function used to normalize the data prior to plotting.
            Allowable strings are: ``'auto'``, ``'linear'``, ``'log'``.
            (default value is ``'auto'``).
            If ``'auto'``, intensity is plotted on a linear scale except when
            ``power_spectrum=True`` (only for complex signals).
        autoscale : str
            The string must contain any combination of the 'x' and 'v'
            characters. If 'x' or 'v' (for values) are in the string, the
            corresponding horizontal or vertical axis limits are set to their
            maxima and the axis limits will reset when the data or the
            navigation indices are changed. Default is 'v'.
        """


PLOT2D_DOCSTRING = \
    """colorbar : bool, optional
            If true, a colorbar is plotted for non-RGB images.
        autoscale : str
            The string must contain any combination of the 'x', 'y' and 'v'
            characters. If 'x' or 'y' are in the string, the corresponding
            axis limits are set to cover the full range of the data at a given
            position. If 'v' (for values) is in the string, the contrast of the
            image will be set automatically according to `vmin` and `vmax` when
            the data or navigation indices change. Default is 'v'.
        saturated_pixels: scalar
            The percentage of pixels that are left out of the bounds.
            For example, the low and high bounds of a value of 1 are the 0.5%
            and 99.5% percentiles. It must be in the [0, 100] range.
            If None (default value), the value from the preferences is used.
        .. deprecated:: 1.6.0
           `saturated_pixels` will be removed in HyperSpy 2.0.0, it is replaced
            by `vmin`, `vmax` and `autoscale`.
        norm : {"auto", "linear", "power", "log", "symlog" or a subclass of
                :py:class:`matplotlib.colors.Normalise`}
            Set the norm of the image to display. If "auto", a linear scale is
            used except if when `power_spectrum=True` in case of complex data
            type. "symlog" can be used to display negative value on a negative
            scale - read :py:class:`matplotlib.colors.SymLogNorm` and the
            `linthresh` and `linscale` parameter for more details.
        vmin, vmax : {scalar, str}, optional
            `vmin` and `vmax` are used to normalise the displayed data. It can
            be a float or a string. If string, it should be formatted as 'xth',
            where 'x' must be an float in the [0, 100] range. 'x' is used to
            compute the x-th percentile of the data. See
            :py:func:`numpy.percentile` for more information.
        gamma : float
            Parameter used in the power-law normalisation when the parameter
            norm="power". Read :py:class:`matplotlib.colors.PowerNorm` for more
            details. Default value is 1.0.
        linthresh : float
            When used with norm="symlog", define the range within which the
            plot is linear (to avoid having the plot go to infinity around
            zero). Default value is 0.01.
        linscale : float
            This allows the linear range (-linthresh to linthresh) to be
            stretched relative to the logarithmic range. Its value is the
            number of powers of base to use for each half of the linear range.
            See :py:class:`matplotlib.colors.SymLogNorm` for more details.
            Defaulf value is 0.1.
        scalebar : bool, optional
            If True and the units and scale of the x and y axes are the same a
            scale bar is plotted.
        scalebar_color : str, optional
            A valid MPL color string; will be used as the scalebar color.
        axes_ticks : {None, bool}, optional
            If True, plot the axes ticks. If None axes_ticks are only
            plotted when the scale bar is not plotted. If False the axes ticks
            are never plotted.
        axes_off : {bool}
            Default is False.
        no_nans : bool, optional
            If True, set nans to zero for plotting.
        centre_colormap : {"auto", True, False}
            If True the centre of the color scheme is set to zero. This is
            specially useful when using diverging color schemes. If "auto"
            (default), diverging color schemes are automatically centred.
        min_aspect : float
            Set the minimum aspect ratio of the image and the figure. To
            keep the image in the aspect limit the pixels are made
            rectangular.
        """


COMPLEX_DOCSTRING = \
    """power_spectrum : bool, default is False.
            If True, plot the power spectrum instead of the actual signal, if
            False, plot the real and imaginary parts of the complex signal.
        representation : {'cartesian' or 'polar'}
            Determines if the real and imaginary part of the complex data is plotted ('cartesian',
            default), or if the amplitude and phase should be used ('polar').
        same_axes : bool, default True
            If True (default) plot the real and
            imaginary parts (or amplitude and phase) in the same figure if
            the signal is one-dimensional.
        fft_shift : bool, default False
            If True, shift the zero-frequency component.
            See :py:func:`numpy.fft.fftshift` for more details.
        """


PLOT2D_KWARGS_DOCSTRING = \
    """**kwargs
            Only when plotting an image: additional (optional) keyword
            arguments for :py:func:`matplotlib.pyplot.imshow`.
        """
