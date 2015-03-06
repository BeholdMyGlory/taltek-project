#!/usr/bin/env python3
"""VoiceXML battelships

Usage:
  main.py [options]

Options:
  -h, --help                Show this screen.
  -p NUMBER, --port=NUMBER  Port to listen on [default: 8080]
  -l ADDR, --listen=ADDR    Address to listen on, by default all interfaces
"""

import datetime
import logging
import uuid

from docopt import docopt
from lxml import etree
import tornado.ioloop
import tornado.gen
import tornado.web

class XMLHandler(tornado.web.RequestHandler):
    # called before running any other methods (get, post, etc)
    def prepare(self):
        self.set_header("Content-Type", "application/xml")

    def write_xml(self, tagname="response", **attributes):
        self.write(etree.tostring(etree.Element(tagname, **attributes)))

# new instances of the request handlers are created on every request,
# so changes to member variables won't be seen across requests
class DialogHandler(XMLHandler):
    def get(self):
        token = uuid.uuid1().hex
        self.render("dialog.xml", token=token)


class WaitForGameHandler(XMLHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForGame: %s", self.request.query)
        yield tornado.gen.sleep(9)
        self.write_xml(ready="true")

class PlaceShipHandler(XMLHandler):
    def get(self):
        logger.debug("GET-PlaceShip: %s", self.request.query)
        self.write_xml(name="battleship", size="4")

    def post(self):
        logger.debug("POST-PlaceShip: %s", self.request.body)
        self.write_xml(allowed="yes")

class WaitForTurnHandler(XMLHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForTurn: %s", self.request.query)
        yield tornado.gen.sleep(9)
        self.write_xml(gamestate="canplay")

class PutCoordHandler(XMLHandler):
    def get(self):
        logger.debug("PutCoord: %s", self.request.query)
        self.write_xml(shot="hit")

class LogHandler(XMLHandler):
    def get(self):
        logger.info("GET-LOG: %s", self.request.query)
        self.write_xml()

    def post(self):
        logger.info("POST-LOG: %s", self.request.body)
        self.write_xml()

if __name__ == "__main__":
    args = docopt(__doc__)
    loop = tornado.ioloop.IOLoop.current()
    logger = logging.getLogger('battleships-web')
    logger.setLevel(logging.DEBUG)

    # debug=True will reload the application if a file is changed,
    # and disable the template cache, among other things
    app = tornado.web.Application([
        (r"/dialog", DialogHandler),
        (r"/waitforgame", WaitForGameHandler),
        (r"/placeship", PlaceShipHandler),
        (r"/waitforturn", WaitForTurnHandler),
        (r"/putcoord", PutCoordHandler),
        (r"/log", LogHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {'path': 'static'})
    ], template_path="templates", debug=True)

    port = int(args['--port'])
    address = args['--listen'] or ''
    app.listen(port, address=address)

    # this starts the event loop. Tornado is single threaded,
    # and will sleep until it is notified of new events on one of
    # its sockets.
    loop.start()
