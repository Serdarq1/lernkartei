#!/usr/bin/env python3
"""Builds data.js for the flashcard game (index.html).

Sources:
  - A1_Wortschatz_und_Verben.docx / A2_Wortschatz_und_Verben.docx (this folder)
  - Goethe-Institut A1/A2 Wortliste as TSV (github.com/ilkermeliksitki/goethe-institute-wordlist),
    downloaded once into .cache/
  - Most-common-verbs list (Jones & Tschirner frequency dictionary, via lingoda.com) -> FREQ_VERBS below

Run:  python3 build.py
"""
import json, re, zipfile, urllib.request, pathlib
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).parent
CACHE = HERE / ".cache"
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
GOETHE = "https://raw.githubusercontent.com/ilkermeliksitki/goethe-institute-wordlist/HEAD/"


def docx_blocks(path):
    """Yield ('p', text) and ('t', rows) in document order."""
    def txt(e): return ''.join(t.text or '' for t in e.iter(W + 't')).strip()
    body = ET.fromstring(zipfile.ZipFile(path).read('word/document.xml')).find(W + 'body')
    for el in body:
        if el.tag == W + 'p' and txt(el):
            yield 'p', txt(el)
        elif el.tag == W + 'tbl':
            yield 't', [[txt(c) for c in r.iter(W + 'tc')] for r in el.iter(W + 'tr')]


def goethe(level):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{level}.tsv"
    if not f.exists():
        files = [f"{level}/a1.tsv"] if level == "a1" else [f"a2/{c}.tsv" for c in "abcdefghijklmnopqrstuvwxyz"]
        out = []
        for p in files:
            try:
                out.append(urllib.request.urlopen(GOETHE + p, timeout=30).read().decode())
            except Exception:
                pass  # some letters (q, x, y) don't exist
        f.write_text("\n".join(out))
    rows = []
    for line in f.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] != "german word":
            rows.append(parts[:3])
    return rows


ART = re.compile(r'^(der|die|das)\s+(.+)$')
nouns, vocab, verbs, phrases, adjprep, verbprep, antonyms = {}, [], {}, [], [], [], []


def clean(s):
    return re.sub(r'\s+', ' ', s.replace('★', '')).strip()


def add_noun(sing, plural, en, level, topic):
    sing = clean(sing)
    m = ART.match(sing)
    if not m or '/' in sing or '(' in sing:
        return
    art, word = m.groups()
    plural = clean(plural)
    if plural.startswith('—'):
        pl = '' if 'nur Plural' not in plural else None
        if pl is None:
            return  # plural-only nouns (die Eltern) don't fit the article drill
    else:
        pm = ART.match(plural)
        if not pm or '/' in plural:
            return
        pl = pm.group(2)
    if word not in nouns:
        nouns[word] = dict(a=art, w=word, p=pl, en=en, l=level, t=topic)


# ---------- regular verb forms ----------
INSEP = ('be', 'emp', 'ent', 'er', 'ge', 'miss', 'ver', 'zer', 'über', 'unter', 'wieder')
SEP = ('ab', 'an', 'auf', 'aus', 'bei', 'ein', 'fern', 'fest', 'her', 'herunter', 'hin', 'los', 'mit',
       'nach', 'statt', 'weiter', 'vorbei', 'teil', 'um', 'vor', 'weg', 'zu', 'zurück', 'zusammen', 'kennen', 'kaputt', 'spazieren')
IST_REG = {'passieren', 'reisen', 'verreisen', 'wandern', 'landen', 'klettern', 'aufwachen', 'folgen', 'begegnen'}


def stem_of(inf):
    if inf.endswith(('eln', 'ern')):
        return inf[:-1]
    return inf[:-2] if inf.endswith('en') else inf[:-1]


def needs_e(stem):
    return bool(re.search(r'([td]|chn|[^aeiouäöülhrmn][mn])$', stem))


def regular(inf):
    """er-Präsens, Präteritum (er), Perfekt for a weak verb (handles separable prefixes)."""
    prefix = ''
    for p in sorted(SEP, key=len, reverse=True):
        if inf.startswith(p) and len(inf) > len(p) + 3:
            prefix, inf = p, inf[len(p):]
            break
    s = stem_of(inf)
    e = 'e' if needs_e(s) else ''
    er = s + e + 't'
    if s.endswith(('s', 'ß', 'z', 'x')):
        er = s + 't'
    prt = s + e + 'te'
    no_ge = inf.endswith('ieren') or inf.startswith(INSEP)
    part = (prefix + ('' if no_ge else 'ge') + s + e + 't')
    aux = 'ist' if (prefix + inf) in IST_REG else 'hat'
    sp = (' ' + prefix) if prefix else ''
    return er + sp, prt + sp, f"{aux} {part}"


def add_verb(inf, en, er=None, prt=None, perf=None, level='A1', kind=None, freq=None):
    inf = clean(inf)
    refl = inf.startswith('sich ')
    base = inf[5:] if refl else inf
    base = re.sub(r'\s*\(.*?\)\s*', '', base).strip()
    if '/' in base or ' ' in base or not base.isalpha():
        return
    if base in verbs:
        verbs[base]['freq'] = verbs[base].get('freq') or freq
        return
    derived = er is None
    if derived:
        er, prt, perf = regular(base)
    verbs[base] = dict(i=base, refl=refl, en=en, er=clean(er), prt=clean(prt or ''), perf=clean(perf),
                       k=kind or ('schwach' if derived else 'stark'), l=level, freq=freq, derived=derived)


def split_prefix(inf):
    for p in sorted(SEP, key=len, reverse=True):
        if inf.startswith(p) and len(inf) > len(p) + 3:
            return p, inf[len(p):], True
    for p in sorted(INSEP, key=len, reverse=True):
        if inf.startswith(p) and len(inf) > len(p) + 3:
            return p, inf[len(p):], False
    return '', inf, False


def finalize():
    """Fix derived/missing forms of prefixed strong verbs from their base verb, then add 'sich'."""
    strong = {k: v for k, v in verbs.items() if not v['derived'] and v['prt'] and v['k'] != 'schwach'}
    for k, v in verbs.items():
        pre, base, sep = split_prefix(k)
        b = strong.get(base)
        if pre and b and (v['derived'] or not v['prt']):
            aux, part = b['perf'].split(' ', 1)
            if sep:
                er, prt, perf = f"{b['er']} {pre}", f"{b['prt']} {pre}", f"{aux} {pre}{part}"
                v['k'] = 'trennbar'
            else:
                er, prt, perf = pre + b['er'], pre + b['prt'], f"{aux} {pre}{part[2:] if part.startswith('ge') else part}"
                v['k'] = b['k']
            if v['derived']:
                v['er'], v['perf'] = er, perf
            v['prt'] = prt
        elif not v['prt']:
            v['prt'] = regular(k)[1]
        if v['derived'] and split_prefix(k)[2]:
            v['k'] = 'trennbar'
    for v in verbs.values():
        if v.pop('refl'):
            v['i'] = 'sich ' + v['i']
            for f in ('er', 'prt'):
                w = v[f].split(' ')
                if 'sich' not in w:
                    v[f] = ' '.join([w[0], 'sich'] + w[1:])
            aux, part = v['perf'].split(' ', 1)
            if 'sich' not in part:
                v['perf'] = f"{aux} sich {part}"
        del v['derived']


# ---------- parse A1 docx ----------
def parse(path, level):
    head = ''
    for kind, val in docx_blocks(path):
        if kind == 'p':
            head = val
            continue
        rows = val
        hdr = rows[0]
        body = rows[1:]
        if hdr == ['Singular', 'Plural', 'Englisch']:
            for r in body:
                add_noun(r[0], r[1], r[2], level, head)
        elif hdr[:3] == ['Infinitiv', 'ich', 'du'] and 'Perfekt' in hdr:  # A1 2.3
            for r in body:
                m = re.match(r'(\w+)\s*\((.*)\)', r[0])
                if m:
                    add_verb(m[1], m[2], r[3], None, r[7], level, 'stark')
        elif hdr == ['Infinitiv', 'Englisch', 'Perfekt']:  # A1 2.4
            for r in body:
                add_verb(r[0], r[1], r[0][:-2] + 't', None, r[2], level, 'stark')
        elif hdr[:3] == ['Infinitiv', 'er/sie/es Präsens', 'Präteritum']:  # A2 2.6
            for r in body:
                kind_ = 'gemischt' if 'Gemischte' in head else 'stark'
                if '(' in r[0] and 'sich' not in r[0]:
                    r[0] = re.sub(r'\s*\(sich\)', '', r[0])
                if re.search(r'[/(]', r[3] + r[1] + r[2]) or len(r[3].split()) != 2:
                    continue
                add_verb(r[0], r[4], r[1], r[2], r[3], level, kind_)
        elif hdr == ['Infinitiv', 'er/sie/es (Präsens)', 'Perfekt', 'Englisch']:  # A2 2.8 separable
            for r in body:
                if '/' in r[1] + r[2] or '(' in r[0]:
                    continue
                add_verb(r[0], r[3], r[1], None, r[2], level, 'trennbar')
        elif hdr in (['Verb', 'Englisch', 'Verb', 'Englisch'],) and ('2.5' in head or 'Muster' in head or 'Regel' in head or 'regelmäßig' in head.lower()):
            for r in body:
                for i in (0, 2):
                    if r[i] and '*' not in r[i]:
                        inf = r[i].replace('(ist)', '').strip()
                        add_verb(inf, r[i + 1], level=level, kind='schwach')
        elif hdr == ['Verb', 'Englisch', 'Verb', 'Englisch'] and 'Trennbare' in head:  # A1 2.7
            for r in body:
                for i in (0, 2):
                    if r[i]:
                        inf = r[i].replace('(ist)', '').strip()
                        if inf.replace(' ', '').isalpha():
                            add_verb(inf, r[i + 1], level=level, kind='trennbar')
        elif hdr[:2] == ['Verb', 'Englisch'] and len(hdr) == 2:  # A1 reflexive
            for r in body:
                add_verb(r[0], r[1], level=level, kind='schwach')
        elif hdr[:4] == ['#', 'Verb', 'Englisch', 'Zipf']:  # A2 0.1 top-70
            for r in body:
                for i in (0, 4):
                    rank = int(r[i].rstrip('.'))
                    v = re.sub(r'^sich ', '', r[i + 1])
                    if v in verbs:
                        verbs[v]['freq'] = rank
                    else:
                        add_verb(r[i + 1], r[i + 2], level=level, freq=rank)
                        if v in verbs:
                            verbs[v]['freq'] = rank
        elif hdr == ['Verb', 'Präposition + Kasus', 'Englisch', 'Beispiel']:
            for r in body:
                verbprep.append(dict(v=r[0], p=r[1], en=r[2], ex=r[3]))
        elif hdr == ['Adjektiv + Präposition', 'Kasus', 'Englisch', 'Beispiel']:
            for r in body:
                adjprep.append(dict(v=r[0], p=r[1], en=r[2], ex=r[3]))
        elif hdr == ['Paar', 'Englisch', 'Paar', 'Englisch']:
            for r in body:
                for i in (0, 2):
                    if '↔' in r[i]:
                        antonyms.append(dict(de=r[i], en=r[i + 1]))
        elif hdr == ['Deutsch', 'Englisch', 'Deutsch', 'Englisch'] or hdr == ['Nomen', 'Englisch', 'Nomen', 'Englisch'] \
                or hdr == ['Verbindung', 'Englisch', 'Verbindung', 'Englisch'] or hdr == ['Wort', 'Englisch', 'Wort', 'Englisch']:
            topic = re.sub(r'^[\d.]+\s*', '', head)
            for r in body:
                for i in (0, 2):
                    if r[i] and r[i + 1]:
                        m = ART.match(r[i])
                        vocab.append(dict(de=clean(r[i]), en=r[i + 1], l=level, t=topic))
        elif hdr == ['Deutsch', 'Englisch']:
            topic = re.sub(r'^[\d.]+\s*', '', head)
            for r in body:
                phrases.append(dict(de=r[0], en=r[1], l=level, t=topic))


parse(HERE / 'A1_Wortschatz_und_Verben.docx', 'A1')
parse(HERE / 'A2_Wortschatz_und_Verben.docx', 'A2')

# ---------- Extracted once from this folder's PDFs (Möbel, In der Küche, 55 Alltagssätze A1-A2) ----------
PDF_NOUNS = [["das", "Sofa", "Sofas", "Möbel"], ["der", "Teppich", "Teppiche", "Möbel"], ["die", "Lampe", "Lampen", "Möbel"], ["der", "Couchtisch", "Couchtische", "Möbel"], ["der", "Stuhl", "Stühle", "Möbel"], ["die", "Stehlampe", "Stehlampen", "Möbel"], ["die", "Wandleuchte", "Wandleuchten", "Möbel"], ["das", "Leselicht", "Leselichter", "Möbel"], ["die", "Hängeleuchte", "Hängeleuchten", "Möbel"], ["die", "Tischlampe", "Tischlampen", "Möbel"], ["der", "Fußhocker", "Fußhocker", "Möbel"], ["der", "Sessel", "Sessel", "Möbel"], ["der", "Esstisch", "Esstische", "Möbel"], ["der", "Essstuhl", "Essstühle", "Möbel"], ["das", "Bücherregal", "Bücherregale", "Möbel"], ["der", "Schreibtisch", "Schreibtische", "Möbel"], ["der", "Stuhl", "Stühle", "Möbel"], ["das", "Bild", "Bilder", "Möbel"], ["der", "Küchenhocker", "Küchenhocker", "Möbel"], ["die", "Vase", "Vasen", "Möbel"], ["der", "Spiegel", "Spiegel", "Möbel"], ["die", "Kommode", "Kommoden", "Möbel"], ["der", "Nachttisch", "Nachttische", "Möbel"], ["das", "Bett", "Betten", "Möbel"], ["das", "Kissen", "Kissen", "Möbel"], ["die", "Sitzbank", "Sitzbänke", "Möbel"], ["das", "Etagenbett", "Etagenbetten", "Möbel"], ["der", "Kleiderschrank", "Kleiderschränke", "Möbel"], ["das", "Schuhregal", "Schuhregale", "Möbel"], ["der", "Pflanzentopf", "Pflanzentöpfe", "Möbel"], ["das", "Gartenmöbel", "Gartenmöbel", "Möbel"], ["der", "Löffel", "Löffel", "In der Küche"], ["das", "Messer", "Messer", "In der Küche"], ["die", "Gabel", "Gabeln", "In der Küche"], ["die", "Tasse", "Tassen", "In der Küche"], ["die", "Untertasse", "Untertassen", "In der Küche"], ["die", "Schüssel", "Schüsseln", "In der Küche"], ["der", "Teller", "Teller", "In der Küche"], ["die", "Pfanne", "Pfannen", "In der Küche"], ["die", "Reibe", "Reiben", "In der Küche"], ["das", "Nudelsieb", "Nudelsiebe", "In der Küche"], ["der", "Topf", "Töpfe", "In der Küche"], ["der", "Deckel", "Deckel", "In der Küche"], ["die", "Pfeffermühle", "Pfeffermühlen", "In der Küche"], ["die", "Teekanne", "Teekannen", "In der Küche"], ["das", "Sieb", "Siebe", "In der Küche"], ["das", "Nudelholz", "Nudelhölzer", "In der Küche"], ["das", "Teigrädchen", "Teigrädchen", "In der Küche"], ["der", "Krug", "Krüge", "In der Küche"], ["das", "Glas", "Gläser", "In der Küche"], ["der", "Abfalleimer", "Abfalleimer", "In der Küche"], ["der", "Wasserhahn", "Wasserhähne", "In der Küche"], ["die", "Küchenwaage", "Küchenwaagen", "In der Küche"], ["der", "Dosenöffner", "Dosenöffner", "In der Küche"], ["die", "Dose", "Dosen", "In der Küche"], ["der", "Flaschenöffner", "Flaschenöffner", "In der Küche"], ["der", "Korb", "Körbe", "In der Küche"], ["die", "Küchenschürze", "Küchenschürzen", "In der Küche"], ["der", "Kochlöffel", "Kochlöffel", "In der Küche"], ["das", "Schneidebrett", "Schneidebretter", "In der Küche"], ["die", "Crepepfanne", "Crepepfannen", "In der Küche"], ["die", "Stielkasserolle", "Stielkasserollen", "In der Küche"], ["der", "Schneebesen", "Schneebesen", "In der Küche"], ["die", "Suppenkelle", "Suppenkellen", "In der Küche"]]
PDF_PHRASES = [["Bis bald!", "See you soon!"], ["Lass uns gehen.", "Let's go."], ["Alles klar.", "Got it. / Okay."], ["Na klar!", "Of course!"], ["Alles in Ordnung?", "Everything okay?"], ["Was ist los?", "What's wrong? / What's going on?"], ["Ich hoffe es.", "I hope so."], ["Was machst du heute Abend?", "What are you doing tonight?"], ["Das ist eine gute Idee.", "That is a good idea."], ["Willst du mit uns gehen?", "Do you want to go with us?"], ["Kannst du mit mir kommen?", "Can you come with me?"], ["Das gefällt mir.", "I like that."], ["Ich bin gespannt.", "I'm excited / curious."], ["Das war lecker.", "That was delicious."], ["Ich glaube dir.", "I believe you."], ["Ich bin gleich zurück.", "I'll be right back."], ["Ich bin fast fertig.", "I'm almost done."], ["Ich bin gleich fertig.", "I'll be done in a moment."], ["Warte mal!", "Wait a moment!"], ["Ich muss los.", "I have to go. / I have to leave."], ["Ich bin unterwegs.", "I'm on my way."], ["Ich habe keine Zeit.", "I don't have time."], ["Ich melde mich später.", "I'll get in touch later."], ["Ich rufe dich später an.", "I'll call you later."], ["Das ist unmöglich!", "That's impossible!"], ["Bist du sauer?", "Are you angry?"], ["Ich habe es vergessen.", "I forgot it."], ["Ich weiß es nicht.", "I don't know."], ["Ich verstehe das nicht.", "I don't understand that."], ["Es tut mir leid, ich habe das nicht verstanden.", "I'm sorry, I didn't understand that."], ["Keine Ahnung.", "No idea."], ["Was meinst du?", "What do you mean?"], ["Verstehst du mich?", "Do you understand me?"], ["Keine Sorge!", "No worries!"], ["Sei nicht böse.", "Don't be angry."], ["Ich bin total kaputt.", "I am completely exhausted."], ["Ich brauche eine Pause.", "I need a break."], ["Der Zug hat Verspätung.", "The train is delayed."], ["Das ist komisch!", "That is strange / funny!"], ["Ich hab keine Lust.", "I don't feel like it."], ["Davon kann ich nur abraten.", "I can only advise against that."], ["Ich schaffe das.", "I can do it. / I'll manage."], ["Ich habe es geschafft.", "I did it! / I succeeded!"], ["Du schaffst das!", "You can do it! / You got this!"], ["Gute Besserung!", "Get well soon."], ["Viel Glück!", "Good luck!"], ["Ich bin fertig!", "I am finished / ready!"], ["Mach langsam.", "Take it easy. / Slow down."], ["Vergiss es!", "Forget it!"], ["Mach keinen Stress.", "Don't stress out."], ["Komm schon!", "Come on!"], ["Vielen Dank für Ihr Verständnis.", "Thank you for your understanding."], ["Auf Wiedersehen!", "Goodbye!"], ["Es ist (mir) egal.", "It doesn't matter."], ["Vielen Dank für Ihre Zeit.", "Thank you for your time."]]
for a, w, p, t in PDF_NOUNS:
    add_noun(f'{a} {w}', f'die {p}', '', 'A1', t)
for de, en in PDF_PHRASES:
    phrases.append(dict(de=de, en=en, l='A1', t='55 Alltagssätze'))

# ---------- Hand-checked core verbs (aux/modal + most-common verbs missing above) ----------
# (infinitive, english, er-Präsens, Präteritum, Perfekt, kind)
CORE = [
    ('sein', 'to be', 'ist', 'war', 'ist gewesen', 'stark'),
    ('haben', 'to have', 'hat', 'hatte', 'hat gehabt', 'gemischt'),
    ('werden', 'to become', 'wird', 'wurde', 'ist geworden', 'stark'),
    ('können', 'can, to be able to', 'kann', 'konnte', 'hat gekonnt', 'modal'),
    ('müssen', 'must, to have to', 'muss', 'musste', 'hat gemusst', 'modal'),
    ('dürfen', 'may, to be allowed to', 'darf', 'durfte', 'hat gedurft', 'modal'),
    ('sollen', 'should, to be supposed to', 'soll', 'sollte', 'hat gesollt', 'modal'),
    ('wollen', 'to want', 'will', 'wollte', 'hat gewollt', 'modal'),
    ('mögen', 'to like', 'mag', 'mochte', 'hat gemocht', 'modal'),
    ('wissen', 'to know (a fact)', 'weiß', 'wusste', 'hat gewusst', 'gemischt'),
    ('kennen', 'to know (be familiar with)', 'kennt', 'kannte', 'hat gekannt', 'gemischt'),
    ('denken', 'to think', 'denkt', 'dachte', 'hat gedacht', 'gemischt'),
    ('bringen', 'to bring', 'bringt', 'brachte', 'hat gebracht', 'gemischt'),
    ('nennen', 'to name, to call', 'nennt', 'nannte', 'hat genannt', 'gemischt'),
    ('rennen', 'to run, to race', 'rennt', 'rannte', 'ist gerannt', 'gemischt'),
    ('senden', 'to send', 'sendet', 'sendete', 'hat gesendet', 'schwach'),
    ('verbinden', 'to connect', 'verbindet', 'verband', 'hat verbunden', 'stark'),
    ('gehen', 'to go, to walk', 'geht', 'ging', 'ist gegangen', 'stark'),
    ('kommen', 'to come', 'kommt', 'kam', 'ist gekommen', 'stark'),
    ('stehen', 'to stand', 'steht', 'stand', 'hat gestanden', 'stark'),
    ('verstehen', 'to understand', 'versteht', 'verstand', 'hat verstanden', 'stark'),
    ('tun', 'to do', 'tut', 'tat', 'hat getan', 'stark'),
    ('heißen', 'to be called', 'heißt', 'hieß', 'hat geheißen', 'stark'),
    ('rufen', 'to call, to shout', 'ruft', 'rief', 'hat gerufen', 'stark'),
    ('anrufen', 'to phone', 'ruft an', 'rief an', 'hat angerufen', 'trennbar'),
    ('anfangen', 'to begin', 'fängt an', 'fing an', 'hat angefangen', 'trennbar'),
    ('aufstehen', 'to get up', 'steht auf', 'stand auf', 'ist aufgestanden', 'trennbar'),
    ('einkaufen', 'to shop', 'kauft ein', 'kaufte ein', 'hat eingekauft', 'trennbar'),
    ('fernsehen', 'to watch TV', 'sieht fern', 'sah fern', 'hat ferngesehen', 'trennbar'),
    ('mitkommen', 'to come along', 'kommt mit', 'kam mit', 'ist mitgekommen', 'trennbar'),
    ('ankommen', 'to arrive', 'kommt an', 'kam an', 'ist angekommen', 'trennbar'),
    ('einladen', 'to invite', 'lädt ein', 'lud ein', 'hat eingeladen', 'trennbar'),
    ('einsteigen', 'to get on (a vehicle)', 'steigt ein', 'stieg ein', 'ist eingestiegen', 'trennbar'),
    ('aussteigen', 'to get off (a vehicle)', 'steigt aus', 'stieg aus', 'ist ausgestiegen', 'trennbar'),
    ('umsteigen', 'to change (trains)', 'steigt um', 'stieg um', 'ist umgestiegen', 'trennbar'),
    ('anziehen', 'to put on (clothes)', 'zieht an', 'zog an', 'hat angezogen', 'trennbar'),
    ('umziehen', 'to move (house)', 'zieht um', 'zog um', 'ist umgezogen', 'trennbar'),
    ('aussehen', 'to look, to appear', 'sieht aus', 'sah aus', 'hat ausgesehen', 'trennbar'),
    ('ansehen', 'to look at', 'sieht an', 'sah an', 'hat angesehen', 'trennbar'),
    ('anbieten', 'to offer', 'bietet an', 'bot an', 'hat angeboten', 'trennbar'),
    ('vorschlagen', 'to suggest', 'schlägt vor', 'schlug vor', 'hat vorgeschlagen', 'trennbar'),
    ('bieten', 'to offer', 'bietet', 'bot', 'hat geboten', 'stark'),
    ('ziehen', 'to pull', 'zieht', 'zog', 'hat gezogen', 'stark'),
    ('schließen', 'to close', 'schließt', 'schloss', 'hat geschlossen', 'stark'),
    ('sehen', 'to see', 'sieht', 'sah', 'hat gesehen', 'stark'),
    ('laden', 'to load', 'lädt', 'lud', 'hat geladen', 'stark'),
    ('schlagen', 'to hit', 'schlägt', 'schlug', 'hat geschlagen', 'stark'),
    ('betreffen', 'to concern', 'betrifft', 'betraf', 'hat betroffen', 'stark'),
    ('ergeben', 'to result in', 'ergibt', 'ergab', 'hat ergeben', 'stark'),
    ('erscheinen', 'to appear', 'erscheint', 'erschien', 'ist erschienen', 'stark'),
    ('verlassen', 'to leave', 'verlässt', 'verließ', 'hat verlassen', 'stark'),
    ('verwenden', 'to use', 'verwendet', 'verwendete', 'hat verwendet', 'schwach'),
    ('erkennen', 'to recognise', 'erkennt', 'erkannte', 'hat erkannt', 'gemischt'),
    ('führen', 'to lead', 'führt', 'führte', 'hat geführt', 'schwach'),
    ('handeln', 'to act; to trade', 'handelt', 'handelte', 'hat gehandelt', 'schwach'),
    ('lieben', 'to love', 'liebt', 'liebte', 'hat geliebt', 'schwach'),
    ('lachen', 'to laugh', 'lacht', 'lachte', 'hat gelacht', 'schwach'),
    ('leben', 'to live', 'lebt', 'lebte', 'hat gelebt', 'schwach'),
    ('wohnen', 'to live, to reside', 'wohnt', 'wohnte', 'hat gewohnt', 'schwach'),
    ('folgen', 'to follow', 'folgt', 'folgte', 'ist gefolgt', 'schwach'),
    ('danken', 'to thank', 'dankt', 'dankte', 'hat gedankt', 'schwach'),
    ('bilden', 'to form', 'bildet', 'bildete', 'hat gebildet', 'schwach'),
    ('entwickeln', 'to develop', 'entwickelt', 'entwickelte', 'hat entwickelt', 'schwach'),
    ('erwarten', 'to expect', 'erwartet', 'erwartete', 'hat erwartet', 'schwach'),
    ('fühlen', 'to feel', 'fühlt', 'fühlte', 'hat gefühlt', 'schwach'),
    ('glauben', 'to believe', 'glaubt', 'glaubte', 'hat geglaubt', 'schwach'),
    ('kaufen', 'to buy', 'kauft', 'kaufte', 'hat gekauft', 'schwach'),
    ('lernen', 'to learn', 'lernt', 'lernte', 'hat gelernt', 'schwach'),
    ('reden', 'to talk', 'redet', 'redete', 'hat geredet', 'schwach'),
    ('reisen', 'to travel', 'reist', 'reiste', 'ist gereist', 'schwach'),
    ('schmecken', 'to taste', 'schmeckt', 'schmeckte', 'hat geschmeckt', 'schwach'),
    ('setzen', 'to put, to set', 'setzt', 'setzte', 'hat gesetzt', 'schwach'),
    ('studieren', 'to study (at university)', 'studiert', 'studierte', 'hat studiert', 'schwach'),
    ('warten', 'to wait', 'wartet', 'wartete', 'hat gewartet', 'schwach'),
    ('zählen', 'to count', 'zählt', 'zählte', 'hat gezählt', 'schwach'),
    ('machen', 'to make, to do', 'macht', 'machte', 'hat gemacht', 'schwach'),
    ('sagen', 'to say', 'sagt', 'sagte', 'hat gesagt', 'schwach'),
    ('spielen', 'to play', 'spielt', 'spielte', 'hat gespielt', 'schwach'),
    ('arbeiten', 'to work', 'arbeitet', 'arbeitete', 'hat gearbeitet', 'schwach'),
    ('öffnen', 'to open', 'öffnet', 'öffnete', 'hat geöffnet', 'schwach'),
    ('kosten', 'to cost', 'kostet', 'kostete', 'hat gekostet', 'schwach'),
    ('regnen', 'to rain', 'regnet', 'regnete', 'hat geregnet', 'schwach'),
    ('gefallen', 'to please (Es gefällt mir.)', 'gefällt', 'gefiel', 'hat gefallen', 'stark'),
    ('essen', 'to eat', 'isst', 'aß', 'hat gegessen', 'stark'),
    ('trinken', 'to drink', 'trinkt', 'trank', 'hat getrunken', 'stark'),
    ('fahren', 'to drive, to go (by vehicle)', 'fährt', 'fuhr', 'ist gefahren', 'stark'),
    ('fliegen', 'to fly', 'fliegt', 'flog', 'ist geflogen', 'stark'),
    ('laufen', 'to run, to walk', 'läuft', 'lief', 'ist gelaufen', 'stark'),
    ('bleiben', 'to stay', 'bleibt', 'blieb', 'ist geblieben', 'stark'),
    ('schlafen', 'to sleep', 'schläft', 'schlief', 'hat geschlafen', 'stark'),
    ('lesen', 'to read', 'liest', 'las', 'hat gelesen', 'stark'),
    ('sprechen', 'to speak', 'spricht', 'sprach', 'hat gesprochen', 'stark'),
    ('nehmen', 'to take', 'nimmt', 'nahm', 'hat genommen', 'stark'),
    ('geben', 'to give', 'gibt', 'gab', 'hat gegeben', 'stark'),
    ('helfen', 'to help', 'hilft', 'half', 'hat geholfen', 'stark'),
    ('treffen', 'to meet', 'trifft', 'traf', 'hat getroffen', 'stark'),
    ('finden', 'to find', 'findet', 'fand', 'hat gefunden', 'stark'),
    ('schreiben', 'to write', 'schreibt', 'schrieb', 'hat geschrieben', 'stark'),
    ('waschen', 'to wash', 'wäscht', 'wusch', 'hat gewaschen', 'stark'),
    ('tragen', 'to carry, to wear', 'trägt', 'trug', 'hat getragen', 'stark'),
    ('halten', 'to hold, to stop', 'hält', 'hielt', 'hat gehalten', 'stark'),
    ('lassen', 'to let, to leave', 'lässt', 'ließ', 'hat gelassen', 'stark'),
    ('liegen', 'to lie (be lying)', 'liegt', 'lag', 'hat gelegen', 'stark'),
    ('sitzen', 'to sit', 'sitzt', 'saß', 'hat gesessen', 'stark'),
    ('vergessen', 'to forget', 'vergisst', 'vergaß', 'hat vergessen', 'stark'),
    ('verlieren', 'to lose', 'verliert', 'verlor', 'hat verloren', 'stark'),
    ('gewinnen', 'to win', 'gewinnt', 'gewann', 'hat gewonnen', 'stark'),
    ('beginnen', 'to begin', 'beginnt', 'begann', 'hat begonnen', 'stark'),
    ('bekommen', 'to get, to receive', 'bekommt', 'bekam', 'hat bekommen', 'stark'),
    ('singen', 'to sing', 'singt', 'sang', 'hat gesungen', 'stark'),
    ('riechen', 'to smell', 'riecht', 'roch', 'hat gerochen', 'stark'),
    ('scheinen', 'to seem; to shine', 'scheint', 'schien', 'hat geschienen', 'stark'),
    ('schaffen', 'to manage', 'schafft', 'schaffte', 'hat geschafft', 'schwach'),
    ('verschieben', 'to postpone', 'verschiebt', 'verschob', 'hat verschoben', 'stark'),
    ('empfehlen', 'to recommend', 'empfiehlt', 'empfahl', 'hat empfohlen', 'stark'),
    ('sterben', 'to die', 'stirbt', 'starb', 'ist gestorben', 'stark'),
    ('fallen', 'to fall', 'fällt', 'fiel', 'ist gefallen', 'stark'),
    ('schwimmen', 'to swim', 'schwimmt', 'schwamm', 'ist geschwommen', 'stark'),
]
for inf, en, er, prt, perf, kind in CORE:
    verbs.pop(inf, None)
    add_verb(inf, en, er, prt, perf, 'A1', kind)

finalize()

# frequency rank among the 100 most common verbs (Jones & Tschirner via lingoda + A2 doc Zipf list)
FREQ_VERBS = ("sein haben werden können müssen sagen machen geben kommen sollen wollen gehen wissen sehen lassen stehen "
              "finden bleiben liegen heißen denken nehmen tun dürfen glauben halten nennen mögen zeigen führen sprechen "
              "bringen leben fahren meinen fragen kennen gelten stellen spielen arbeiten brauchen folgen lernen bestehen "
              "verstehen setzen bekommen beginnen erzählen versuchen schreiben laufen erklären entsprechen sitzen ziehen "
              "scheinen fallen gehören entstehen erhalten treffen suchen legen vorstellen handeln erreichen tragen schaffen "
              "lesen verlieren darstellen erkennen entwickeln reden aussehen erscheinen bilden anfangen erwarten wohnen "
              "betreffen warten vergehen helfen gewinnen schließen fühlen bieten interessieren erinnern ergeben anbieten "
              "studieren verbinden ansehen fehlen bedeuten vergleichen").split()
for rank, v in enumerate(FREQ_VERBS, 1):
    if v in verbs:
        verbs[v]['freq'] = rank

# ---------- Goethe lists: extra nouns (article only) + example sentences ----------
UML = {'a': 'ä', 'o': 'ö', 'u': 'ü', 'A': 'Ä', 'O': 'Ö', 'U': 'Ü'}


def umlaut(w):
    # umlaut the last a/o/u (au -> äu)
    m = list(re.finditer(r'au|[aouAOU]', w))
    if not m:
        return w
    x = m[-1]
    rep = 'äu' if x.group().lower() == 'au' else UML[x.group()]
    if x.group() == 'Au':
        rep = 'Äu'
    return w[:x.start()] + rep + w[x.end():]


def goethe_plural(word, note):
    note = note.replace(' ', '')
    if note in ('-', '–'):
        return word
    m = re.fullmatch(r'(?:¨-|-¨)(\w*)', note) or re.fullmatch(r'-[äöüÄÖÜ],?(\w*)', note)
    if m:
        return umlaut(word) + m.group(1)
    m = re.fullmatch(r'-(e|en|n|er|s|nen|se)', note)
    if m:
        return word + m.group(1)
    return None


examples = {}
sentences = []
for level, rows in (('A1', goethe('a1')), ('A2', goethe('a2'))):
    for head, de, en in rows:
        head = head.strip()
        base = re.sub(r'\(\d\)', '', head)
        base = re.sub(r'\((Sg|Pl)\.\)', '', base).strip()
        note = None
        if ',' in base:
            base, note = [x.strip() for x in base.split(',', 1)]
        m = ART.match(base)
        if m and ' ' not in m.group(2) and m.group(2).isalpha():
            art, word = m.groups()
            pl = goethe_plural(word, note) if note else None
            if word not in nouns and note and pl:
                nouns[word] = dict(a=art, w=word, p=pl, en='', l=level, t='Goethe-Wortliste')
            elif word not in nouns and not note:
                nouns[word] = dict(a=art, w=word, p=None, en='', l=level, t='Goethe-Wortliste')
            key = word
        else:
            key = base
        de, en = de.strip(), en.strip()
        if len(de.split()) >= 3 and re.search(r'[.!?]$', de):
            examples.setdefault(key, (de, en))
            sentences.append(dict(h=key, de=de, en=en, l=level))

for n in nouns.values():
    if n['w'] in examples:
        n['ex'] = examples[n['w']]
for v in verbs.values():
    k = v['i'].replace('sich ', '')
    if k in examples:
        v['ex'] = examples[k]

# ---------- cloze items from Goethe sentences ----------
cloze, seen = [], set()
for s in sentences:
    h = s['h']
    stem = h[:-2] if h.endswith('en') else h
    toks = re.findall(r"[\wÄÖÜäöüß-]+", s['de'])
    hit = next((t for t in toks if t.lower() == h.lower()), None)
    if not hit and len(stem) >= 4:
        hit = next((t for t in toks if t.lower().startswith(stem.lower()) and len(t) <= len(h) + 3), None)
    if not hit or len(hit) < 3 or s['de'] in seen:
        continue
    seen.add(s['de'])
    cloze.append(dict(de=s['de'], en=s['en'], a=hit, l=s['l'], n=hit[0].isupper() and h[0].isupper()))

# English for nouns whose source (PDF / Goethe list) had none
EN_FILL = dict(Teppich='carpet, rug', Couchtisch='coffee table', Stehlampe='floor lamp', Wandleuchte='wall light',
    Leselicht='reading light', Hängeleuchte='pendant light', Tischlampe='table lamp', Fußhocker='footstool',
    Sessel='armchair', Esstisch='dining table', Essstuhl='dining chair', Bücherregal='bookshelf',
    Schreibtisch='desk', Küchenhocker='kitchen stool', Vase='vase', Spiegel='mirror', Kommode='chest of drawers',
    Nachttisch='bedside table', Kissen='pillow, cushion', Sitzbank='bench', Etagenbett='bunk bed',
    Kleiderschrank='wardrobe', Schuhregal='shoe rack', Pflanzentopf='plant pot', Gartenmöbel='garden furniture',
    Untertasse='saucer', Schüssel='bowl', Pfanne='pan', Reibe='grater', Nudelsieb='colander', Deckel='lid',
    Pfeffermühle='pepper mill', Teekanne='teapot', Sieb='sieve', Nudelholz='rolling pin', Teigrädchen='pastry wheel',
    Krug='jug', Abfalleimer='rubbish bin', Wasserhahn='tap, faucet', Küchenwaage='kitchen scale',
    Dosenöffner='can opener', Dose='can, tin', Flaschenöffner='bottle opener', Korb='basket',
    Küchenschürze='apron', Kochlöffel='wooden spoon', Schneidebrett='chopping board', Crepepfanne='crêpe pan',
    Stielkasserolle='saucepan', Schneebesen='whisk', Suppenkelle='ladle', Ansage='announcement',
    Apartment='apartment', Arzt='doctor', Ausländer='foreigner', Aussage='statement', Beamte='civil servant',
    Beispiel='example', CD='CD', Durchsage='announcement (PA)', Ergebnis='result', Erwachsene='adult (m.)',
    Fax='fax', Job='job', Jugendliche='teenager (m.)', Karte='card; ticket; map', Kunde='customer',
    Lehrer='teacher', Lkw='truck, lorry', Lösung='solution', Oma='grandma', Opa='grandpa', Plan='plan',
    Schüler='pupil, student', Student='(university) student', Teil='part', Verkäufer='salesperson',
    Verwandte='relative (m.)', Zigarette='cigarette', Nachbar='neighbour', Partner='partner (m.)',
    Partnerin='partner (f.)', Person='person', Stadtplan='city map')
for n in nouns.values():
    n['en'] = n['en'] or EN_FILL.get(n['w'], '')

# docx English beats Goethe-only nouns; drop nouns with no plural info and no English
noun_list = [n for n in nouns.values() if n['p'] is not None or n['en']]
for n in noun_list:
    if n['p'] is None:
        n['p'] = ''
        n['np'] = 1  # plural unknown -> excluded from plural drill

data = dict(nouns=noun_list, verbs=list(verbs.values()), vocab=vocab, phrases=phrases,
            verbprep=verbprep, adjprep=adjprep, antonyms=antonyms, cloze=cloze)
(HERE / 'data.js').write_text('window.DATA=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
print({k: len(v) for k, v in data.items()},
      'nouns with plural:', sum(1 for n in noun_list if not n.get('np')),
      'nouns with English:', sum(1 for n in noun_list if n['en']))
