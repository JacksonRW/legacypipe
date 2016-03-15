from __future__ import print_function

import os
import fitsio

import numpy as np

from astrometry.util.util import wcs_pv2sip_hdr

from legacypipe.image import LegacySurveyImage, CalibMixin
from legacypipe.common import LegacySurveyData

class MosaicImage(LegacySurveyImage, CalibMixin):
    def __init__(self, survey, t):
        super(MosaicImage, self).__init__(survey, t)

        # convert FWHM into pixel units
        self.fwhm /= self.pixscale

        self.dqfn = self.imgfn.replace('_ooi_', '_ood_').replace('_oki_','_ood_')
        self.wtfn = self.imgfn.replace('_ooi_', '_oow_').replace('_oki_','_oow_')
        assert(self.dqfn != self.imgfn)
        assert(self.wtfn != self.imgfn)

        expstr = '%08i' % self.expnum
        self.name = '%s-%s' % (expstr, self.ccdname)
        self.calname = '%s/%s/mosaic-%s-%s' % (expstr[:5], expstr, expstr, self.ccdname)
        calibdir = os.path.join(self.survey.get_calib_dir(), self.camera)
        self.sefn = os.path.join(calibdir, 'sextractor', self.calname + '.fits')
        self.psffn = os.path.join(calibdir, 'psfex', self.calname + '.fits')

    def read_sky_model(self, imghdr=None, **kwargs):
        from tractor.sky import ConstantSky
        return ConstantSky(imghdr['AVSKY'])
        
    def get_wcs(self):
        hdr = fitsio.read_header(self.imgfn, self.hdu)
        wcs = wcs_pv2sip_hdr(hdr)
        dra,ddec = self.survey.get_astrometric_zeropoint_for(self)
        r,d = wcs.get_crval()
        print('Applying astrometric zeropoint:', (dra,ddec))
        wcs.set_crval((r + dra, d + ddec))
        wcs.version = ''
        phdr = fitsio.read_header(self.imgfn, 0)
        wcs.plver = phdr.get('PLVER', '').strip()
        return wcs

    def read_dq(self, **kwargs):
        '''
        Reads the Data Quality (DQ) mask image.
        '''
        print('Reading data quality image', self.dqfn, 'ext', self.hdu)
        dq = self._read_fits(self.dqfn, self.hdu, **kwargs)
        return dq

    def read_invvar(self, clip=True, **kwargs):
        '''
        Reads the inverse-variance (weight) map image.
        '''
        print('Reading weight map image', self.wtfn, 'ext', self.hdu)
        invvar = self._read_fits(self.wtfn, self.hdu, **kwargs)
        return invvar

    def run_calibs(self, psfex=True, funpack=False, git_version=None,
                   force=False, **kwargs):
        #from legacypipe.common import (get_version_header, get_git_version)
                                       
        print('run_calibs for', self.name, 'kwargs', kwargs)

        se = False
        if psfex and os.path.exists(self.psffn) and (not force):
            if self.check_psf(self.psffn):
                psfex = False
        # dependency
        if psfex:
            se = True

        if se and os.path.exists(self.sefn) and (not force):
            if self.check_se_cat(self.sefn):
                se = False
        # dependency
        if se:
            funpack = True

        todelete = []
        if funpack:
            # The image & mask files to process (funpacked if necessary)
            imgfn,maskfn = self.funpack_files(self.imgfn, self.dqfn, self.hdu, todelete)
        else:
            imgfn,maskfn = self.imgfn,self.dqfn
    
        if se:
            self.run_se('mzls', imgfn, maskfn)
        if psfex:
            self.run_psfex('mzls')

        for fn in todelete:
            os.unlink(fn)


def main():

    from astrometry.util.fits import fits_table, merge_tables
    from legacypipe.common import exposure_metadata
    # Fake up a survey-ccds.fits table from MzLS_CP
    from glob import glob
    #fns = glob('/project/projectdirs/cosmo/staging/mosaicz/MZLS_CP/CP20160202/k4m_160203_*oki*')
    fns = glob('/project/projectdirs/cosmo/staging/mosaicz/MZLS_CP/CP20160202/k4m_160203_08*oki*')

    print('Filenames:', fns)
    T = exposure_metadata(fns)

    # HACK
    T.fwhm = T.seeing / 0.262

    # FAKE
    T.ccdnmatch = np.zeros(len(T), np.int32) + 50
    T.zpt = np.zeros(len(T), np.float32) + 26.518
    T.ccdzpt = T.zpt.copy()

    fmap = {'zd':'z'}
    T.filter = np.array([fmap[f] for f in T.filter])
    
    T.writeto('mzls-ccds.fits')

    os.system('cp mzls-ccds.fits ~/legacypipe-dir/survey-ccds.fits')
    os.system('gzip -f ~/legacypipe-dir/survey-ccds.fits')
    
    import sys
    sys.exit(0)
    
    '''
HDU #2  Binary Table:  47 columns x 514378 rows
 COL NAME             FORMAT
    1 expnum           J
       2 exptime          E
          3 filter           1A
             4 seeing           E
                5 date_obs         10A
                   6 mjd_obs          D
                      7 ut               15A
                         8 airmass          E
                            9 propid           10A
                              10 zpt              E
                                11 avsky            E
                                  12 arawgain         E
                                    13 fwhm             E
                                      14 crpix1           E
                                        15 crpix2           E
                                          16 crval1           D
                                            17 crval2           D
                                              18 cd1_1            E
                                                19 cd1_2            E
                                                  20 cd2_1            E
                                                    21 cd2_2            E
                                                      22 ccdnum           I
                                                        23 ccdname          3A
                                                          24 ccdzpt           E
                                                            25 ccdzpta          E
                                                              26 ccdzptb          E
                                                                27 ccdphoff         E
                                                                  28 ccdphrms         E
                                                                    29 ccdskyrms        E
                                                                      30 ccdraoff         E
                                                                        31 ccddecoff        E
                                                                          32 ccdtransp        E
                                                                            33 ccdnstar         I
                                                                              34 ccdnmatch        I
                                                                                35 ccdnmatcha       I
                                                                                  36 ccdnmatchb       I
                                                                                    37 ccdmdncol        E
                                                                                      38 camera           5A
                                                                                        39 expid            12A
                                                                                          40 image_hdu        I
                                                                                            41 image_filename   61A
                                                                                              42 width            I
                                                                                                43 height           I
                                                                                                  44 ra_bore          D
                                                                                                    45 dec_bore         D
                                                                                                      46 ra               D
                                                                                                      dec

    '''

    


    import logging
    import sys
    from legacypipe.runbrick import run_brick, get_runbrick_kwargs, get_parser

    parser = get_parser()
    opt = parser.parse_args()
    if opt.brick is None and opt.radec is None:
        parser.print_help()
        return -1
    kwargs = get_runbrick_kwargs(opt)
    if kwargs in [-1, 0]:
        return kwargs

    if opt.verbose == 0:
        lvl = logging.INFO
    else:
        lvl = logging.DEBUG
    logging.basicConfig(level=lvl, format='%(message)s', stream=sys.stdout)

    kwargs.update(splinesky=True, pixPsf=True)

    run_brick(opt.brick, **kwargs)
    
if __name__ == '__main__':
    main()
