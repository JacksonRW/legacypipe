from __future__ import print_function
import sys
import os

import fitsio

from astrometry.util.fits import fits_table, merge_tables

from tractor.sfd import SFDMap

from catalog import prepare_fits_catalog

def main(args=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infn',
                        help='Input intermediate tractor catalog file')
    parser.add_argument('--out', help='Output catalog filename')
    parser.add_argument('--allbands', default='ugrizY',
                        help='Full set of bands to expand arrays out to')
    parser.add_argument('--flux-prefix', default='',
                        help='Prefix on FLUX etc columns (eg, "decam_" to match DR3) for output file')
    parser.add_argument('--in-flux-prefix', default='',
                        help='Prefix on FLUX etc columns (eg, "decam_" to match DR3) for input file')

    opt = parser.parse_args(args=args)

    T = fits_table(opt.infn)
    hdr = T.get_header()
    primhdr = fitsio.read_header(opt.infn)
    
    allbands = opt.allbands
    
    # Retrieve the bands in this catalog.
    bands = []
    for i in range(10):
        b = hdr.get('BAND%i' % i)
        if b is None:
            break
        bands.append(b)

    # Expand out FLUX and related fields.

    B = np.array([allbands.index(band) for band in bands])

    for k in ['rchi2', 'fracflux', 'fracmasked', 'fracin', 'nobs',
              'anymask', 'allmask', 'psfsize', 'depth', 'galdepth']:
        incol = '%s%s' % (opt.in_flux_prefix, k)
        X = T.get(incol)
        A = np.zeros((len(T), len(allbands)), X.dtype)
        A[:,B] = X
        T.delete_column(incol)
        T.set('%s%s' % (opt.flux_prefix, k), A)
        
    primhdr.add_record(dict(name='ALLBANDS', value=allbands,
                            comment='Band order in array values'))

    # Units
    deg='deg'
    degiv='1/deg^2'
    flux = 'nanomaggy'
    fluxiv = '1/nanomaggy^2'
    units = dict(
        ra=deg, dec=deg, ra_ivar=degiv, dec_ivar=degiv, ebv='mag',

    ##### FIXME
        decam_flux=flux, decam_flux_ivar=fluxiv,
        decam_apflux=flux, decam_apflux_ivar=fluxiv, decam_apflux_resid=flux,
        decam_depth=fluxiv, decam_galdepth=fluxiv,

        wise_flux=flux, wise_flux_ivar=fluxiv,
        wise_lc_flux=flux, wise_lc_flux_ivar=fluxiv,
        shapeexp_r='arcsec', shapeexp_r_ivar='1/arcsec^2',
        shapedev_r='arcsec', shapedev_r_ivar='1/arcsec^2')
    # Reformat as list aligned with cols
    units = [units.get(c, '') for c in cols]
    
    T.writeto(opt.outfn, header=hdr, primheader=primhdr, units=units)
        
if __name__ == '__main__':
    main()
    
