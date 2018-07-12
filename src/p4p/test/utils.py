
from __future__ import print_function

import logging, warnings
_log = logging.getLogger(__name__)

import gc, inspect, unittest, functools, time, os
import fnmatch

from .. import listRefs

_ignore_transient = os.environ.get('REFTEST_IGNORE_TRANSIENT','')=='YES'

try:
    import asyncio
except ImportError:
    pass
else:
    def inloop(fn):
        """Decorator assumes wrapping method of object with .loop and maybe .timeout
        """
        @functools.wraps(fn)
        def testmethod(self):
            F = fn(self)
            if not hasattr(self, 'loop'):
                self.loop = asyncio.new_event_loop()
                self.loop.set_debug(True)
            timeout = getattr(self, 'timeout', None)
            if timeout is not None:
                F = asyncio.wait_for(F, timeout, loop=self.loop)
            self.loop.run_until_complete(F)
        return testmethod

    def clearloop(self):
        if hasattr(self, 'loop'):
            self.loop.close()
            del self.loop

class RefTestMixin(object):
    """Ensure that each test does not result in a net change in extension object counts
    """
    # set to list of names to compare.  Set to None to disable
    ref_check = ('*',)

    def __refs(self, refs=None):
        refs = refs or listRefs()
        _log.debug("REFS %s", refs)
        names = set()
        for pat in self.ref_check:
            names |= set(fnmatch.filter(refs, pat))
        return dict([(K,V) for K,V in refs.items() if K in names])

    def setUp(self):
        if self.ref_check is not None:
            self.__before = self.__refs()
        super(RefTestMixin, self).setUp()

    def tearDown(self):
        super(RefTestMixin, self).tearDown()
        if self.ref_check is not None:
            gc.collect()
            after = self.__refs()

            test1 = self.__before==after

            if not test1:
                _log.error("Mis-match, attempting to detect if transient")
                time.sleep(1.0)
                gc.collect()
                after1, after = after, self.__refs()

            self.assertDictEqual(self.__before, after)
            # check for any obviously corrupt counters, even those not being compared
            #self.assertFalse(any([V>1000000 for V in refs.values()]), "before %s after %s"%(self.__raw_before, refs))

            if not test1:
                if _ignore_transient:
                    _log.info("IGNORE transient refs")
                else:
                    self.assertDictEqual(self.__before, after1)

class RefTestCase(RefTestMixin, unittest.TestCase):
    def setUp(self):
        super(RefTestCase, self).setUp()
    def tearDown(self):
        super(RefTestCase, self).tearDown()

def gctrace(obj, maxdepth=8):
    # depth first traversal
    pop = object()
    top = inspect.currentframe()
    next = top.f_back
    stack, todo = [], [obj]
    visited = set()

    while len(todo):
        obj = todo.pop(0)
        #print('N', obj)
        I = id(obj)
        if inspect.isframe(obj):
            S = 'Frame %s:%d'%(obj.f_code.co_filename, obj.f_lineno)
        else:
            S = str(obj)

        if obj is pop:
            stack.pop()
            #break
            continue

        print('-'*len(stack), S, end='')

        if I in stack:
            print(' Recurse')
            continue
        elif I in visited:
            print(' Visited')
            continue
        elif len(stack)>=maxdepth:
            print(' Depth limit')
            continue
        else:
            print(' ->')

        stack.append(I)
        visited.add(I)

        todo.insert(0,pop)

        for R in gc.get_referrers(obj):
            if R is top or R is next or R is todo:
                continue
            todo.insert(0,R)
