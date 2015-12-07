from __future__ import print_function
import numpy as np

import matplotlib
matplotlib.use('Agg')

from astrometry.util.fits import fits_table, merge_tables
from astrometry.util.starutil_numpy import degrees_between
from astrometry.util.util import Tan
from astrometry.util.miscutils import polygon_area
from legacypipe.common import Decals
import tractor

def main(outfn='ccds-annotated.fits', ccds=None):
    decals = Decals()
    if ccds is None:
        ccds = decals.get_ccds()

    # File from the "observing" svn repo:
    # https://desi.lbl.gov/svn/decam/code/observing/trunk
    tiles = fits_table('decam-tiles_obstatus.fits')

    #ccds.cut(np.arange(100))
    #print("HACK!")
    #ccds.cut(np.array([name in ['N15', 'N16', 'N21', 'N9']
    #                   for name in ccds.ccdname]) *
    #                   ccds.expnum == 229683)

    I = decals.photometric_ccds(ccds)
    ccds.photometric = np.zeros(len(ccds), bool)
    ccds.photometric[I] = True

    I = decals.apply_blacklist(ccds)
    ccds.blacklist_ok = np.zeros(len(ccds), bool)
    ccds.blacklist_ok[I] = True

    ccds.good_region = np.empty((len(ccds), 4), np.int16)
    ccds.good_region[:,:] = -1

    ccds.ra0  = np.zeros(len(ccds), np.float64)
    ccds.dec0 = np.zeros(len(ccds), np.float64)
    ccds.ra1  = np.zeros(len(ccds), np.float64)
    ccds.dec1 = np.zeros(len(ccds), np.float64)
    ccds.ra2  = np.zeros(len(ccds), np.float64)
    ccds.dec2 = np.zeros(len(ccds), np.float64)
    ccds.ra3  = np.zeros(len(ccds), np.float64)
    ccds.dec3 = np.zeros(len(ccds), np.float64)

    ccds.dra  = np.zeros(len(ccds), np.float32)
    ccds.ddec = np.zeros(len(ccds), np.float32)
    ccds.ra_center  = np.zeros(len(ccds), np.float64)
    ccds.dec_center = np.zeros(len(ccds), np.float64)

    ccds.sig1 = np.zeros(len(ccds), np.float32)

    ccds.meansky = np.zeros(len(ccds), np.float32)
    ccds.stdsky  = np.zeros(len(ccds), np.float32)
    ccds.maxsky  = np.zeros(len(ccds), np.float32)
    ccds.minsky  = np.zeros(len(ccds), np.float32)

    ccds.pixscale_mean = np.zeros(len(ccds), np.float32)
    ccds.pixscale_std  = np.zeros(len(ccds), np.float32)
    ccds.pixscale_max  = np.zeros(len(ccds), np.float32)
    ccds.pixscale_min  = np.zeros(len(ccds), np.float32)

    ccds.psfnorm_mean = np.zeros(len(ccds), np.float32)
    ccds.psfnorm_std  = np.zeros(len(ccds), np.float32)
    ccds.galnorm_mean = np.zeros(len(ccds), np.float32)
    ccds.galnorm_std  = np.zeros(len(ccds), np.float32)

    gaussgalnorm = np.zeros(len(ccds), np.float32)

    # 2nd moments
    ccds.psf_mx2 = np.zeros(len(ccds), np.float32)
    ccds.psf_my2 = np.zeros(len(ccds), np.float32)
    ccds.psf_mxy = np.zeros(len(ccds), np.float32)
    #
    ccds.psf_a = np.zeros(len(ccds), np.float32)
    ccds.psf_b = np.zeros(len(ccds), np.float32)
    ccds.psf_theta = np.zeros(len(ccds), np.float32)
    ccds.psf_ell   = np.zeros(len(ccds), np.float32)

    ccds.humidity = np.zeros(len(ccds), np.float32)
    ccds.outtemp  = np.zeros(len(ccds), np.float32)

    ccds.tileid   = np.zeros(len(ccds), np.int32)
    ccds.tilepass = np.zeros(len(ccds), np.uint8)
    ccds.tileebv  = np.zeros(len(ccds), np.float32)

    plvers = []

    for iccd,ccd in enumerate(ccds):
        im = decals.get_image_object(ccd)
        print('Reading CCD %i of %i:' % (iccd+1, len(ccds)), im)

        X = im.get_good_image_subregion()
        for i,x in enumerate(X):
            if x is not None:
                ccds.good_region[iccd,i] = x

        W,H = ccd.width, ccd.height

        psf = None
        wcs = None
        sky = None
        try:
            tim = im.get_tractor_image(pixPsf=True, splinesky=True,
                                       subsky=False, pixels=False)
        except:
            import traceback
            traceback.print_exc()
            continue

        if tim is None:
            continue

        psf = tim.psf
        wcs = tim.wcs.wcs
        sky = tim.sky
        hdr = tim.primhdr

        print('Got PSF', psf)
        print('Got sky', type(sky))
        print('Got WCS', wcs)

        ccds.humidity[iccd] = hdr.get('HUMIDITY')
        ccds.outtemp[iccd]  = hdr.get('OUTTEMP')

        ccds.sig1[iccd] = tim.sig1
        plvers.append(tim.plver)

        obj = hdr.get('OBJECT')
        # parse 'DECaLS_15150_r'
        words = obj.split('_')
        tile = None
        if len(words) == 3 and words[0] == 'DECaLS':
            try:
                tileid = int(words[1])
                tile = tiles[tileid - 1]
                if tile.tileid != tileid:
                    I = np.flatnonzero(tile.tileid == tileid)
                    tile = tiles[I[0]]
            except:
                pass

        if tile is not None:
            ccds.tileid  [iccd] = tile.tileid
            ccds.tilepass[iccd] = tile.get('pass')
            ccds.tileebv [iccd] = tile.ebv_med

        # Instantiate PSF on a grid
        S = 32
        xx = np.linspace(1+S, W-S, 5)
        yy = np.linspace(1+S, H-S, 5)
        xx,yy = np.meshgrid(xx, yy)
        psfnorms = []
        galnorms = []
        for x,y in zip(xx.ravel(), yy.ravel()):
            p = im.psf_norm(tim, x=x, y=y)
            g = im.galaxy_norm(tim, x=x, y=y)
            psfnorms.append(p)
            galnorms.append(g)
        ccds.psfnorm_mean[iccd] = np.mean(psfnorms)
        ccds.psfnorm_std [iccd] = np.std (psfnorms)
        ccds.galnorm_mean[iccd] = np.mean(galnorms)
        ccds.galnorm_std [iccd] = np.std (galnorms)

        # PSF in center of field
        cx,cy = (W+1)/2., (H+1)/2.
        p = psf.getPointSourcePatch(cx, cy).patch
        ph,pw = p.shape
        px,py = np.meshgrid(np.arange(pw), np.arange(ph))
        psum = np.sum(p)
        print('psum', psum)
        p /= psum
        # centroids
        cenx = np.sum(p * px)
        ceny = np.sum(p * py)
        print('cenx,ceny', cenx,ceny)
        # second moments
        x2 = np.sum(p * (px - cenx)**2)
        y2 = np.sum(p * (py - ceny)**2)
        xy = np.sum(p * (px - cenx)*(py - ceny))
        # semi-major/minor axes and position angle
        theta = np.rad2deg(np.arctan2(2 * xy, x2 - y2) / 2.)
        theta = np.abs(theta) * np.sign(xy)
        s = np.sqrt(((x2 - y2)/2.)**2 + xy**2)
        a = np.sqrt((x2 + y2) / 2. + s)
        b = np.sqrt((x2 + y2) / 2. - s)
        ell = 1. - b/a

        print('PSF second moments', x2, y2, xy)
        print('PSF position angle', theta)
        print('PSF semi-axes', a, b)
        print('PSF ellipticity', ell)

        ccds.psf_mx2[iccd] = x2
        ccds.psf_my2[iccd] = y2
        ccds.psf_mxy[iccd] = xy
        ccds.psf_a[iccd] = a
        ccds.psf_b[iccd] = b
        ccds.psf_theta[iccd] = theta
        ccds.psf_ell  [iccd] = ell

        # Galaxy norm using Gaussian approximation of PSF.
        realpsf = tim.psf
        tim.psf = im.read_psf_model(0, 0, gaussPsf=True,
                                    psf_sigma=tim.psf_sigma)
        gaussgalnorm[iccd] = im.galaxy_norm(tim, x=cx, y=cy)
        tim.psf = realpsf
        
        # Sky
        mod = np.zeros((ccd.height, ccd.width), np.float32)
        sky.addTo(mod)
        ccds.meansky[iccd] = np.mean(mod)
        ccds.stdsky[iccd]  = np.std(mod)
        ccds.maxsky[iccd]  = mod.max()
        ccds.minsky[iccd]  = mod.min()

        # WCS
        ccds.ra0[iccd],ccds.dec0[iccd] = wcs.pixelxy2radec(1, 1)
        ccds.ra1[iccd],ccds.dec1[iccd] = wcs.pixelxy2radec(1, H)
        ccds.ra2[iccd],ccds.dec2[iccd] = wcs.pixelxy2radec(W, H)
        ccds.ra3[iccd],ccds.dec3[iccd] = wcs.pixelxy2radec(W, 1)

        midx, midy = (W+1)/2., (H+1)/2.
        rc,dc  = wcs.pixelxy2radec(midx, midy)
        ra,dec = wcs.pixelxy2radec([1,W,midx,midx], [midy,midy,1,H])
        ccds.dra [iccd] = max(degrees_between(ra, dc+np.zeros_like(ra),
                                              rc, dc))
        ccds.ddec[iccd] = max(degrees_between(rc+np.zeros_like(dec), dec,
                                              rc, dc))
        ccds.ra_center [iccd] = rc
        ccds.dec_center[iccd] = dc

        # Compute scale change across the chip
        # how many pixels to step
        step = 10
        xx = np.linspace(1+step, W-step, 5)
        yy = np.linspace(1+step, H-step, 5)
        xx,yy = np.meshgrid(xx, yy)
        pixscale = []
        for x,y in zip(xx.ravel(), yy.ravel()):
            sx = [x-step, x-step, x+step, x+step, x-step]
            sy = [y-step, y+step, y+step, y-step, y-step]
            sr,sd = wcs.pixelxy2radec(sx, sy)
            rc,dc = wcs.pixelxy2radec(x, y)
            # project around a tiny little TAN WCS at (x,y), with 1" pixels
            locwcs = Tan(rc, dc, 0., 0., 1./3600, 0., 0., 1./3600, 1., 1.)
            ok,lx,ly = locwcs.radec2pixelxy(sr, sd)
            #print('local x,y:', lx, ly)
            A = polygon_area((lx, ly))
            pixscale.append(np.sqrt(A / (2*step)**2))
        # print('Pixel scales:', pixscale)
        ccds.pixscale_mean[iccd] = np.mean(pixscale)
        ccds.pixscale_min[iccd] = min(pixscale)
        ccds.pixscale_max[iccd] = max(pixscale)
        ccds.pixscale_std[iccd] = np.std(pixscale)


    ccds.plver = np.array(plvers)

    sfd = tractor.sfd.SFDMap()
    allbands = 'ugrizY'
    filts = ['%s %s' % ('DES', f) for f in allbands]
    wisebands = ['WISE W1', 'WISE W2', 'WISE W3', 'WISE W4']
    ebv,ext = sfd.extinction(filts + wisebands, ccds.ra_center,
                             ccds.dec_center, get_ebv=True)
    ext = ext.astype(np.float32)
    ccds.ebv = ebv.astype(np.float32)
    ccds.decam_extinction = ext[:,:len(allbands)]
    ccds.wise_extinction = ext[:,len(allbands):]

    # Depth
    detsig1 = ccds.sig1 / ccds.psfnorm_mean
    depth = 5. * detsig1
    # that's flux in nanomaggies -- convert to mag
    ccds.psfdepth = -2.5 * (np.log10(depth) - 9)

    detsig1 = ccds.sig1 / ccds.galnorm_mean
    depth = 5. * detsig1
    # that's flux in nanomaggies -- convert to mag
    ccds.galdepth = -2.5 * (np.log10(depth) - 9)

    # Depth using Gaussian FWHM.
    psf_sigma = ccds.fwhm / 2.35
    gnorm = 1./(2. * np.sqrt(np.pi) * psf_sigma)
    detsig1 = ccds.sig1 / gnorm
    depth = 5. * detsig1
    # that's flux in nanomaggies -- convert to mag
    ccds.gausspsfdepth = -2.5 * (np.log10(depth) - 9)

    # Gaussian galaxy depth
    detsig1 = ccds.sig1 / gaussgalnorm
    depth = 5. * detsig1
    # that's flux in nanomaggies -- convert to mag
    ccds.gaussgaldepth = -2.5 * (np.log10(depth) - 9)

    ccds.writeto(outfn)


def _bounce_main((i, ccds)):
    outfn = 'ccds-annotated-%03i.fits' % i
    main(outfn=outfn, ccds=ccds)

if __name__ == '__main__':
    import sys
    sys.exit(main())

    decals = Decals()
    ccds = decals.get_ccds()
    from astrometry.util.multiproc import *
    mp = multiproc(24)
    N = 1000
    args = []
    i = 0
    while len(ccds):
        c = ccds[:N]
        ccds = ccds[N:]
        args.append((i, c))
    mp.map(_bounce_main, args)

    # reassemble outputs
    TT = [fits_table('ccds-annotated-%03i.fits' % i for i,nil in args)]
    T = merge_tables(TT)
    T.writeto('ccds-annotated.fits')

