python-alkivi-logger
==========================

[![Build Status](https://travis-ci.org/alkivi-sas/python-alkivi-logger.svg?branch=master)](https://travis-ci.org/alkivi-sas/python-alkivi-logger)
[![Requirements Status](https://requires.io/github/alkivi-sas/python-alkivi-logger/requirements.svg?branch=master)](https://requires.io/github/alkivi-sas/python-alkivi-logger/requirements/?branch=master)

Python logger used at Alkivi

## Package

Example

```python
from alkivi import logger as _logger
import logging

#
# Define Logger
#
logger = _logger.Logger(
        min_log_level_to_mail   = logging.ERROR,
        min_log_level_to_save   = logging.DEBUG,
        min_log_level_to_print  = logging.DEBUG,
        min_log_level_to_syslog = None,
        emails=['anthony@alkivi.fr'])

#
# Basic usage
#
logger.debug_debug('This is a very low level debug')
logger.debug('This is a debug comment')
logger.log('This is a basic log')
logger.info('This is a info comment')
logger.important('This is an important comment')
logger.warning('This is a warning comment')
logger.error('This is a error comment')
logger.critical('THis is very dangerous, please have a look !')

#
# Now let's do some loop
#
logger.new_loop_logger()
for i in range(0, 11):
    logger.new_iteration(prefix='i=%i' % (i))
    logger.debug("We are now prefixing all logger")
    if i == 9:
        logger.debug("Lets do another loop")
        logger.new_loop_logger()
        for j in range(0, 5):
            logger.new_iteration(prefix='j=%i' % (j))
            logger.debug("Alkivi pow@")

        # Dont forget to close logger or shit will happen
        logger.del_loop_logger()

logger.del_loop_logger()
logger.debug('We now remove an loop, thus a prefix')
```

## Tests

Testing is set up using [pytest](http://pytest.org) and coverage is handled
with the pytest-cov plugin.

Run your tests with ```py.test``` in the root directory.

Coverage is ran by default and is set in the ```pytest.ini``` file.
To see an html output of coverage open ```htmlcov/index.html``` after running the tests.

TODO

## Travis CI

There is a ```.travis.yml``` file that is set up to run your tests for python 2.7
and python 3.2, should you choose to use it.

TODO
