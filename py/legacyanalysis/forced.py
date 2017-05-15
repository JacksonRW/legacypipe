from __future__ import print_function
import os
from astrometry.util.fits import *
from astrometry.util.file import *
from astrometry.util.util import Tan
import numpy as np
import pylab as plt
from legacypipe.survey import LegacySurveyData

def make_pickle_file(pfn):
    survey = LegacySurveyData()
    ccds = survey.get_ccds()

    brickname = '0364m042'
    
    bricks = survey.get_bricks()
    brick = bricks[bricks.brickname == brickname][0]
    print('Brick', brick)

    catfn = survey.find_file('tractor', brick=brickname)
    print('Reading catalog from', catfn)
    cat = fits_table(catfn)
    print(len(cat), 'catalog entries')
    cat.cut(cat.brick_primary)
    print(len(cat), 'brick primary')

    '''
    BRICKNAM     BRICKID BRICKQ    BRICKROW    BRICKCOL                      RA                     DEC
    0364m042      306043      3         343         145        36.4255910987483       -4.25000000000000

    RA1                     RA2                    DEC1                    DEC2
    36.3004172461752        36.5507649513213       -4.37500000000000       -4.12500000000000
    '''

    #rlo,rhi = brick.ra1, brick.ra2
    #dlo,dhi = brick.dec1, brick.dec2
    rlo,rhi = 36.4, 36.5
    dlo,dhi = -4.4, -4.3
    ra,dec = (rlo+rhi)/2., (dlo+dhi)/2.

    ## optional
    cat.cut((cat.ra > rlo) * (cat.ra < rhi) * (cat.dec > dlo) * (cat.dec < dhi))
    print('Cut to', len(cat), 'catalog objects in RA,Dec box')

    lightcurves = dict([((brickname, oid), []) for oid in cat.objid])

    # close enough to equator to ignore cos(dec)
    dra  = 4096 / 2. * 0.262 / 3600.
    ddec = 2048 / 2. * 0.262 / 3600.

    ccds.cut((np.abs(ccds.ra  - ra ) < (rhi-rlo)/2. + dra) *
             (np.abs(ccds.dec - dec) < (dhi-dlo)/2. + ddec))
    print('Cut to', len(ccds), 'CCDs overlapping brick')

    ### HACK
    #ccds = ccds[:500]

    for i,(expnum,ccdname) in enumerate(zip(ccds.expnum, ccds.ccdname)):
        ee = '%08i' % expnum
        fn = 'forced/vanilla/%s/%s/forced-decam-%s-%s.fits' % (ee[:5], ee, ee, ccdname)
        T = fits_table(fn)
        print(i+1, 'of', len(ccds), ':', len(T), 'in', fn)
        T.cut(T.brickname == brickname)
        print(len(T), 'in brick', brickname)
        found = 0
        for oid,expnum,ccdname,mjd,filter,flux,fluxiv in zip(T.objid, T.expnum, T.ccdname, T.mjd, T.filter, T.flux, T.flux_ivar):
            lc = lightcurves.get((brickname,oid), None)
            if lc is None:
                continue
            found += 1
            lc.append((expnum, ccdname, mjd, filter, flux, fluxiv))
        print('Matched', found, 'sources to light curves')

    #pickle_to_file(lightcurves, pfn)

    ll = {}
    for k,v in lightcurves.items():
        if len(v) == 0:
            continue
        T = fits_table()
        T.expnum = np.array([vv[0] for vv in v])
        T.ccdname= np.array([vv[1] for vv in v])
        T.mjd    = np.array([vv[2] for vv in v])
        T.filter = np.array([vv[3] for vv in v])
        T.flux   = np.array([vv[4] for vv in v])
        T.fluxiv = np.array([vv[5] for vv in v])
        ll[k] = T
    pickle_to_file(ll, pfn)


def plot_light_curves(pfn):
    lightcurves = unpickle_from_file(pfn)

    survey = LegacySurveyData()
    brickname = '0364m042'
    catfn = survey.find_file('tractor', brick=brickname)
    print('Reading catalog from', catfn)
    cat = fits_table(catfn)
    print(len(cat), 'catalog entries')
    cat.cut(cat.brick_primary)
    print(len(cat), 'brick primary')

    I = []
    for i,oid in enumerate(cat.objid):
        if (brickname,oid) in lightcurves:
            I.append(i)
    I = np.array(I)
    cat.cut(I)
    print('Cut to', len(cat), 'with light curves')

    S = fits_table('specObj-dr12-trim-2.fits')

    from astrometry.libkd.spherematch import *
    I,J,d = match_radec(S.ra, S.dec, cat.ra, cat.dec, 2./3600.)
    print('Matched', len(I), 'to spectra')


    plt.subplots_adjust(hspace=0)

    movie_jpegs = []
    movie_wcs = None

    for i in range(28):
        fn = os.path.join('des-sn-movie', 'epoch%i' % i, 'coadd', brickname[:3],
                          brickname, 'legacysurvey-%s-image.jpg' % brickname)
        print(fn)
        if not os.path.exists(fn):
            continue

        img = plt.imread(fn)
        img = np.flipud(img)
        h,w,d = img.shape

        fn = os.path.join('des-sn-movie', 'epoch%i' % i, 'coadd', brickname[:3],
                          brickname, 'legacysurvey-%s-image-r.fits' % brickname)
        if not os.path.exists(fn):
            continue
        wcs = Tan(fn)

        movie_jpegs.append(img)
        movie_wcs = wcs


    plt.figure(figsize=(8,6), dpi=100)
    n = 0
    for oid,ii in zip(cat.objid[J], I):
        spec = S[ii]
        k = (brickname, oid)
        v = lightcurves[k]

        # Cut bad CCDs
        v.cut(np.array([e not in [230151, 230152, 230153] for e in v.expnum]))

        plt.clf()
        print('obj', k, 'has', len(v), 'measurements')
        T = v
        # T = fits_table()
        # T.mjd    = np.array([vv[0] for vv in v])
        # T.filter = np.array([vv[1] for vv in v])
        # T.flux   = np.array([vv[2] for vv in v])
        # T.fluxiv = np.array([vv[3] for vv in v])
        #print('filters:', np.unique(T.filter))
        filts = np.unique(T.filter)
        for i,f in enumerate(filts):
            plt.subplot(len(filts),1,i+1)

            I = np.flatnonzero((T.filter == f) * (T.fluxiv > 0))
            print('  ', len(I), 'in', f, 'band')
            I = I[np.argsort(T.mjd[I])]
            mediv = np.median(T.fluxiv[I])
            # cut really noisy ones
            I = I[T.fluxiv[I] > 0.25 * mediv]
            
            #plt.plot(T.mjd[I], T.flux[I], '.-', color=dict(g='g',r='r',z='m')[f])
            # plt.errorbar(T.mjd[I], T.flux[I], yerr=1/np.sqrt(T.fluxiv[I]),
            #              fmt='.-', color=dict(g='g',r='r',z='m')[f])
            plt.errorbar(T.mjd[I], T.flux[I], yerr=1/np.sqrt(T.fluxiv[I]),
                         fmt='.', color=dict(g='g',r='r',z='m')[f])
            if i+1 < len(filts):
                plt.xticks([])
            #plt.yscale('symlog')


        outfn = 'cutout_%.4f_%.4f.jpg' % (spec.ra, spec.dec)
        if not os.path.exists(outfn):
            url = 'http://legacysurvey.org/viewer/jpeg-cutout/?ra=%.4f&dec=%.4f&zoom=14&layer=sdssco&size=128' % (spec.ra, spec.dec)
            cmd = 'wget -O %s "%s"' % (outfn, url)
            print(cmd)
            os.system(cmd)
        pix = plt.imread(outfn)
        h,w,d = pix.shape
        fig = plt.gcf()

        print('fig bbox:', fig.bbox)
        print('xmax, ymax', fig.bbox.xmax, fig.bbox.ymax)
        #plt.figimage(pix, 0, fig.bbox.ymax - h, zorder=10)
        #plt.figimage(pix, 0, fig.bbox.ymax, zorder=10)
        #plt.figimage(pix, fig.bbox.xmax - w, fig.bbox.ymax, zorder=10)
        plt.figimage(pix, fig.bbox.xmax - (w+2), fig.bbox.ymax - (h+2), zorder=10)

        plt.suptitle('SDSS spectro object: %s at (%.4f, %.4f)' % (spec.label.strip(), spec.ra, spec.dec))
        plt.savefig('forced-%i.png' % n)

        ok,x,y = movie_wcs.radec2pixelxy(spec.ra, spec.dec)
        x = int(np.round(x-1))
        y = int(np.round(y-1))
        sz = 32

        plt.clf()
        plt.subplots_adjust(hspace=0, wspace=0)
        k = 1
        for i,img in enumerate(movie_jpegs):
            stamp = img[y-sz:y+sz+1, x-sz:x+sz+1]            

            plt.subplot(5, 6, k)
            plt.imshow(stamp, interpolation='nearest', origin='lower')
            plt.xticks([]); plt.yticks([])
            k += 1
        plt.suptitle('SDSS spectro object: %s at (%.4f, %.4f): DES images' % (spec.label.strip(), spec.ra, spec.dec))
        plt.savefig('forced-%i-b.png' % n)

        n += 1

if __name__ == '__main__':
    pfn = 'pickles/lightcurves.pickle'
    if not os.path.exists(pfn):
        make_pickle_file(pfn)
    plot_light_curves(pfn)

