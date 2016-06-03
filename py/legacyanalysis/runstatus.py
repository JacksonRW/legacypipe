from __future__ import print_function
import matplotlib
matplotlib.use('Agg')
import pylab as plt
import qdo
import sys
import argparse
from legacypipe.common import LegacySurveyData
from astrometry.libkd.spherematch import *

parser = argparse.ArgumentParser()
parser.add_argument('--wrap', action='store_true',
                    help='Wrap RA at 180 degrees?')
parser.add_argument('args',nargs=argparse.REMAINDER)
opt = parser.parse_args()
args = opt.args
if len(args) != 1:
    print('Need one arg: qdo queue name')
    sys.exit(-1)

qname = args[0]

q = qdo.connect(qname, create_ok=False)
print('Connected to QDO queue', qname, q)

plt.clf()

cmap = { qdo.Task.WAITING: 'k',
         qdo.Task.PENDING: '0.5',
         qdo.Task.RUNNING: 'b',
         qdo.Task.SUCCEEDED: 'g',
         qdo.Task.FAILED: 'r',
}

lp,lt = [],[]

allra = []
alldec = []
allq = []
allstate = []

for state in qdo.Task.VALID_STATES:
    print('State', state)

    ra,dec = [],[]
    brickq = []
    tasks = q.tasks(state=state)
    print(len(tasks), 'tasks with state', state)
    
    for task in tasks:
        brick = task.task

        #brickobj = survey.get_brick_by_name(brick)
        #r = brickobj.ra
        #d = brickobj.dec
        
        rastr = brick[:4]
        r = int(rastr, 10) / 10.
        decstr = brick[5:]
        d = int(decstr, 10) / 10.
        d *= (-1 if brick[4] == 'm' else 1)

        #print('Brick', brick, '->', r, d)
        if opt.wrap:
            if r > 180:
                r -= 360.
        ra.append(r)
        dec.append(d)

    ra = np.array(ra)
    dec = np.array(dec)

    p = plt.plot(ra, dec, '.', color=cmap.get(state, 'y'))
    lp.append(p[0])
    lt.append(state)

    allra.append(ra)
    alldec.append(dec)
    #allq.append(brickq)
    allstate.append([state] * len(ra))

# HACK
plt.xlim([-45, 65])
plt.figlegend(lp, lt, 'upper right')
plt.savefig('status.png')

ra = np.hstack(allra)
dec = np.hstack(alldec)
state = np.hstack(allstate)

# Match to actual table of bricks to get brickq.
survey = LegacySurveyData()
bricks = survey.get_bricks_readonly()
I,J,d = match_radec(ra, dec, bricks.ra, bricks.dec, 0.2, nearest=True)
print(len(ra), 'jobs')
print(len(I), 'matches')
ra = ra[I]
dec = dec[I]
state = state[I]
brickq = bricks.brickq[J]

for q in [0,1,2,3]:
    plt.clf()
    lp,lt = [],[]
    for s in qdo.Task.VALID_STATES:
        I = np.flatnonzero((brickq == q) * (state == s))
        if len(I) == 0:
            continue
        
        p = plt.plot(ra[I], dec[I], '.', color=cmap.get(s, 'y'))
        lp.append(p[0])
        lt.append(s)
    plt.title('Brickq = %i' % q)
    # HACK
    plt.xlim([-45, 65])
    plt.figlegend(lp, lt, 'upper right')
    plt.savefig('status-%i.png' % q)
    
