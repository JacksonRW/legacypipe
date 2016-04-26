import fitsio
from legacypipe.common import *

from astrometry.util.fits import fits_table
from astrometry.util.file import trymakedirs

def add_depth_tag(survey, brick, outdir, overwrite=False):
    outfn = os.path.join(outdir, 'tractor', brick[:3], 'tractor-%s.fits' % brick)
    if os.path.exists(outfn) and not overwrite:
        print 'Exists:', outfn
        return
    fn = survey.find_file('tractor', brick=brick)
    if not os.path.exists(fn):
        print 'Does not exist:', fn
        return
    T = fits_table(fn, lower=False)
    primhdr = fitsio.read_header(fn)
    hdr = fitsio.read_header(fn, ext=1)
    print 'Read', len(T), 'from', fn
    T.decam_depth    = np.zeros((len(T), len(survey.allbands)), np.float32)
    T.decam_galdepth = np.zeros((len(T), len(survey.allbands)), np.float32)
    bands = 'grz'
    ibands = [survey.index_of_band(b) for b in bands]
    ix = np.clip(np.round(T.bx).astype(int), 0, 3599)
    iy = np.clip(np.round(T.by).astype(int), 0, 3599)
    for iband,band in zip(ibands, bands):
        fn = survey.find_file('depth', brick=brick, band=band)
        if os.path.exists(fn):
            print 'Reading', fn
            img = fitsio.read(fn)
            T.decam_depth[:,iband] = img[iy, ix]

        fn = survey.find_file('galdepth', brick=brick, band=band)
        if os.path.exists(fn):
            print 'Reading', fn
            img = fitsio.read(fn)
            T.decam_galdepth[:,iband] = img[iy, ix]
    outfn = os.path.join(outdir, 'tractor', brick[:3], 'tractor-%s.fits' % brick)
    trymakedirs(outfn, dir=True)

    for s in [
        'Data product of the DECam Legacy Survey (DECaLS)',
        'Full documentation at http://legacysurvey.org',
        ]:
        primhdr.add_record(dict(name='COMMENT', value=s, comment=s))

    # print 'Header:', hdr
    # T.writeto(outfn, header=hdr, primheader=primhdr)

    # Yuck, all this to get the units right
    tmpfn = outfn + '.tmp'
    fits = fitsio.FITS(tmpfn, 'rw', clobber=True)
    fits.write(None, header=primhdr)
    cols = T.get_columns()
    units = []
    for i in range(1, len(cols)+1):
        u = hdr.get('TUNIT%i' % i, '')
        units.append(u)
    # decam_depth units
    fluxiv = '1/nanomaggy^2'
    units[-2] = fluxiv
    units[-1] = fluxiv
    fits.write([T.get(c) for c in cols], names=cols, header=hdr, units=units)
    fits.close()
    os.rename(tmpfn, outfn)
    print 'Wrote', outfn

def bounce_add_depth_tag(X):
    return add_depth_tag(*X)

if __name__ == '__main__':
    import sys
    outdir = 'tractor2'
    survey = LegacySurveyData()
    bricks = survey.get_bricks()
    bricks.cut(bricks.dec > -15)
    bricks.cut(bricks.dec <  45)

    # Add has_[grz] tags and cut to bricks that exist in DR2.
    if True:
        bricks.nobs_med_g = np.zeros(len(bricks), np.uint8)
        bricks.nobs_med_r = np.zeros(len(bricks), np.uint8)
        bricks.nobs_med_z = np.zeros(len(bricks), np.uint8)
        bricks.nobs_max_g = np.zeros(len(bricks), np.uint8)
        bricks.nobs_max_r = np.zeros(len(bricks), np.uint8)
        bricks.nobs_max_z = np.zeros(len(bricks), np.uint8)
        bricks.in_dr2 = np.zeros(len(bricks), bool)

        for ibrick,brick in enumerate(bricks.brickname):

            fn = '/project/projectdirs/desiproc/dr2/tractor/%s/tractor-%s.fits' % (brick[:3], brick)
            bricks.in_dr2[ibrick] = os.path.exists(fn)

            dirnm = '/project/projectdirs/desiproc/dr2/coadd/%s/%s' % (brick[:3], brick)
            for band in 'grz':
                fn = os.path.join(dirnm, 'legacysurvey-%s-nexp-%s.fits.gz' % (brick, band))
                if not os.path.exists(fn):
                    continue
                N = fitsio.read(fn)
                mn = np.min(N)
                md = np.median(N)
                mx = np.max(N)
                print 'Brick', brick, 'band', band, 'has min/median/max nexp', mn,md,mx
                bricks.get('nobs_med_%s' % band)[ibrick] = md
                bricks.get('nobs_max_%s' % band)[ibrick] = mx

        bricks.writeto('legacysurvey-brick-dr2-a.fits')
        mxobs = reduce(np.logical_or, [bricks.nobs_max_g, bricks.nobs_max_r, bricks.nobs_max_r])
        assert(np.all(mxobs > 0 == bricks.in_dr2))
        bricks.cut(mxobs > 0)
        bricks.delete('in_dr2')
        print len(bricks), 'bricks with coverage'
        bricks.writeto('legacysurvey-brick-dr2.fits')

        sys.exit(0)

    # Note to self: don't bother multiprocessing this; I/O bound
    for brick in bricks.brickname:
        add_depth_tag(survey, brick, outdir)


