#!/usr/bin/env python

"""Build and write out the NGC-star-clusters.fits catalog.

"""
import os
import numpy as np
import numpy.ma as ma
from astropy.io import ascii
from astropy.table import Table, vstack
from astrometry.util.starutil_numpy import hmsstring2ra, dmsstring2dec
from astrometry.libkd.spherematch import match_radec
from pkg_resources import resource_filename

#import desimodel.io
#import desimodel.footprint

#tiles = desimodel.io.load_tiles(onlydesi=True)

if not os.path.isfile('/tmp/NGC.csv'):
    os.system('wget -P /tmp https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/NGC.csv')
    
names = ('name', 'type', 'ra_hms', 'dec_dms', 'const', 'majax', 'minax',
         'pa', 'bmag', 'vmag', 'jmag', 'hmag', 'kmag', 'sbrightn', 'hubble',
         'cstarumag', 'cstarbmag', 'cstarvmag', 'messier', 'ngc', 'ic',
         'cstarnames', 'identifiers', 'commonnames', 'nednotes', 'ongcnotes')
NGC = ascii.read('/tmp/NGC.csv', delimiter=';', names=names)
NGC = NGC[(NGC['ra_hms'] != 'N/A')]

ra, dec = [], []
for _ra, _dec in zip(ma.getdata(NGC['ra_hms']), ma.getdata(NGC['dec_dms'])):
    ra.append(hmsstring2ra(_ra.replace('h', ':').replace('m', ':').replace('s','')))
    dec.append(dmsstring2dec(_dec.replace('d', ':').replace('m', ':').replace('s','')))
NGC['ra'] = ra
NGC['dec'] = dec

objtype = np.char.strip(ma.getdata(NGC['type']))

# Keep all globular clusters and planetary nebulae
keeptype = ('PN', 'GCl')
keep = np.zeros(len(NGC), dtype=bool)
for otype in keeptype:
    ww = [otype == tt for tt in objtype]
    keep = np.logical_or(keep, ww)
print(np.sum(keep))

clusters = NGC[keep]

# Fill missing major axes with a nominal 0.4 arcmin (roughly works
# for NGC7009, which is the only missing PN in the footprint).
ma.set_fill_value(clusters['majax'], 0.4)
clusters['majax'] = ma.filled(clusters['majax'].data)

# Increase the radius of IC4593
# https://github.com/legacysurvey/legacypipe/issues/347
clusters[clusters['name'] == 'IC4593']['majax'] = 0.5

#indesi = desimodel.footprint.is_point_in_desi(tiles, ma.getdata(clusters['ra']),
#                                              ma.getdata(clusters['dec']))
#print(np.sum(indesi))
#bb = clusters[indesi]
#bb[np.argsort(bb['majax'])[::-1]]['name', 'ra', 'dec', 'majax', 'type']

# Build the output catalog: select a subset of the columns and rename
# majax-->radius (arcmin-->degree)
out = Table()
out['name'] = clusters['name']
out['alt_name'] = ['' if mm == 0 else 'M{}'.format(str(mm))
                   for mm in ma.getdata(clusters['messier'])]
out['type'] = clusters['type']
out['ra'] = clusters['ra']
out['dec'] = clusters['dec']
out['radius'] = (clusters['majax'] / 60).astype('f4') # [degrees]
#out['radius'] = out['radius_orig']

# Read the updated radii based on visual inspection by Arjun Dey (Feb 2020):
radiifile = resource_filename('legacypipe', 'data/NGC-star-clusters-radii.csv')
newname, newradii = np.loadtxt(radiifile, dtype=str, delimiter=',', unpack=True)
out['radius'][np.isin(out['name'], newname)] = newradii.astype('f4')

#oldradii = out['radius'].copy()
#import matplotlib.pyplot as plt
#plt.scatter(oldradii*60, oldradii/out['radius'], s=15)
#plt.xlabel('Old radii [arcmin]')
#plt.ylabel('Old radii / New radii')
#plt.show()

# Read the ancillary globular cluster catalog and update the radii in the NGC.
#https://heasarc.gsfc.nasa.gov/db-perl/W3Browse/w3table.pl?tablehead=name%3Dglobclust&Action=More+Options
if False:
    gcfile = resource_filename('legacypipe', 'data/globular_clusters.fits')
    gcs = Table.read(gcfile)
    I, J, _ = match_radec(clusters['ra'], clusters['dec'], gcs['RA'], gcs['DEC'], 10./3600., nearest=True)
    out['radius'][I] = (gcs['HALF_LIGHT_RADIUS'][J] / 60).astype('f4') # [degrees]

# Read the supplemental catalog of globular clusters and (compact) open clusters
# from Arjun Dey (Mar 2020). Note that the NGC open clusters were culled above,
# but we put them back here because the diameters have been vetted. 
names = ('name', 'alt_name', 'ra', 'dec', 'type', 'radius')
suppfile = resource_filename('legacypipe', 'data/star-clusters-supplemental.csv')
supp = ascii.read(suppfile, delimiter=',', names=names, fill_values='')
#supp['alt_name'] = supp['alt_name'].astype('U4')
supp['radius'] = supp['radius'].astype('f4')
out = vstack((out, supp))

# add a position angle and ellipticity (b/a)
out['pa'] = np.zeros(len(out), dtype='f4')
out['ba'] = np.ones(len(out), dtype='f4')

# add Fornax and Scluptor -- LG dwarfs by hand
#  GALAXY         RA                DEC           D25     PA     BA
# bytes24      float64            float64       float32 int16 float32
# ------- ----------------- ------------------- ------- ----- -------
#   Fornax 39.99708333333332 -34.449166666666656    66.4    41     0.7
# Sculptor 15.039166666666665 -33.70916666666666    45.2    99    0.68

dwarfs = Table()
dwarfs['name'] = ['Sculptor', 'Fornax']
dwarfs['alt_name'] = ['', '']
dwarfs['type'] = ['Dwrf', 'Dwrf']
dwarfs['ra'] = np.array([15.039166666666665, 39.99708333333332]).astype('f8')
dwarfs['dec'] = np.array([-33.70916666666666, -34.449166666666656]).astype('f8')
dwarfs['radius'] = np.array([45.2/2/60, 66.4/2/60]).astype('f4')
dwarfs['pa'] = np.array([99, 41]).astype('f4')
dwarfs['ba'] = np.array([0.68, 0.7]).astype('f4')
out = vstack((out, dwarfs))

if False: # debugging
    bb = out[['M' in nn for nn in out['alt_name']]]
    bb[np.argsort(bb['radius'])]
    bb['radius'] *= 60
    bb['radius_orig'] *= 60
    print(bb)

out = out[np.argsort(out['ra'])]
print(out)
clusterfile = resource_filename('legacypipe', 'data/NGC-star-clusters.fits')

print('Writing {}'.format(clusterfile))
out.write(clusterfile, overwrite=True)

# Code to help visually check all the globular clusters.
if False:
    checktype = ('GCl', 'PN')
    check = np.zeros(len(NGC), dtype=bool)
    for otype in checktype:
        ww = [otype == tt for tt in objtype]
        check = np.logical_or(check, ww)
    check_clusters = NGC[check] # 845 of them

    # Write out a catalog, load it into the viewer and look at each of them.
    check_clusters[['ra', 'dec', 'name']].write('/tmp/check.fits', overwrite=True) # 25 of them
