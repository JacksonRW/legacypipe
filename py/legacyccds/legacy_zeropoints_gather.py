#!/usr/bin/env python

"""
mpi gather all ccd fits files together and write single ccd table
"""
from __future__ import division, print_function

import os
import argparse
import numpy as np
import pickle
from astrometry.util.fits import fits_table, merge_tables

def read_lines(fn):
    fin=open(fn,'r')
    lines=fin.readlines()
    fin.close()
    if len(lines) < 1: raise ValueError('lines not read properly from %s' % fn)
    return np.array( list(np.char.strip(lines)) )

def hdu_minus_1(cat):
    cat.set('image_hdu',cat.image_hdu - 1)

def cut_nans(cat):
    flag={}
    for col in cat.get_columns():
        try:
            flag[col]= np.isfinite(cat.get(col)) == False
            print('col=%s has %d NaNs' % (col,np.where(flag[col])[0].size))
        except TypeError:
            pass
    # cut all nans
    keep= (np.ones(len(cat),bool) )
    for key in flag.keys():
        keep *= (flag[key] == False)
    print('Removing %d NaNs' % (np.where(keep == False)[0].size,))
    cat2= cat.copy()
    cat2.cut(keep)
    print('len cat=%d, cat2=%d' % (len(cat),len(cat2)))
    return cat,cat2,flag

def write_cat(cat, outname):
    # needs be fixed better
    #hdu_minus_1(cat)
    #
    cat,cat2,flag= cut_nans(cat)
    # save
    outname= outname.replace('.fits','')
    fn= outname+'_hasnans.fits'
    fn2= outname+'.fits'
    fn_flag= outname+'_flag.pickle'
    for f in [fn,fn2,fn_flag]:
        if os.path.exists(f):
            os.remove(f)
    cat.writeto(fn)
    cat2.writeto(fn2)
    with open(fn_flag,'w') as foo:
        pickle.dump(flag, foo)
    print('Wrote Files')
    for f in [fn,fn2]:
        os.system('gzip --best ' + f)
    print('gzipped files')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate a legacypipe-compatible CCDs file from a set of reduced imaging.')
    parser.add_argument('--file_list',action='store',help='List of zeropoint fits files to concatenate',required=True)
    parser.add_argument('--nproc',type=int,action='store',default=1,help='number mpi tasks',required=True)
    parser.add_argument('--outname', type=str, default='combined_legacy_zpt.fits', help='Output directory.')
    opt = parser.parse_args()
    
    fns= read_lines(opt.file_list) 

    # RUN HERE
    if opt.nproc > 1:
        from mpi4py.MPI import COMM_WORLD as comm
        fn_split= np.array_split(fns, comm.size)
        cats=[]
        for fn in fn_split[comm.rank]:
            try:
                cats.append( fits_table(fn) )
            except IOError:
                print('File is bad, skipping: %s' % fn)
        cats= merge_tables(cats, columns='fillzero')
        # Gather
        all_cats = comm.gather( cats, root=0 )
        if comm.rank == 0:
            all_cats= merge_tables(all_cats, columns='fillzero')
            write_cat(all_cats,outname=opt.outname)
            print("Done")
    else:
        cats=[]
        for cnt,fn in enumerate(fns):
            print('Reading %d/%d' % (cnt,len(fns)))
            cats.append( fits_table(fn) )
        cats= merge_tables(cats, columns='fillzero')
        write_cat(cats, outname=opt.outname)
        print("Done")
