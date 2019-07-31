import re, io, copy, os, sys, argparse, json, pdb, jsonlines, datetime, calendar
from tqdm import tqdm
from collections import Counter
from pprint import pprint
import pandas as pd
sys.path.insert(0, '../purification/')
from domain_knowledge import Domain_Knowledge
knowledge_container = Domain_Knowledge()
DELIM = "￨"
LOWER = False
all_games = pd.read_pickle("/mnt/bhd/hongmin/nba/crawl/all_games.pkl")

# ---------------------- #
# --- add game arena --- #
# ---------------------- #
def _get_arena_old_new(hometeam, year):
    if (hometeam == 'Hawks' and year <= 2018) \
        or (hometeam == 'Jazz' and year <= 2015) \
        or (hometeam == 'Kings' and year <= 2016) \
        or (hometeam == 'Pistons' and year <= 2017) \
        or (hometeam == 'Raptors' and year <= 2018) \
        or (hometeam == 'Suns' and year <= 2015) \
        or (hometeam == 'Wizards' and year <= 2017) :
        return 1
    return 0


def get_arena(records, summary, tbl):
    this_arena = None
    first_sent = summary.split(' . ')[0].strip()
    arenas_dict = dict.fromkeys(knowledge_container.arenas)
    team2alias = knowledge_container.team2alias
    team2arenas = knowledge_container.team2arenas
    year = int(tbl['day'].split('_')[-1])

    for word in first_sent.split():
        if word in arenas_dict:
            this_arena = word
            break

    # get home/away teams
    hometeam, awayteam = None, None
    for r in records:
        cell, ent_type, rcd_type, ha = r.strip().split(DELIM)
        if ha == 'HOME' and rcd_type.startswith('TEAM'):
            hometeam = ent_type
        if ha == 'AWAY' and rcd_type.startswith('TEAM'):
            awayteam = ent_type
        if hometeam and awayteam:
            break

    # if not mentioned in the 1st sentence, look it up instead
    if this_arena is None:
        this_arena = team2arenas[hometeam][_get_arena_old_new(hometeam, year)]

    home_arena_rcd = DELIM.join([this_arena, hometeam, 'TEAM-ARENA', 'HOME'])
    # dummy arena record for away team to keep it balanced, not necessary
    away_arena_rcd = DELIM.join(['N/A', awayteam, 'TEAM-ARENA', 'AWAY'])
    home_alias_rcd = DELIM.join([team2alias.get(hometeam, 'N/A'), hometeam, 'TEAM-ALIAS', 'HOME'])
    away_alias_rcd = DELIM.join([team2alias.get(awayteam, 'N/A'), awayteam, 'TEAM-ALIAS', 'AWAY'])

    output = copy.deepcopy(records)
    output.extend([home_arena_rcd, away_arena_rcd, home_alias_rcd, away_alias_rcd])
    return output


# ------------------------------------- #
# --- add the following PTS entries --- #
# ------------------------------------- #
"""
    1. [done] half-time PTS
    2. [done] 1-3 quarter PTS
    3. [done] 2-4 quarter PTS
    NOTE: the following are +- numbers, need a feature to indicate sign
    4. [done] half-time PTS diff
    5. [done] per quarter PTS diff
    6. [done] 1-3 quarter diff
    7. [done] 2-4 quarter diff
"""

num2ord = {
    1: 'FIRST',
    2: 'SECOND',
    3: 'THIRD',
    4: 'FOURTH',
}

def game_points(records):
    team_points = {}
    team_names = {}
    for r in records:
        cell, ent_type, rcd_type, ha = r.strip().split(DELIM)
        if rcd_type.startswith('TEAM-PTS_QTR'):
            quarter = int(rcd_type.strip('TEAM-PTS_QTR'))
            if not ha in team_points:
                team_points[ha] = {quarter: int(cell)}
            else:
                team_points[ha].update({quarter: int(cell)})

        if rcd_type.startswith('TEAM') and ha == 'HOME':
            team_names['HOME'] = ent_type
        if rcd_type.startswith('TEAM') and ha == 'AWAY':
            team_names['AWAY'] = ent_type

            #     pprint(team_points)
    combo_pts = {'HOME': {}, 'AWAY': {}, 'quarter_diffs': {}, 'half_diff_1st': 0, 'half_diff_2nd': 0}
    for team in ['HOME', 'AWAY']:
        combo_pts[team]['1st_half'] = team_points[team][1] + team_points[team][2]
        combo_pts[team]['2nd_half'] = team_points[team][3] + team_points[team][4]
        combo_pts[team]['first_three_quarter'] = combo_pts[team]['1st_half'] + team_points[team][3]
        combo_pts[team]['last_three_quarter'] = team_points[team][2] + combo_pts[team]['2nd_half']
    combo_pts['1st_half_diff'] = combo_pts['HOME']['1st_half'] - combo_pts['AWAY']['1st_half']
    combo_pts['2nd_half_diff'] = combo_pts['HOME']['2nd_half'] - combo_pts['AWAY']['2nd_half']
    combo_pts['total_diff'] = combo_pts['HOME']['1st_half'] + combo_pts['HOME']['2nd_half'] - (
    combo_pts['AWAY']['1st_half'] + combo_pts['AWAY']['2nd_half'])
    for i in range(1, 5):
        combo_pts['quarter_diffs'][i] = team_points['HOME'][i] - team_points['AWAY'][i]
    # pprint(combo_pts)

    for team in ['HOME', 'AWAY']:
        first_half_pts = DELIM.join([str(combo_pts[team]['1st_half']), team_names[team], 'TEAM-PTS_HALF-FIRST', team])
        second_half_pts = DELIM.join([str(combo_pts[team]['2nd_half']), team_names[team], 'TEAM-PTS_HALF-SECOND', team])
        quarter_pts_1to3 = DELIM.join(
            [str(combo_pts[team]['first_three_quarter']), team_names[team], 'TEAM-PTS_QTR-1to3', team])
        quarter_pts_2to4 = DELIM.join(
            [str(combo_pts[team]['last_three_quarter']), team_names[team], 'TEAM-PTS_QTR-2to4', team])
        records.extend([first_half_pts, second_half_pts, quarter_pts_1to3, quarter_pts_2to4])

    first_half_diff = combo_pts['1st_half_diff']
    team = 'HOME' if first_half_diff > 0 else 'AWAY'
    first_half_diff = DELIM.join([str(abs(first_half_diff)), team_names[team], 'TEAM-PTS_HALF_DIFF-FIRST', team])
    the_other_team = 'HOME' if team == 'AWAY' else 'AWAY'
    temp = DELIM.join(['N/A', team_names[the_other_team], 'TEAM-PTS_HALF_DIFF-FIRST', the_other_team])
    records.extend([first_half_diff, temp])

    second_half_diff = combo_pts['2nd_half_diff']
    team = 'HOME' if second_half_diff > 0 else 'AWAY'
    second_half_diff = DELIM.join([str(abs(second_half_diff)), team_names[team], 'TEAM-PTS_HALF_DIFF-SECOND', team])
    the_other_team = 'HOME' if team == 'AWAY' else 'AWAY'
    temp = DELIM.join(['N/A', team_names[the_other_team], 'TEAM-PTS_HALF_DIFF-SECOND', the_other_team])
    records.extend([second_half_diff, temp])

    total_diff = combo_pts['total_diff']
    team = 'HOME' if total_diff > 0 else 'AWAY'
    total_diff = DELIM.join([str(abs(total_diff)), team_names[team], 'TEAM-PTS_TOTAL_DIFF', team])
    the_other_team = 'HOME' if team == 'AWAY' else 'AWAY'
    temp = DELIM.join(['N/A', team_names[the_other_team], 'TEAM-PTS_TOTAL_DIFF', the_other_team])
    records.extend([total_diff, temp])

    for i in range(1, 5):
        quarter_diff = combo_pts['quarter_diffs'][i]
        team = 'HOME' if quarter_diff > 0 else 'AWAY'
        quarter_diff = DELIM.join([str(abs(quarter_diff)), team_names[team], 'TEAM-PTS_QTR_DIFF-{}'.format(num2ord[i]), team])
        the_other_team = 'HOME' if team == 'AWAY' else 'AWAY'
        temp = DELIM.join(['N/A', team_names[the_other_team], 'TEAM-PTS_QTR_DIFF-{}'.format(num2ord[i]), the_other_team])
        records.extend([quarter_diff, temp])

    return records


# -------------------------------------------------------------------- #
# --- add the following entries calculated by summing player stats --- #
# -------------------------------------------------------------------- #
"""
    1. [done][START=F,C,G] Starting line-up points
    2. [done][START=N/A] Bench points
    3. [done][FGM and FGA] field-goal attempt and made
    4. [done][FG3M and FG3A] 3pt attempt and made
    5. [done][FTM and FTA] free-throw attempt and made
    6. [done][OREB] offensive rebound
    7. [done][DREB] defensive rebound
    8. [done][STL] steals
    9. [done][BLK] blocks
"""
# There is a more efficient way but I'll leave it as it is for now


class feature(object):
    def __init__(self, team):
        self.team = team
        self.total_sum = 0
        self.start_sum = 0
        self.bench_sum = 0
        self.fg = {'attempt': 0, 'made': 0}
        self.fg_3pt = {'attempt': 0, 'made': 0}
        self.ft = {'attempt': 0, 'made': 0}
        self.off_reb = 0
        self.def_reb = 0
        self.steals = 0
        self.blocks = 0


def get_sums(records, idx):
    team_names = {}

    for r in records:
        cell, ent_type, rcd_type, ha = r.strip().split(DELIM)

        if rcd_type.startswith('TEAM') and ha == 'HOME':
            team_names['HOME'] = ent_type
        if rcd_type.startswith('TEAM') and ha == 'AWAY':
            team_names['AWAY'] = ent_type

    stats = {'HOME': feature(team_names['HOME']), 'AWAY': feature(team_names['AWAY'])}

    player2pts = {'HOME': {}, 'AWAY': {}}

    for r in records:
        cell, ent_type, rcd_type, ha = r.strip().split(DELIM)

        if rcd_type == 'TEAM-PTS':
            stats[ha].total_sum = int(cell)

        if not ent_type in player2pts[ha] and not rcd_type.startswith('TEAM') and not rcd_type.startswith('GAME'):
            player2pts[ha][ent_type] = {'pts': 0, 'start': None}

        if rcd_type == 'PTS':
            if cell != 'N/A':
                player2pts[ha][ent_type]['pts'] = int(cell)
        if rcd_type == 'START_POSITION':
            player2pts[ha][ent_type]['start'] = cell

        if cell != 'N/A':
            if cell.isdigit():
                cell = int(cell)
            if rcd_type == 'FGA':
                stats[ha].fg['attempt'] += cell
            elif rcd_type == 'FGM':
                stats[ha].fg['made'] += cell
            elif rcd_type == 'FG3A':
                stats[ha].fg_3pt['attempt'] += cell
            elif rcd_type == 'FG3M':
                stats[ha].fg_3pt['made'] += cell
            elif rcd_type == 'FTA':
                stats[ha].ft['attempt'] += cell
            elif rcd_type == 'FTM':
                stats[ha].ft['made'] += cell
            elif rcd_type == 'OREB':
                stats[ha].off_reb += cell
            elif rcd_type == 'DREB':
                stats[ha].def_reb += cell
            elif rcd_type == 'STL':
                stats[ha].steals += cell
            elif rcd_type == 'BLK':
                stats[ha].blocks += cell

    for team in ['HOME', 'AWAY']:
        team_pts = player2pts[team]
        start_pts = [x['pts'] for x in team_pts.values() if x['start'] != 'N/A']
        if not len(start_pts) == 5:
            print("missing one start")
        stats[team].start_sum = sum(start_pts)
        bench_pts = [x['pts'] for x in team_pts.values() if x['start'] == 'N/A']
        stats[team].bench_sum = sum(bench_pts)
        try:
            assert stats[team].start_sum + stats[team].bench_sum == stats[team].total_sum
        except AssertionError:
            print("\nteam_names : {}".format(team_names))
            mysum = stats[team].start_sum + stats[team].bench_sum
            theirsum = stats[team].total_sum
            if abs(mysum-theirsum) == 1:
                print('differs by 1 at line {}'.format(idx))
            else:
                print('Stats error at line {}'.format(idx))
                print("records:\n{}".format(records))
                print("start_pts = {}".format(start_pts))
                print("bench_pts = {}".format(bench_pts))
                print(stats[team].start_sum)
                print(stats[team].bench_sum)
                print(stats[team].total_sum)
                pdb.set_trace()

    for team in ['HOME', 'AWAY']:
        #         pprint(vars(stats[team]))
        start_sum = DELIM.join([str(stats[team].start_sum), stats[team].team, 'TEAM-PTS_SUM-START', team])
        bench_sum = DELIM.join([str(stats[team].bench_sum), stats[team].team, 'TEAM-PTS_SUM-BENCH', team])

        fg_att = DELIM.join([str(stats[team].fg['attempt']), stats[team].team, 'TEAM-FGA', team])
        fg_md = DELIM.join([str(stats[team].fg['made']), stats[team].team, 'TEAM-FGM', team])

        ft = DELIM.join([str(stats[team].ft['attempt']), stats[team].team, 'TEAM-FTA', team])
        ft_md = DELIM.join([str(stats[team].ft['made']), stats[team].team, 'TEAM-FTM', team])

        fg_3pt = DELIM.join([str(stats[team].fg_3pt['attempt']), stats[team].team, 'TEAM-FG3A', team])
        fg_3pt_md = DELIM.join([str(stats[team].fg_3pt['made']), stats[team].team, 'TEAM-FG3M', team])

        off_reb = DELIM.join([str(stats[team].off_reb), stats[team].team, 'TEAM-OREB', team])
        def_reb = DELIM.join([str(stats[team].def_reb), stats[team].team, 'TEAM-DREB', team])

        steals = DELIM.join([str(stats[team].steals), stats[team].team, 'TEAM-STL', team])
        blocks = DELIM.join([str(stats[team].blocks), stats[team].team, 'TEAM-BLK', team])

        records.extend(
            [start_sum, bench_sum, fg_att, fg_md, ft, ft_md, fg_3pt, fg_3pt_md, off_reb, def_reb, steals, blocks])

    return records


'''
This part augment the input table with extra numeric features: number type and/or if the player has double double
# ----------------------- #
# --- Add cardinality --- #
# ----------------------- #
"""
    Player features:
    1. [done]player vs team feature 
    2. [done]start vs bench: simply convert to START VS BENCH ???
    3. [done]single/double/triple digits/percentages/others
    3. [done]double-double/ triple-double
"""
def issingle(x):
    assert isinstance(x, int) and x >= 0
    return x < 10


def isdouble(x):
    assert isinstance(x, int) and x >= 0
    return x >= 10 and x < 100


def istriple(x):
    assert isinstance(x, int) and x >= 0
    return x >= 100


def check_double_triple(player_stats):
    stats = player_stats.values()
    is_double = [int(isdouble(x)) for x in stats if isinstance(x, int)]
    cnt = sum(is_double)
    if cnt < 2:
        return 'N/A'
    elif cnt == 2:
        return 'double_double'
    elif cnt == 3:
        return 'triple_double'


def player_features(records, add_dd=False):
    output = []

    for r in records:

        cell, ent_type, rcd_type, ha = r.strip().split(DELIM)

        # if rcd_type.startswith('TEAM') or rcd_type.startswith('GAME'):
        #     t_or_p = 'TEAM'
        # else:
        #     t_or_p = 'PLAYER'

        if cell.isdigit():
            cell = int(cell)
            if 'PCT' in rcd_type:
                cell_dtype = 'PCT'
            elif issingle(cell):
                cell_dtype = 'SINGLE'
            elif isdouble(cell):
                cell_dtype = 'DOUBLE'
            elif istriple(cell):
                cell_dtype = 'TRIPLE'
            else:
                raise ValueError('record {} misformated'.format(r))

        else:
            cell_dtype = 'OTHERS'

            if rcd_type == 'START_POSITION':
                # change START_POSITION to START and BENCH
                if cell == 'N/A':
                    cell = 'BENCH'
                else:
                    cell = 'START'

        rcd_ext = [cell, ent_type, rcd_type, ha, cell_dtype]
        output.append(DELIM.join([str(x) for x in rcd_ext]))

    if add_dd:
        player2pts = {}
        for r in records:
            cell, ent_type, rcd_type, ha = r.strip().split(DELIM)

            if rcd_type.startswith('TEAM') or rcd_type.startswith('GAME'):
                continue
            if not cell.isdigit():
                continue
            else:
                cell = int(cell)

            if not ent_type in player2pts:
                player2pts[ent_type] = {'pts': 0, 'reb': 0, 'ast': 0, 'stl': 0, 'blk': 0, 'ha': ha}

            if rcd_type == 'PTS':
                player2pts[ent_type]['pts'] = cell
            elif rcd_type == 'REB':
                player2pts[ent_type]['reb'] = cell
            elif rcd_type == 'AST':
                player2pts[ent_type]['ast'] = cell
            elif rcd_type == 'STL':
                player2pts[ent_type]['stl'] = cell
            elif rcd_type == 'BLK':
                player2pts[ent_type]['blk'] = cell
                #     pprint(player2pts)

        for player, stats in player2pts.items():
            cell = check_double_triple(stats)
            double_feat = [cell, player, 'DOUBLE_TRIPLE', stats['ha'], 'OTHERS']
    
            output.append(DELIM.join([str(x) for x in double_feat]))

    return output
'''


def _search_game(gameday, name, city):
    team = ' '.join([city, name])
    today = gameday
    for i in range(5):
        # increment day by 1
        today += datetime.timedelta(days=1)
        month, day, year = today.month, today.day, today.year
        datestr = "20%02d-%02d-%02d" % (year, month, day)
        candidate = all_games[(all_games.GAME_DATE == datestr) & (all_games.TEAM_NAME.isin([team]))]

        # candidate game: the most recent game with the team name
        if not candidate.empty:
            # get the opponent team
            game_id = candidate.GAME_ID.values[0]
            next = all_games[(all_games.GAME_ID == game_id) & (~all_games.TEAM_NAME.isin([team]))]
            next_full = next.TEAM_NAME.values[0]

            # the only two-word team
            if 'Trail Blazers' in next_full:
                next_name = 'Trail Blazers'
            else:
                next_name = next_full.split()[-1].strip()
            next_city = next_full.replace(next_name, '').strip()

            # get if this team is home/away in the next game by checking if 'vs' is in MATCHUP, '@' for away team
            next_ha = 'home' if 'vs' in next['MATCHUP'].values[0] else 'away'
            # daystr = "%02d_%02d_%02d" % (month, day, year)
            # key = "{}-{}-{}".format(daystr, name, next_name)
            # try:
            #     next_ha = homeaway_lkt[key][name]
            # except:
            #     next_ha = 'N/A'
            # pdb.set_trace()

            day_of_week = calendar.day_name[today.weekday()]

            return '_'.join(next_name.strip().split()), '_'.join(next_city.strip().split()), day_of_week, next_ha

    return 'N/A', 'N/A', 'N/A', 'N/A'


no_next = {'home':0, 'away':0, 'ha':0}
no_next_summaries = []
def get_next_games(records, tbl):
    global no_next
    month, day, year = tbl['day'].split('_')
    gameday = datetime.date(int(year), int(month), int(day))

    for identifier in ['home', 'vis']:
        this_name = tbl['{}_name'.format(identifier)]
        this_city = tbl['{}_city'.format(identifier)]

        next_name, next_city, next_day, next_ha = _search_game(gameday, this_name, this_city)

        prefix = 'away' if identifier == 'vis' else 'home'
        if next_name == 'N/A':
            no_next[prefix] += 1
            no_next_summaries.append(' '.join(tbl['summary']))
        if next_ha == 'N/A':
            no_next['ha'] += 1

        for entry, suffix in zip([next_name, next_city, next_day, next_ha], ['NAME', 'CITY', 'DAY', 'HA']):
            records.append(DELIM.join([entry,
                                       '_'.join(this_name.split()),
                                       'TEAM-NEXT_{}'.format(suffix),
                                       prefix.upper()]))

    return records


def _print_additional_rcdtypes(old, new):
    print(len(old))
    print(len(new))
    old_keys = [i.split(DELIM)[-2] for i in old]
    new_keys = [i.split(DELIM)[-2] for i in new]
    print(sorted(list(set(new_keys) - set(old_keys))))
    pdb.set_trace()


def _update_linescores(records_feat, tbl):
    line_keys_ext = sorted(knowledge_container.line_keys_ext)

    home = {x.split(DELIM)[2]: x.split(DELIM)[0]
            for x in records_feat if x.split(DELIM)[-1] == 'HOME' and x.split(DELIM)[2].startswith('TEAM')}
    away = {x.split(DELIM)[2]: x.split(DELIM)[0]
            for x in records_feat if x.split(DELIM)[-1] == 'AWAY' and x.split(DELIM)[2].startswith('TEAM')}
    out = copy.deepcopy(tbl)
    out['home_line'].update(home)
    out['vis_line'].update(away)

    assert sorted(list(out['home_line'].keys())) == line_keys_ext
    assert sorted(list(out['vis_line'].keys())) == line_keys_ext

    return out


def main(js, src, tgt, src_out, json_out):

    with jsonlines.open(js, 'r') as fin_js, \
            io.open(src, 'r', encoding='utf-8') as fin_src, \
            io.open(tgt, 'r', encoding='utf-8') as fin_tgt, \
            io.open(src_out, 'w+', encoding='utf-8') as fout, \
            jsonlines.open(json_out, 'w') as fout_js:

        targets = fin_tgt.read()
        targets = targets.strip().split('\n')

        inputs = fin_src.read()
        inputs = inputs.strip().split('\n')

        tables = [i for i in fin_js.iter(type=dict, skip_invalid=True)]
        print(len(targets))
        assert len(targets) == len(inputs) == len(tables)

        if LOWER:
            inputs = [x.lower() for x in inputs]
            targets = [x.lower() for x in targets]

        output = []

        for idx, (tbl, inp, summary) in tqdm(enumerate(zip(tables, inputs, targets))):
            records = inp.strip().split()
            # print(len(records))
            # (1) game arena
            records_feat = get_arena(records, summary, tbl)

            # (2) Point features
            records_feat = game_points(records_feat)

            # (3) Sum features
            records_feat = get_sums(records_feat, idx)

            # (4) Player features
            # records_feat = player_features(records_feat)

            # (5) Team schedules
            records_feat = get_next_games(records_feat, tbl)

            output.append(' '.join(records_feat))
            # print(len(records_feat))
            # _print_additional_rcdtypes(records, records_feat)
            tbl_out = _update_linescores(records_feat, tbl)
            # print(tbl_out['home_line'].keys())
            fout_js.write(tbl_out)

        pprint(no_next)
        # pdb.set_trace()

        for s in output:
            fout.write("{}\n".format(s))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--dir', type=str, default='../new_dataset/',
                        help='directory of src/tgt_train/valid/test.txt files')
    args = parser.parse_args()

    # homeaway_lkt = _get_homeaway_lkt()

    for DATASET in ['train', 'valid', 'test']:

        print("Enrich dataset for {}".format(DATASET))

        INP_DIR = os.path.join(args.dir, "new_clean/{}".format(DATASET))
        OUT_DIR = os.path.join(args.dir, "new_extend/{}".format(DATASET))
        os.makedirs(OUT_DIR, exist_ok=True)

        js = os.path.join("../new_dataset/new_jsonl", "%s.jsonl" % DATASET)

        input_files = [
            "src_%s.norm.tk.txt" % DATASET,
            "tgt_%s.norm.mwe.txt" % DATASET,
        ]

        src, tgt = [os.path.join(INP_DIR, f) for f in input_files]

        output_files = [
            "src_%s.norm.ext.txt" % DATASET,
            "%s.ext.jsonl" % DATASET,
        ]

        src_out, json_out = [os.path.join(OUT_DIR, f) for f in output_files]

        main(js, src, tgt, src_out, json_out)
