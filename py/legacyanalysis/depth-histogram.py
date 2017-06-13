from __future__ import print_function
from glob import glob
import os
import matplotlib
matplotlib.use('Agg')
import pylab as plt
import numpy as np
from astrometry.util.fits import fits_table, merge_tables
from astrometry.util.plotutils import PlotSequence

def brickname_from_filename(fn):
    fn = os.path.basename(fn)
    words = fn.split('-')
    assert(len(words) == 3)
    return words[1]

def summarize_depths(basedir, outfn, summaryfn):
    fns = glob(os.path.join(basedir, 'coadd', '*', '*', '*-depth.fits'))
    fns.sort()
    print(len(fns), 'depth files')
    
    fn = fns.pop(0)
    print('Reading', fn)
    # We'll keep all files for merging...
    TT = []

    T = fits_table(fn)
    # Create / upgrade the count columns to int64.
    for band in 'grz':
        for pro in ['ptsrc', 'gal']:
            col = 'counts_%s_%s' % (pro, band)
            if not col in T.columns():
                v = np.zeros(len(T), np.int64)
            else:
                v = T.get(col).astype(np.int64)
            T.set(col, v)
    T.brickname = np.array([brickname_from_filename(fn)] * len(T))
    TT.append(T.copy())
    
    for ifn,fn in enumerate(fns):
        print('Reading', ifn, 'of', len(fns), ':', fn)
        t = fits_table(fn)
        if not (np.all(t.depthlo == T.depthlo) and
                np.all(t.depthhi == T.depthhi)):
            print('T depthlo', T.depthlo)
            print('T depthhi', T.depthhi)
            print('t depthlo', t.depthlo)
            print('t depthhi', t.depthhi)

            assert(len(t.depthlo) == 50)
            assert(len(T.depthlo) == 50)

            # if len(t.depthlo) == 52 and len(T.depthlo) == 50:
            #     # [0,] 20, 20.1, ..., 24.9, [25,] 100
            #     for band in 'grz':
            #         for pro in ['ptsrc', 'gal']:
            #             col = 'counts_%s_%s' % (pro, band)
            #             if col in t.columns():
            #                 # merge counts for bin 0-20 into bin 20-20.1
            #                 counts = t.get(col)
            #                 counts[1] += counts[0]
            #                 counts[0] = 0
            #                 # merge counts for bin 25-100 into bin 24.9-100
            #                 counts[-2] += counts[-1]
            #                 counts[-1] = 0
            #     # change lower limit of bin 1 from 20 to 0
            #     t.depthlo[1] = t.depthlo[0]
            #     # change upper limit of bin -2 from 25 to 100
            #     t.depthhi[-2] = t.depthhi[-1]
            #     t = t[1:-1]
            #     
            #     print('Cut to:')
            #     print('T depthlo', T.depthlo)
            #     print('T depthhi', T.depthhi)
            #     print('t depthlo', t.depthlo)
            #     print('t depthhi', t.depthhi)


        assert(np.all(t.depthlo == T.depthlo))
        assert(np.all(t.depthhi == T.depthhi))
        cols = t.get_columns()
        t.brickname = np.array([brickname_from_filename(fn)] * len(t))
        for band in 'grz':
            col = 'counts_ptsrc_%s' % band
            if not col in cols:
                continue
            C = T.get(col)
            C += t.get(col)
            col = 'counts_gal_%s' % band
            C = T.get(col)
            C += t.get(col)
        TT.append(t)
            
    T.delete_column('brickname')
    T.writeto(summaryfn)
    print('Wrote', summaryfn)
    
    T = merge_tables(TT, columns='fillzero')
    T.writeto(outfn)
    print('Wrote', outfn)



def summary_plots(summaryfn, ps):
    T = fits_table(summaryfn)
    dlo = T.depthlo.copy()
    dd = dlo[2] - dlo[1]
    dlo[0] = dlo[1] - dd

    for band in 'grz':

        I = np.flatnonzero((dlo >= 21.5) * (dlo < 24.8))
        #I = np.flatnonzero((dlo >= 21.5))

        pixarea = (0.262 / 3600.)**2
        
        plt.clf()
        plt.bar(dlo[I], T.get('counts_ptsrc_%s' % band)[I] * pixarea, width=dd)
        plt.xlabel('Depth: %s band' % band)
        #plt.ylabel('Number of pixels')
        plt.ylabel('Area (sq.deg)')
        plt.title('DECaLS DR3 Depth: Point Sources, %s' % band)
        plt.xlim(21.5, 24.8)
        #plt.xlim(21.5, 25.)
        ps.savefig()

        plt.clf()
        plt.bar(dlo[I], T.get('counts_gal_%s' % band)[I] * pixarea, width=dd)
        plt.xlabel('Depth: %s band' % band)
        #plt.ylabel('Number of pixels')
        plt.ylabel('Area (sq.deg)')
        plt.title('DECaLS DR3 Depth: Canonical Galaxy, %s' % band)
        plt.xlim(21.5, 24.8)
        #plt.xlim(21.5, 25.)
        ps.savefig()

    for band in 'grz':
        c = list(reversed(np.cumsum(list(reversed(T.get('counts_gal_%s' % band))))))
        #N = np.sum(T.get('counts_gal_%s' % band))
        # Skip bin with no observations?
        N = np.sum(T.get('counts_gal_%s' % band)[1:])

        plt.clf()
        plt.bar(dlo, c, width=dd)

        target = dict(g=24.0, r=23.4, z=22.5)[band]
        plt.axvline(target)
        plt.axvline(target - 0.3)
        plt.axvline(target - 0.6)
        plt.axhline(N * 0.90)
        plt.axhline(N * 0.95)
        plt.axhline(N * 0.98)
        
        plt.xlabel('Depth: %s band' % band)
        plt.ylabel('Number of pixels')
        plt.title('Depth: SIMP Galaxy, %s' % band)

        ps.savefig()

if __name__ == '__main__':
    # outfn = 'dr3-depth.fits'
    # summaryfn = 'dr3-depth-summary.fits'
    # basedir = '/project/projectdirs/cosmo/data/legacysurvey/dr3'
    # summarize_depths(basedir, outfn, summaryfn)

    outfn = 'dr4-depth.fits'
    summaryfn = 'dr4-depth-summary.fits'
    basedir = '/global/cscratch1/sd/dstn/galdepths-dr4'
    summarize_depths(basedir, outfn, summaryfn)

    ps = PlotSequence('depth')
    summary_plots(summaryfn, ps)
    sys.exit(0)
