import numpy as np
import fitsio

def patch_from_coadd(coimgs, targetwcs, bands, tims, mp=None):
    from astrometry.util.resample import resample_with_wcs, OverlapError

    H,W = targetwcs.shape
    ibands = dict([(b,i) for i,b in enumerate(bands)])
    for tim in tims:
        ie = tim.getInvvar()
        img = tim.getImage()
        if np.any(ie == 0):
            # Patch from the coadd
            co = coimgs[ibands[tim.band]]
            # resample from coadd to img -- nearest-neighbour
            iy,ix = np.nonzero(ie == 0)
            if len(iy) == 0:
                continue
            ra,dec = tim.subwcs.pixelxy2radec(ix+1, iy+1)[-2:]
            ok,xx,yy = targetwcs.radec2pixelxy(ra, dec)
            xx = np.round(xx-1).astype(np.int16)
            yy = np.round(yy-1).astype(np.int16)
            keep = (xx >= 0) * (xx < W) * (yy >= 0) * (yy < H)
            if not np.any(keep):
                continue
            img[iy[keep],ix[keep]] = coimgs[ibands[tim.band]][yy[keep],xx[keep]]

            # try:
            #     yo,xo,yi,xi,nil = resample_with_wcs(tim.subwcs, targetwcs, [])
            #     I, = np.nonzero(ie[yo,xo] == 0)
            #     if len(I):
            #         img[yo[I],xo[I]] = coimgs[ibands[tim.band]][yi[I],xi[I]]
            # except OverlapError:
            #     print('No overlap')
            del co


def mask_outlier_pixels(survey, tims, bands, targetwcs, brickname, version_header,
                        mp=None, plots=False, ps=None):
    from scipy.ndimage.morphology import binary_dilation
    from scipy.ndimage.filters import gaussian_filter
    from legacypipe.image import CP_DQ_BITS
    from astrometry.util.resample import resample_with_wcs,OverlapError
    if plots:
        import pylab as plt

    H,W = targetwcs.shape

    badcoadds = []
    for iband,band in enumerate(bands):
        btims = [tim for tim in tims if tim.band == band]
        if len(btims) == 0:
            continue
        print(len(btims), 'images for band', band)
        sigs = np.array([tim.psf_sigma for tim in btims])
        print('PSF sigmas:', sigs)
        targetsig = max(sigs) + 0.5
        addsigs = np.sqrt(targetsig**2 - sigs**2)
        print('Target sigma:', targetsig)
        print('Blur sigmas:', addsigs)
        resams = []
        coimg = np.zeros((H,W), np.float32)
        cow   = np.zeros((H,W), np.float32)
        masks = np.zeros((H,W), np.int16)

        for tim,sig in zip(btims, addsigs):
            img = gaussian_filter(tim.getImage(), sig)
            try:
                Yo,Xo,Yi,Xi,[rimg] = resample_with_wcs(
                    targetwcs, tim.subwcs, [img], 3)
            except OverlapError:
                resams.append(None)
                continue
            del img
            blurnorm = 1./(2. * np.sqrt(np.pi) * sig)
            #print('Blurring "psf" norm', blurnorm)
            wt = tim.getInvvar()[Yi,Xi] / (blurnorm**2)
            coimg[Yo,Xo] += rimg * wt
            cow  [Yo,Xo] += wt
            masks[Yo,Xo] |= (tim.dq[Yi,Xi])
            resams.append([x.astype(np.int16) for x in [Yo,Xo,Yi,Xi]] + [rimg,wt])

        #
        veto = np.logical_or(
            binary_dilation(masks & CP_DQ_BITS['bleed'], iterations=3),
            binary_dilation(masks & CP_DQ_BITS['satur'], iterations=10))
        del masks

        if plots:
            plt.clf()
            plt.imshow(veto, interpolation='nearest', origin='lower', cmap='gray')
            plt.title('SATUR, BLEED veto (%s band)' % band)
            ps.savefig()

        badcoadd = np.zeros((H,W), np.float32)
        badcon   = np.zeros((H,W), np.int16)
        for tim,resam in zip(btims, resams):
            if resam is None:
                continue
            (Yo,Xo,Yi,Xi,rimg,wt) = resam

            # Subtract this image from the coadd
            otherwt = cow[Yo,Xo] - wt
            otherimg = (coimg[Yo,Xo] - rimg*wt) / np.maximum(otherwt, 1e-16)
            this_sig1 = 1./np.sqrt(np.median(wt[wt>0]))

            ## FIXME -- this image edges??

            # Compute the error on our estimate of (thisimg - co) =
            # sum in quadrature of the errors on thisimg and co.
            with np.errstate(divide='ignore'):
                diffvar = 1./wt + 1./otherwt
                sndiff = (rimg - otherimg) / np.sqrt(diffvar)

            with np.errstate(divide='ignore'):
                reldiff = ((rimg - otherimg) / np.maximum(otherimg, this_sig1))

            if plots:
                plt.clf()
                showimg = np.zeros((H,W),np.float32)
                showimg[Yo,Xo] = otherimg
                plt.subplot(2,3,1)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=-0.01, vmax=0.1,
                           cmap='gray')
                plt.title('other images')
                showimg[Yo,Xo] = otherwt
                plt.subplot(2,3,2)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=0)
                plt.title('other wt')
                showimg[Yo,Xo] = sndiff
                plt.subplot(2,3,3)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=0, vmax=10)
                plt.title('S/N diff')
                showimg[Yo,Xo] = rimg
                plt.subplot(2,3,4)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=-0.01, vmax=0.1,
                           cmap='gray')
                plt.title('this image')
                showimg[Yo,Xo] = wt
                plt.subplot(2,3,5)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=0)
                plt.title('this wt')
                plt.suptitle(tim.name)
                showimg[Yo,Xo] = reldiff
                plt.subplot(2,3,6)
                plt.imshow(showimg, interpolation='nearest', origin='lower', vmin=0, vmax=4)
                plt.title('rel diff')
                ps.savefig()
                

            del otherimg

            # Significant pixels
            hotpix = ((sndiff > 5.) * (reldiff > 2.) * (otherwt > 1e-16) * (wt > 0.) *
                      (veto[Yo,Xo] == False))

            del reldiff, otherwt

            if not np.any(hotpix):
                continue

            hot = np.zeros((H,W), bool)
            hot[Yo,Xo] = hotpix

            del hotpix

            snmap = np.zeros((H,W), np.float32)
            snmap[Yo,Xo] = sndiff

            hot = binary_dilation(hot, iterations=1)
            if plots:
                heat = hot.astype(np.uint8)
            # "warm"
            hot = np.logical_or(hot,
                                binary_dilation(hot, iterations=5) * (snmap > 3.))
            hot = binary_dilation(hot, iterations=1)
            if plots:
                heat += hot
            # "lukewarm"
            hot = np.logical_or(hot,
                                binary_dilation(hot, iterations=5) * (snmap > 2.))
            hot = binary_dilation(hot, iterations=3)

            if plots:
                heat += hot
                plt.clf()
                plt.imshow(heat, interpolation='nearest', origin='lower', cmap='hot')
                plt.title(tim.name + ': outliers')
                ps.savefig()
                del heat

            del snmap

            bad, = np.nonzero(hot[Yo,Xo])
            badcoadd[Yo[bad],Xo[bad]] += tim.getImage()[Yi[bad],Xi[bad]]
            badcon[Yo[bad],Xo[bad]] += 1

            # Actually do the masking!
            # Resample "hot" (in brick coords) back to tim coords.
            try:
                mYo,mXo,mYi,mXi,nil = resample_with_wcs(
                    tim.subwcs, targetwcs, [], 3)
            except OverlapError:
                continue
            Ibad, = np.nonzero(hot[mYi,mXi])
            # Zero out the invvar for the bad pixels
            if len(Ibad):
                print('Masking', len(Ibad), 'outlier pixels')
                nz = np.sum(tim.getInvError() == 0)
                tim.getInvError()[mYo[Ibad],mXo[Ibad]] = 0.
                nz2 = np.sum(tim.getInvError() == 0)
                print('Masked', nz2-nz, 'outlier pixels')
                # Also update DQ mask.
                tim.dq[mYo[Ibad],mXo[Ibad]] |= CP_DQ_BITS['outlier']

                # Write out a mask file.
                maskedpix = np.zeros(tim.shape, np.uint8)
                maskedpix[mYo[Ibad], mXo[Ibad]] = 1
                # copy version_header before modifying it.
                hdr = fitsio.FITSHDR()
                for r in version_header.records():
                    hdr.add_record(r)
                # Plug in the tim WCS header
                tim.subwcs.add_to_header(hdr)
                hdr.delete('IMAGEW')
                hdr.delete('IMAGEH')
                hdr.add_record(dict(name='IMTYPE', value='outlier_mask',
                                    comment='LegacySurvey image type'))
                hdr.add_record(dict(name='CAMERA', value=tim.imobj.camera))
                hdr.add_record(dict(name='EXPNUM', value=tim.imobj.expnum))
                hdr.add_record(dict(name='CCDNAME', value=tim.imobj.ccdname))
                hdr.add_record(dict(name='X0', value=tim.x0))
                hdr.add_record(dict(name='Y0', value=tim.y0))
                with survey.write_output('outliers_mask', brick=brickname,
                                              camera=tim.imobj.camera.strip(), expnum=tim.imobj.expnum, ccdname=tim.imobj.ccdname.strip(), shape=maskedpix.shape) as out:
                    out.fits.write(maskedpix, header=hdr)

        badcoadds.append(badcoadd / np.maximum(badcon, 1))
    return badcoadds
