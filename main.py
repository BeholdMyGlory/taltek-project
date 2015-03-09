#!/usr/bin/env python3
"""VoiceXML battelships

Usage:
  main.py [options]

Options:
  -h, --help                Show this screen.
  -p NUMBER, --port=NUMBER  Port to listen on [default: 8080]
  -l ADDR, --listen=ADDR    Address to listen on, by default all interfaces
"""

import logging
import uuid
import time
import sys
import traceback

from docopt import docopt
from lxml import etree
import tornado.ioloop
import tornado.gen
import tornado.web

import game


class SessionTokenToGame(object):
    """
    Usage:
    >>> g = SessionTokenToGame()
    >>> g[42]
    None
    >>> g[123]
    Game('42', 123)
    >>> g[42]
    Game('42', 123)
    """

    def __init__(self):
        self.session_token_game_dict = {}
        self.unmatched_players = set()

    def __getitem__(self, player_token):
        if player_token not in self.session_token_game_dict:
            self.session_token_game_dict[player_token] = None
            self.unmatched_players.add(player_token)

        if self.session_token_game_dict[player_token] is None and len(self.unmatched_players) > 1:
            unmatched_player = self.unmatched_players.pop()
            if unmatched_player == player_token:  # oops, we popped ourselves, let's pop once more
                unmatched_player = self.unmatched_players.pop()
            logger.debug('Matching players %s and %s' % (unmatched_player, player_token))
            self.unmatched_players.discard(player_token)

            new_game = game.Game(unmatched_player, player_token)
            self.session_token_game_dict[unmatched_player] = game.GameProxy(new_game, unmatched_player)
            self.session_token_game_dict[player_token] = game.GameProxy(new_game, player_token)

        return self.session_token_game_dict[player_token]


class XMLHandler(tornado.web.RequestHandler):
    # called before running any other methods (get, post, etc)
    def prepare(self):
        self.set_header("Content-Type", "application/xml")

    def write_xml(self, tagname="response", **attributes):
        response = etree.tostring(etree.Element(tagname, **attributes))
        logger.debug("Response: %s", response)
        self.write(response)


# new instances of the request handlers are created on every request,
# so changes to member variables won't be seen across requests
class DialogHandler(XMLHandler):
    def get(self):
        template_data = {
            'token': uuid.uuid1().hex,
            'grid_size': game.Game.GRID_SIZE,
            'ships': game.Game.AVAILABLE_SHIPS,
        }
        self.render("dialog.xml", **template_data)


class DynamicDataHandler(XMLHandler):
    TIMEOUT_SECONDS = 9.0
    POLL_INTERVAL_SECONDS = 0.5

    def prepare(self):
        self.token = self.get_argument('token')
        self.game = GAMES[self.token]
        self.out = {}

    def check_with_timeout(self, what, timeout_value=None):
        start_time = time.time()
        result = None
        while True:
            result = what()
            if result != timeout_value:
                return result
            elif time.time() - start_time > self.TIMEOUT_SECONDS:
                return timeout_value
            yield tornado.gen.sleep(self.POLL_INTERVAL_SECONDS)

    def write_error(self, status_code, **kwargs):
        (exc_type, value, tb) = kwargs['exc_info']
        error_data = {
            'type': exc_type.__name__,
            'message': getattr(value, 'message', '') or getattr(value, 'log_message', ''),
            'traceback': traceback.extract_tb(tb),
        }
        self.render("error.xml", **error_data)


class WaitForGameHandler(DynamicDataHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForGame: %s", self.request.query)
        ready = yield from self.check_with_timeout(lambda: GAMES[self.token], None)
        self.out['ready'] = str(bool(ready)).lower()
        self.write_xml(**self.out)


class PlaceShipHandler(DynamicDataHandler):
    def prepare(self):
        super(PlaceShipHandler, self).prepare()
        if not self.game:
            raise Exception('no_game')

    def get(self):
        logger.debug("GET-PlaceShip: %s", self.request.query)
        self._add_next_ship_info_to_output()
        self.write_xml(**self.out)

    def _add_next_ship_info_to_output(self):
        ship = self.game.get_ship_to_place()
        if ship:
            self.out.update({
                'name': ship.name,
                'size': str(ship.size),
            })

    def post(self):
        logger.debug("POST-PlaceShip: %s", self.request.body)
        self.out.update({
            'conflictingcoords': '',
            'allowed': 'yes',
        })

        coord = game.Coord(*self.get_argument('coord'))
        map_orientation = {
            'horizontally': game.Orientation.horizontal,
            'vertically': game.Orientation.vertical,
        }

        orientation = map_orientation[self.get_argument('orientation')]
        try:
            self.game.place_ship(top_left_coord=coord, orientation=orientation)
        except game.OccupiedFieldsException as e:
            self.out['conflictingcoords'] = ' '.join(str(occ) for occ in e.occupied_fields)
            self.out['allowed'] = 'conflict'
        except IndexError:
            self.out['allowed'] = 'beyondfield'
        self._add_next_ship_info_to_output()
        self.write_xml(**self.out)


class WaitForTurnHandler(DynamicDataHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForTurn: %s", self.request.query)
        game_state = yield from self.check_with_timeout(lambda: self.game.get_game_state(),
                                                        timeout_value=game.GameState.wait)
        self.out['gamestate'] = game_state.name
        if game_state == game.GameState.canPlay:
            (coord, what_was_at_coord) = self.game.get_last_opponent_move()
            if coord:
                self.out['coordhit'] = str(coord)
            if what_was_at_coord:
                self.out['shiptypehit'] = what_was_at_coord.name
                self.out['shippartsleft'] = str(what_was_at_coord.fields_intact)
        self.write_xml(**self.out)


class PutCoordHandler(DynamicDataHandler):
    def get(self):
        logger.debug("PutCoord: %s", self.request.query)
        coord = game.Coord(*self.get_argument('coord'))
        shot_result = self.game.shoot_field(coord)
        self.out['shot'] = shot_result.name
        self.write_xml(**self.out)


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
    logger.addHandler(logging.FileHandler("battleships.log"))
    logger.addHandler(logging.StreamHandler(stream=sys.stderr))

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
    logger.debug('Server listening on %s:%s' % (address, port))
    GAMES = SessionTokenToGame()

    # this starts the event loop. Tornado is single threaded,
    # and will sleep until it is notified of new events on one of
    # its sockets.
    loop.start()
