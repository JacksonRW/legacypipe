from __future__ import print_function
import sys
import os
import numpy as np
import pylab as plt
import fitsio
from astrometry.util.fits import fits_table, merge_tables
from astrometry.util.plotutils import PlotSequence, plothist, loghist
from legacypipe.common import LegacySurveyData, imsave_jpeg, get_rgb

'''
A script to examine the pixel distributions vs the CP weight maps.
'''


survey = LegacySurveyData()
ccds = survey.get_ccds_readonly()
#ccds = ccds[np.abs(ccds.mjd_obs - 57444) < 7.]
#print(len(ccds), 'CCDs near mjd')
ccds.cut(ccds.ccdname == 'N4')
print(len(ccds), 'exposures')
print('bands:', np.unique(ccds.filter))

## HACK
np.random.seed(44)

# Alternate 'oki' and 'ooi' images...
oki = np.array(['oki' in ccd.image_filename for ccd in ccds])
I1 = np.flatnonzero(oki)
I2 = np.flatnonzero(oki == False)
print(len(I1), 'oki images')
print(len(I2), 'non-oki images')
ccds.cut(np.hstack(zip(I1[np.random.permutation(len(I1))],
                       I2[np.random.permutation(len(I2))])))
#ccds.cut(np.random.permutation(len(ccds)))

ps = PlotSequence('noise')

for ccd in ccds[:1]:
    im = survey.get_image_object(ccd)

    #tim2 = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False,
    #                             nanomaggies=False, subsky=False)
    #tim = tim2
    tim = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False)
    img = tim.getImage()
    ie = tim.getInvError()

    plt.clf()
    plt.subplot(2,1,1)
    n,b,p1 = plt.hist(img[ie>0].ravel(), range=(-5. * tim.sig1, 5. * tim.sig1),
                     bins=100, histtype='step', color='b')
    bc = (b[:-1] + b[1:])/2.
    y = np.exp(-0.5 * bc**2 / tim.sig1**2)
    N = np.sum(n)
    y *= N / np.sum(y)
    p2 = plt.plot(bc, y, 'r--')
    plt.xlim(-5.*tim.sig1, 5.*tim.sig1)
    plt.yscale('symlog')
    plt.legend((p1[0], p2[0]), ('Image pixels', 'Gaussian sig1'), loc='lower center')

    plt.subplot(2,1,2)
    n,b,p1 = plt.hist((img * ie)[ie>0].ravel(), range=(-5., 5.), bins=100,
                      histtype='step', color='b')
    bc = (b[:-1] + b[1:])/2.
    y = np.exp(-0.5 * bc**2)
    N = np.sum(n)
    y *= N / np.sum(y)
    p2 = plt.plot(bc, y, 'r--')
    plt.xlim(-5., 5.)
    plt.yscale('symlog')
    plt.legend((p1[0], p2[0]), ('Image pixels * sqrt(Weight map)', 'Unit gaussian'),
               loc='lower center')

    plt.suptitle(tim.name)
    ps.savefig()


for ccd in ccds[:2]:
    im = survey.get_image_object(ccd)

    tim2 = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False,
                                 nanomaggies=False, subsky=False)
    tim = tim2
    #tim = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False)
    img = tim.getImage()
    ie = tim.getInvError()

    skymod = np.zeros_like(img)
    tim.getSky().addTo(skymod)
    midsky = np.median(skymod)
    print('Median spline sky model level:', midsky)
    #img -= midsky

    medsky = np.median(img[ie > 0])
    print('Median image level:', medsky)
    img -= medsky

    # Select pixels in range [-2 sigma, +2 sigma]

    ie[np.logical_or(img < -2.*tim.sig1, img > 2.*tim.sig1)] = 0.

    medsky = np.median(img[ie > 0])
    print('Median of unmasked image pixels:', medsky)

    plt.clf()
    plt.imshow(img * (ie > 0), interpolation='nearest', origin='lower',
               vmin=-2.*tim.sig1, vmax=2.*tim.sig1)
    plt.title(tim.name)
    ps.savefig()

    dists = np.arange(1, 51)
    corrs = []
    corrs_x = []
    corrs_y = []

    rcorrs = []
    rcorrs_x = []
    rcorrs_y = []


    for dist in dists:
        offset = dist
        slice1 = (slice(0,-offset,1),slice(0,-offset,1))
        slice2 = (slice(offset,None,1),slice(offset,None,1))

        slicex = (slice1[0], slice2[1])
        slicey = (slice2[0], slice1[1])

        corr = img[slice1] * img[slice2]
        corr = corr[(ie[slice1] > 0) * (ie[slice2] > 0)]
        print('Dist', dist, '; number of corr pixels', len(corr))
        rcorr = np.median(corr) / tim.sig1**2
        corr = np.mean(corr) / tim.sig1**2
        print('-> corr', corr)
        corrs.append(corr)
        rcorrs.append(rcorr)

        corr = img[slice1] * img[slicex]
        corr = corr[(ie[slice1] > 0) * (ie[slicex] > 0)]
        rcorr = np.median(corr) / tim.sig1**2
        corr = np.mean(corr) / tim.sig1**2
        corrs_x.append(corr)
        rcorrs_x.append(rcorr)

        corr = img[slice1] * img[slicey]
        corr = corr[(ie[slice1] > 0) * (ie[slicey] > 0)]
        rcorr = np.median(corr) / tim.sig1**2
        corr = np.mean(corr) / tim.sig1**2
        corrs_y.append(corr)
        rcorrs_y.append(rcorr)

    plt.clf()
    p1 = plt.plot(dists, corrs, 'b.-')
    p2 = plt.plot(dists, corrs_x, 'r.-')
    p3 = plt.plot(dists, corrs_y, 'g.-')
    p4 = plt.plot(dists, rcorrs, 'b.--')
    p5 = plt.plot(dists, rcorrs_x, 'r.--')
    p6 = plt.plot(dists, rcorrs_y, 'g.--')
    plt.xlabel('Pixel offset')
    plt.ylabel('Correlation')
    plt.legend([p1[0],p2[0],p3[0]], ['Diagonal', 'X', 'Y'], loc='upper right')
    plt.title(tim.name + ' ' + '/'.join(im.imgfn.split('/')[-2:]))
    #plt.ylim(-0.005, 0.02)
    plt.ylim(-0.001, 0.011)
    plt.axhline(0, color='k', alpha=0.3)
    ps.savefig()



sys.exit(0)


allsigs1 = []
allsigs2 = []

for ccd in ccds[:16]:
    im = survey.get_image_object(ccd)

    tim1 = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False)

    tim2 = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False,
                                 nanomaggies=False, subsky=False)
    tim = tim2

    for tim,sigs in [(tim1,allsigs1),(tim2,allsigs2)]:
        img = tim.getImage()
        ie = tim.getInvError()

        # # Estimate per-pixel noise via Blanton's 5-pixel MAD
        #plt.clf()
    
        bsigs = {}
        for offset in [5, 3, 1]:
            slice1 = (slice(0,-offset,10),slice(0,-offset,10))
            slice2 = (slice(offset,None,10),slice(offset,None,10))
            diff = img[slice1] - img[slice2]
            #print('Blanton number of pixels:', len(diff.ravel()))
            diff = diff[(ie[slice1] > 0) * (ie[slice2] > 0)]
            #print('Blanton number of pixels kept:', len(diff.ravel()))
            mad = np.median(np.abs(diff).ravel())
            bsig1 = 1.4826 * mad / np.sqrt(2.)
            bsigs[offset] = bsig1
    
            #plt.hist(np.abs(diff), range=(0, tim.sig1*5), bins=100, histtype='step',
            #         label='Blanton(%i)' % offset, normed=True)
        # Draw random pixels and see what that MAD distribution looks like
        pix = img[ie>0].ravel()
        Ndiff = len(diff)
        P = np.random.permutation(len(pix))[:(Ndiff*2)]
        diff2 = pix[P[:Ndiff]] - pix[P[Ndiff:]]
        mad2 = np.median(np.abs(diff2).ravel())
        bsig2 = 1.4826 * mad2 / np.sqrt(2.)
        bsigs[0] = bsig2
        #plt.hist(np.abs(diff2), range=(0, tim.sig1*5), bins=50, histtype='step',
        #         label='Blanton(Random)', normed=True)
    
        # Draw Gaussian random pixels
        print('                                           sig1: %.2f' % tim.sig1)
        diff3 = tim.sig1 * (np.random.normal(size=Ndiff) - np.random.normal(size=Ndiff))
        mad3 = np.median(np.abs(diff3).ravel())
        bsig3 = 1.4826 * mad3 / np.sqrt(2.)
        print('Blanton sig1 estimate for Gaussian pixels      : %.2f' % bsig3)
        bsigs[-1] = bsig3
        #plt.hist(np.abs(diff3), range=(0, tim.sig1*5), bins=50, histtype='step',
        #         label='Blanton(Gaussian)', normed=True)
    
        for offset in [1,3,5]:
            print('Blanton sig1 estimate for offset of %i pixels   : %.2f' % (offset, bsigs[offset]))
    
        print('Blanton sig1 estimate for randomly drawn pixels: %.2f' % bsig2)
    
        # plt.xlim(0, tim.sig1*5)
        # plt.legend()
        # plt.xlabel('abs(pixel difference)')
        # ps.savefig()
    
        sigs.append([bsigs[o]/tim.sig1 for o in [-1, 1, 3, 5, 0]])


allsigs = np.array(allsigs1)

plt.clf()
plt.plot(allsigs.T, 'bo-')
plt.xticks(np.arange(5), ['Gaussian', '1 pix', '3 pix', '5 pix', 'Random'])
plt.axhline(1., color='k', alpha=0.3)
plt.ylabel('Error estimate / pipeline sig1')
plt.title('Error estimates vs pixel difference distributions (w/splinesky)')
ps.savefig()

allsigs = np.array(allsigs2)

plt.clf()
plt.plot(allsigs.T, 'bo-')
plt.xticks(np.arange(5), ['Gaussian', '1 pix', '3 pix', '5 pix', 'Random'])
plt.axhline(1., color='k', alpha=0.3)
plt.ylabel('Error estimate / pipeline sig1')
plt.title('Error estimates vs pixel difference distributions')
ps.savefig()


sys.exit(0)



for ccd in ccds[:1]:
    im = survey.get_image_object(ccd)

    plt.clf()
    plt.subplot(3,1,1)
    n,b,p1 = plt.hist(img[ie>0].ravel(), range=(-5. * tim.sig1, 5. * tim.sig1),
                     bins=100, histtype='step', color='b')
    bc = (b[:-1] + b[1:])/2.
    y = np.exp(-0.5 * bc**2 / tim.sig1**2)
    N = np.sum(n)
    y *= N / np.sum(y)
    p2 = plt.plot(bc, y, 'r--')
    plt.xlim(-5.*tim.sig1, 5.*tim.sig1)
    plt.yscale('symlog')
    plt.legend((p1[0], p2[0]), ('Image pixels', 'Gaussian sig1'), loc='lower center')

    plt.subplot(3,1,2)
    n,b,p1 = plt.hist((img * ie)[ie>0].ravel(), range=(-5., 5.), bins=100,
                      histtype='step', color='b')
    bc = (b[:-1] + b[1:])/2.
    y = np.exp(-0.5 * bc**2)
    N = np.sum(n)
    y *= N / np.sum(y)
    p2 = plt.plot(bc, y, 'r--')
    plt.xlim(-5., 5.)
    plt.yscale('symlog')
    plt.legend((p1[0], p2[0]), ('Image pixels / sqrt(Weight map)', 'Unit gaussian'),
               loc='lower center')


    bsig1 = bsigs[5]

    plt.subplot(3,1,3)
    lo,hi = min(tim.sig1 * 0.8, bsig1*0.9), max(tim.sig1 * 1.2, bsig1*1.1)
    n,b,p1 = plt.hist((1. / ie[ie>0]).ravel(), range=(lo,hi), bins=100,
                     histtype='step', color='b')
    p2 = plt.axvline(tim.sig1, color='b')
    p3 = plt.axvline(bsig1, color='r')

    pb3 = plt.axvline(bsigs[3], color='g')
    pb1 = plt.axvline(bsigs[1], color='m')
    pb0 = plt.axvline(bsigs[0], color='k')

    plt.xlim(lo,hi)
    #plt.legend((p1[0],p2,p3), ('Weight map', 'sig1', 'Blanton sig1'))
    plt.legend((p1[0],p2,p3,pb3,pb1,pb0), ('Weight map', 'sig1', 'Blanton(5) sig1',
                                           'Blanton(3)', 'Blanton(1)', 'Blanton(random)'))

    # This shows the results without any zeropoint scaling or sky subtraction; looks the same.
    # tim2 = im.get_tractor_image(gaussPsf=True, splinesky=True, dq=False,
    #                             nanomaggies=False, subsky=False)
    # img = tim2.getImage()
    # ie = tim2.getInvError()
    # diff = img[slice1] - img[slice2]
    # diff = diff[(ie[slice1] > 0) * (ie[slice2] > 0)]
    # mad = np.median(np.abs(diff).ravel())
    # bsig2 = 1.4826 * mad / np.sqrt(2.)
    # print('Blanton sig1 estimate #2:', bsig2)
    # print('sig1 #2:', tim2.sig1)
    # plt.subplot(2,2,4)
    # lo,hi = min(tim2.sig1 * 0.8, bsig2*0.9), max(tim2.sig1 * 1.2, bsig2*1.1)
    # n,b,p1 = plt.hist((1. / ie[ie > 0]).ravel(), range=(lo,hi), bins=100,
    #                  histtype='step', color='b')
    # p2 = plt.axvline(tim2.sig1, color='b')
    # p3 = plt.axvline(bsig2, color='r')
    # plt.xlim(lo,hi)
    # plt.legend((p1[0],p2,p3), ('Weight map', 'sig1', 'Blanton sig1'))

    plt.suptitle(tim.name)
    ps.savefig()


    


