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
import math
import traceback

from docopt import docopt
from lxml import etree
import tornado.concurrent
import tornado.ioloop
import tornado.gen
import tornado.web

import game


class SessionTokenToGame(object):
    """

    """

    def __init__(self):
        self.session_token_game_dict = {}
        self.unmatched_players = set()
        self.futures = {}

    def get_game(self, player_token):
        if player_token not in self.session_token_game_dict:
            self.session_token_game_dict[player_token] = None
            self.futures[player_token] = tornado.concurrent.Future()
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

            self.futures[unmatched_player].set_result(self.session_token_game_dict[unmatched_player])
            self.futures[player_token].set_result(self.session_token_game_dict[player_token])

        return self.futures[player_token]

    def get(self, key, default=None):
        return self.session_token_game_dict.get(key, default)

    def __getitem__(self, key):
        return self.session_token_game_dict[key]

    def __delitem__(self, key):
        del self.session_token_game_dict[key]
        del self.futures[key]

    @classmethod
    def generate_token(self):
        return uuid.uuid1().hex


class XMLHandler(tornado.web.RequestHandler):
    # called before running any other methods (get, post, etc)
    def prepare(self):
        self.set_header("Content-Type", "application/xml")

    def write_xml(self, tagname="response", **attributes):
        xml_doc = etree.ElementTree(etree.Element(tagname, **attributes))
        response = etree.tostring(xml_doc, xml_declaration=True)
        logger.debug("Response: %s", response)
        self.write(response)


# new instances of the request handlers are created on every request,
# so changes to member variables won't be seen across requests
class DialogHandler(XMLHandler):
    def get(self):
        template_data = {
            'token': SessionTokenToGame.generate_token(),
            'grid_size': game.Game.GRID_SIZE,
            'ships': game.Game.AVAILABLE_SHIPS,
            'explicit_feedback': True,
            'feedback_timeout': '1s'
        }
        self.render("dialog.xml", **template_data)


class DynamicDataHandler(XMLHandler):
    def prepare(self):
        super().prepare()
        self.token = self.get_argument('token')
        self.out = {}

    def write_error(self, status_code, **kwargs):
        (exc_type, value, tb) = kwargs['exc_info']
        error_data = {
            'type': exc_type.__name__,
            'message': getattr(value, 'message', '') or getattr(value, 'log_message', ''),
            'traceback': traceback.extract_tb(tb),
        }
        self.render("error.xml", **error_data)


class PollDynamicDataHandler(DynamicDataHandler):
    POLL_INTERVAL_SECONDS = 0.5

    def check_with_timeout(self, what, as_long_as_returns=None, timeout_seconds=0.0):
        # TODO: refactor to be idiomatic wrt. to Tornado!

        if timeout_seconds > 0:
            times = math.floor(timeout_seconds / self.POLL_INTERVAL_SECONDS)
        else:
            times = 1
        if not times:
            times = 1

        for _ in range(times):
            result = what()
            if result != as_long_as_returns:
                return result
            yield tornado.gen.sleep(self.POLL_INTERVAL_SECONDS)
        return result


class GameVanishedException(Exception):
    pass


class GameDynamicDataHandler(DynamicDataHandler):
    '''
    To be used for any handlers that handle the active game.
    If the game no longer exists (e.g. because the opponent hung up) a GameVanishedException is raised,
    '''

    def prepare(self):
        super().prepare()
        if GAMES.get(self.token):
            self.game = GAMES[self.token]
        else:
            self.set_status(410)
            raise GameVanishedException()


class WaitForGameHandler(PollDynamicDataHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForGame: %s", self.request.query)
        timeout_seconds = float(self.get_argument('timeout', 0))
        #ready = yield from self.check_with_timeout(lambda: GAMES.get_game(self.token), as_long_as_returns=None,
                                                   #timeout_seconds=timeout_seconds)
        try:
            yield tornado.gen.with_timeout(datetime.timedelta(seconds=timeout_seconds),
                                           GAMES.get_game(self.token))
            self.out['ready'] = "true"
        except tornado.gen.TimeoutError:
            self.out['ready'] = "false"
        self.write_xml(**self.out)


class PlaceShipHandler(GameDynamicDataHandler):
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


class WaitForTurnHandler(GameDynamicDataHandler, PollDynamicDataHandler):
    @tornado.gen.coroutine
    def get(self):
        logger.debug("WaitForTurn: %s", self.request.query)
        timeout_seconds = float(self.get_argument('timeout', 0))
        try:
            yield tornado.gen.with_timeout(datetime.timedelta(seconds=timeout_seconds),
                                           self.game.wait_for_turn())
        except tornado.gen.TimeoutError:
            pass
        #game_state = yield from self.check_with_timeout(lambda: self.game.get_game_state(),
        #                                                as_long_as_returns=game.GameState.wait,
        #                                                timeout_seconds=timeout_seconds)
        game_state = self.game.get_game_state()
        self.out['gamestate'] = game_state.name
        if game_state in (game.GameState.canPlay, game.GameState.lost):
            (coord, what_was_at_coord) = self.game.get_last_opponent_move()
            if coord:
                self.out['coordhit'] = str(coord)
            if what_was_at_coord:
                self.out['shiptypehit'] = what_was_at_coord.name
                self.out['shippartsleft'] = str(what_was_at_coord.fields_intact)
        self.write_xml(**self.out)


class PutCoordHandler(GameDynamicDataHandler):
    def get(self):
        logger.debug("PutCoord: %s", self.request.query)
        coord = game.Coord(*self.get_argument('coord'))
        shot_result = self.game.shoot_field(coord)
        self.out['shot'] = shot_result.name
        self.write_xml(**self.out)


class QuitAppHandler(DynamicDataHandler):
    def post(self):
        logger.debug("QuitGame: %s", self.request.query)
        game = GAMES.get(self.token)
        if game:
            opponent_token = game.get_opponent()
            del GAMES[self.token]
            del GAMES[opponent_token]
        self.write_xml(**self.out)


class LogHandler(XMLHandler):
    def get(self):
        logger.info("GET-LOG: %s", self.request.query)
        self.write_xml()

    def post(self):
        logger.info("POST-LOG: %s", self.request.body)
        self.write_xml()

class GetShipCoordsHandler(GameDynamicDataHandler):
    def get(self):
        self.out['owncoords'] = ' '.join(str(coord) for coord in self.game.get_own_ship_coords())
        self.out['opponentcoords'] = ' '.join(str(coord) for coord in self.game.get_opponent_ship_coords())
        self.write_xml(**self.out)

class WebViewHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("webview.html", token=SessionTokenToGame.generate_token(),
                    gridsize=game.Game.GRID_SIZE)


if __name__ == "__main__":
    args = docopt(__doc__)
    loop = tornado.ioloop.IOLoop.current()
    logger = logging.getLogger('battleships-web')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.FileHandler("battleships.log"))

    # debug=True will reload the application if a file is changed,
    # and disable the template cache, among other things
    app = tornado.web.Application([
                                      (r"/dialog", DialogHandler),
                                      (r"/waitforgame", WaitForGameHandler),
                                      (r"/placeship", PlaceShipHandler),
                                      (r"/waitforturn", WaitForTurnHandler),
                                      (r"/putcoord", PutCoordHandler),
                                      (r"/getshipcoords", GetShipCoordsHandler),
                                      (r"/quitapp", QuitAppHandler),
                                      (r"/log", LogHandler),
                                      (r"/webview", WebViewHandler),
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
