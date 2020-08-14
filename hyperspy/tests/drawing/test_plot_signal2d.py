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

import matplotlib.pyplot as plt
import numpy as np
import pytest
import scipy.ndimage
import traits.api as t

import hyperspy.api as hs
from hyperspy.drawing.utils import make_cmap, plot_RGB_map
from hyperspy.tests.drawing.test_plot_signal import _TestPlot

scalebar_color = 'blue'
default_tol = 2.0
baseline_dir = 'plot_signal2d'
style_pytest_mpl = 'default'


def _generate_image_stack_signal():
    image = hs.signals.Signal2D(np.random.random((2, 3, 512, 512)))
    for i in range(2):
        for j in range(3):
            image.data[i, j, :] = scipy.misc.ascent() * (i + 0.5 + j)
    axes = image.axes_manager
    axes[2].name = "x"
    axes[3].name = "y"
    axes[2].units = "nm"
    axes[3].units = "nm"

    return image


def _set_navigation_axes(axes_manager, name=t.Undefined, units=t.Undefined,
                         scale=1.0, offset=0.0):
    for nav_axis in axes_manager.navigation_axes:
        nav_axis.units = units
        nav_axis.scale = scale
        nav_axis.offset = offset
    return axes_manager


def _set_signal_axes(axes_manager, name=t.Undefined, units=t.Undefined,
                     scale=1.0, offset=0.0):
    for sig_axis in axes_manager.signal_axes:
        sig_axis.name = name
        sig_axis.units = units
        sig_axis.scale = scale
        sig_axis.offset = offset
    return axes_manager


@pytest.mark.parametrize("normalization", ['single', 'global'])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_rgb_image(normalization):
    w = 20
    data = np.arange(1, w * w + 1).reshape(w, w)
    ch1 = hs.signals.Signal2D(data)
    ch1.axes_manager = _set_signal_axes(ch1.axes_manager)
    ch2 = hs.signals.Signal2D(data.T * 2)
    ch2.axes_manager = _set_signal_axes(ch2.axes_manager)
    plot_RGB_map([ch1, ch2], normalization=normalization)
    return plt.gcf()


def _generate_parameter():
    parameters = []
    for scalebar in [True, False]:
        for colorbar in [True, False]:
            for axes_ticks in [True, False]:
                for centre_colormap in [True, False]:
                    for min_aspect in [0.2, 0.7]:
                        parameters.append([scalebar, colorbar, axes_ticks,
                                           centre_colormap, min_aspect])
    return parameters


@pytest.mark.parametrize(("scalebar", "colorbar", "axes_ticks",
                          "centre_colormap", "min_aspect"),
                         _generate_parameter())
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot(scalebar, colorbar, axes_ticks, centre_colormap, min_aspect):
    test_plot = _TestPlot(ndim=0, sdim=2)
    test_plot.signal.plot(scalebar=scalebar,
                          colorbar=colorbar,
                          axes_ticks=axes_ticks,
                          centre_colormap=centre_colormap,
                          min_aspect=min_aspect)
    return test_plot.signal._plot.signal_plot.figure


def _generate_parameter_plot_images():
    # There are 9 images in total
    vmin, vmax = [None] * 9, [None] * 9
    vmin[1], vmax[2] = 30, 200
    return vmin, vmax


@pytest.mark.parametrize("percentile", [(None, None), ("1th", "99th")])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_log_scale(percentile):
    test_plot = _TestPlot(ndim=0, sdim=2)
    test_plot.signal += 1  # need to avoid zeros in log
    test_plot.signal.plot(norm='log', vmin=percentile[0], vmax=percentile[1])
    return test_plot.signal._plot.signal_plot.figure


@pytest.mark.parametrize("fft_shift", [True, False])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_FFT(fft_shift):
    s = hs.datasets.example_signals.object_hologram()
    s2 = s.isig[:128, :128].fft()
    s2.plot(fft_shift=fft_shift, axes_ticks=True, power_spectrum=True)
    return s2._plot.signal_plot.figure


@pytest.mark.parametrize(("vmin", "vmax"), (_generate_parameter_plot_images(),
                                            (None, None)))
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_multiple_images_list(vmin, vmax):
    # load red channel of raccoon as an image
    image0 = hs.signals.Signal2D(scipy.misc.face()[:, :, 0])
    image0.metadata.General.title = 'Rocky Raccoon - R'
    axes0 = image0.axes_manager
    axes0[0].name = "x"
    axes0[1].name = "y"
    axes0[0].units = "mm"
    axes0[1].units = "mm"

    # load ascent into 2x3 hyperimage
    image1 = _generate_image_stack_signal()

    # load green channel of raccoon as an image
    image2 = hs.signals.Signal2D(scipy.misc.face()[:, :, 1])
    image2.metadata.General.title = 'Rocky Raccoon - G'
    axes2 = image2.axes_manager
    axes2[0].name = "x"
    axes2[1].name = "y"
    axes2[0].units = "mm"
    axes2[1].units = "mm"

    # load rgb imimagesage
    rgb = hs.signals.Signal1D(scipy.misc.face())
    rgb.change_dtype("rgb8")
    rgb.metadata.General.title = 'RGB'
    axesRGB = rgb.axes_manager
    axesRGB[0].name = "x"
    axesRGB[1].name = "y"
    axesRGB[0].units = "nm"
    axesRGB[1].units = "nm"

    hs.plot.plot_images([image0, image1, image2, rgb], tight_layout=True,
                        labelwrap=20, vmin=vmin, vmax=vmax)
    return plt.gcf()

@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_rgb_image():
    # load rgb imimagesage
    rgb = hs.signals.Signal1D(scipy.misc.face())
    rgb.change_dtype("rgb8")
    rgb.metadata.General.title = 'RGB'
    axesRGB = rgb.axes_manager
    axesRGB[0].name = "x"
    axesRGB[1].name = "y"
    axesRGB[0].units = "cm"
    axesRGB[1].units = "cm"
    rgb.plot()
    return plt.gcf()

class _TestIteratedSignal:

    def __init__(self):
        s = hs.signals.Signal2D([scipy.misc.ascent()] * 6)
        angles = hs.signals.BaseSignal(range(00, 60, 10))
        s.map(scipy.ndimage.rotate, angle=angles.T, reshape=False)
        # prevent values outside of integer range
        s.data = np.clip(s.data, 0, 255)
        title = 'Ascent'

        s.axes_manager = self._set_signal_axes(s.axes_manager,
                                               name='spatial',
                                               units='nm', scale=1,
                                               offset=0.0)
        s.axes_manager = self._set_navigation_axes(s.axes_manager,
                                                   name='index',
                                                   units='images',
                                                   scale=1, offset=0)
        s.metadata.General.title = title

        self.signal = s

    def _set_navigation_axes(self, axes_manager, name=t.Undefined,
                             units=t.Undefined, scale=1.0, offset=0.0):
        for nav_axis in axes_manager.navigation_axes:
            nav_axis.units = units
            nav_axis.scale = scale
            nav_axis.offset = offset
        return axes_manager

    def _set_signal_axes(self, axes_manager, name=t.Undefined,
                         units=t.Undefined, scale=1.0, offset=0.0):
        for sig_axis in axes_manager.signal_axes:
            sig_axis.name = name
            sig_axis.units = units
            sig_axis.scale = scale
            sig_axis.offset = offset
        return axes_manager


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_default():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal)
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_list():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap=['viridis', 'gray'])
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_list_w_diverging():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap=['viridis', 'gray', 'RdBu_r'])
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_mpl_colors():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap='mpl_colors')
    return plt.gcf()


def test_plot_images_cmap_mpl_colors_w_single_cbar():
    # This should give an error, so test for that
    test_im_plot = _TestIteratedSignal()
    with pytest.raises(ValueError):
        hs.plot.plot_images(test_im_plot.signal,
                            axes_decor='off',
                            cmap='mpl_colors',
                            colorbar='single')


def test_plot_images_bogus_cmap():
    # This should give an error, so test for that
    test_im_plot = _TestIteratedSignal()
    with pytest.raises(ValueError) as val_error:
        hs.plot.plot_images(test_im_plot.signal,
                            axes_decor='off',
                            cmap=3.14159265359,
                            colorbar=None)
    assert str(val_error.value) == 'The provided cmap value was not ' \
                                   'understood. Please check input values.'


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_one_string():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap='RdBu_r',
                        colorbar='single')
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_make_cmap_bittrue():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap=make_cmap([(255, 255, 255),
                                        '#F5B0CB',
                                        (220, 106, 207),
                                        '#745C97',
                                        (57, 55, 91)],
                                       bit=True,
                                       name='test_cmap',
                                       register=True))
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_make_cmap_bitfalse():
    test_im_plot = _TestIteratedSignal()
    hs.plot.plot_images(test_im_plot.signal,
                        axes_decor='off',
                        cmap=make_cmap([(1, 1, 1),
                                        '#F5B0CB',
                                        (0.86, 0.42, 0.81),
                                        '#745C97',
                                        (0.22, 0.22, 0.36)],
                                       bit=False,
                                       name='test_cmap',
                                       register=True))
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_multi_signal():
    test_plot1 = _TestIteratedSignal()

    test_plot2 = _TestIteratedSignal()
    test_plot2.signal *= 2  # change scale of second signal
    test_plot2.signal = test_plot2.signal.inav[::-1]
    test_plot2.signal.metadata.General.title = 'Descent'

    hs.plot.plot_images([test_plot1.signal, test_plot2.signal],
                        axes_decor='off',
                        per_row=4,
                        cmap='mpl_colors')
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_cmap_multi_w_rgb():
    test_plot1 = _TestIteratedSignal()

    test_plot2 = _TestIteratedSignal()
    test_plot2.signal *= 2  # change scale of second signal
    test_plot2.signal.metadata.General.title = 'Ascent-2'

    rgb_sig = hs.signals.Signal1D(scipy.misc.face())
    rgb_sig.change_dtype('rgb8')
    rgb_sig.metadata.General.title = 'Racoon!'

    hs.plot.plot_images([test_plot1.signal, test_plot2.signal, rgb_sig],
                        axes_decor='off',
                        per_row=4,
                        cmap='mpl_colors')
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_single_image():
    image0 = hs.signals.Signal2D(np.arange(100).reshape(10, 10))
    image0.isig[5, 5] = 200
    image0.metadata.General.title = 'This is the title from the metadata'
    hs.plot.plot_images(image0, vmin="0.05th", vmax="99.95th")
    return plt.gcf()


@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_single_image_stack():
    image0 = hs.signals.Signal2D(np.arange(200).reshape(2, 10, 10))
    image0.isig[5, 5] = 200
    image0.metadata.General.title = 'This is the title from the metadata'
    hs.plot.plot_images(image0, vmin="0.05th", vmax="99.95th")
    return plt.gcf()


def test_plot_images_multi_signal_w_axes_replot():
    imdata = np.random.rand(3, 5, 5)
    imgs = hs.signals.Signal2D(imdata)
    img_list = [imgs, imgs.inav[:2], imgs.inav[0]]
    subplots = hs.plot.plot_images(img_list, axes_decor=None)
    f = plt.gcf()
    f.canvas.draw()
    f.canvas.flush_events()

    tests = []
    for axi in subplots:
        imi = axi.images[0].get_array()
        x, y = axi.transData.transform((2, 2))
        # Calling base class method because of backends
        plt.matplotlib.backends.backend_agg.FigureCanvasBase.button_press_event(
            f.canvas, x, y, 'left', True)
        fn = plt.gcf()
        tests.append(
            np.allclose(imi, fn.axes[0].images[0].get_array().data))
        plt.close(fn)
    assert np.alltrue(tests)
    return f


@pytest.mark.parametrize("percentile", [("2.5th", "97.5th"),
                                        [["0th", "10th", "20th"], ["100th", "90th", "80th"]],
                                        [["5th", "10th"], ["95th", "90th"]],
                                        [["5th", None, "10th"], ["95th", None, "90th"]],
                                        ])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_vmin_vmax_percentile(percentile):
    image0 = hs.signals.Signal2D(np.arange(100).reshape(10, 10))
    image0.isig[5, 5] = 200
    image0.metadata.General.title = 'This is the title from the metadata'
    ax = hs.plot.plot_images([image0, image0, image0],
                             vmin=percentile[0],
                             vmax=percentile[1],
                             axes_decor='off')
    return ax[0].figure


@pytest.mark.parametrize("vmin_vmax", [(50, 150),
                                       ([0, 10], [120, None])])
@pytest.mark.parametrize("colorbar", ['single', 'multi', None])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_images_colorbar(colorbar, vmin_vmax):
    print("vmin_vmax:", vmin_vmax)
    image0 = hs.signals.Signal2D(np.arange(100).reshape(10, 10))
    image0.isig[5, 5] = 200
    image0.metadata.General.title = 'This is the title from the metadata'
    ax = hs.plot.plot_images([image0, image0],
                             colorbar=colorbar,
                             vmin=vmin_vmax[0],
                             vmax=vmin_vmax[1],
                             axes_decor='ticks')
    return ax[0].figure


def test_plot_images_signal1D():
    image0 = hs.signals.Signal1D(np.arange(100).reshape(10, 10))
    with pytest.raises(ValueError):
        hs.plot.plot_images([image0, image0])


def test_plot_images_not_signal():
    data = np.arange(100).reshape(10, 10)
    with pytest.raises(ValueError):
        hs.plot.plot_images([data, data])

    with pytest.raises(ValueError):
        hs.plot.plot_images(data)

    with pytest.raises(ValueError):
        hs.plot.plot_images('not a list of signal')


def test_plot_images_tranpose():
    a = hs.signals.BaseSignal(np.arange(100).reshape(10, 10))
    b = hs.signals.BaseSignal(np.arange(100).reshape(10, 10)).T

    hs.plot.plot_images([a, b.T])
    hs.plot.plot_images([a, b])


# Ignore numpy warning about clipping np.nan values
@pytest.mark.filterwarnings("ignore:Passing `np.nan` to mean no clipping in np.clip")
def test_plot_with_non_finite_value():
    s = hs.signals.Signal2D(np.array([[np.nan, 2.0] for v in range(2)]))
    s.plot()
    s.axes_manager.events.indices_changed.trigger(s.axes_manager)

    s = hs.signals.Signal2D(np.array([[np.nan, np.nan] for v in range(2)]))
    s.plot()
    s.axes_manager.events.indices_changed.trigger(s.axes_manager)

    s = hs.signals.Signal2D(np.array([[-np.inf, np.nan] for v in range(2)]))
    s.plot()
    s.axes_manager.events.indices_changed.trigger(s.axes_manager)

    s = hs.signals.Signal2D(np.array([[np.inf, np.nan] for v in range(2)]))
    s.plot()
    s.axes_manager.events.indices_changed.trigger(s.axes_manager)


@pytest.mark.parametrize("cmap", ['gray', None])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_log_negative_value(cmap):
    s = hs.signals.Signal2D(np.arange(10*10).reshape(10, 10))
    s -= 5*10
    if cmap:
        s.plot(norm='log', cmap=cmap)
    else:
        s.plot(norm='log')
    return plt.gcf()


@pytest.mark.parametrize("cmap", ['gray', None, 'preference'])
@pytest.mark.mpl_image_compare(
    baseline_dir=baseline_dir, tolerance=default_tol, style=style_pytest_mpl)
def test_plot_navigator_colormap(cmap):
    if cmap == 'preference':
        hs.preferences.Plot.cmap_navigator = 'hot'
        cmap = None
    s = hs.signals.Signal1D(np.arange(10*10*10).reshape(10, 10, 10))
    s.plot(navigator_kwds={'cmap':cmap})
    return s._plot.navigator_plot.figure


@pytest.mark.parametrize("autoscale", ['', 'xy', 'xv', 'xyv', 'v'])
@pytest.mark.mpl_image_compare(baseline_dir=baseline_dir,
                               tolerance=default_tol, style=style_pytest_mpl)
def test_plot_autoscale(autoscale):
    s = hs.signals.Signal2D(np.arange(100).reshape(10, 10))
    s.plot(autoscale=autoscale, axes_ticks=True)
    imf = s._plot.signal_plot
    ax = imf.ax
    extend = [5.0, 10.0, 3., 10.0]
    ax.images[0].set_extent(extend)
    ax.set_xlim(5.0, 10.0)
    ax.set_ylim(3., 10.0)

    ax.images[0].norm.vmin = imf._vmin = 10
    ax.images[0].norm.vmax = imf._vmax = 50

    s.axes_manager.events.indices_changed.trigger(s.axes_manager)
    # Because we are hacking the vmin, vmax with matplotlib, we need to update
    # colorbar too
    imf._colorbar.draw_all()

    return s._plot.signal_plot.figure


@pytest.mark.parametrize("autoscale", ['', 'v'])
def test_plot_autoscale_data_changed(autoscale):
    s = hs.signals.Signal2D(np.arange(100).reshape(10, 10))
    s.plot(autoscale=autoscale, axes_ticks=True)
    imf = s._plot.signal_plot
    _vmin = imf._vmin
    _vmax = imf._vmax

    s.data = s.data / 2
    s.events.data_changed.trigger(s)

    if 'v' in autoscale:
        np.testing.assert_allclose(imf._vmin, s.data.min())
        np.testing.assert_allclose(imf._vmax, s.data.max())
    else:
        np.testing.assert_allclose(imf._vmin, _vmin)
        np.testing.assert_allclose(imf._vmax, _vmax)
