#! /usr/bin/env python

import os
import numpy as np
from astrometry.util.fits import fits_table

from common import run_calibs, DecamImage, Decals

if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--force', action='store_true', default=False,
                      help='Run calib processes even if files already exist?')
    parser.add_option('--ccds', help='Set ccds.fits file to load')

    parser.add_option('--expnum', type=int, help='Cut to a single exposure')
    parser.add_option('--extname', '--ccdname', help='Cut to a single extension/CCD name')

    opt,args = parser.parse_args()

    D = Decals()
    if opt.ccds is not None:
        T = fits_table(opt.ccds)
        print 'Read', len(T), 'from', opt.ccds
    else:
        T = D.get_ccds()
        print len(T), 'CCDs'
    print len(T), 'CCDs'

    if len(args) == 0:
        if opt.expnum is not None:
            T.cut(T.expnum == opt.expnum)
            print 'Cut to', len(T), 'with expnum =', opt.expnum
        if opt.extname is not None:
            T.cut(np.array([(t.strip() == opt.extname) for t in T.ccdname]))
            print 'Cut to', len(T), 'with extname =', opt.extname

        args = range(len(T))
            
    for a in args:
        i = int(a)
        t = T[i]

        im = DecamImage(D, t)
        print 'Running', im.calname

        if opt.force:
            kwargs.update(force=True)

        run_calibs((im, kwargs))
