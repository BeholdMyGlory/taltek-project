
import re
import sys
import urllib.parse

if __name__ == '__main__':
    with open(sys.argv[1]) as f:
        last_player = None
        for line in f:
            match = re.match(r"^\d+\.\d+:INFO:battleships-web:main:POST-LOG: b'(.*)'$", line)
            if match:
                query = urllib.parse.parse_qs(match.group(1))
                if "feedback" in query:
                    print(query['feedback'][0])
                    human_player = query['token'][0]

            match = re.match(r"^(\d+\.\d+):DEBUG:battleships-web:main:PutCoord: (.*)$", line)
            if match:
                last_player = urllib.parse.parse_qs(match.group(2))['token'][0]

            match = re.match(r"^(\d+\.\d+):DEBUG:battleships-web:main:Response: .*canPlay.*$", line)
            if match:
                this_time = float(match.group(1))
                if last_player is not None and last_player == human_player:
                    print(last_player, "took", this_time - last_time)
                last_time = this_time
