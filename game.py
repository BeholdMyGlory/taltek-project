import collections
from copy import copy
from enum import Enum
import functools
from types import MethodType

Orientation = Enum('Orientation', 'horizontal vertical')
GameState = Enum('GameState', 'won lost canPlay wait')
ShotResult = Enum('ShotResult', 'hit miss sunk alreadyShot')


class Ship(object):
    def __init__(self, name, size, fields_intact=None):
        self.name = name
        self.size = size
        self.fields_intact = fields_intact or size

    def __repr__(self):
        return 'Ship(%s, %s, %s)' % (self.name, self.size, self.fields_intact)


class GameProxy(object):
    """
    Convenience proxy for accessing Game instances in the perspective of one player.
    All methods in Game take the session token of the current player as parameter.
    This object enables one to omit this parameter.
    """

    def __init__(self, game, player_token):
        """
        :param game: game to build the proxy for
        :param player_token: the player to create the proxy for.
        """
        self.__player_token = player_token
        self.__game = game

    def __getattr__(self, item):
        attr = getattr(self.__game, item)

        if isinstance(attr, MethodType):
            return functools.partial(attr, self.__player_token)
        else:
            return attr


class Game(object):
    """ Represents the game logic  """

    GRID_SIZE = 6
    """
    Size of the grid/field
    """

    AVAILABLE_SHIPS = [
        (Ship('Battleship', 4), 1),
        (Ship('Destroyer', 3), 1),
        (Ship('Submarine', 2), 2),
    ]
    """
    Initial list of number of ships available for each type as list of tuples (ship, count)
    """

    def __init__(self, p1_token, p2_token):
        """
        :param p1_token: unique token/identifier for player 1
        :param p2_token: unique token/identifier for player 2
        """
        self.p1_token = p1_token
        self.p2_token = p2_token

        p1_ships = Game.generate_ships_to_place()
        p2_ships = Game.generate_ships_to_place()
        self.whose_turn = self.p1_token

        self.opponent = {
            p1_token: p2_token,
            p2_token: p1_token,
        }
        self.ships_to_place = {
            p1_token: collections.deque(p1_ships),
            p2_token: collections.deque(p2_ships),
        }
        self.own_ships = {
            p1_token: p1_ships,
            p2_token: p2_ships,
        }
        self.grids = {
            p1_token: Grid(Game.GRID_SIZE),
            p2_token: Grid(Game.GRID_SIZE),
        }

        self.moves_done = {
            p1_token: [],
            p2_token: [],
        }

        self.whose_turn = self.p1_token

    def get_game_state(self, player_token):
        """
        :param player_token: unique player token
        :return: GameState
        """
        all_ships_placed = not self.ships_to_place[self.p1_token] and not self.ships_to_place[self.p2_token]

        state = GameState.wait
        if not sum((ship.fields_intact for ship in self.own_ships[player_token])):
            state = GameState.lost
        elif not sum((ship.fields_intact for ship in self.own_ships[self.opponent[player_token]])):
            state = GameState.won
        elif all_ships_placed and self.is_players_turn(player_token):
            state = GameState.canPlay

        return state

    def is_players_turn(self, player_token):
        """
        :param player_token: unique player token
        :return: true if it is the players turn; false if it is not
        """
        return self.whose_turn == player_token

    def get_ship_to_place(self, player_token):
        """
        Returns instance of the ship that is to be placed next by the given player
        :param player_token: unique player token
        :return: instance of Ship, None if all ships have been placed
        """
        if self.ships_to_place[player_token]:
            return self.ships_to_place[player_token][0]
        else:
            return None

    def place_ship(self, player_token, top_left_coord, orientation):
        """
        Places the *current* ship (returned by get_ship_to_place)
        :param player_token: unique player token
        :param top_left_coord: top left Coord of the ship on the field
        :param orientation: Orientation of the ship on the field, e.g. Orientation.vertical
        :raises OccupiedFieldsException if fields are blocked by other ships
        :raises IndexError if coord out of range
        """

        ship_to_place = self.get_ship_to_place(player_token)
        grid = self.grids[player_token]
        if orientation is Orientation.horizontal:
            coord_range_x = range(top_left_coord.x, top_left_coord.x + ship_to_place.size)
            coords = [Coord(x, top_left_coord.y) for x in coord_range_x]
        else:
            coord_range_y = range(top_left_coord.y, top_left_coord.y + ship_to_place.size)
            coords = [Coord(top_left_coord.x, y) for y in coord_range_y]

        grid.put(ship_to_place, coords)
        self.ships_to_place[player_token].popleft()

    def shoot_field(self, player_token, opponent_field_coord):
        """
        shoots a field on the opponent's given by opponent_field_coord.
        :param player_token: player_token
        :param opponent_field_coord: the coordinate to shoot on the opponent's field
        :return: a ShotResult
        """
        if self.get_game_state(player_token) != GameState.canPlay:
            raise Exception('Not your turn')

        opponent = self.opponent[player_token]
        opponent_field = self.grids[opponent]
        what_is_at_coord = opponent_field[opponent_field_coord]
        shot_result = None
        if what_is_at_coord is None:
            shot_result = ShotResult.miss
            opponent_field[opponent_field_coord] = Grid.FIELD_SHOT
        elif what_is_at_coord is Grid.FIELD_SHOT:
            shot_result = ShotResult.alreadyShot
        else:
            shot_result = ShotResult.hit
            what_is_at_coord.fields_intact -= 1
            opponent_field[opponent_field_coord] = Grid.FIELD_SHOT
            if not what_is_at_coord.fields_intact:
                shot_result = ShotResult.sunk
        if shot_result != ShotResult.alreadyShot:
            self.moves_done[player_token].append((opponent_field_coord, what_is_at_coord))
            self.whose_turn = opponent

        return shot_result

    def get_last_opponent_move(self, player_token):
        opponent = self.opponent[player_token]
        if self.moves_done[opponent]:
            move_done = self.moves_done[opponent][-1]
            return move_done
        return None, None

    @classmethod
    def generate_ships_to_place(cls):
        ships_to_place = collections.deque()
        for (ship, number) in cls.AVAILABLE_SHIPS:
            for _ in range(number):
                # copying here, because we need to be able to detect that an /individual/ ship has sunk
                ships_to_place.append(copy(ship))
        return ships_to_place


class Coord(object):
    def __init__(self, x, y):
        """
        Accepts coordinates either as ('A', 1') or (*'A1') or (0,0) or with kwargs x and y
        """

        if isinstance(x, str):
            self.x = ord(x) - ord('A')
            self.y = int(y) - 1
        else:
            self.x = x
            self.y = y

    def __str__(self):
        x_str = chr(self.x + ord('A'))
        y_str = str(self.y + 1)
        return x_str + y_str

    def __repr__(self):
        return 'Coord(*%s)' % str(self)


class OccupiedFieldsException(Exception):
    def __init__(self, message=None, occupied_fields=None):
        """
        :param message: exception message
        :param occupied_fields: list of Coord-objects denoting the fields that are occupied
        """
        super(Exception, self).__init__(message)
        self.occupied_fields = occupied_fields


class Grid(object):
    FIELD_SHOT = "SHOT"

    def __init__(self, grid_size):
        self.field = [[None for _ in range(grid_size)] for _ in range(grid_size)]

    def __getitem__(self, coord):
        return self.field[coord.x][coord.y]

    def __setitem__(self, coord, value):
        self.field[coord.x][coord.y] = value

    def put(self, ship, coords):
        """
        :param ship: instance of Ship (note to properly clone objects, when placing two ships of the same type)
        :param coords: list of Coords
        :raises IndexError if ship is partially or completely out of grid
        :raises OccupiedFieldsException if field is not empty
        :return: None
        """

        occupied_fields = [coord for coord in coords if self[coord] is not None]
        if occupied_fields:
            raise OccupiedFieldsException(occupied_fields=occupied_fields)

        for coord in coords:
            self[coord] = ship
        print('Put %s at %s' % (str(ship), coords))