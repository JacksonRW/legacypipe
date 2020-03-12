import numpy as np

class Duck(object):
    pass

def stage_largegalaxies(
        survey=None, targetwcs=None, pixscale=None, bands=None, tims=None,
        brickname=None, version_header=None,
        apodize=True,
        plots=False, ps=None, coadd_bw=False, W=None, H=None,
        brick=None, blobs=None, lanczos=True, ccds=None,
        write_metrics=True,
        mp=None, record_event=None,
        **kwargs):

    from legacypipe.coadds import make_coadds, write_coadd_images
    from legacypipe.bits import DQ_BITS
    from legacypipe.survey import get_rgb, imsave_jpeg, LegacySurveyWcs

    from tractor.image import Image
    from tractor.basics import NanoMaggies, LinearPhotoCal
    from tractor.sky import ConstantSky
    from tractor.psf import PixelizedPSF
    #from tractor.wcs import ConstantFitsWcs
    #from tractor import GaussianMixturePSF
    from tractor.tractortime import TAITime
    import astropy.time
    import fitsio
    from collections import Counter
    
    # Create coadds and then build custom tims from them.

    # We tried setting the invvars constant per tim -- this makes things worse, since we *remove*
    # the lowered invvars at the cores of galaxies.
    # for tim in tims:
    #     ie = tim.inverr
    #     newie = np.ones(ie.shape, np.float32) / (tim.sig1)
    #     newie[ie == 0] = 0.
    #     tim.inverr = newie

    # Here we're hacking the relative weights -- squaring the weights but then making the median
    # the same, ie, squaring the dynamic range or relative weights -- ie, downweighting the cores
    # even more than they already are from source Poisson terms.
    for tim in tims:
        ie = tim.inverr
        median_ie = np.median(ie[ie>0])
        # newie = (ie / median_ie)**2 * median_ie
        newie = ie**2 / median_ie
        tim.inverr = newie    
        #print('Tim', tim.name, ': dq values', Counter(tim.dq.ravel()))
        
    C = make_coadds(tims, bands, targetwcs,
                    detmaps=True, ngood=True, lanczos=lanczos,
                    allmasks=True, psf_images=True,
                    mp=mp, plots=plots, ps=ps,
                    callback=None)
    if False: # useful for quickly looking at the image coadd
        with survey.write_output('image-jpeg', brick=brickname) as out:
            imsave_jpeg(out.fn, get_rgb(C.coimgs, bands), origin='lower')

    if plots:
        import pylab as plt
        for band,iv in zip(bands, C.cowimgs):
            plt.clf()
            plt.imshow(np.sqrt(iv), interpolation='nearest', origin='lower')
            plt.title('Coadd Inverr: band %s' % band)
            ps.savefig()

        for band,psf in zip(bands, C.psf_imgs):
            plt.clf()
            plt.imshow(psf, interpolation='nearest', origin='lower')
            plt.title('Coadd PSF image: band %s' % band)
            ps.savefig()

        for band,img,iv in zip(bands, C.coimgs, C.cowimgs):
            from scipy.ndimage.filters import gaussian_filter
            plt.clf()
            plt.hist((img * np.sqrt(iv))[iv>0], bins=50, range=(-5,8), log=True)
            plt.title('Coadd pixel values (sigmas): band %s' % band)
            ps.savefig()

            psf_sigma = np.mean([(tim.psf_sigma * tim.imobj.pixscale / pixscale)
                                 for tim in tims if tim.band == band])
            gnorm = 1./(2. * np.sqrt(np.pi) * psf_sigma)
            psfnorm = gnorm #np.sqrt(np.sum(psfimg**2))
            detim = gaussian_filter(img, psf_sigma) / psfnorm**2
            cosig1 = 1./np.sqrt(np.median(iv[iv>0]))
            detsig1 = cosig1 / psfnorm
            plt.clf()
            plt.hist(detim.ravel() / detsig1, bins=50, range=(-5,8), log=True)
            plt.title('Coadd detection map values (sigmas): band %s' % band)
            ps.savefig()
   
    cotims = []
    for band,img,iv,mask,psfimg in zip(bands, C.coimgs, C.cowimgs, C.allmasks, C.psf_imgs):
        mjd = np.mean([tim.imobj.mjdobs for tim in tims if tim.band == band])
        mjd_tai = astropy.time.Time(mjd, format='mjd', scale='utc').tai.mjd
        tai = TAITime(None, mjd=mjd_tai)

        twcs = LegacySurveyWcs(targetwcs, tai)

        #print('PSF sigmas (in pixels) for band', band, ':',
        #      ['%.2f' % tim.psf_sigma for tim in tims if tim.band == band])
        print('PSF sigmas in coadd pixels:',
              ['%.2f' % (tim.psf_sigma * tim.imobj.pixscale / pixscale)
               for tim in tims if tim.band == band])
        psf_sigma = np.mean([(tim.psf_sigma * tim.imobj.pixscale / pixscale)
                             for tim in tims if tim.band == band])
        print('Using average PSF sigma', psf_sigma)

        psf = PixelizedPSF(psfimg)
        gnorm = 1./(2. * np.sqrt(np.pi) * psf_sigma)

        psfnorm = np.sqrt(np.sum(psfimg**2))
        print('Gaussian PSF norm', gnorm, 'vs pixelized', psfnorm)

        # if plots:
        #     plt.clf()
        #     plt.imshow(mask, interpolation='nearest', origin='lower')
        #     plt.colorbar()
        #     plt.title('allmask')
        #     ps.savefig()
        #     print('allmask for band', band, ': values:', Counter(mask.ravel()))

        # Scale invvar to take into account that we have resampled (~double-counted) pixels
        cscale = np.mean([tim.imobj.pixscale / pixscale for tim in tims if tim.band == band])
        print('average tim pixel scale / coadd scale:', cscale)

        iv /= cscale**2

        cotim = Image(img, invvar=iv, wcs=twcs, psf=psf,
                      photocal=LinearPhotoCal(1., band=band),
                      sky=ConstantSky(0.), name='coadd-'+band)
        cotim.band = band
        cotim.subwcs = targetwcs
        cotim.psf_sigma = psf_sigma
        cotim.sig1 = 1./np.sqrt(np.median(iv[iv>0]))
        cotim.dq = mask
        cotim.dq_saturation_bits = DQ_BITS['satur']
        cotim.psfnorm = gnorm
        cotim.galnorm = 1.0 # bogus!
        cotim.imobj = Duck()
        cotim.imobj.fwhm = 2.35 * psf_sigma
        cotim.time = tai
        cotim.primhdr = fitsio.FITSHDR()

        cotims.append(cotim)

    # EVIL
    return dict(tims=cotims)

