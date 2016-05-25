#!/usr/bin/env python

"""compare two tractor catalogues that should have same objects
"""

from __future__ import division, print_function

import matplotlib
matplotlib.use('Agg') #display backend
import os
import sys
import logging
import argparse
import numpy as np
#import seaborn as sns

import matplotlib.pyplot as plt

from astropy.io import fits
from astrometry.libkd.spherematch import match_radec

#from thesis_code.fits import tractor_cat
import thesis_code.targets as targets

class Matched_Cats():
    def __init__(self):
        self.data={}
    def initialize(self,data_1,data_2,m1,m2,m1_unm,m2_unm,d12):
        self.d12= d12 #deg separations between matches objects
        self.data['m_decam']= targets.data_extract(data_1,m1) 
        self.data['m_bokmos']= targets.data_extract(data_2,m2)
        self.data['u_decam']= targets.data_extract(data_1,m1_unm)
        self.data['u_bokmos']= targets.data_extract(data_2,m2_unm)
    def add_d12(self,d12):
        '''concatenate new d12 with existing matched deg separation array'''
        self.d12= np.concatenate([self.d12, d12])
    def add_dict(self,match_type,new_data):
        '''match_type -- m_decam,m_bokmos,u_decam, etc
        new data -- data returend from read_from..() to be concatenated with existing m_decam, etc'''
        for key in self.data[match_type].keys(): 
            self.data[match_type][key]= np.concatenate([self.data[match_type][key],new_data[key]])

def match_it(cat1,cat2):
    '''cat1,2 are tractor catalogue to match objects between'''
    #match cats
    data_1= targets.read_from_tractor_cat(cat1)
    data_2= targets.read_from_tractor_cat(cat2)
    #all the 'all1' objects that have match in 'all2' 
    m1, m2, d12 = match_radec(data_1['ra'],data_1['dec'],data_2['ra'],data_2['dec'],\
                            1.0/3600.0,nearest=True)
    m1_unm = np.delete(np.arange(len(data_1['ra'])),m1,axis=0)
    m2_unm = np.delete(np.arange(len(data_2['ra'])),m2,axis=0)
    return data_1,data_2,m1,m2,m1_unm,m2_unm,d12

def read_lines(fn):
    fin=open(fn,'r')
    lines=fin.readlines()
    fin.close()
    return list(np.char.strip(lines))

#plotting vars
laba=dict(fontweight='bold',fontsize='x-large')
kwargs_axtext=dict(fontweight='bold',fontsize='x-large',va='top',ha='left')
leg_args=dict(frameon=True,fontsize='small')

def plot_radec(obj,m_types=['u_decam','u_bokmos']): 
    '''obj[m_types] -- DECaLS() objects with matched OR unmatched indices'''
    assert (m_types[0].startswith('u_') and m_types[1].startswith('u_'))
    #set seaborn panel styles
    #sns.set_style('ticks',{"axes.facecolor": ".97"})
    #sns.set_palette('colorblind')
    #setup plot
    fig,ax=plt.subplots() #1,figsize=(9,3)) #,sharey=True)
    #plt.subplots_adjust(wspace=0.5)
    #plot
    colors=['b','g']
    for ith,m_type,color in zip(range(2),m_types,colors):
        ax.scatter(obj[m_type].data['ra'], obj[m_type].data['dec'], \
                        edgecolor=color,c='none',lw=2.,label=m_type.split('_')[-1])
    xlab=ax.set_xlabel('RA', **laba)
    ylab=ax.set_ylabel('DEC', **laba)
    ti=ax.set_title('Unmatched', **laba)
    leg=ax.legend(loc=(1.01,0),**leg_args)
    #save
    #sns.despine()
    plt.savefig('radec_Unmatched.png', bbox_extra_artists=[xlab,ylab,ti,leg], bbox_inches='tight',dpi=150)
    plt.close()


def plot_HistTypes(obj,m_types=['m_decam','m_bokmos']):
    '''decam,bokmos -- DECaLS() objects with matched OR unmatched indices'''
    #matched or unmatched objects
    if m_types[0].startswith('m_') and m_types[1].startswith('m_'): matched=True
    elif m_types[0].startswith('u_') and m_types[1].startswith('u_'): matched=False   
    else: raise ValueError
    #sns.set_style("whitegrid")
    #sns.set_palette('colorblind')
    #c1=sns.color_palette()[2] 
    #c2=sns.color_palette()[0] #'b'
    c1= 'b' 
    c2= 'r'
    ###
    types= ['PSF','SIMP','EXP','DEV','COMP']
    ind = np.arange(len(types))  # the x locations for the groups
    width = 0.35       # the width of the bars
    ###
    ht_decam, ht_bokmos= np.zeros(5,dtype=int),np.zeros(5,dtype=int)
    for cnt,typ in enumerate(types):
        ht_decam[cnt]= np.where(obj[m_types[0]].data['type'] == typ)[0].shape[0]
        ht_bokmos[cnt]= np.where(obj[m_types[1]].data['type'] == typ)[0].shape[0]
    ###
    fig, ax = plt.subplots()
    rects1 = ax.bar(ind, ht_decam, width, color=c1)
    rects2 = ax.bar(ind + width, ht_bokmos, width, color=c2)
    ylab= ax.set_ylabel("N")
    if matched: ti= ax.set_title('Matched')
    else: ti= ax.set_title('Unmatched')
    ax.set_xticks(ind + width)
    ax.set_xticklabels(types)
    ax.legend((rects1[0], rects2[0]), ('decam', 'bokmos'),**leg_args)
    #save
    if matched: name='hist_types_Matched.png'
    else: name='hist_types_Unmatched.png'
    plt.savefig(name, bbox_extra_artists=[ylab,ti], bbox_inches='tight',dpi=150)
    plt.close()

def plot_matched_color_color(decam,bokmos, zoom=False):
    '''decam,bokmos are DECaLS() objects matched to decam ra,dec'''
    #set seaborn panel styles
    #sns.set_style('ticks',{"axes.facecolor": ".97"})
    #sns.set_palette('colorblind')
    #setup plot
    fig,ax=plt.subplots(1,3,figsize=(9,3)) #,sharey=True)
    plt.subplots_adjust(wspace=0.5)
    #plot
    for cnt,val in zip(range(3),['rmag','gmag','zmag']):
        diff= bokmos[val]- decam[val]
        ax[cnt].scatter(decam[val], diff)
        xlab=ax[cnt].set_xlabel('%s (decam)' % val[0], **laba)
        ylab=ax[cnt].set_ylabel('%s (bokmos - decam)' % val[0], **laba)
        if zoom: 
            ax[cnt].set_ylim(-0.1,0.1)
            ax[cnt].set_xlim(20,25)
    # sup=plt.suptitle('decam with matching bokmos',**laba)
    #save
    #sns.despine()
    if zoom: name="color_diff_zoom.png"
    else: name="color_diff.png"
    plt.savefig(name, bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
    plt.close()

def bin_up(data_bin_by,data_percentile,bL=20., bH=26.,bW=0.25):
    '''finds indices for 0.25 bins, returns bin centers and q25,50,75 percentiles of data_percentile in each bin
    bL,bH -- min and max values of data_bin to consider
    bW -- bin width'''
    low_vals= np.arange(bL,bH,bW)
    q25= np.zeros(low_vals.size)+np.nan
    q50,q75= q25.copy(),q25.copy()
    for i,low in enumerate(low_vals):
        ind= np.all((low <= data_bin_by,data_bin_by < low+bW),axis=0)
        if np.where(ind)[0].size > 0:
            q25[i]= np.percentile(data_percentile[ind],q=25)
            q50[i]= np.percentile(data_percentile[ind],q=50)
            q75[i]= np.percentile(data_percentile[ind],q=75)
        else: 
            pass #given qs nan, which they already have
    return low_vals+bW/2,q25,q50,q75


def plot_SN(obj, found_by='matched',type='all'):
    '''obj['m_decam'] is DECaLS() object
    found_by -- 'matched' or 'unmatched' 
    type -- all,psf,lrg'''
    #indices for type == all,psf, or lrg
    assert(found_by == 'matched' or found_by == 'unmatched')
    prefix= found_by[0]+'_' # m_ or u_
    index={}
    for key in ['decam','bokmos']:
        if type == 'all': 
            index[key]= np.arange(obj[prefix+key].data['gflux'].size)
        elif index == 'psf': 
            index[key]= obj[prefix+key].data['type'] == 'PSF'
        elif index == 'lrg': 
            index[key]= obj[prefix+key].data['i_lrg']
        else: raise ValueError
    #bin up SN values
    bin_SN=dict(decam={},bokmos={})
    for key in binned.keys():
        for band in ['g','r','z']:
            bin_SN[key][band]={}
            i= index[key]
            bin_SN[key][band]['binc'],bin_SN[key][band]['q25'],bin_SN[key][band]['q50'],bin_SN[key][band]['q75']=\
                    bin_up(obj['m_'+key].data[band+'mag'][i], obj['m_'+key].data[band+'flux'][i]*np.sqrt(obj['m_'+key].data[band+'flux_ivar'][i]))
    #setup plot
    fig,ax=plt.subplots(1,3,figsize=(9,3),sharey=True)
    plt.subplots_adjust(wspace=0)
    #plot SN
    for cnt,band in zip(range(3),['g','r','z']):
        #horiz line at SN = 5
        ax[cnt].plot([1,40],[5,5],'k--',lw=2,label='S/N = 5')
        #data
        for inst,color in zip(['decam','bokmos'],['b','g']):
            ax[cnt].plot(bin_SN[inst][band]['binc'], bin_SN[inst][band]['q50'],c=color,ls='-',lw=2,label=inst)
            ax[cnt].fill_between(bin_SN[inst][band]['binc'],bin_SN[inst][band]['q25'],bin_SN[inst][band]['q75'],color=color,alpha=0.25)
    #labels
    ax[2].legend(loc=1,**leg_args)
    for cnt,band in zip(range(3),['g','r','z']):
    for cnt in range(3):
        xlab=ax[cnt].set_xlabel('%s' % band, **laba)
        ax[cnt].set_ylim(1,100)
        ax[cnt].set_xlim(20.,26.)
    ylab=ax[0].set_ylabel(r'S/N = f / $\sigma_f$', **laba)
    plt.savefig('sn_%s_%s.png' % (found_by,type), bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
    plt.close()

def plot_matched_separation_hist(d12, zoom=False):
    '''d12 is array of distances in degress between matched objects'''
    #pixscale to convert d12 into N pixels
    pixscale=dict(decam=0.25,bokmos=0.45)
    #sns.set_style('ticks',{"axes.facecolor": ".97"})
    #sns.set_palette('colorblind')
    #setup plot
    fig,ax=plt.subplots()
    #plot
    ax.hist(d12*3600./pixscale['decam'],bins=50,color='b',align='mid')
    ax2 = ax.twiny()
    ax2.hist(d12*3600./pixscale['bokmos'],bins=50,color='g',align='mid',visible=False)
    xlab= ax.set_xlabel("pixel separation [decam]")
    xlab= ax2.set_xlabel("pixel separation [bok]")
    ylab= ax.set_ylabel("Counts")
    ti= ax.set_title('Matched')
    if zoom: ax.set_xlim(0,3)
    # sup=plt.suptitle('decam with matching bokmos',**laba)
    #save
    #sns.despine()
    if zoom: name="separation_hist_zoom.png"
    else: name="separation_hist.png"
    plt.savefig(name, bbox_extra_artists=[xlab,ylab,ti], bbox_inches='tight',dpi=150)
    plt.close()

def plot_PSF_color(obj): 
    '''obj['m_decam'] is a DECaLS() object'''
    #set seaborn panel styles
    #sns.set_style('ticks',{"axes.facecolor": ".97"})
    #sns.set_palette('colorblind')
    #setup plot
    fig,ax=plt.subplots(2,2) #,figsize=(9,3)) #,sharey=True)
    plt.subplots_adjust(wspace=0.5,hspace=0)
    #PSF indices
    i_PSF={}
    for val in ['m_decam','m_bokmos','u_decam','u_bokmos']: 
        i_PSF[val]= obj[val].data['type'] == 'PSF'
    #bin by g mag
    width=0.25 #in mag
    low_vals= np.arange(20.,26.,width)
    med,rms={},{}
    for val in ['m_decam','m_bokmos','u_decam','u_bokmos']:
        med[val]=np.zeros(low_vals.size)-100
        rms[val]=np.zeros(low_vals.size)-100
    for val in ['m_decam','m_bokmos','u_decam','u_bokmos']:
        for i,low in enumerate(low_vals):
            ind= np.all((low <= obj[val].data['gmag'][i_PSF[val]],obj[val].data['gmag'][i_PSF[val]] < low+width),axis=0)
            if np.where(ind)[0].size > 0:
                sample=obj[val].data['gmag'][ind]-obj[val].data['rmag'][ind]
                med[val][i]= np.percentile(sample,q=50)
                rms[val][i]= np.sqrt( np.mean( np.power(sample,2) ) )
            else: 
                med[val][i]= np.nan
                med[val][i]= np.nan
    #plot
    ti=ax[0,0].set_title('Decam PSF')
    ti=ax[0,1].set_title('Bokmos PSF')
    ylab=ax[0,0].set_ylabel('Median g-r')
    ylab=ax[1,0].set_ylabel('RMS g-r')
    xlab=ax[1,0].set_xlabel('g binned 0.25')
    xlab=ax[1,1].set_xlabel('g binned 0.25')
    #decam
    ax[0,0].scatter(low_vals,med['m_decam'],edgecolor='b',c='none',lw=2.,label='Matched')
    ax[0,0].scatter(low_vals,med['u_decam'],edgecolor='g',c='none',lw=2.,label='Unmatched')
    ax[1,0].scatter(low_vals,rms['m_decam'],edgecolor='b',c='none',lw=2.)
    ax[1,0].scatter(low_vals,rms['u_decam'],edgecolor='g',c='none',lw=2.)
    #bokmos
    ax[0,0].scatter(low_vals,med['m_bokmos'],edgecolor='b',c='none',lw=2.)
    ax[0,0].scatter(low_vals,med['u_bokmos'],edgecolor='g',c='none',lw=2.)
    ax[1,0].scatter(low_vals,rms['m_bokmos'],edgecolor='b',c='none',lw=2.)
    ax[1,0].scatter(low_vals,rms['u_bokmos'],edgecolor='g',c='none',lw=2.)
    #finish
    ax[0,0].legend(loc=3,**leg_args)
    #save
    #sns.despine()
    plt.savefig('psf_color_binned.png', bbox_extra_artists=[ti,xlab,ylab], bbox_inches='tight',dpi=150)
    plt.close()

def plot_psf_hists(decam,bokmos, zoom=False):
    '''decam,bokmos are DECaLS() objects matched to decam ra,dec'''
    #divide into samples of 0.25 mag bins, store q50 of each
    width=0.25 #in mag
    low_vals= np.arange(20.,26.,width)
    med={}
    for b in ['g','r','z']: med[b]=np.zeros(low_vals.size)-100
    for i,low in enumerate(low_vals):
        for band in ['g','r','z']:
            ind= np.all((low <= decam[band+'mag'],decam[band+'mag'] < low+width),axis=0)
            if np.where(ind)[0].size > 0:
                med[band][i]= np.percentile(bokmos[band+'mag'][ind] - decam[band+'mag'][ind],q=50)
            else: 
                med[band][i]= np.nan
    #make plot
    #set seaborn panel styles
    #sns.set_style('ticks',{"axes.facecolor": ".97"})
    #sns.set_palette('colorblind')
    #setup plot
    fig,ax=plt.subplots(1,3,figsize=(9,3)) #,sharey=True)
    plt.subplots_adjust(wspace=0.5)
    #plot
    for cnt,band in zip(range(3),['r','g','z']):
        ax[cnt].scatter(low_vals, med[band],\
                       edgecolor='b',c='none',lw=2.) #,label=m_type.split('_')[-1])
        xlab=ax[cnt].set_xlabel('bins of %s (decam)' % band, **laba)
        ylab=ax[cnt].set_ylabel('q50[%s bokmos - decam]' % band, **laba)
        if zoom: ax[cnt].set_ylim(-0.25,0.25)
    # sup=plt.suptitle('decam with matching bokmos',**laba)
    #save
    #sns.despine()
    if zoom: name="median_color_diff_zoom.png"
    else: name="median_color_diff.png"
    plt.savefig(name, bbox_extra_artists=[xlab,ylab], bbox_inches='tight',dpi=150)
    plt.close()



parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                 description='DECaLS simulations.')
parser.add_argument('-fn1', type=str, help='process this brick (required input)')
parser.add_argument('-fn2', type=str, help='object type (STAR, ELG, LRG, BGS)') 

args = parser.parse_args()

#get lists of tractor cats to compare
fns_1= read_lines(args.fn1) 
fns_2= read_lines(args.fn2) 
#if fns_1.size == 1: fns_1,fns_2= [fns_1],[fns_2]
#object to store concatenated matched tractor cats
a=Matched_Cats()
for cnt,cat1,cat2 in zip(range(len(fns_1)),fns_1,fns_2):
    data_1,data_2,m1,m2,m1_unm,m2_unm,d12= match_it(cat1,cat2)
    if cnt == 0:
        a.initialize(data_1,data_2,m1,m2,m1_unm,m2_unm,d12)
    else:  
        a.add_d12(d12)
        a.add_dict('m_decam', targets.data_extract(data_1,m1) )
        a.add_dict('m_bokmos', targets.data_extract(data_2,m2))
        a.add_dict('u_decam', targets.data_extract(data_1,m1_unm))
        a.add_dict('u_bokmos', targets.data_extract(data_2,m2_unm))
#each key a.data[key] becomes DECaLS() object with grz mags,i_lrg, etc
b={}
b['d12']= a.d12
for match_type in a.data.keys(): b[match_type]= targets.DECaLS(a.data[match_type], w1=True)
#store N matched objects not masked before join decam,bokmos masks
m_decam_not_masked,m_bokmos_not_masked= b['m_decam'].count_not_masked(),b['m_bokmos'].count_not_masked()
#join decam,bokmos masks for matched pairs 
mask= np.any((b['m_decam'].data['gmag'].mask, b['m_bokmos'].data['gmag'].mask),axis=0)
b['m_decam'].propogate_new_mask(mask)
b['m_bokmos'].propogate_new_mask(mask)
#plots
plot_radec(b,m_types=['u_decam','u_bokmos'])

plot_SN(b, found_by='matched',type='all')
#plot_SN(b, found_by='matched',type='psf')
#plot_SN(b, found_by='unmatched',type='all')
print('exit')
sys.exit()


plot_matched_color_diff_binned(b['m_decam'].data,b['m_bokmos'].data)
plot_matched_color_diff_binned(b['m_decam'].data,b['m_bokmos'].data,zoom=True)

plot_matched_separation_hist(b['d12'])

plot_PSF_color(b)

print('exiting early')
sys.exit()
plot_HistTypes(b,m_types=['m_decam','m_bokmos'])
plot_HistTypes(b,m_types=['u_decam','u_bokmos'])

plot_matched_color_color(b['m_decam'].data,b['m_bokmos'].data)
plot_matched_color_color(b['m_decam'].data,b['m_bokmos'].data, zoom=True)
#print stats of total objects, each group, # masked, etc
print("---- DECAM ----")
print("N not masked due to grz= %d, N total= %d" % \
        (m_decam_not_masked+b['u_decam'].count_not_masked(), b['m_decam'].count_total()+b['u_decam'].count_total()))
print("-- Matched --")
print("N not masked before join bokmos mask= %d, N not masked after= %d" % \
        (m_decam_not_masked, b['m_decam'].count_not_masked()))
print("-- Unmatched -- ")
print("N masked before join bokmos mask = N masked after = %d" % \
        (b['u_decam'].count_total()- b['u_decam'].count_not_masked()))
###bokmos
print("---- BOKMOS ----")
print("N not masked due to grz= %d, N total= %d" % \
        (m_bokmos_not_masked+b['u_bokmos'].count_not_masked(), b['m_bokmos'].count_total()+b['u_bokmos'].count_total()))
print("-- Matched --")
print("N not masked before join decam mask= %d, N not masked after= %d" % \
        (m_bokmos_not_masked, b['m_bokmos'].count_not_masked()))
print("-- Unmatched -- ")
print("N masked before join decam mask = N masked after = %d" % \
        (b['u_bokmos'].count_total()- b['u_bokmos'].count_not_masked()))
print('done')


