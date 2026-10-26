from dotenv import load_dotenv
load_dotenv()
"""Bincom test - Flask + MySQL.
Run: pip install -r requirements.txt && python app.py
Schema notes (from bincom_test.sql):
  - ward_id repeats across LGAs, so wards are identified by ward.uniqueid,
    which polling_unit stores as uniquewardid.
  - announced_pu_results.polling_unit_uniqueid is VARCHAR and matches polling_unit.uniqueid.
  - party.partyid has 'LABOUR' but results store 'LABO' (CHAR(4)), so we store the first 4 chars.
"""
import os
from datetime import datetime
import pymysql
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
DELTA_STATE_ID = 25


def db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "bincom_test"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def q(sql, args=()):
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        conn.close()


def lgas():
    return q("SELECT lga_id, lga_name FROM lga WHERE state_id=%s ORDER BY lga_name",
             (DELTA_STATE_ID,))


# ---------- JSON endpoints for chained dropdowns ----------
@app.get("/api/wards/<int:lga_id>")
def api_wards(lga_id):
    # value = ward.uniqueid (unique), label = ward name
    return jsonify(q("SELECT uniqueid AS id, ward_name AS name FROM ward "
                     "WHERE lga_id=%s ORDER BY ward_name", (lga_id,)))


@app.get("/api/pus/<int:ward_uid>")
def api_pus(ward_uid):
    return jsonify(q(
        """SELECT uniqueid AS id,
                  CONCAT(COALESCE(polling_unit_number,''), ' - ',
                         COALESCE(polling_unit_name,'')) AS name
           FROM polling_unit WHERE uniquewardid=%s ORDER BY polling_unit_number""",
        (ward_uid,)))


# ---------- shared layout ----------
BASE = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bincom Election Results</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:16px;color:#222}
 nav a{margin-right:12px;text-decoration:none;color:#0a58ca;font-weight:600}
 label{display:block;margin:14px 0 4px;font-weight:600}
 select,input{width:100%;padding:10px;font-size:16px;border:1px solid #bbb;border-radius:6px;box-sizing:border-box}
 select:disabled{background:#eee}
 button{margin-top:16px;padding:12px 20px;font-size:16px;border:0;border-radius:6px;background:#0a58ca;color:#fff}
 table{border-collapse:collapse;width:100%;margin-top:16px}
 th,td{border:1px solid #ddd;padding:8px;text-align:left} th{background:#f3f3f3}
 .ok{background:#d1e7dd;padding:10px;border-radius:6px;margin-top:12px}
 .err{background:#f8d7da;padding:10px;border-radius:6px;margin-top:12px}
</style></head><body>
<nav><a href="/">1. Polling Unit</a><a href="/lga">2. LGA Total</a><a href="/new">3. New Result</a></nav>
<h2>{{ title }}</h2>
{{ body|safe }}
<script>
async function fill(sel, url, ph){
  sel.innerHTML = '<option value="">Loading...</option>';
  const r = await (await fetch(url)).json();
  sel.innerHTML = '<option value="">' + ph + '</option>' +
    r.map(x => '<option value="'+x.id+'">'+x.name+'</option>').join('');
  sel.disabled = false;
}
(function(){
  const l=document.getElementById('lga'), w=document.getElementById('ward'), p=document.getElementById('pu');
  if(!l||!w) return;
  l.onchange=()=>{ w.disabled=true; w.innerHTML='<option value="">Select ward</option>';
    if(p){p.disabled=true; p.innerHTML='<option value="">Select polling unit</option>';}
    if(l.value) fill(w,'/api/wards/'+l.value,'Select ward'); };
  if(p) w.onchange=()=>{ p.disabled=true; p.innerHTML='<option value="">Select polling unit</option>';
    if(w.value) fill(p,'/api/pus/'+w.value,'Select polling unit'); };
})();
</script></body></html>"""


def page(title, body):
    return render_template_string(BASE, title=title, body=body)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def lga_options(selected=None):
    return "".join(
        f'<option value="{r["lga_id"]}"{" selected" if str(r["lga_id"]) == str(selected) else ""}>'
        f'{esc(r["lga_name"])}</option>' for r in lgas())


def results_table(rows):
    if not rows:
        return '<p class="err">No results have been recorded for this selection.</p>'
    body = "".join(f"<tr><td>{esc(r['party_abbreviation'])}</td><td>{int(r['score'])}</td></tr>"
                   for r in rows)
    total = sum(int(r["score"]) for r in rows)
    return (f"<table><tr><th>Party</th><th>Score</th></tr>{body}"
            f"<tr><th>Total</th><th>{total}</th></tr></table>")


# ---------- Q1: single polling unit ----------
@app.route("/", methods=["GET", "POST"])
def pu_result():
    out = ""
    sel_lga = None
    ward_html = '<option value="">Select ward</option>'
    pu_html = '<option value="">Select polling unit</option>'
    enabled = " disabled"
    if request.method == "POST" and request.form.get("pu"):
        pu = request.form["pu"]
        info = q("""SELECT polling_unit_number, polling_unit_name, lga_id, uniquewardid
                    FROM polling_unit WHERE uniqueid=%s""", (pu,))
        rows = q("""SELECT party_abbreviation, party_score AS score
                    FROM announced_pu_results WHERE polling_unit_uniqueid=%s
                    ORDER BY party_abbreviation""", (pu,))
        head = ""
        if info:
            i = info[0]
            head = f"<p><b>{esc(i['polling_unit_number'])}</b> {esc(i['polling_unit_name'])}</p>"
            # keep the user's selections after the page reloads
            wr = q("SELECT lga_id FROM ward WHERE uniqueid=%s", (i["uniquewardid"],))
            sel_lga = wr[0]["lga_id"] if wr else i["lga_id"]
            wards = q("SELECT uniqueid, ward_name FROM ward WHERE lga_id=%s ORDER BY ward_name", (sel_lga,))
            pus = q("""SELECT uniqueid, polling_unit_number, polling_unit_name FROM polling_unit
                       WHERE uniquewardid=%s ORDER BY polling_unit_number""", (i["uniquewardid"],))
            ward_html += "".join(
                f'<option value="{w["uniqueid"]}"{" selected" if w["uniqueid"] == i["uniquewardid"] else ""}>'
                f'{esc(w["ward_name"])}</option>' for w in wards)
            pu_html += "".join(
                f'<option value="{p["uniqueid"]}"{" selected" if str(p["uniqueid"]) == pu else ""}>'
                f'{esc(p["polling_unit_number"])} - {esc(p["polling_unit_name"])}</option>' for p in pus)
            enabled = ""
        out = head + results_table(rows)
    body = f"""<form method="post" autocomplete="off">
      <label>Local Government</label>
      <select id="lga" required><option value="">Select LGA</option>{lga_options(sel_lga)}</select>
      <label>Ward</label>
      <select id="ward"{enabled}>{ward_html}</select>
      <label>Polling Unit</label>
      <select id="pu" name="pu" required{enabled}>{pu_html}</select>
      <button>Show result</button></form>{out}"""
    return page("Polling Unit Result", body)


# ---------- Q2: LGA summed total (from polling units, NOT announced_lga_results) ----------
@app.route("/lga", methods=["GET", "POST"])
def lga_total():
    out, sel = "", request.form.get("lga")
    if request.method == "POST" and sel:
        rows = q("""SELECT r.party_abbreviation, SUM(r.party_score) AS score
                    FROM announced_pu_results r
                    JOIN polling_unit p ON p.uniqueid = r.polling_unit_uniqueid
                    WHERE p.lga_id=%s
                    GROUP BY r.party_abbreviation ORDER BY score DESC""", (sel,))
        out = results_table(rows)
    body = f"""<form method="post">
      <label>Local Government</label>
      <select name="lga" id="lga" required onchange="this.form.submit()">
        <option value="">Select LGA</option>{lga_options(sel)}</select>
      <noscript><button>Show total</button></noscript></form>{out}"""
    return page("LGA Summed Result", body)


# ---------- Q3: store results for a new polling unit ----------
@app.route("/new", methods=["GET", "POST"])
def new_pu():
    msg = ""
    parties = q("SELECT partyid FROM party ORDER BY id")
    if request.method == "POST":
        f = request.form
        conn = db()
        try:
            scores = {}
            for p in parties:
                s = int(f.get("score_" + p["partyid"], 0) or 0)
                if s < 0:
                    raise ValueError("Scores cannot be negative.")
                scores[p["partyid"][:4]] = s  # results table stores CHAR(4), e.g. LABOUR -> LABO
            name = f["name"].strip()[:50]
            if not name:
                raise ValueError("Polling unit name is required.")
            by = f["entered_by"].strip()[:50]
            now, ip = datetime.now(), request.remote_addr or ""
            with conn.cursor() as cur:
                cur.execute("SELECT ward_id, lga_id FROM ward WHERE uniqueid=%s", (f["ward"],))
                w = cur.fetchone()
                if not w or str(w["lga_id"]) != f["lga"]:
                    raise ValueError("Ward does not belong to the selected LGA.")
                cur.execute("SELECT COALESCE(MAX(polling_unit_id),0)+1 AS n FROM polling_unit WHERE uniquewardid=%s",
                            (f["ward"],))
                next_no = cur.fetchone()["n"]
                cur.execute(
                    """INSERT INTO polling_unit
                       (polling_unit_id, ward_id, lga_id, uniquewardid, polling_unit_number,
                        polling_unit_name, polling_unit_description,
                        entered_by_user, date_entered, user_ip_address)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (next_no, w["ward_id"], w["lga_id"], f["ward"], f"NEW-{f['ward']}-{next_no}"[:50],
                     name, name, by, now, ip))
                pu_id = cur.lastrowid
                cur.executemany(
                    """INSERT INTO announced_pu_results
                       (polling_unit_uniqueid, party_abbreviation, party_score,
                        entered_by_user, date_entered, user_ip_address)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    [(str(pu_id), p, s, by, now, ip) for p, s in scores.items()])
            conn.commit()
            msg = (f'<div class="ok">Saved polling unit #{pu_id} with {len(scores)} party results. '
                   f'Look it up on the first page to confirm.</div>')
        except Exception as e:
            conn.rollback()
            msg = f'<div class="err">Could not save: {esc(e)}</div>'
        finally:
            conn.close()
    inputs = "".join(
        f'<label>{esc(p["partyid"])}</label><input type="number" min="0" value="0" '
        f'name="score_{esc(p["partyid"])}" required>' for p in parties)
    body = f"""{msg}<form method="post">
      <label>Local Government</label>
      <select id="lga" name="lga" required><option value="">Select LGA</option>{lga_options()}</select>
      <label>Ward</label>
      <select id="ward" name="ward" required disabled><option value="">Select ward</option></select>
      <label>New polling unit name</label><input name="name" maxlength="50" required>
      <label>Entered by</label><input name="entered_by" maxlength="50" required>
      <h3>Party scores</h3>{inputs}
      <button>Save results</button></form>"""
    return page("Add New Polling Unit Results", body)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(debug=True, port=port)
