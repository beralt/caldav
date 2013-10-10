#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from datetime import datetime
import urlparse
import logging
import threading
from nose.tools import assert_equal, assert_not_equal

from conf import caldav_urls, proxy, proxy_noport
from proxy import ThreadingHTTPServer, ProxyHandler

from caldav.davclient import DAVClient
from caldav.objects import Principal, Calendar, Event, DAVObject
from caldav.lib import url
from caldav.lib.namespace import ns
from caldav.elements import dav, cdav


ev1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
UID:20010712T182145Z-123401@example.com
DTSTAMP:20060712T182145Z
DTSTART:20060714T170000Z
DTEND:20060715T040000Z
SUMMARY:Bastille Day Party
END:VEVENT
END:VCALENDAR
"""

ev2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp.//CalDAV Client//EN
BEGIN:VEVENT
UID:20010712T182145Z-123401@example.com
DTSTAMP:20070712T182145Z
DTSTART:20070714T170000Z
DTEND:20070715T040000Z
SUMMARY:Bastille Day Party +1year
END:VEVENT
END:VCALENDAR
"""
testcal_id = "pythoncaldav-test"

class RepeatedFunctionalTestsBaseClass(object):
    """
    This is a class with functional tests (tests that goes through
    basic functionality and actively communicates with third parties)
    that we want to repeat for all configured caldav_urls.
    """
    def setup(self):
        self.caldav = DAVClient(self.principal_url)
        self.principal = Principal(self.caldav, self.principal_url)

    def teardown(self):
        p = url.make(self.principal.url)
        path = url.join(p, testcal_id)

        cal = Calendar(self.caldav, name="Yep", parent = self.principal,
                       url = path)
        cal.delete()

    def testGetCalendars(self):
        assert_not_equal(len(self.principal.calendars()), 0)

    def testProxy(self):
        server_address = ('127.0.0.1', 8080)
        proxy_httpd = ThreadingHTTPServer (server_address, ProxyHandler, logging.getLogger ("TinyHTTPProxy"))
        
        threading.Thread(target=proxy_httpd.handle_request).start()
        c = DAVClient(self.principal_url, proxy)
        p = Principal(c, self.principal_url)
        assert_not_equal(len(p.calendars()), 0)

        threading.Thread(target=proxy_httpd.handle_request).start()
        c = DAVClient(self.principal_url, proxy_noport)
        p = Principal(c, self.principal_url)
        assert_not_equal(len(p.calendars()), 0)

    def testPrincipal(self):
        assert_equal(url.make(self.principal.url), self.principal_url)

        collections = self.principal.calendars()
        for c in collections:
            assert_equal(c.__class__.__name__, "Calendar")

    def testCalendar(self):
        c = Calendar(self.caldav, name="Yep", parent = self.principal,
                     id = testcal_id).save()
        assert_not_equal(c.url, None)
        # TODO: fail
        #props = c.get_properties([dav.DisplayName(),])
        #assert_equal("Yep", props[dav.DisplayName.tag])

        c.set_properties([dav.DisplayName("hooray"),])
        props = c.get_properties([dav.DisplayName(),])
        assert_equal(props[dav.DisplayName.tag], "hooray")
        print c

        cc = Calendar(self.caldav, name="Yep", parent = self.principal).save()
        assert_not_equal(cc.url, None)
        cc.delete()

        e = Event(self.caldav, data = ev1, parent = c).save()
        assert_not_equal(e.url, None)
        print e, e.data

        ee = Event(self.caldav, url = url.make(e.url), parent = c)
        ee.load()
        assert_equal(e.instance.vevent.uid, ee.instance.vevent.uid)

        r = c.date_search(datetime(2006,7,13,17,00,00),
                          datetime(2006,7,15,17,00,00))
        assert_equal(e.instance.vevent.uid, r[0].instance.vevent.uid)
        for e in r: print e.data
        assert_equal(len(r), 1)

        all = c.events()
        print all
        assert_equal(len(all), 1)

        e2 = Event(self.caldav, data = ev2, parent = c).save()
        assert_not_equal(e.url, None)

        tmp = c.event("20010712T182145Z-123401@example.com")
        assert_equal(e2.instance.vevent.uid, tmp.instance.vevent.uid)

        r = c.date_search(datetime(2006,7,13,17,00,00),
                          datetime(2006,7,15,17,00,00))
        for e in r: print e.data
        assert_equal(len(r), 1)

        e.data = ev2
        e.save()

        r = c.date_search(datetime(2006,7,13,17,00,00),
                          datetime(2006,7,15,17,00,00))
        for e in r: print e.data
        assert_equal(len(r), 1)

        e.instance = e2.instance
        e.save()
        r = c.date_search(datetime(2006,7,13,17,00,00),
                          datetime(2006,7,15,17,00,00))
        for e in r: print e.data
        assert_equal(len(r), 1)

    def testObjects(self):
        o = DAVObject(self.caldav)
        failed = False
        try:
            o.save()
        except:
            failed = True
        assert_equal(failed, True)

# We want to run all tests in the above class through all caldav_urls;
# and I don't really want to create a custom nose test loader.  The
# solution here seems to be to generate one child class for each
# caldav_url, and inject it into the module namespace. TODO: This is
# very hacky.  If there are better ways to do it, please let me know.
# (maybe a custom nose test loader really would be the better option?)
# -- Tobias Brox <t-caldav@tobixen.no>, 2013-10-10

_servernames = set()
for _caldav_url in caldav_urls:
    # create a unique identifier out of the server domain name
    _parsed_url = urlparse.urlparse(_caldav_url)
    _servername = _parsed_url.hostname.replace('.','_') + str(_parsed_url.port or '')
    while _servername in _servernames:
        _servername = _servername + '_'
    _servernames.add(_servername)

    # create a classname and a class
    _classname = 'TestForServer_' + _servername

    # inject the new class into this namespace
    vars()[_classname] = type(_classname, (RepeatedFunctionalTestsBaseClass,), {'principal_url': _caldav_url})

class TestCalDAV:
    """
    Test class for "pure" unit tests (small internal tests, testing that
    a small unit of code works as expected, without any no third party
    dependencies)
    """
    def testFilters(self):
        # TODO: move this into a separate class, since it does not
        # depend on self.setup() and is a pure unit test (meaning,
        # without third party dependencies)?

        filter = cdav.Filter()\
                    .append(cdav.CompFilter("VCALENDAR")\
                    .append(cdav.CompFilter("VEVENT")\
                    .append(cdav.PropFilter("UID")\
                    .append([cdav.TextMatch("pouet", negate = True)]))))
        print filter

        crash = cdav.CompFilter()
        value = None
        try:
            value = str(crash)
        except:
            pass
        if value is not None:
            raise Exception("This should have crashed")
