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

from docopt import docopt
import tornado.ioloop
import tornado.web

class XMLHandler(tornado.web.RequestHandler):
    # called before running any other methods (get, post, etc)
    def prepare(self):
        self.set_header("Content-Type", "application/xml")

# new instances of the request handlers are created on every request,
# so changes to member variables won't be seen across requests
class HelloWorld(XMLHandler):
    def get(self):
        curdate = datetime.datetime.now()
        self.render("dialog.xml", month=curdate.strftime("%B"),
                    day=curdate.day,
                    hour=curdate.hour, minute=curdate.minute)

if __name__ == "__main__":
    args = docopt(__doc__)
    loop = tornado.ioloop.IOLoop.current()

    # debug=True will reload the application if a file is changed,
    # and disable the template cache, among other things
    app = tornado.web.Application([
        (r"/dialog\.xml", HelloWorld)
    ], template_path="templates", debug=True)

    port = int(args['--port'])
    address = args['--listen'] or ''
    app.listen(port, address=address)

    # this starts the event loop. Tornado is single threaded,
    # and will sleep until it is notified of new events on one of
    # its sockets.
    loop.start()
