from __future__ import print_function
import os
from legacypipe.runbrick import main

if __name__ == '__main__':
    surveydir = os.path.join(os.path.dirname(__file__), 'testcase3')
    main(args=['--brick', '2447p120', '--zoom', '1020', '1070', '2775', '2815',
               '--no-wise', '--force-all', '--no-write',
               '--survey-dir', surveydir,
               '--outdir', 'out-testcase3'])

    # With ceres
    main(args=['--brick', '2447p120', '--zoom', '1020', '1070', '2775', '2815',
               '--no-wise', '--force-all', '--no-write', '--ceres',
               '--survey-dir', surveydir,
               '--outdir', 'out-testcase3-ceres'])
    

    
