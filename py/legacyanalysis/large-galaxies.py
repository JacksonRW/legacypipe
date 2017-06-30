#!/usr/bin/env python

"""Redo the Tractor photometry of the "large" galaxies in Legacy Survey imaging.

dependencies:
  pillow
  photutils

python large-galaxies --build-sample
python large-galaxies --viewer-cutouts
python large-galaxies --ccd-cutouts
python large-galaxies --runbrick


rsync -avPn --files-from='/tmp/ccdfiles.txt' nyx:/usr/local/legacysurvey/legacypipe-dir/ /Users/ioannis/repos/git/legacysurvey/legacypipe-dir/

J. Moustakas
Siena College
2016 June 6

ToDo:  redo the query with objtype restricted (see my TechNote)

objtype='G' or objtype='g' or objtype='M' or objtype='M2' or objtype='M3' or objtype='MG' or objtype='MC'




http://leda.univ-lyon1.fr/leda/fullsql.html

Output file 1: leda-logd25-0.05-0.50.txt

SELECT
  pgc,
  objname,
  objtype,
  al2000,
  de2000,
  type,
  multiple,
  logd25,
  logr25,
  pa,
  bt,
  it,
  v
WHERE logd25 > 0.05 AND logd25 < 0.5

Output file 1: leda-logd25-0.50.txt

SELECT
  pgc,
  objname,
  objtype,
  al2000,
  de2000,
  type,
  multiple,
  logd25,
  logr25,
  pa,
  bt,
  it,
  v
WHERE logd25 > 0.5

"""
from __future__ import division, print_function

import os
import sys
import pdb
import argparse
import multiprocessing

import numpy as np
from glob import glob

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LogNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable

from scipy.ndimage.morphology import binary_dilation
#from scipy.ndimage.filters import gaussian_filter
import astropy.units as u
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.coordinates import SkyCoord

from astropy.io import fits
from astropy.table import Table, vstack, hstack
from astropy.visualization import scale_image
from astropy.modeling import models, fitting

from PIL import Image, ImageDraw, ImageFont
from photutils import CircularAperture, CircularAnnulus, aperture_photometry
                
import seaborn as sns

from astrometry.util.util import Tan
from astrometry.util.fits import fits_table, merge_tables
from astrometry.util.plotutils import dimshow
from astrometry.util.miscutils import clip_polygon
from astrometry.libkd.spherematch import match_radec
from tractor.splinesky import SplineSky

from legacypipe.runbrick import run_brick
from legacypipe.survey import ccds_touching_wcs, LegacySurveyData

from legacypipe.cpimage import CP_DQ_BITS

PIXSCALE = 0.262 # average pixel scale [arcsec/pix]
DIAMFACTOR = 5
#DIAMFACTOR = 10

def _uniqccds(ccds):
    '''Get the unique set of CCD files.'''
    ccdfile = []
    [ccdfile.append('{}-{}'.format(expnum, ccdname)) for expnum,
     ccdname in zip(ccds.expnum, ccds.ccdname)]
    _, indx = np.unique(ccdfile, return_index=True)
    return ccds[indx]

def _getfiles(ccdinfo):
    '''Figure out the set of images and calibration files we need to transfer, if any.'''

    nccd = len(ccdinfo)

    survey = LegacySurveyData()
    calibdir = survey.get_calib_dir()
    imagedir = survey.survey_dir

    expnum = ccdinfo.expnum
    ccdname = ccdinfo.ccdname

    psffiles = list()
    skyfiles = list()
    imagefiles = list()
    for ccd in ccdinfo:
        info = survey.get_image_object(ccd)
        for attr in ['imgfn', 'dqfn', 'wtfn']:
            imagefiles.append(getattr(info, attr).replace(imagedir+'/', ''))
        psffiles.append(info.psffn.replace(calibdir, 'calib'))
        skyfiles.append(info.splineskyfn.replace(calibdir, 'calib'))

    ccdfiles = open('/tmp/ccdfiles.txt', 'w')
    for ff in psffiles:
        ccdfiles.write(ff+'\n')
    for ff in skyfiles:
        ccdfiles.write(ff+'\n')
    for ff in imagefiles:
        ccdfiles.write(ff+'\n')
    ccdfiles.close()

    cmd = "rsync -avPn --files-from='/tmp/ccdfiles.txt' edison:/global/cscratch1/sd/desiproc/dr3/ /global/work/legacysurvey/"
    print('You should run the following command:')
    print('  {}'.format(cmd))

def _catalog_template(nobj=1):
    cols = [
        ('GALAXY', 'S28'), 
        ('PGC', 'S10'), 
        ('RA', 'f8'), 
        ('DEC', 'f8'),
        ('TYPE', 'S8'),
        ('MULTIPLE', 'S1'),
        ('RADIUS', 'f4'),
        ('BA', 'f4'),
        ('PA', 'f4'),
        ('BMAG', 'f4'),
        ('IMAG', 'f4'),
        ('VHELIO', 'f4'),
        ('BRICKNAME', 'S17', (4,))
        ]
    catalog = Table(np.zeros(nobj, dtype=cols))
    catalog['RADIUS'].unit = 'arcsec'
    catalog['VHELIO'].unit = 'km/s'

    return catalog

def _ccdwcs(ccd):
    '''Build a simple WCS object for each CCD.'''
    W, H = ccd.width, ccd.height
    ccdwcs = Tan(*[float(xx) for xx in [ccd.crval1, ccd.crval2, ccd.crpix1,
                                        ccd.crpix2, ccd.cd1_1, ccd.cd1_2,
                                        ccd.cd2_1, ccd.cd2_2, W, H]])
    return W, H, ccdwcs

def _galwcs(gal, factor=DIAMFACTOR):
    '''Build a simple WCS object for a single galaxy.'''
    diam = factor*np.ceil(2.0*gal['RADIUS']/PIXSCALE).astype('int16') # [pixels]
    galwcs = Tan(gal['RA'], gal['DEC'], diam/2+0.5, diam/2+0.5,
                 -PIXSCALE/3600.0, 0.0, 0.0, PIXSCALE/3600.0, 
                 float(diam), float(diam))
    return galwcs

def _build_sample_onegalaxy(args):
    """Filler function for the multiprocessing."""
    return build_sample_onegalaxy(*args)

def build_sample_onegalaxy(gal, allccds, ccdsdir, bricks, survey):
    """Wrapper function to find overlapping CCDs for a given galaxy.

    First generously find the nearest set of CCDs that are near the galaxy and
    then demand that there's 3-band coverage in a much smaller region centered
    on the galaxy.

    """
    #print('Working on {}...'.format(gal['GALAXY'].strip()))
    galwcs = _galwcs(gal)
    these = ccds_touching_wcs(galwcs, allccds)

    if len(these) > 0:
        ccds1 = _uniqccds( allccds[these] )

        # Is there 3-band coverage?
        galwcs_small = _galwcs(gal, factor=0.5)
        these_small = ccds_touching_wcs(galwcs_small, ccds1)
        ccds1_small = _uniqccds( ccds1[these_small] )

        if 'g' in ccds1_small.filter and 'r' in ccds1_small.filter and 'z' in ccds1_small.filter:
            print('For {} found {} CCDs, RA = {:.5f}, Dec = {:.5f}, Radius={:.4f} arcsec'.format(
                gal['GALAXY'].strip(), len(ccds1), gal['RA'], gal['DEC'], gal['RADIUS']))

            ccdsfile = os.path.join(ccdsdir, '{}-ccds.fits'.format(gal['GALAXY'].strip().lower()))
            #print('  Writing {}'.format(ccdsfile))
            if os.path.isfile(ccdsfile):
                os.remove(ccdsfile)
            ccds1.writeto(ccdsfile)

            # Also get the set of bricks touching this footprint.
            rad = 2*gal['RADIUS']/3600 # [degree]
            brickindx = survey.bricks_touching_radec_box(bricks,
                                                         gal['RA']-rad, gal['RA']+rad,
                                                         gal['DEC']-rad, gal['DEC']+rad)
            if len(brickindx) == 0 or len(brickindx) > 4:
                print('This should not happen!')
                pdb.set_trace()
            gal['BRICKNAME'][:len(brickindx)] = bricks.brickname[brickindx]

            return [gal, ccds1]

    return None

def read_rc3():
    """Read the RC3 catalog and put it in a standard format."""
    catdir = os.getenv('CATALOGS_DIR')
    cat = fits.getdata(os.path.join(catdir, 'rc3', 'rc3_catalog.fits'), 1)

    ## For testing -- randomly pre-select a subset of galaxies.
    #nobj = 500
    #seed = 5781
    #rand = np.random.RandomState(seed)
    #these = rand.randint(0, len(cat)-1, nobj)
    #cat = cat[these]

    outcat = _catalog_template(len(cat))
    outcat['RA'] = cat['RA']
    outcat['DEC'] = cat['DEC']
    outcat['RADIUS'] = 0.1*10.0**cat['LOGD_25']*60.0/2.0 # semi-major axis diameter [arcsec]
    fix = np.where(outcat['RADIUS'] == 0.0)[0]
    if len(fix) > 0:
        outcat['RADIUS'][fix] = 30.0
    
    #plt.hist(outcat['RADIUS'], bins=50, range=(1, 300))
    #plt.show()

    for name in ('NAME1', 'NAME2', 'NAME3', 'PGC'):
        need = np.where(outcat['GALAXY'] == '')[0]
        if len(need) > 0:
            outcat['GALAXY'][need] = cat[name][need].replace(' ', '')

    # Temporarily cull the sample.
    these = np.where((outcat['RADIUS'] > 20)*(outcat['RADIUS'] < 25))[0]
    outcat = outcat[these] 

    return outcat

def read_leda(largedir='.', d25min=0.0, d25max=1000.0,
              decmin=-90.0, decmax=+90.0,
              ramin=0.0, ramax=360.0):
    """Read the parent LEDA catalog and put it in a standard format."""

    cat = fits.getdata(os.path.join(largedir, 'sample', 'leda-logd25-0.05.fits.gz'), 1)

    outcat = _catalog_template(len(cat))
    outcat['GALAXY'] = cat['GALAXY']
    outcat['PGC'] = cat['PGC']
    outcat['RA'] = cat['RA']
    outcat['DEC'] = cat['DEC']
    outcat['TYPE'] = cat['TYPE']
    outcat['MULTIPLE'] = cat['MULTIPLE']
    outcat['RADIUS'] = cat['D25']/2.0 # semi-major axis radius [arcsec]
    outcat['BA'] = cat['BA']
    outcat['PA'] = cat['PA']
    outcat['BMAG'] = cat['BMAG']
    outcat['IMAG'] = cat['IMAG']
    outcat['VHELIO'] = cat['VHELIO']

    these = np.where((outcat['RADIUS']*2/60.0 <= d25max) *
                     (outcat['RADIUS']*2/60.0 >= d25min) *
                     (outcat['DEC'] <= decmax) *
                     (outcat['DEC'] >= decmin) *
                     (outcat['RA'] <= ramax) *
                     (outcat['RA'] >= ramin)
                     )[0]
    outcat = outcat[these] 

    return outcat

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--dr', type=str, default='dr3', help='DECaLS Data Release')
    parser.add_argument('--build-sample', action='store_true', help='Build the sample.')
    parser.add_argument('--viewer-cutouts', action='store_true', help='Get jpg cutouts from the viewer.')
    parser.add_argument('--ccd-cutouts', action='store_true', help='Get CCD cutouts of each galaxy.')
    parser.add_argument('--runbrick', action='store_true', help='Run the pipeline.')
    parser.add_argument('--runbrick-cutouts', action='store_true', help='Annotate the jpg cutouts from the custom pipeline.')
    parser.add_argument('--build-webpage', action='store_true', help='(Re)build the web content.')
    parser.add_argument('--nproc', type=int, help='number of concurrent processes to use', default=16)
    args = parser.parse_args()

    # Top-level directory
    key = 'LEGACY_SURVEY_LARGE_GALAXIES'
    if key not in os.environ:
        print('Required ${} environment variable not set'.format(key))
        return 0
    largedir = os.getenv(key)

    dr = args.dr.lower()
    key = 'DECALS_{}_DIR'.format(dr.upper())
    if key not in os.environ:
        print('Required ${} environment variable not set'.format(key))
        return 0
    drdir = os.getenv(key)

    # Some convenience variables.
    objtype = ('PSF', 'SIMP', 'EXP', 'DEV', 'COMP')
    objcolor = ('white', 'red', 'orange', 'cyan', 'yellow')
    thumbsize = 100

    #fonttype = os.path.join(os.sep, 'Volumes', 'Macintosh\ HD', 'Library', 'Fonts', 'Georgia.ttf')
    fonttype = os.path.join(os.sep, 'usr', 'share', 'fonts', 'gnu-free', 'FreeSans.ttf')

    # Read the sample (unless we're building it!)
    samplefile = os.path.join(largedir, 'sample', 'large-galaxies-{}.fits'.format(dr))
    if not args.build_sample:
        sample = fits.getdata(samplefile, 1)
        #sample = sample[np.where(np.char.strip(sample['GALAXY']) == 'NGC4073')]
        #sample = sample[np.where(np.char.strip(sample['GALAXY']) == 'UGC04203')]
        #sample = sample[0:3] # Hack!
        #sample = sample[np.where(np.sum((sample['BRICKNAME'] != '')*1, 1) > 1)[0]]
        #pdb.set_trace()
    survey = LegacySurveyData()
    #survey = LegacySurveyData(version=dr) # update to DR3!

    sns.set(style='white', font_scale=1.2, palette='Set2')
    #sns.set(style='white', font_scale=1.3, palette='Set2')
    setcolors = sns.color_palette()

    # Make sure all the necessary subdirectories have been built.
    newdir = ['ccds', 'cutouts', 'html', 'qa', 'sample']
    [os.mkdir(dd) for dd in newdir if not os.path.isdir(dd)]
    
    # --------------------------------------------------
    # Build the sample of large galaxies based on the available imaging.

    # When we read the parent catalog remove the very largest galaxies.  The
    # five galaxies with the largest angular diameters in the LEDA catalog are
    # M31=NGC0224, M33, SMC=NGC0292, the Sagittarius Dwarf, and ESO056-115, all
    # of which have D(25)>50 arcmin (up to 650 arcmin for ESO056-115).  So for
    # now let's cull the sample to everything smaller than about 10 arcmin,
    # which spans no more than two-ish DECam CCDs.  To reduce the size of the
    # sample further, also restrict to things larger than about 30 arcsec (0.5
    # arcmin) in *diameter*.
    
    if args.build_sample:

        # Read the brick and survey-ccds files for this DR.
        if dr == 'dr2':
            bricks = survey.get_bricks_dr2()
        else:
            bricks = survey.get_bricks()

        allccds = survey.get_annotated_ccds()
        cut = survey.photometric_ccds(allccds)
        if cut is not None:
            allccds.cut(cut)
        cut = survey.ccd_cuts(allccds)
        allccds.cut(cut == 0)

        # Read the parent super-sample.
        if False:
            print('Testing with smaller sample cuts!')
            d25min, d25max = 1.0, 5.0
            ramin, ramax = 175, 185
        else:
            d25min, d25max = 0.5, 10.0
            ramin, ramax = 0, 360

        cat = read_leda(largedir=largedir, d25min=d25min, d25max=d25max,
                        decmax=np.max(allccds.dec)+0.3,
                        decmin=np.min(allccds.dec)-0.3,
                        #ramin=ramin, ramax=ramax
                        )
        ngal = len(cat)
        print('Read {} galaxies in the parent catalog with D25 = {}-{} arcmin.'.format(
            ngal, d25min, d25max))

        #print('HACK!!!!!!!!!!!!!!!')
        #cat = read_rc3()
        #cat = cat[0:20]
        #cat = cat[np.where(np.char.strip(cat['GALAXY'].data) == 'NGC4073')[0]]
        #cat = cat[np.where(np.char.strip(cat['GALAXY'].data) == 'IC0497')[0]]
        #cat = cat[np.where(np.char.strip(cat['GALAXY'].data) == 'NGC0963')[0]]
        #cat = cat[:100]

        # Do a gross spherematch of the parent sample against the data release
        # to reduce the sample down to a more reasonable size.  match_radec
        # segfaults -- not sure why.
        
        #m1, m2, d12 = match_radec(allccds.ra, allccds.dec, cat['RA'], cat['DEC'], 0.25, nearest=False)
        rad = 1.0
        print('Spherematching parent catalog against CCDs catalog within {} deg...'.format(rad))
        ccdcoord = SkyCoord(ra=allccds.ra*u.degree, dec=allccds.dec*u.degree)
        catcoord = SkyCoord(ra=cat['RA']*u.degree, dec=cat['DEC']*u.degree)
        idx, sep2d, dist3d = catcoord.match_to_catalog_sky(ccdcoord)
        match = np.where( sep2d < rad*u.degree )[0]

        catindx = np.unique(match)
        ccdindx = np.unique(idx[match])
        print('Selecting subset of {}/{} galaxies and {}/{} CCDs.'.format(
            len(catindx), len(cat), len(ccdindx), len(allccds)))
        
        if False:
            plt.scatter(cat['RA'], cat['DEC'])
            plt.scatter(cat['RA'][catindx], cat['DEC'][catindx], alpha=0.5, color='blue')
            plt.scatter(allccds.ra[ccdindx], allccds.dec[ccdindx], alpha=0.5, color='orange', marker='s')
            plt.show()
            pdb.set_trace()

        cat = cat[catindx]
        allccds = allccds[ccdindx]

        # Next, create a simple WCS object for each object and find all the CCDs
        # touching that WCS footprint.
        ccdsdir = os.path.join(largedir, 'ccds')

        sampleargs = list()
        for cc in cat:
            sampleargs.append( (cc, allccds, ccdsdir, bricks, survey) )

        if args.nproc > 1:
            p = multiprocessing.Pool(args.nproc)
            result = p.map(_build_sample_onegalaxy, sampleargs)
            p.close()
        else:
            result = list()
            for args in sampleargs:
                result.append(_build_sample_onegalaxy(args))

        # Remove non-matching galaxies, write out the sample, and then determine
        # the set of files that need to be transferred to nyx.
        result = list(filter(None, result))
        result = list(zip(*result))

        outcat = vstack(result[0])
        outccds = merge_tables(result[1])

        print(outcat)
        if os.path.isfile(samplefile):
            os.remove(samplefile)
            
        print('Writing {}'.format(samplefile))
        outcat.write(samplefile)

        # Do we need to transfer any of the data to nyx?
        _getfiles(outccds)
        pdb.set_trace()

    # --------------------------------------------------
    # Get data, model, and residual cutouts from the legacysurvey viewer.  Also
    # get thumbnails that are lower resolution.
    if args.viewer_cutouts:
        cutoutdir = os.path.join(largedir, 'cutouts')

        for gal in sample:
            galaxy = gal['GALAXY'].strip().lower()
            cutdir = os.path.join(cutoutdir, '{}'.format(galaxy))
            try:
                os.stat(cutdir)
            except:
                os.mkdir(cutdir)

            # SIZE here should be consistent with DIAM in args.runbrick, below
            size = DIAMFACTOR*np.ceil(gal['RADIUS']/PIXSCALE).astype('int16') # [pixels]
            thumbpixscale = PIXSCALE*size/thumbsize

            # Get cutouts of the data, model, and residual images.
            for imtype, layer in zip( ('image', 'model', 'resid'),
                                      ('', '&layer=decals-{}-model'.format(dr), '&layer=decals-{}-resid'.format(dr))
                                      ):
                imageurl = 'http://legacysurvey.org/viewer-dev/jpeg-cutout/?ra={:.6f}&dec={:.6f}&pixscale={:.3f}&size={:g}{}'.format(
                    gal['RA'], gal['DEC'], PIXSCALE, size, layer)
                imagejpg = os.path.join(cutdir, '{}-{}.jpg'.format(galaxy, imtype))
                #print('Uncomment me to redownload')
                if os.path.isfile(imagejpg):
                    os.remove(imagejpg)
                os.system('wget --continue -O {:s} "{:s}"' .format(imagejpg, imageurl))

            # Also get a small thumbnail of just the image.
            thumburl = 'http://legacysurvey.org/viewer-dev/jpeg-cutout/?ra={:.6f}&dec={:.6f}'.format(gal['RA'], gal['DEC'])+\
              '&pixscale={:.3f}&size={:g}'.format(thumbpixscale, thumbsize)
            thumbjpg = os.path.join(cutdir, '{}-image-thumb.jpg'.format(galaxy))
            if os.path.isfile(thumbjpg):
                os.remove(thumbjpg)
            os.system('wget --continue -O {:s} "{:s}"' .format(thumbjpg, thumburl))

            rad = 10
            for imtype in ('image', 'model', 'resid'):
                imfile = os.path.join(cutdir, '{}-{}.jpg'.format(galaxy, imtype))
                cutoutfile = os.path.join(cutdir, '{}-{}-runbrick-annot.jpg'.format(galaxy, imtype))

                print('Reading {}'.format(imfile))
                im = Image.open(imfile)
                sz = im.size
                fntsize = np.round(sz[0]/35).astype('int')
                font = ImageFont.truetype(fonttype, size=fntsize)
                # Annotate the sources on each cutout.
                wcscutout = Tan(gal['RA'], gal['DEC'], sz[0]/2+0.5, sz[1]/2+0.5,
                                -PIXSCALE/3600.0, 0.0, 0.0, PIXSCALE/3600.0, float(sz[0]), float(sz[1]))
                draw = ImageDraw.Draw(im)
                for bb, brick in enumerate(gal['BRICKNAME'][np.where(gal['BRICKNAME'] != '')[0]]):
                    tractorfile = os.path.join(drdir, 'tractor', '{}'.format(brick[:3]),
                                               'tractor-{}.fits'.format(brick))
                    print('  Reading {}'.format(tractorfile))
                    cat = fits.getdata(tractorfile, 1)
                    cat = cat[np.where(cat['BRICK_PRIMARY']*1)[0]]
                    for ii, (thistype, thiscolor) in enumerate(zip(objtype, objcolor)):
                        these = np.where(cat['TYPE'].strip().upper() == thistype)[0]
                        if len(these) > 0:
                            for obj in cat[these]:
                                ok, xx, yy = wcscutout.radec2pixelxy(obj['RA'], obj['DEC'])
                                xx -= 1 # PIL is zero-indexed
                                yy -= 1
                                #print(obj['RA'], obj['DEC'], xx, yy)
                                draw.ellipse((xx-rad, sz[1]-yy-rad, xx+rad, sz[1]-yy+rad),
                                             outline=thiscolor)

                        # Add a legend, but just after the first brick.
                        if bb == 0:
                            draw.text((20, 20+ii*fntsize*1.2), thistype, font=font, fill=thiscolor)
                draw.text((sz[0]-fntsize*4, sz[1]-fntsize*2), imtype.upper(), font=font)
                print('Writing {}'.format(cutoutfile))
                im.save(cutoutfile)
                #pdb.set_trace()

    # --------------------------------------------------
    # Get cutouts and build diagnostic plots of all the CCDs for each galaxy.
    if args.ccd_cutouts:
        for gal in sample:
            galaxy = gal['GALAXY'].strip().lower()
            print('Building CCD QA for galaxy {}'.format(galaxy.upper()))
            qadir = os.path.join(largedir, 'qa', '{}'.format(galaxy))
            try:
                os.stat(qadir)
            except:
                os.mkdir(qadir)
            
            ccdsfile = os.path.join(largedir, 'ccds', '{}-ccds.fits'.format(galaxy))
            ccds = fits_table(ccdsfile)
            #print('Hack!!!  Testing with 3 CCDs!')
            #ccds = ccds[4:5]

            # Build a QAplot showing the position of all the CCDs and the coadd
            # cutout (centered on the galaxy).
            galwcs = _galwcs(gal)
            pxscale = galwcs.pixel_scale()/3600.0
            (width, height) = (galwcs.get_width()*pxscale, galwcs.get_height()*pxscale)
            bb = galwcs.radec_bounds()
            bbcc = galwcs.radec_center()
            ww = 0.2

            qaccdposfile = os.path.join(qadir, 'qa-{}-ccdpos.png'.format(galaxy))
            fig, allax = plt.subplots(1, 3, figsize=(12, 5), sharey=True, sharex=True)

            for ax, band in zip(allax, ('g', 'r', 'z')):
                ax.set_aspect('equal')
                ax.set_xlim(bb[0]+width+ww, bb[0]-ww)
                ax.set_ylim(bb[2]-ww, bb[2]+height+ww)
                ax.set_xlabel('RA (deg)')
                ax.text(0.9, 0.05, band, ha='center', va='bottom',
                        transform=ax.transAxes, fontsize=18)

                if band == 'g':
                    ax.set_ylabel('Dec (deg)')
                ax.get_xaxis().get_major_formatter().set_useOffset(False)
                ax.add_patch(patches.Rectangle((bb[0], bb[2]), bb[1]-bb[0], bb[3]-bb[2],
                                               fill=False, edgecolor='black', lw=3, ls='--'))
                ax.add_patch(patches.Circle((bbcc[0], bbcc[1]), gal['RADIUS']/3600.0/2, 
                                            fill=False, edgecolor='black', lw=2))

                these = np.where(ccds.filter == band)[0]
                col = plt.cm.Set1(np.linspace(0, 1, len(ccds)))
                for ii, ccd in enumerate(ccds[these]):
                    print(ccd.expnum, ccd.ccdname, ccd.filter)
                    W, H, ccdwcs = _ccdwcs(ccd)

                    cc = ccdwcs.radec_bounds()
                    ax.add_patch(patches.Rectangle((cc[0], cc[2]), cc[1]-cc[0],
                                                   cc[3]-cc[2], fill=False, lw=2, 
                                                   edgecolor=col[these[ii]],
                                                   label='ccd{:02d}'.format(these[ii])))
                    ax.legend(ncol=2, frameon=False, loc='upper left')
                    
            plt.subplots_adjust(bottom=0.12, wspace=0.05, left=0.06, right=0.97)
            print('Writing {}'.format(qaccdposfile))
            plt.savefig(qaccdposfile)

            #print('Exiting prematurely!')
            #sys.exit(1)

            #tims = []
            for iccd, ccd in enumerate(ccds):
                im = survey.get_image_object(ccd)
                print(im, im.band, 'exptime', im.exptime, 'propid', ccd.propid,
                      'seeing {:.2f}'.format(ccd.fwhm*im.pixscale), 
                      'object', getattr(ccd, 'object', None))
                tim = im.get_tractor_image(splinesky=True, subsky=False,
                                           hybridPsf=True, dq=True)
                #tims.append(tim)

                # Get the (pixel) coordinates of the galaxy on this CCD
                W, H, wcs = _ccdwcs(ccd)
                ok, x0, y0 = wcs.radec2pixelxy(gal['RA'], gal['DEC'])
                xcen, ycen = x0-1.0, y0-1.0
                pxscale = wcs.pixel_scale()
                radius = DIAMFACTOR*gal['RADIUS']/pxscale/2.0

                # Get the image, read and instantiate the splinesky model, and
                # also reproduce the image mask used in legacypipe.decam.run_calibs.
                image = tim.getImage()
                weight = tim.getInvvar()
                sky = tim.getSky()
                skymodel = np.zeros_like(image)
                sky.addTo(skymodel)

                med = np.median(image[weight > 0])
                skyobj = SplineSky.BlantonMethod(image - med, weight>0, 512)
                skymod = np.zeros_like(image)
                skyobj.addTo(skymod)
                sig1 = 1.0/np.sqrt(np.median(weight[weight > 0]))
                mask = ((image - med - skymod) > (5.0*sig1))*1.0
                mask = binary_dilation(mask, iterations=3)
                mask[weight == 0] = 1 # 0=good, 1=bad
                pipeskypix = np.flatnonzero((mask == 0)*1)

                # Make a more aggressive object mask but reset the badpix and
                # edge bits.
                print('Iteratively building a more aggressive object mask.')
                #newmask = ((image - med - skymod) > (3.0*sig1))*1.0
                newmask = mask.copy()
                #newmask = (weight == 0)*1 
                for bit in ('edge', 'edge2'):
                    ww = np.flatnonzero((tim.dq & CP_DQ_BITS[bit]) == CP_DQ_BITS[bit])
                    if len(ww) > 0:
                        newmask.flat[ww] = 0
                for jj in range(2):
                    gauss = Gaussian2DKernel(stddev=1)
                    newmask = convolve(newmask, gauss)
                    newmask[newmask > 0] = 1 # 0=good, 1=bad

                #http://stackoverflow.com/questions/8647024/how-to-apply-a-disc-shaped-mask-to-a-numpy-array
                #ymask, xmask = np.ogrid[-a:n-a, -b:n-b]
                #mask = x*x + y*y <= r*r
                
                newmask += mask
                newmask[newmask > 0] = 1

                # Build a new sky model.
                newskypix = np.flatnonzero((newmask == 0)*1)
                newmed = np.median(image.flat[newskypix])
                newsky = np.zeros_like(image) + newmed
                #newsky = skymodel.copy()
                
                # Now do a lower-order polynomial sky subtraction.
                xall, yall = np.mgrid[:H, :W]
                xx = xall.flat[newskypix]
                yy = yall.flat[newskypix]
                sky = image.flat[newskypix]
                if False:
                    plt.clf() ; plt.scatter(xx[:5000], sky[:5000]) ; plt.show()
                    pdb.set_trace()
                    pinit = models.Polynomial2D(degree=1)
                    pfit = fitting.LevMarLSQFitter()
                    coeff = pfit(pinit, xx, yy, sky)
                    # evaluate the model back on xall, yall

                # Perform aperture photometry on the sky-subtracted images.
                image_nopipesky = image - skymodel
                image_nonewsky = image - newsky

                #import fitsio
                #fitsio.write('junk.fits', image_nopipesky)
                #x0 = 1000 # Hack!!!
                
                #with np.errstate(divide = 'ignore'):
                #    imsigma = 1.0/np.sqrt(weight)
                #    imsigma[weight == 0] = 0

                deltar = 5.0
                rin = np.arange(0.0, np.floor(5 * gal['RADIUS'] / pxscale), 5.0)
                nap = len(rin)

                apphot = Table(np.zeros(nap, dtype=[('RCEN', 'f4'), ('RIN', 'f4'),
                                                    ('ROUT', 'f4'), ('PIPEFLUX', 'f4'),
                                                    ('NEWFLUX', 'f4'), ('PIPESKYFLUX', 'f4'), 
                                                    ('NEWSKYFLUX', 'f4'), ('AREA', 'f4'),
                                                    ('SKYAREA', 'f4')]))
                apphot['RIN'] = rin
                apphot['ROUT'] = rin + deltar
                apphot['RCEN'] = rin + deltar/2.0
                for ii in range(nap):
                    ap = CircularAperture((xcen, ycen), apphot['RCEN'][ii])
                    skyap = CircularAnnulus((xcen, ycen), r_in=apphot['RIN'][ii],
                                            r_out=apphot['ROUT'][ii])

                    #pdb.set_trace()
                    apphot['PIPEFLUX'][ii] = aperture_photometry(image_nopipesky, ap)['aperture_sum'].data
                    apphot['NEWFLUX'][ii] = aperture_photometry(image_nonewsky, ap)['aperture_sum'].data
                    apphot['PIPESKYFLUX'][ii] = aperture_photometry(image_nopipesky, skyap)['aperture_sum'].data
                    apphot['NEWSKYFLUX'][ii] = aperture_photometry(image_nonewsky, skyap)['aperture_sum'].data
                    
                    apphot['AREA'][ii] = ap.area()
                    apphot['SKYAREA'][ii] = skyap.area()

                # Convert to arcseconds
                apphot['RIN'] *= pxscale
                apphot['ROUT'] *= pxscale
                apphot['RCEN'] *= pxscale
                apphot['AREA'] *= pxscale**2
                apphot['SKYAREA'] *= pxscale**2
                print(apphot)
                #pdb.set_trace()

                # Now generate some QAplots related to the sky.
                sbinsz = 0.001
                srange = (-5*sig1, +5*sig1)
                #sbins = 50
                sbins = np.int( (srange[1]-srange[0]) / sbinsz )

                qaccd = os.path.join(qadir, 'qa-{}-ccd{:02d}-sky.png'.format(galaxy, iccd))
                fig, ax = plt.subplots(1, 2, figsize=(8, 4))
                fig.suptitle('{} (ccd{:02d})'.format(tim.name, iccd), y=0.97)
                for data1, label, color in zip((image_nopipesky.flat[pipeskypix],
                                                image_nonewsky.flat[newskypix]),
                                               ('Pipeline Sky', 'New Sky'), setcolors):
                    nn, bins = np.histogram(data1, bins=sbins, range=srange)
                    nn = nn/float(np.max(nn))
                    cbins = (bins[:-1] + bins[1:]) / 2.0
                    #pdb.set_trace()
                    ax[0].step(cbins, nn, color=color, lw=2, label=label)
                    ax[0].set_ylim(0, 1.2)
                    #(nn, bins, _) = ax[0].hist(data1, range=srange, bins=sbins,
                    #                           label=label, normed=True, lw=2, 
                    #                           histtype='step', color=color)
                ylim = ax[0].get_ylim()
                ax[0].vlines(0.0, ylim[0], 1.05, colors='k', linestyles='dashed')
                ax[0].set_xlabel('Residuals (nmaggie)')
                ax[0].set_ylabel('Relative Fraction of Pixels')
                ax[0].legend(frameon=False, loc='upper left')

                ax[1].plot(apphot['RCEN'], apphot['PIPESKYFLUX']/apphot['SKYAREA'], 
                              label='DR2 Pipeline', color=setcolors[0])
                ax[1].plot(apphot['RCEN'], apphot['NEWSKYFLUX']/apphot['SKYAREA'], 
                              label='Large Galaxy Pipeline', color=setcolors[1])
                #ax[1].scatter(apphot['RCEN'], apphot['PIPESKYFLUX']/apphot['SKYAREA'], 
                #              label='DR2 Pipeline', marker='o', color=setcolors[0])
                #ax[1].scatter(apphot['RCEN']+1.0, apphot['NEWSKYFLUX']/apphot['SKYAREA'], 
                #              label='Large Galaxy Pipeline', marker='s', color=setcolors[1])
                ax[1].set_xlabel('Galactocentric Radius (arcsec)')
                ax[1].set_ylabel('Flux in {:g}" Annulus (nmaggie/arcsec$^2$)'.format(deltar))
                ax[1].set_xlim(-2.0, apphot['ROUT'][-1])
                ax[1].legend(frameon=False, loc='upper right')

                xlim = ax[1].get_xlim()
                ylim = ax[1].get_ylim()
                ax[1].hlines(0.0, xlim[0], xlim[1]*0.99999, colors='k', linestyles='dashed')
                ax[1].vlines(gal['RADIUS'], ylim[0], ylim[1]*0.5, colors='k', linestyles='dashed')

                plt.tight_layout(w_pad=0.25)
                plt.subplots_adjust(bottom=0.15, top=0.88)
                print('Writing {}'.format(qaccd))
                plt.savefig(qaccd)
                
                #print('Exiting prematurely!')
                #sys.exit(1)

                # Visualize the data, the mask, and the sky.
                qaccd = os.path.join(qadir, 'qa-{}-ccd{:02d}-2d.png'.format(galaxy, iccd))
                fig, ax = plt.subplots(1, 5, sharey=True, figsize=(14, 4.5))
                #fig, ax = plt.subplots(3, 2, sharey=True, figsize=(14, 6))
                fig.suptitle('{} (ccd{:02d})'.format(tim.name, iccd), y=0.97)

                vmin_image, vmax_image = np.percentile(image, (1, 99))
                vmin_weight, vmax_weight = np.percentile(weight, (1, 99))
                vmin_mask, vmax_mask = (0, 1)
                vmin_sky, vmax_sky = np.percentile(skymodel, (1, 99))
                
                for thisax, data, title in zip(ax.flat, (image, mask, newmask, skymodel, newsky), 
                                               ('Image', 'Pipeline Mask', 'New Mask',
                                                'Pipeline Sky', 'New Sky')):
                    if 'Mask' in title:
                        vmin, vmax = vmin_mask, vmax_mask
                    elif 'Sky' in title:
                        vmin, vmax = vmin_sky, vmax_sky
                    elif 'Image' in title:
                        vmin, vmax = vmin_image, vmax_image
                    elif 'Weight' in title:
                        vmin, vmax = vmin_weight, vmax_weight
                        
                    thisim = thisax.imshow(data, cmap='inferno', interpolation='nearest', origin='lower',
                                           vmin=vmin, vmax=vmax)
                    thisax.add_patch(patches.Circle((xcen, ycen), radius, fill=False, edgecolor='white', lw=2))
                    div = make_axes_locatable(thisax)
                    cax = div.append_axes('right', size='15%', pad=0.1)
                    cbar = fig.colorbar(thisim, cax=cax, format='%.4g')

                    thisax.set_title(title)
                    thisax.xaxis.set_visible(False)
                    thisax.yaxis.set_visible(False)
                    thisax.set_aspect('equal')

                ## Shared colorbar.
                plt.tight_layout(w_pad=0.25, h_pad=0.25)
                plt.subplots_adjust(bottom=0.0, top=0.93)
                print('Writing {}'.format(qaccd))
                plt.savefig(qaccd)

                #print('Exiting prematurely!')
                #sys.exit(1)
                #pdb.set_trace()

    # --------------------------------------------------
    # Run the pipeline.
    if args.runbrick:
        for gal in sample:
            galaxy = gal['GALAXY'].strip().lower()

            ccdsdir = os.path.join(largedir, 'ccds')
            ccdsfile = os.path.join(ccdsdir, '{}-ccds.fits'.format(galaxy))
            ccds = fits_table(ccdsfile)
            _getfiles(ccds)

            # DIAM here should be consistent with SIZE in args.viewer_cutouts,
            # above.  Also note that ZOOM is relative to the center of an
            # imaginary brick with dimensions (0, 3600, 0, 3600).
            diam = DIAMFACTOR * np.ceil(gal['RADIUS']/PIXSCALE).astype('int16') # [pixels]
            zoom = (1800-diam/2, 1800+diam/2, 1800-diam/2, 1800+diam/2)

            #nsigma = 15
            nsigma = 6
            #stages = ['fitblobs']
            stages = ['writecat']
            plots = False
            #blobxy = zip([diam/2], [diam/2])
            blobxy = None
            survey = LegacySurveyData(output_dir=largedir)
            run_brick(None, survey, radec=(gal['RA'], gal['DEC']), blobxy=blobxy, 
                      threads=args.nproc, zoom=zoom, wise=False, forceAll=True, writePickles=False,
                      do_calibs=False, write_metrics=True, pixPsf=True, splinesky=True, 
                      early_coadds=False, stages=stages, ceres=False, nsigma=nsigma,
                      plots=plots)

            #pdb.set_trace()

    # --------------------------------------------------
    # Annotate the image/model/resid jpg cutouts after running the custom pipeline.
    if args.runbrick_cutouts:
        for gal in sample:
            galaxy = gal['GALAXY'].strip().lower()
            cutdir = os.path.join(cutoutdir, '{}'.format(galaxy))
            qadir = os.path.join(largedir, 'qa', '{}'.format(galaxy))
            for dd in [cutdir, qadir]:
                try:
                    os.stat(dd)
                except:
                    os.mkdir(dd)

            ra = gal['RA']
            dec = gal['DEC']
            brick = 'custom-{:06d}{}{:05d}'.format(int(1000*ra), 'm' if dec < 0 else 'p',
                                                   int(1000*np.abs(dec)))
            tractorfile = os.path.join(largedir, 'tractor', 'cus', 'tractor-{}.fits'.format(brick))
            blobsfile = os.path.join(largedir, 'metrics', 'cus', '{}'.format(brick), 'blobs-{}.fits.gz'.format(brick))

            print('Reading {}'.format(tractorfile))
            cat = fits.getdata(tractorfile, 1)

            print('Reading {}'.format(blobsfile))
            blobs = fits.getdata(blobsfile)

            qablobsfile = os.path.join(qadir, 'qa-{}-blobs.png'.format(galaxy))
            fig, ax = plt.subplots(1, figsize=(6, 6))
            dimshow(blobs != -1)
            for blob in np.unique(cat['BLOB']):
                these = np.where(cat['BLOB'] == blob)[0]
                xx, yy = (np.mean(cat['BX'][these]), np.mean(cat['BY'][these]))
                ax.text(xx, yy, '{}'.format(blob), ha='center', va='bottom', color='orange')
                ax.xaxis.set_visible(False)
                ax.yaxis.set_visible(False)
            plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
            
            print('Writing {}'.format(qablobsfile))
            plt.savefig(qablobsfile)

            #print('Exiting prematurely!')
            #sys.exit(1)

            rad = 10
            for imtype in ('image', 'model', 'resid'):
                cutoutfile = os.path.join(cutdir, '{}-{}-custom-annot.jpg'.format(galaxy, imtype))
                imfile = os.path.join(largedir, 'coadd', 'cus', brick, 'legacysurvey-{}-{}.jpg'.format(brick, imtype))
                print('Reading {}'.format(imfile))

                im = Image.open(imfile)
                sz = im.size
                fntsize = np.round(sz[0]/35).astype('int')
                font = ImageFont.truetype(fonttype, size=fntsize)
                draw = ImageDraw.Draw(im)
                for ii, (thistype, thiscolor) in enumerate(zip(objtype, objcolor)):
                    these = np.where(cat['TYPE'].strip().upper() == thistype)[0]
                    if len(these) > 0:
                        [draw.ellipse((obj['BX']-rad, sz[1]-obj['BY']-rad, obj['BX']+rad,
                                       sz[1]-obj['BY']+rad), outline=thiscolor) for obj in cat[these]]
                    # Add a legend.
                    draw.text((20, 20+ii*fntsize*1.2), thistype, font=font, fill=thiscolor)
                draw.text((sz[0]-fntsize*4, sz[1]-fntsize*2), imtype.upper(), font=font)
                #draw.text((sz[0], sz[1]-20), imtype.upper(), font=font)
                im.save(cutoutfile)
                
    # --------------------------------------------------
    # Build the webpage.
    if args.build_webpage:
        #sample = fits.getdata(samplefile, 1)
        
        # index.html
        htmlfile = os.path.join(largedir, 'index.html')
        print('Writing {}'.format(htmlfile))
        html = open(htmlfile, 'w')
        html.write('<html><body>\n')
        html.write('<h1>Sample of Large Galaxies</h1>\n')
        html.write('<table border="2" width="30%"><tbody>\n')
        for ii, gal in enumerate(sample):
            # Add coordinates and sizes here.
            galaxy = gal['GALAXY'].strip().lower()
            html.write('<tr>\n')
            html.write('<td>{}</td>\n'.format(ii))
            html.write('<td><a href="html/{}.html">{}</a></td>\n'.format(galaxy, galaxy, galaxy.upper()))
            html.write('<td><a href="http://legacysurvey.org/viewer/?ra={:.6f}&dec={:.6f}" target="_blank"><img src=cutouts/{}/{}-image-thumb.jpg alt={} /></a></td>\n'.format(gal['RA'], gal['DEC'], galaxy, galaxy, galaxy.upper()))
            html.write('</tr>\n')
        html.write('</tbody></table>\n')
        html.write('</body></html>\n')
        html.close()

        # individual galaxy pages
        for gal in sample:
            galaxy = gal['GALAXY'].strip().lower()
            qadir = os.path.join(largedir, 'qa', '{}'.format(galaxy))

            htmlfile = os.path.join(largedir, 'html/{}.html'.format(galaxy, galaxy))
            print('Writing {}'.format(htmlfile))
            html = open(htmlfile, 'w')
            html.write('<html>\n')
            html.write('<head>\n')
            html.write('<style type="text/css">\n')
            html.write('table {width: 90%; }\n')
            html.write('table, th, td {border: 1px solid black; }\n')
            html.write('img {width: 100%; }\n')
            #html.write('td {width: 100px; }\n')
            #html.write('h2 {color: orange; }\n')
            html.write('</style>\n')
            html.write('</head>\n')
            html.write('<body>\n')
            html.write('<h1>{}</h1>\n'.format(galaxy.upper()))
            # ----------
            # DR2 Pipeline cutouts
            html.write('<h2>DR2 Pipeline (Image, Model, Residuals)</h2>\n')
            html.write('<table><tbody>\n')
            html.write('<tr>\n')
            for imtype in ('image', 'model', 'resid'):
                html.write('<td><a href=../cutouts/{}/{}-{}-runbrick-annot.jpg>'.format(galaxy, galaxy, imtype)+\
                           '<img src=../cutouts/{}/{}-{}-runbrick-annot.jpg alt={} /></a></td>\n'.format(galaxy, galaxy, imtype, galaxy.upper()))
            html.write('</tr>\n')
            #html.write('<tr><td>Data</td><td>Model</td><td>Residuals</td></tr>\n')
            html.write('</tbody></table>\n')
            # ----------
            # Large-Galaxy custom pipeline cutouts
            html.write('<h2>Large-Galaxy Pipeline (Image, Model, Residuals)</h2>\n')
            html.write('<table><tbody>\n')
            html.write('<tr>\n')
            for imtype in ('image', 'model', 'resid'):
                html.write('<td><a href=../cutouts/{}/{}-{}-custom-annot.jpg><img width="100%" src=../cutouts/{}/{}-{}-custom-annot.jpg alt={} /></a></td>\n'.format(
                    galaxy, galaxy, imtype, galaxy, galaxy, imtype, galaxy.upper()))
            html.write('</tr>\n')
            html.write('</tbody></table>\n')
            # ----------
            # Blob diagnostic plot
            html.write('<h2>Segmentation (nsigma>20)</h2>\n')
            html.write('<table><tbody>\n')
            html.write('<tr><td><a href=../qa/{}/qa-{}-blobs.png>'.format(galaxy, galaxy)+\
                       '<img src=../qa/{}/qa-{}-blobs.png alt={} Blobs /></a></td>'.format(galaxy, galaxy, galaxy.upper())+\
                       '</tr>\n')
                       #'<td>&nbsp</td><td>&nbsp</td></tr>\n')
            html.write('</tbody></table>\n')
            # ----------
            # CCD cutouts
            html.write('<h2>Configuration of CCDs and Sky-Subtraction</h2>\n')
            html.write('<table><tbody>\n')
            html.write('<tr><td><a href=../qa/{}/qa-{}-ccdpos.png>'.format(galaxy, galaxy)+\
                       '<img src=../qa/{}/qa-{}-ccdpos.png alt={} CCD Positions /></a></td>'.format(galaxy, galaxy, galaxy.upper())+\
                       '</tr>\n')
            html.write('</tbody></table>\n')
            qaccd = glob(os.path.join(qadir, 'qa-{}-ccd??-*.png'.format(galaxy)))
            if len(qaccd) > 0:
                html.write('<table><tbody>\n')
                for ccd in qaccd:
                    qaccd1 = os.path.split(ccd)[-1]
                    html.write('<tr><td><a href=../qa/{}/{}>'.format(galaxy, qaccd1)+\
                               '<img src=../qa/{}/{} alt={} Sky in CCD /></a></td>'.format(galaxy, qaccd1, galaxy.upper())+\
                               '</tr>\n')
                html.write('</tbody></table>\n')
            html.write('</body></html>\n')
            html.close()
            
if __name__ == "__main__":
    main()
