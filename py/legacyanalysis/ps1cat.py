#! /usr/bin/env python

"""
Find all the PS1 stars in a given DECaLS CCD.
"""

import os
import numpy as np

class ps1cat():
    ps1band = dict(g=0,r=1,i=2,z=3,Y=4)
    def __init__(self,expnum=None,ccdname=None,ccdwcs=None):
        """Initialize the class with either the exposure number *and* CCD name, or
        directly with the WCS of the CCD of interest.

        """
        self.ps1dir = os.getenv('PS1CAT_DIR')
        if self.ps1dir is None:
            raise ValueError('You must have the PS1CAT_DIR environment variable set to point to Pan-STARRS1 catalogs')
        self.nside = 32
        if ccdwcs is None:
            from legacypipe.common import Decals
            decals = Decals()
            ccd = decals.find_ccds(expnum=expnum,ccdname=ccdname)[0]
            im = decals.get_image_object(ccd)
            self.ccdwcs = im.get_wcs()
        else:
            self.ccdwcs = ccdwcs

    def get_cat(self,ra,dec):
        """Read the healpixed PS1 catalogs given input ra,dec coordinates."""
        from astrometry.util.fits import fits_table, merge_tables
        from astrometry.util.util import radecdegtohealpix, healpix_xy_to_ring
        ipring = np.empty(len(ra)).astype(int)
        for iobj, (ra1, dec1) in enumerate(zip(ra,dec)):
            hpxy = radecdegtohealpix(ra1,dec1,self.nside)
            ipring[iobj] = healpix_xy_to_ring(hpxy,self.nside)
        pix = np.unique(ipring)

        cat = list()
        for ipix in pix:
            fname = os.path.join(self.ps1dir,'ps1-'+'{:05d}'.format(ipix)+'.fits')
            print('Reading {}'.format(fname))
            cat.append(fits_table(fname))
        cat = merge_tables(cat)
        return cat

    def get_stars(self,magrange=None,band='r'):
        """Return the set of PS1 stars on a given CCD with well-measured grz
        magnitudes. Optionally trim the stars to a desired r-band magnitude
        range.

        """
        bounds = self.ccdwcs.radec_bounds()

        W,H = self.ccdwcs.get_width(), self.ccdwcs.get_height()
        xx,yy = np.meshgrid(np.linspace(1, W, W/100.),
                            np.linspace(1, H, H/100.))
        ra,dec = self.ccdwcs.pixelxy2radec(xx.ravel(), yy.ravel())
        allcat = self.get_cat(ra, dec)

        #allcat = self.get_cat([bounds[0],bounds[1]],[bounds[2],bounds[3]])
        ok,xx,yy = self.ccdwcs.radec2pixelxy(allcat.ra, allcat.dec)
        onccd = np.flatnonzero((xx >= 1.) * (xx <= self.ccdwcs.get_width()) *
                               (yy >= 1.) * (yy <= self.ccdwcs.get_height()))
        cat = allcat[onccd]
        #cat = allcat[np.where((onccd*1)*
        #                      ((allcat.nmag_ok[:,0]>0)*1)*     # g
        #                      ((allcat.nmag_ok[:,1]>0)*1)*     # r
        #                      ((allcat.nmag_ok[:,3]>0)*1)==1)] # z
        print('Found {} good PS1 stars'.format(len(cat)))
        if magrange is not None:
            keep = np.where((cat.median[:,ps1cat.ps1band[band]]>magrange[0])*
                            (cat.median[:,ps1cat.ps1band[band]]<magrange[1]))[0]
            cat = cat[keep]
            print('Trimming to {} stars with {}=[{},{}]'.
                  format(len(cat),band,magrange[0],magrange[1]))
        return cat


def ps1_to_decam(psmags, band):
    '''
    psmags: 2-d array (Nstars, Nbands)
    band: [grz]
    '''
    g_index = ps1cat.ps1band['g']
    i_index = ps1cat.ps1band['i']
    gmag = psmags[:,g_index]
    imag = psmags[:,i_index]
    gi = gmag - imag
    coeffs = dict(
        g = [0.0, -0.04709, -0.00084, 0.00340],
        r = [0.0,  0.09939, -0.04509, 0.01488],
        z = [0.0,  0.13404, -0.06591, 0.01695])[band]

    colorterm = -(coeffs[0] + coeffs[1]*gi + coeffs[2]*gi**2 + coeffs[3]*gi**3)
    return colorterm
    
