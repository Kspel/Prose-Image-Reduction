from prose.blocks.registration import distances
import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from prose import utils
from prose.utils import binning
import matplotlib.patches as mpatches
import prose.visualisation as viz
import os
from os import path
import shutil
from prose import Observation
from astropy.time import Time
from astropy import units as u
from prose.models import transit


def protopapas2005(t, t0, duration, depth, c, period=1):
    _t = period * np.sin(np.pi * (t - t0) / period) / (np.pi * duration)
    return (1 - depth) + (depth / 2) * (
            2 - np.tanh(c * (_t + 1 / 2)) + np.tanh(c * (_t - 1 / 2))
    )


def template_transit(t, t0, duration):
    return protopapas2005(t, t0, duration, 1, 50, 100)


class NEB(Observation):
    """Tool to detect and diagnose near eclipsing binaries in a field

    Parameters
    ----------
    observation : prose.Observation
        observation on which to apply the tool
    radius : float, optional
       radius around the target in which to analyse other stars fluxes, by default 2.5 (in arcminutes)
    """

    def __init__(self, observation, radius=2.5):
        
        super(NEB, self).__init__(observation.xarray.copy())
        
        self.radius = radius
        target_distance = np.array(distances(observation.stars.T, observation.stars[observation.target]))
        self.nearby_ids = np.argwhere(target_distance * observation.telescope.pixel_scale / 60 < self.radius).flatten()

        self.nearby_ids = self.nearby_ids[np.argsort(np.array(distances(observation.stars[self.nearby_ids].T, observation.stars[observation.target])))]

        self.time = self.time
        self.epoch = None
        self.duration = None
        self.period = None
        self.depth = None
        self.expected_depth = None
        self.rms_ppt = None
        self.depth_rms = None

        self.transits = np.ones((len(self.nearby_ids), len(self.time)))
        self.cleared = np.ones(len(self.nearby_ids))
        self.likely_cleared = np.ones(len(self.nearby_ids))
        self.not_cleared = np.ones(len(self.nearby_ids))
        self.flux_too_low = np.ones(len(self.nearby_ids))
        self.cleared_too_faint = np.ones(len(self.nearby_ids))

        self.cmap =['r', 'g']

    def mask_lc(self, star, sigma=3):
        return np.abs(self.diff_fluxes[self.aperture, star] - np.median(
            self.diff_fluxes[self.aperture, star])) < sigma * np.std(self.diff_fluxes[self.aperture, star])

    def get_transit(self, value, star, dmag_buffer=-0.5, bins=0.0027):
        """Set transit parameters and run analysis of other stars to detect matching signals

        Parameters
        ----------
        value : dict
            dict containing:

            - epoch
            - duration 
            - period
            - depth (in ppt)
            in same time unit as observation
        """
        self.epoch = value["epoch"]
        self.duration = value["duration"]
        self.period = value["period"]
        self.depth = value["depth"]

        flux = self.raw_fluxes[self.aperture, star][self.mask_lc(star)]
        flux_target = self.raw_fluxes[self.aperture, self.target][self.mask_lc(star)]
        dmag = np.nanmean(-2.5 * np.log10(flux / flux_target))
        bins, binned_flux = binning(self.time[self.mask_lc(star)], self.diff_fluxes[self.aperture, star][self.mask_lc(star)], bins)
        variance = np.var(binned_flux)
        rms_bin = np.sqrt(variance)
        if star == self.target:
            corr_dmag = dmag
        else:
            corr_dmag = dmag + dmag_buffer
        x = np.power(10, -corr_dmag / 2.50)
        self.expected_depth = self.depth / x
        self.rms_ppt = rms_bin * 1000
        self.depth_rms = self.expected_depth / self.rms_ppt

        return transit(self.time, self.epoch, self.duration, depth=self.expected_depth*1e-3, c=50,
                                period=self.period)

    def evaluate_score(self, value):
        for i_star in np.arange(len(self.nearby_ids)):
            x = self.xarray.isel(star=i_star, apertures=self.aperture)
            flux = x.diff_fluxes.values
            error = x.diff_errors.values
            self.transits[i_star] = self.get_transit(value,star=i_star, dmag_buffer=-0.5, bins=0.0027).flatten()
            self.cleared[i_star] = self.depth_rms > 5
            self.likely_cleared[i_star] = (self.depth_rms > 3) & (self.depth_rms < 5)
            self.cleared_too_faint[i_star] = (self.expected_depth > 1000)
            self.not_cleared[i_star] = (self.depth_rms < 3)
            self.flux_too_low[i_star] = any(self.raw_fluxes[self.aperture, i_star] / self.apertures_area[self.aperture].mean() < 2)

    def plot_lc(self, star):
        viz.plot(self.time[self.mask_lc(star)], self.diff_fluxes[self.aperture, self.nearby_ids[star]][self.mask_lc(star)], std=True)
        plt.plot(self.time, self.transits[star]+1, label="expected transit")
        plt.legend()

    def show_stars(self, size=10):

        self._check_show(size=size)

        search_radius = 60*self.radius/self.telescope.pixel_scale
        target_coord = self.stars[self.target]
        circle = mpatches.Circle(
            target_coord,
            search_radius,
            fill=None,
            ec="white",
            alpha=0.6)

        ax = plt.gca()
        ax.add_artist(circle)
        plt.annotate("radius {}'".format(self.radius),
                     xy=[target_coord[0], target_coord[1] + search_radius + 15],
                     color="white",
                     ha='center', fontsize=12, va='bottom', alpha=0.6)

        viz.plot_marks(*self.stars.T, alpha=0.4)

        clean = self.nearby_ids[np.argwhere(np.logical_and(np.logical_not(self.potentials), np.logical_not(self.suspects))).flatten()]
        clean = np.setdiff1d(clean, self.target)
        suspects = self.nearby_ids[np.argwhere(self.suspects).flatten()]
        potentials = np.setdiff1d(self.nearby_ids[np.argwhere(self.potentials).flatten()], suspects)

        viz.plot_marks(*self.stars[self.target], self.target, position="top")
        viz.plot_marks(*self.stars[clean].T, clean, color="white", position="top")
        viz.plot_marks(*self.stars[potentials].T, potentials, color="goldenrod", position="top")
        viz.plot_marks(*self.stars[suspects].T, suspects, color="indianred", position="top")

        # plt.tight_layout()
        # ax = plt.gca()
        #
        # if self.telescope.pixel_scale is not None:
        #     ob = viz.AnchoredHScaleBar(size=60 / self.telescope.pixel_scale,
        #                                label="1'", loc=4, frameon=False, extent=0,
        #                                pad=0.6, sep=4, linekw=dict(color="white", linewidth=0.8))
        #     ax.add_artist(ob)

        ylim = np.array([target_coord[1] + search_radius + 100, target_coord[1] - search_radius - 100])
        xlim = np.array([target_coord[0] - search_radius - 100, target_coord[0] + search_radius + 100])
        xlim.sort()
        ylim.sort()

        plt.ylim(ylim)
        plt.xlim(xlim)
        plt.tight_layout()

    def color(self, i, white=False):
        if self.nearby_ids[i] == self.target:
            return 'k'
        elif self.suspects[i]:
            return "firebrick"
        elif self.potentials[i]:
            return "goldenrod"
        else:
            if white:
                return "grey"
            else:
                return "yellowgreen" #np.array([131, 220, 255]) / 255 #np.array([78, 144, 67])/255

    def plot_suspects(self):
        """Plot fluxes on which a suspect NEB signal has been identified
        """
        self.plot(idxs=np.unique(np.hstack([np.argwhere(self.suspects).flatten(), np.argwhere(self.potentials).flatten()])), force_width=False)

    def plot(self, idxs=None, **kwargs):
        """Plot all fluxes and model fit used for NEB detection

        Parameters
        ----------
        idxs : list of int, optional
            list of star indexes to plot, by default None and plot fluxes of all stars
        """
        if idxs is None:
            idxs = np.arange(len(self.nearby_ids))

        nearby_ids = self.nearby_ids[idxs]
        viz.plot_lcs(
            [(self.time, self.diff_fluxes[self.aperture, i]) for i in nearby_ids],
            indexes=nearby_ids,
            colors=[self.color(idxs[i], white=True) for i in range(len(nearby_ids))],
            **kwargs
        )
        axes = plt.gcf().get_axes()
        for i, axe in enumerate(axes):
            if i < len(nearby_ids):
                if nearby_ids[i] == self.target:
                    color = "k"
                else:
                    color = self.color(idxs[i], white=True)
                axe.plot(self.time, self.X @ self.ws[idxs[i]], c=color)

    def save_report(self, destination, remove_temp=True):
        """Save a detailed report of the NEB check

        Parameters
        ----------
        destination : str
            path of the pdf report to be saved (must contain extension .pdf)
        remove_temp : bool, optional
            weather to remove the emporary folder used to build report, by default True
        """
        def draw_table(table, table_start, marg=5, table_cell=(20, 4)):

            pdf.set_draw_color(200, 200, 200)

            for i, datum in enumerate(table):
                pdf.set_font("helvetica", size=6)
                pdf.set_fill_color(249, 249, 249)

                pdf.rect(table_start[0] + 5, table_start[1] + 1.2 + i * table_cell[1],
                         table_cell[0] * 3, table_cell[1], "FD" if i % 2 == 0 else "D")

                pdf.set_text_color(100, 100, 100)

                value = datum[1]
                if value is None:
                    value = "--"
                else:
                    value = str(value)

                pdf.text(
                    table_start[0] + marg + 2,
                    table_start[1] + marg + i * table_cell[1] - 1.2, datum[0])

                pdf.set_text_color(50, 50, 50)
                pdf.text(
                    table_start[0] + marg + 2 + table_cell[0]*1.2,
                    table_start[1] + marg + i * table_cell[1] - 1.2, value)

        if path.isdir(destination):
            file_name = "{}_NEB_{}arcmin.pdf".format(self.products_denominator, self.radius)
        else:
            file_name = path.basename(destination.strip(".html").strip(".pdf"))

        temp_folder = path.join(path.dirname(destination), "temp")

        if path.isdir("temp"):
            shutil.rmtree(temp_folder)

        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)

        os.mkdir(temp_folder)

        star_plot = path.join(temp_folder, "starplot.png")
        self.show_stars()
        fig = plt.gcf()
        fig.patch.set_alpha(0)
        plt.savefig(star_plot)
        plt.close()

        lcs = []
        a = np.arange(len(self.nearby_ids))
        if len(self.nearby_ids) > 30:
            split = [np.arange(0, 30), *np.array([a[i:i + 7*8] for i in range(30, len(a), 7*8)])]
        else:
            split = [np.arange(0, len(self.nearby_ids))]

        for i, idxs in enumerate(split):
            lcs_path = path.join(temp_folder, "lcs{}.png".format(i))
            lcs.append(lcs_path)
            if i == 0:
                self.plot(np.arange(0, np.min([30, len(self.nearby_ids)])), W=5)
            else:
                self.plot(idxs, W=8)
            viz.paper_style()
            fig = plt.gcf()
            fig.patch.set_alpha(0)
            plt.savefig(lcs_path)
            plt.close()

        lcs = np.array(lcs)

        plt.figure(figsize=(10, 3.5))
        psf_p = self.plot_psf_fit(cmap="viridis", c="C0")

        psf_fit = path.join(temp_folder, "psf_fit.png")
        plt.savefig(psf_fit, dpi=60)
        plt.close()
        theta = psf_p["theta"]
        std_x = psf_p["std_x"]
        std_y = psf_p["std_y"]

        marg_x = 10
        marg_y = 8

        pdf = viz.prose_FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()

        pdf.set_draw_color(200, 200, 200)

        pdf.set_font("helvetica", size=12)
        pdf.set_text_color(50, 50, 50)
        pdf.text(marg_x, 10, txt="{}".format(self.name))

        pdf.set_font("helvetica", size=6)
        pdf.set_text_color(50, 50, 50)
        pdf.text(240, 15, txt="Nearby Eclipsing Binary diagnostic")

        pdf.set_font("helvetica", size=6)
        pdf.set_text_color(74, 144, 255)
        pdf.text(marg_x, 17, txt="simbad")
        pdf.link(marg_x, 15, 8, 3, self.simbad)

        pdf.set_text_color(150, 150, 150)
        pdf.set_font("Helvetica", size=7)
        pdf.text(marg_x, 14, txt="{} · {} · {}".format(
            self.date, self.telescope.name, self.filter))

        datetimes = Time(self.jd, format='jd', scale='utc').to_datetime()
        min_datetime = datetimes.min()
        max_datetime = datetimes.max()

        obs_duration = "{} - {} [{}h{}]".format(
            min_datetime.strftime("%H:%M"),
            max_datetime.strftime("%H:%M"),
            (max_datetime - min_datetime).seconds // 3600,
            ((max_datetime - min_datetime).seconds // 60) % 60)

        max_psf = np.max([std_x, std_y])
        min_psf = np.min([std_x, std_y])
        ellipticity = (max_psf ** 2 - min_psf ** 2) / max_psf ** 2

        draw_table([
            ["Time", obs_duration],
            ["RA DEC", f"{self.RA} {self.DEC}"],
            ["images", len(self.time)],
            ["GAIA id", None],
            ["mean fwhm", "{:.2f} pixels ({:.2f}\")".format(np.mean(self.fwhm),
                                                            np.mean(self.fwhm) * self.telescope.pixel_scale)],
            ["Telescope", self.telescope.name],
            ["Filter", self.filter],
            ["exposure", "{} s".format(np.mean(self.exptime))],
        ], (5 + 12, 20 + 100))

        draw_table([
            ["stack PSF fwhm (x)", "{:.2f} pixels ({:.2f}\")".format(psf_p["fwhm_x"],
                                                                     psf_p["fwhm_x"] * self.telescope.pixel_scale)],
            ["stack PSF fwhm (y)", "{:.2f} pixels ({:.2f}\")".format(psf_p["fwhm_y"],
                                                                     psf_p["fwhm_y"] * self.telescope.pixel_scale)],
            ["stack PSF model", "Moffat2D"],
            ["stack PSF ellipicity", "{:.2f}".format(ellipticity)],
            ["diff. flux std", "{:.3f} ppt (5 min bins)".format(
                np.mean(utils.binning(self.time, self.flux, 5 / (24 * 60), std=True)[2]) * 1e3)]
        ], (5 + 12, 78 + 100))

        pdf.image(psf_fit, x=5.5 + 12, y=55 + 100, w=65)
        pdf.image(star_plot, x=5, y=20, h=93.5)
        pdf.image(lcs[0], x=100, y=22, w=185)

        for lcs_path in lcs[1::]:
            pdf.add_page()
            pdf.image(lcs_path, x=5, y=22, w=280)

        pdf.output(destination)

        if path.isdir("temp") and remove_temp:
            shutil.rmtree(temp_folder)

        print("report saved at {}".format(destination))

