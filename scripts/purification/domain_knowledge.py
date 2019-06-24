from nba_api.stats.static.players import players
import pandas as pd

class Domain_Knowledge:

    def __init__(self):

        self.all_nba_teams = ['Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets',
                             'Chicago Bulls', 'Cleveland Cavaliers', 'Detroit Pistons', 'Indiana Pacers',
                             'Miami Heat', 'Milwaukee Bucks', 'New York Knicks', 'Orlando Magic',
                             'Philadelphia 76ers', 'Toronto Raptors', 'Washington Wizards', 'Dallas Mavericks',
                             'Denver Nuggets', 'Golden State Warriors', 'Houston Rockets', 'Los Angeles Clippers',
                             'Los Angeles Lakers', 'Memphis Grizzlies', 'Minnesota Timberwolves', 'New Orleans Pelicans',
                             'Oklahoma City Thunder', 'Phoenix Suns', 'Portland Trail Blazers', 'Sacramento Kings',
                             'San Antonio Spurs', 'Utah Jazz']

        self.two_word_cities = ['New York', 'Golden State', 'Los Angeles', 'New Orleans', 'Oklahoma City', 'San Antonio']

        self.two_word_teams = ['Trail Blazers']

        self.team2alias = {
            '76ers': 'Sixers',
            'Thunder': 'OKC',
            'Cavaliers': 'Cavs',
            'Mavericks': 'Mavs',
            'Timberwolves': 'Wolves'
        }

        self.alias2team = {
            'Cavs': 'Cavaliers',
            'Mavs': 'Mavericks',
            'OKC': 'Thunder',
            'Sixers': '76ers',
            'Wolves': 'Timberwolves'
        }

        self.alias2player = {
            'The_Greek_Freak': 'Giannis_Antetokounmpo',
            'Melo': 'Carmelo_Anthony',
            'KD': 'Kevin_Durant',

        }
        self.prons = dict.fromkeys(
            ["he", "He", "him", "Him", "his", "His", "they", "They", "them", "Them", "their", "Their", "team"], True)

        self.singular_prons = dict.fromkeys(["he", "He", "him", "Him", "his", "His"], True)

        self.plural_prons = dict.fromkeys(["they", "They", "them", "Them", "their", "Their"], True)

        self.all_nba_players = pd.DataFrame(data=players)

        self.player_lookup = dict.fromkeys([x[3] for x in players], True)




