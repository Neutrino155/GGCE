#!/usr/bin/env python3

__author__ = "Matthew R. Carbone & John Sous"
__maintainer__ = "Matthew Carbone"
__email__ = "x94carbone@gmail.com"
__status__ = "Prototype"

import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from ggce.engine.structures import GridParams
from ggce.utils import utils


class Results:
    """Trials are single spectra A(w) for some fixed k, and all other
    parameters. This class is a helper for querying trials based on the
    parameters specified, and returning spectral functions A(w)."""

    def __init__(self, package_path, res=Path("res.npy")):

        # Load in the initial data
        package_path = Path(package_path)

        self.paths = {
            'results': package_path / Path("results"),
            'bash_script': package_path / Path("submit.sbatch"),
            'configs': package_path / Path("configs"),
            'grids': package_path / Path("grids.yaml")
        }

        # Load in the configurations and set a mapping between the parameters
        # and results
        self.master = pd.DataFrame({
            str(f.stem): yaml.safe_load(open(f, 'r'))
            for f in self.paths['configs'].iterdir()
        }).T.astype(str)
        self.master.drop(columns=['info', 'model'], inplace=True)

        # Load in the grids
        gp = GridParams(yaml.safe_load(open(self.paths['grids'], 'r')))
        self.w_grid = gp.get_grid('w')
        self.k_grid = gp.get_grid('k')

        # Load in the results
        self.results = dict()

        for idx in list(self.master.index):
            self.results[idx] = dict()
            dat = np.load(open(self.paths['results'] / Path(idx) / res, 'rb'))
            for k_val in self.k_grid:
                where = np.where(np.abs(dat[:, 0] - k_val) < 1e-7)[0]
                loaded = dat[where, 1:]
                sorted_indices = np.argsort(loaded[:, 0])
                self.results[idx][k_val] = loaded[sorted_indices, :]

        # Set the default key values for convenience
        self.defaults = dict()
        for col in list(self.master.columns):
            unique = np.unique(self.master[col])
            self.defaults[col] = None
            if len(unique) == 1:
                self.defaults[col] = unique[0]

    def _query(self, **kwargs):
        """Returns the rows of the dataframe corresponding to the kwargs
        specified."""

        prio = {1: kwargs, 2: self.defaults}
        d = {**prio[2], **prio[1]}
        query_base_list = [f"{key} == '{value}'" for key, value in d.items()]
        query_base = " and ".join(query_base_list)
        return self.master.query(query_base)

    def spectrum(self, k, **kwargs):
        """Returns the spectrum for a specified k value."""

        queried_table = self._query(**kwargs)
        if len(queried_table.index) != 1:
            raise RuntimeError("Queried table has != 1 row")
        result = self.results[list(queried_table.index)[0]]
        G = result[k]  # Query will throw a KeyError if k is not found
        return G[:, 0], -G[:, 2] / np.pi

    def band(self, **kwargs):
        """Returns the band structure for the provided run parameters."""

        band = []
        for k in self.k_grid:
            _, A = self.spectrum(k, **kwargs)
            band.append(A)
        return self.w_grid, self.k_grid, np.array(band)

    def ground_state(self, lorentzian_fit=False, offset=5, **kwargs):
        """Returns the ground state dispersion computed as the lowest
        energy peak energy as a function of k.

        Parameters
        ----------
        lorentzian_fit : tuple
            Whether or not to attempt to fit the ground state peak to a
            Lorentzian before finding the location of the state.
        offset : int
            The offset to the left and right of the minimum peak used when
            fitting a lorentzian.
        """

        queried_table = self._query(**kwargs)

        energies = []
        for k in self.k_grid:
            w, A = self.spectrum(k, **kwargs)
            argmax = find_peaks(A)[0][0]
            w_loc = w[argmax]
            if lorentzian_fit:
                eta = float(queried_table['broadening'])
                popt, _ = curve_fit(
                    utils.lorentzian, w[argmax-offset:argmax+offset],
                    A[argmax-offset:argmax+offset], p0=[w_loc, A[argmax], eta]
                )
                w_loc = popt[0]
            energies.append(w_loc)

        return self.k_grid, np.array(energies)
