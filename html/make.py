import json, pandas, argparse, os, pdb, io, copy, jsonlines
from tqdm import tqdm

def print_table(f, table, seen):
    f.write("<table border=1 class=\"table table-hover table-striped table-bordered\">")
    f.write("<tr><th></th>")
    for col in table.columns:
        f.write("<th>%s</th>"%(col))
    f.write("</tr>")
    for row in table.iterrows():
        row_id = row[0].replace(" ", "_").replace("'", "\\'").replace(".", "")
        f.write("<tr class=\"off_row\" id=\"%s\"> <th>%s</th>"%(row_id, row[0]))
        for k, r in enumerate(row[1]):
            key = "%s_%s_%s" %(row_id, table.columns[k], str(r).replace("'", "\\'") )
            key = key.replace(".", "")
            f.write("<td id=\"%s\" onclick=\"tab_select('%s')\">%s</td>"%(key, key, r))
            seen.setdefault(str(r), []).append([key, row_id])
        f.write("</tr>")
    f.write("</table>")


def main(infile, outdir):
    # with io.open(infile, 'r', encoding='utf-8') as fin:
    #     data = json.load(fin)

    data = []
    with jsonlines.open(infile, 'r') as fin:
        for x in fin.iter(type=dict):
            data.append(x)


    order = ["FIRST_NAME", "SECOND_NAME", "H/V", 'POS', 'MIN', 'PTS', 'REB', 'AST', 'BLK', 'TO', 'PF', 'STL', 'DREB', 'OREB', 'FGM',  'FGA', 'FG_PCT', 'FTM', 'FTA','FT_PCT','FG3M', 'FG3A','FG3_PCT']
    # order2 = ["NAME", "CITY", "WINS", "LOSSES", "PTS", "QTR1", "QTR2", "QTR3", "QTR4", "AST", "REB", "TOV", "FG_PCT", "FT_PCT", "FG3_PCT"]
    order2 = ['NAME', 'CITY', 'ALIAS', 'ARENA', 'WINS', 'LOSSES', 'FGA', 'FGM', 'FG_PCT', 'FG3A', 'FG3M', 'FG3_PCT', 'FTA', 'FTM', 'FT_PCT', 'REB', 'OREB', 'DREB', 'AST', 'BLK', 'STL', 'TOV', 'PTS', 'PTS_SUM-BENCH', 'PTS_SUM-START', 'PTS_TOTAL_DIFF', 'PTS_HALF-FIRST', 'PTS_HALF-SECOND', 'PTS_HALF_DIFF-FIRST', 'PTS_HALF_DIFF-SECOND', 'QTR1', 'QTR2', 'QTR3', 'QTR4', 'QTR-1to3', 'QTR-2to4', 'PTS_QTR_DIFF-FIRST', 'PTS_QTR_DIFF-SECOND', 'PTS_QTR_DIFF-THIRD', 'PTS_QTR_DIFF-FOURTH']


    for game_num, game in tqdm(enumerate(data[:50])):
        for idx, name in game["box_score"]['PLAYER_NAME'].items():
            game["box_score"]['PLAYER_NAME'][idx] = '_'.join(name.split())

        # line-score rcd_types
        cols = {k: k.split("TEAM-")[1] if not k[-1].isdigit() else k.split("_")[-1] for k in game["vis_line"]}

        stats = pandas.DataFrame(game["box_score"]).set_index("PLAYER_NAME")
        # game["home_line"]["NAME"] = game["home_name"]
        # game["vis_line"]["NAME"] = game["vis_name"]
        line = pandas.DataFrame({game["home_name"] : game["home_line"], game["vis_name"]: game["vis_line"]})

        stats["H/V"] = (stats["TEAM_CITY"] == game["home_city"] ).map(lambda a: "H" if a else "V")
        # del stats["FIRST_NAME"]
        # del stats["SECOND_NAME"]
        del stats["TEAM_CITY"]

        stats = stats.rename(columns={"START_POSITION": "POS"})
        stats = stats[order]
        stats = stats.applymap(lambda a: int(a) if a[0].isdigit() else a)
        stats = stats.sort_values(by=["PTS", "REB"], ascending=False)
        line= line.transpose().rename(columns =cols)
        line = line[order2]
        line = line.applymap(lambda a: "" if a == "N/A" else a)
        stats = stats.applymap(lambda a: "" if a == "N/A" else a)
        f = open(os.path.join(outdir, "game"+str(game_num)+".html"), "w")
        f.write("""<head>
<link href="https://maxcdn.bootstrapcdn.com/font-awesome/4.6.3/css/font-awesome.min.css" rel="stylesheet"
          integrity="sha384-T8Gy5hrqNKT+hzMclPo118YTQO6cYprQmhrYwIiQ/3axmI1hQomh7Ud2hPOy8SP1" crossorigin="anonymous">
    <link href="https://maxcdn.bootstrapcdn.com/bootswatch/3.3.6/cosmo/bootstrap.min.css" rel="stylesheet"
          integrity="sha384-OiWEn8WwtH+084y4yW2YhhH6z/qTSecHZuk/eiWtnvLtU+Z8lpDsmhOKkex6YARr" crossorigin="anonymous">
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
  <script src="http://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js"></script>
<script src=\"select.js\"></script>
    <style>
        a {
            color: black;
        }

        a:hover {
            color: black;
            font-weight: 500;
        }
        .off_row {
        display: none;
        }

        .ambi_row {
        display: table-row;
        }

        .sel_word {
            color: blue;

            background: yellow;
        }
        .ambi_word {
            color: red;
        }

        .fin_word {
            color: grey;
            # background: grey;
        }

        .sel_tab {
            color: red;
            font-weight: bold;
            background: yellow;
        }
        .fin_tab {
            color: grey;
        }

        .ambi_tab {
            color: red;
        font-weight: bold;
        background: yellow;
        }
        .sum {
            cursor: pointer;
        }

        .table {
            cursor: pointer;
        }
        .sum {
        padding-left: 200px;
        padding-right: 200px;

        font-size: 20px;
        }
    </style>
</head>
<body>
""")
        f.write("<br><div class=\"content\">")
        seen = {}

        f.write("<div class=\"sum\">")
        idx = 0
        for word in game["summary"]:
            for w in word.split('_'):
                id = "sum%d_%s"%(idx,w)
                f.write("<span id=\"%s\" onclick=\"word_select('%s')\">%s</span> " % (id, id, w))
                if w == "\n":
                    f.write("<br>")

                if w.strip() == ".":
                    f.write("<br>")
                idx += 1
        f.write("</div>")
        # f.write("<select name=\"carlist\" form=\"carform\"> <option value=\"volvo\">Volvo</option> <option value=\"saab\">Saab</option> <option value=\"opel\">Opel</option> <option value=\"audi\">Audi</option </select>")
        f.write("<br> <center> <input type='button' value=\"skip\" onclick=\"tab_select('')\"></center><br> ")
        print_table(f, line, seen)
        print_table(f, stats, seen)

        ambi_links = {}
        links = {}
        ord = {}
        last = [""]
        idx = 0
        for word in game["summary"]:
            for w in word.split('_'):
                id = "sum%d_%s"%(idx,w)
                matches = seen.get(w, [])
                if len(matches) == 1:
                    links[id] = matches[0]
                if len(matches) >= 1:
                    for l in last:
                        ord[l] = id
                    last = []
                if len(matches) >= 1:
                    last.append(id)
                    ambi_links[id] = matches
                idx += 1
        # pdb.set_trace()

        f.write("<br> <center><textarea cols=200 rows=10 editable=0 id=\"show\"></textarea></center>")
        f.write("\n<script>init(%s, %s, %s)</script>"%(json.dumps(links), json.dumps(ambi_links), json.dumps(ord)))
        f.write("</div></body>")
        f.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='clean')
    parser.add_argument('--src', type=str, required=True,
                        help='directory of *.json')
    parser.add_argument('--out', type=str, required=True,
                        help='output directory to save the htmls')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    main(args.src, args.out)
