#!/bin/bash 

# DR4 fixes runs from
# $LEGACY_SURVEY_DIR/../dr4_fixes/legacypipe-dir which is
#     /scratch1/scratchdirs/desiproc/DRs/dr4-bootes/dr4_fixes/legacypipe-dir
# $CODE_DIR/../dr4_fixes/legacypipe which is 
#     /scratch1/scratchdirs/desiproc/DRs/code/dr4_fixes/legacypipe

export LEGACY_SURVEY_DIR=/scratch1/scratchdirs/desiproc/DRs/dr4-bootes/dr4_fixes/legacypipe-dir
export CODE_DIR=/scratch1/scratchdirs/desiproc/DRs/code/dr4_fixes/legacypipe
export outdir=/scratch1/scratchdirs/desiproc/DRs/data-releases/dr4_fixes
#export DUST_DIR=adfa
#export unwise_dir=lakdjf

export overwrite_tractor=no
export full_stacktrace=no
export early_coadds=no

bricklist=${LEGACY_SURVEY_DIR}/List_bricks_W3_deep2_BOSS_5017.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-${NERSC_HOST}.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-notdone-${NERSC_HOST}.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-${NERSC_HOST}-oom.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-rerunpsferr-${NERSC_HOST}.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-${NERSC_HOST}-asserterr.txt
#bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-${NERSC_HOST}-hascutccds.txt
if [ "$overwrite_tractor" = "yes" ]; then
    #bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-nowise-${NERSC_HOST}.txt
    #bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-nowiseflux-${NERSC_HOST}.txt
    bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-${NERSC_HOST}-nolc.txt
elif [ "$full_stacktrace" = "yes" ]; then
    bricklist=${LEGACY_SURVEY_DIR}/bricks-dr4-full-stacktrace-${NERSC_HOST}.txt 
fi 
echo bricklist=$bricklist
if [ ! -e "$bricklist" ]; then
    echo file=$bricklist does not exist, quitting
    exit 999
fi

export statdir="${outdir}/progress"
mkdir -p $statdir 

# Loop over bricks
start_brick=1
end_brick=10
cnt=0
while read aline; do
    export brick=`echo $aline|awk '{print $1}'`
    if [ "$full_stacktrace" = "yes" ];then
        stat_file=$statdir/stacktrace_$brick.txt
    else
        stat_file=$statdir/submitted_$brick.txt
    fi
    bri=$(echo $brick | head -c 3)
    tractor_fits=$outdir/tractor/$bri/tractor-$brick.fits
    if [ -e "$tractor_fits" ]; then
        if [ "$overwrite_tractor" = "yes" ]; then
            echo ignoring existing tractor.fits
        else
            continue
        fi
    fi
    if [ -e "$stat_file" ]; then
        continue
    fi
    sbatch ../bin/job_dr4.sh --export brick,outdir,overwrite_tractor,full_stacktrace,early_coadds,dr4_fixes
    touch $stat_file
    let cnt=${cnt}+1
done <<< "$(sed -n ${start_brick},${end_brick}p $bricklist)"
echo submitted $cnt bricks
