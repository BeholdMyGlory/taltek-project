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
import uuid

from docopt import docopt
import tornado.ioloop
import tornado.gen
import tornado.web

class XMLHandler(tornado.web.RequestHandler):
    # called before running any other methods (get, post, etc)
    def prepare(self):
        self.set_header("Content-Type", "application/xml")

# new instances of the request handlers are created on every request,
# so changes to member variables won't be seen across requests
class HelloWorld(XMLHandler):
    def get(self):
        token = uuid.uuid1().hex
        self.render("dialog.xml", token=token)


class FindMatchHandler(XMLHandler):
    @tornado.gen.coroutine
    def get(self):
        print(self.get_argument("token"))
        yield tornado.gen.sleep(9)
        self.write("<response>yes</response>")

placed_ships = {}
ships = [("battleship", 4), ("submarine", 3), ("destroyer", 2)]

class NextShipHandler(XMLHandler):
    def get(self):
        token = self.get_argument('token')
        placed_ships[token] = placed_ships.get(token, -1) + 1
        ship, length = ships[placed_ships[token]]
        self.write('<response ship="{}" length="{}"/>'.format(ship, length))


if __name__ == "__main__":
    args = docopt(__doc__)
    loop = tornado.ioloop.IOLoop.current()

    # debug=True will reload the application if a file is changed,
    # and disable the template cache, among other things
    app = tornado.web.Application([
        (r"/dialog", HelloWorld),
        (r"/findmatch", FindMatchHandler),
        (r"/nextship", NextShipHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {'path': 'static'})
    ], template_path="templates", debug=True)

    port = int(args['--port'])
    address = args['--listen'] or ''
    app.listen(port, address=address)

    # this starts the event loop. Tornado is single threaded,
    # and will sleep until it is notified of new events on one of
    # its sockets.
    loop.start()
