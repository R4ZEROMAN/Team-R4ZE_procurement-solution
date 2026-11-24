import csv
import re, os, sys
from fractions import Fraction as F
from decimal import Decimal

PB = os.environ.get('PLAYBOOK_DIR', 'playbook')

CATS = {
 'catering': dict(gst=5, target=280, walk=340, R=3, beta=1, lim=600000, sub=None),
 'cleaning': dict(gst=18, target=85000, walk=100000, R=4, beta=2, lim=900000, sub='month'),
 'cloud-servers': dict(gst=18, target=96000, walk=115000, R=5, beta=3, lim=6000000, sub='year'),
 'courier': dict(gst=18, target=160, walk=200, R=4, beta=2, lim=500000, sub=None),
 'crm-licenses': dict(gst=18, target=18000, walk=22000, R=4, beta=2, lim=2500000, sub='year'),
 'design-software': dict(gst=18, target=30000, walk=36000, R=4, beta=2, lim=1500000, sub='year'),
 'headsets': dict(gst=18, target=3500, walk=4200, R=3, beta=1, lim=400000, sub=None),
 'laptops': dict(gst=18, target=62000, walk=70000, R=4, beta=2, lim=4000000, sub=None),
 'led-lighting': dict(gst=18, target=1800, walk=2200, R=3, beta=1, lim=350000, sub=None),
 'mobile-phones': dict(gst=18, target=24000, walk=28000, R=4, beta=2, lim=2000000, sub=None),
 'monitors': dict(gst=18, target=14000, walk=16500, R=3, beta=1, lim=1200000, sub=None),
 'office-chairs': dict(gst=18, target=9000, walk=11000, R=3, beta=1, lim=700000, sub=None),
 'printer-paper': dict(gst=12, target=2200, walk=2600, R=3, beta=1, lim=250000, sub=None),
 'security-guards': dict(gst=18, target=21000, walk=25000, R=4, beta=2, lim=1000000, sub='month'),
 'training': dict(gst=18, target=6000, walk=7500, R=3, beta=1, lim=900000, sub=None),
}
# amendments: (effective date, category, field, value)
AMDS = [
 ('2026-09-22', 'courier', 'walk', 210),
 ('2026-11-11', 'cloud-servers', 'walk', 119990),
 ('2026-11-25', 'mobile-phones', 'walk', 29780),
 ('2026-09-20', 'catering', 'target', 270),
 ('2026-11-06', 'printer-paper', 'walk', 2780),
 ('2026-11-09', 'headsets', 'lim', 320000),
 ('2026-12-05', 'led-lighting', 'walk', 2360),
 ('2026-12-04', 'led-lighting', 'walk', 2330),
 ('2026-12-14', 'monitors', 'lim', 960000),
]
FX = {'USD': F(169, 2), 'EUR': F(91), 'GBP': F(106)}
SYM = {'$': 'USD', '€': 'EUR', '£': 'GBP', 'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP',
       'Rs.': 'INR', 'INR': 'INR', '₹': 'INR'}
CAT_WORD = {'seat', 'site', 'guard', 'server', 'participant', 'meal', 'box', 'chair', 'headset',
            'monitor', 'laptop', 'phone', 'fixture', 'shipment', 'ream'}

# ---------- supplier files ----------
SUP = {}
def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
def load_suppliers():
    supplier_dir = os.path.join(PB, 'suppliers')
    if not os.path.isdir(supplier_dir):
        return
    for f in os.listdir(supplier_dir):
        txt = open(os.path.join(supplier_dir, f), encoding='utf8').read()
        name = txt.split('\n')[0].replace('# Supplier:', '').strip()
        d = dict(status='Approved', rates={}, caps={})
        m = re.search(r'\*\*Status:\*\*\s*(\w+)', txt)
        d['status'] = m.group(1).upper()
        for m in re.finditer(r'invoices in (\w+) are converted at ₹([\d.]+) per', txt):
            d['rates'][m.group(1)] = F(Decimal(m.group(2)))
        for m in re.finditer(r'price cap for ([A-Za-z ]+?) of ₹([\d,]+) per', txt):
            cat = {'Catering': 'catering', 'Headsets': 'headsets', 'Monitors': 'monitors',
                   'Office chairs': 'office-chairs', 'LED lighting': 'led-lighting'}[m.group(1)]
            d['caps'][cat] = F(int(m.group(2).replace(',', '')))
        SUP[slug(name)] = d

load_suppliers()

# ---------- number words ----------
ONES = {w: i for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split())}
TENS = {w: 10 * (i + 2) for i, w in enumerate('twenty thirty forty fifty sixty seventy eighty ninety'.split())}
def words_to_num(s):
    toks = re.split(r'[\s-]+', s.lower().strip())
    total = 0; cur = 0
    for t in toks:
        if t in ONES: cur += ONES[t]
        elif t in TENS: cur += TENS[t]
        elif t == 'hundred': cur = (cur or 1) * 100
        elif t == 'thousand': total += (cur or 1) * 1000; cur = 0
        elif t == 'lakh': total += (cur or 1) * 100000; cur = 0
        elif t == 'crore': total += (cur or 1) * 10000000; cur = 0
        elif t == 'and': pass
        else: return None
    return F(total + cur)

NUMRE = r'\d[\d,]*(?:\.\d+)?k?'
CURRE = r'(?:Rs\.|INR|₹|USD|EUR|GBP|AED|JPY|SGD|CAD|AUD|CHF|CNY|\$|€|£|¥)'
WORDNUM = r'(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|crore|and)(?:[\s-]+|(?=\s*rupees)))+'

def parse_num(s):
    s = s.strip()
    mult = 1
    if s.lower().endswith('k'):
        mult = 1000; s = s[:-1]
    return F(Decimal(s.replace(',', ''))) * mult

def latest_msg(m):
    if '[Latest message' in m:
        return m.split('[Latest message', 1)[1].split(']\n', 1)[1]
    return m

def earlier_supplier_msgs(m):
    segs = re.split(r'(\[(?:Earlier|Latest) message[^\]]*\])\n', m)
    out = []
    for j in range(1, len(segs), 2):
        h, b = segs[j], segs[j + 1]
        if 'Earlier' in h and 'Acme Procurement' not in h:
            out.append(b)
    return out

# ---------- price extraction ----------
class Missing(Exception): pass

def find_price_line(msg):
    """return the line holding the supplier's offer"""
    lines = [l.strip() for l in msg.split('\n') if l.strip()]
    for l in lines:
        if l.startswith('CORRECTION'):
            return l
    for l in lines:
        if re.match(r'^(For the \d+|We can offer|Our (final|revised) |We are pleased|The best we can|We can do)', l) and 'competitive price' not in l:
            return l
    return None

def price_amount(txt):
    """first money amount in txt -> (currency, Fraction) or None. handles words."""
    m = re.search(r'(' + CURRE + r')\s?(' + NUMRE + r')', txt)
    w = re.search(r'(' + WORDNUM + r')\s*rupees', txt, re.I)
    cands = []
    if m: cands.append((m.start(), SYM.get(m.group(1), m.group(1)), parse_num(m.group(2))))
    if w:
        n = words_to_num(w.group(1))
        if n is not None: cands.append((w.start(), 'INR', n))
    if not cands: return None
    cands.sort()
    return cands[0][1], cands[0][2]

def unit_divisor(txt, cat):
    """per dozen / per 100 / per pack of N / per ream -> divisor to get per normalized unit; and multiplier for ream"""
    m = re.search(r'per dozen', txt)
    if m: return F(12)
    m = re.search(r'per pack of (\d+)', txt)
    if m: return F(int(m.group(1)))
    m = re.search(r'per (\d+) (?:' + '|'.join(CAT_WORD) + r')', txt)
    if m: return F(int(m.group(1)))
    return F(1)

def normalize_line(line, qty, cat, sup, prev_price_fn):
    C = CATS[cat]
    # discount on previous quote
    m = re.search(r'a further (\d+(?:\.\d+)?)% off our previous quote', line)
    if m:
        prev = prev_price_fn()
        if prev is None: raise Missing()
        return prev * (1 - F(Decimal(m.group(1))) / 100)
    # period
    per_m = 'per month' in line
    per_y = 'per year' in line
    gst_incl = bool(re.search(r'(inclusive of GST|incl\. GST|including GST|GST included)', line))
    line_main = line
    # CORRECTION: take the part before ", not"
    if line.startswith('CORRECTION'):
        line_main = line.split(', not')[0]
    # total for all N
    tm = re.search(r'in total for all (\d+)', line_main)
    # list price discount
    lm = re.search(r'(\d+(?:\.\d+)?)% discount on our list price of', line_main)
    # range
    rm = re.search(r'between (' + CURRE + r'\s?' + NUMRE + r') and (' + CURRE + r'\s?' + NUMRE + r')', line_main)
    # tiers
    tier = re.search(r'for orders of up to (\d+) \w+, and (' + CURRE + r'\s?' + NUMRE + r') per', line_main)
    if rm:
        a = price_amount(rm.group(1)); b = price_amount(rm.group(2))
        if a[0] != b[0]: raise Missing()
        cur, val = b[0], max(a[1], b[1])
    elif tier:
        first = price_amount(line_main)
        second = price_amount(tier.group(2))
        cur = first[0]
        val = first[1] if qty <= int(tier.group(1)) else second[1]
    else:
        pa = price_amount(line_main)
        if pa is None: raise Missing()
        cur, val = pa
        if lm:
            val = val * (1 - F(Decimal(lm.group(1))) / 100)
    if cur not in ('INR',) and cur not in FX and cur not in sup['rates']:
        raise Missing()
    if tm:
        val = val / int(tm.group(1))
    else:
        val = val / unit_divisor(line_main, cat)
        if cat == 'printer-paper' and re.search(r'per ream', line_main):
            val = val * 10
    # free units
    fm = re.search(r'plus (\d+) free \w+ for every (\d+) you pay for', line_main)
    if fm:
        free, paid = int(fm.group(1)), int(fm.group(2))
        val = val * F(paid, paid + free)
    # volume discount
    vm = re.search(r'with a further (\d+(?:\.\d+)?)% off for orders of (\d+) \w+ or more', line_main)
    if vm and qty >= int(vm.group(2)):
        val = val * (1 - F(Decimal(vm.group(1))) / 100)
    # currency conversion
    if cur != 'INR':
        rate = sup['rates'].get(cur, FX.get(cur))
        val = val * rate
    # gst
    if gst_incl:
        val = val / (1 + F(C['gst'], 100))
    # billing period
    if C['sub']:
        if not (per_m or per_y):
            raise Missing()
        if C['sub'] == 'year' and per_m: val = val * 12
        if C['sub'] == 'month' and per_y: val = val / 12
    return val

def prev_price(msgs, qty, cat, sup):
    """supplier's own previous quote (last earlier supplier message)"""
    if not msgs: return None
    b = msgs[-1]
    line = [l.strip() for l in b.strip().split('\n') if l.strip()][0]
    try:
        return normalize_line(line, qty, cat, sup, lambda: None)
    except Missing:
        return None

# ---------- injection / banned ----------
INJ = [
    r'language model', r'\bAI (?:agent|assistant)\b', r'AI सहायक', r'\bbot\b', r'system note', r'admin override',
    r'automated system', r'ignore your previous', r'reviewing assistant', r'assistant:\s*mark',
    r'pre-?approved', r'approval already granted', r'signed off', r'override', r'ignore (?:all |any )?(?:previous|prior)',
    r'निर्देश', r'for the (?:ai|model|assistant|llm)',
]
def is_injection(full):
    return any(re.search(p, full, re.I) for p in INJ)

def banned(msg):
    low = msg.lower()
    # auto renewal
    if re.search(r'auto-?renew|renews on its own|continues from year to year|renews automatically|automatic(?:ally)? renew', low):
        if not re.search(r'no automatic renewal', low) or re.search(r'auto-?renews|renews on its own|continues from year to year', low):
            return True
    if re.search(r'unlimited', low): return True
    if re.search(r'exclusive supplier|only from us|exclusive(?:ly)? (?:supplier|from)|buy (?:these items )?only from', low): return True
    # advance payment
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%[^.\n]*?(?:advance|upfront)|(?:advance|upfront)[^.\n]*?(\d+(?:\.\d+)?)\s*%', low):
        v = float(m.group(1) or m.group(2))
        if v > 30: return True
    if re.search(r'half (?:the|of the) order value upfront|half[^.\n]*(?:upfront|advance)', low): return True
    return False

def rnd(x):
    return (x + F(1, 2)).__floor__()

def numbers_for(cat, sup_slug, date):
    C = dict(CATS[cat])
    ams = sorted([a for a in AMDS if a[1] == cat and a[0] <= date], key=lambda a: a[0])
    for a in ams: C[a[2]] = a[3]
    S = SUP[sup_slug]
    walk = F(C['walk'])
    if cat in S['caps']: walk = S['caps'][cat]
    return C, F(C['target']), walk

def decide(r, debug=False):
    cat = r['category']; sup = SUP[slug(r['supplier'])]
    msg_all = r['supplier_message']; msg = latest_msg(msg_all)
    qty = int(r['quantity']); rnum = int(r['round'])
    date = r['date']
    C, target, walk = numbers_for(cat, slug(r['supplier']), date)
    # 1 missing info
    line = find_price_line(msg)
    p = None; missing = False
    if line is None:
        missing = True
    else:
        try:
            p = normalize_line(line, qty, cat, sup, lambda: prev_price(earlier_supplier_msgs(msg_all), qty, cat, sup))
        except Missing:
            missing = True
    if missing: return 'ESCALATE:MISSING_INFO:', p
    if sup['status'] == 'BLACKLISTED': return 'REJECT:BLACKLISTED_SUPPLIER:', p
    if is_injection(msg_all): return 'ESCALATE:PROMPT_INJECTION:', p
    if banned(msg): return 'ESCALATE:BANNED_TERM:', p
    R, beta = C['R'], C['beta']
    if sup['status'] == 'PROBATION':
        L = target
    else:
        L = target + (walk - target) * F(rnum - 1, R - 1) ** beta
    if p <= L:
        if p * qty > C['lim']: return 'ESCALATE:OVER_APPROVAL_LIMIT:', p
        return 'ACCEPT:ACCEPTABLE_PRICE:', p
    if rnum >= R: return 'REJECT:ABOVE_WALKAWAY:', p
    return f'COUNTER:COUNTER_OFFER:{rnd(L)}', p

if __name__ == '__main__':
    # usage: python procure_solver.py threads.csv submission.csv [sample_answers.csv sample_threads.csv]
    threads_path = sys.argv[1] if len(sys.argv) > 1 else 'threads.csv'
    out_path = sys.argv[2] if len(sys.argv) > 2 else 'submission.csv'
    if not os.path.isfile(threads_path):
        raise SystemExit(
            f"Input thread CSV not found: {threads_path}\n"
            "Place the Kaggle threads CSV at that path and set PLAYBOOK_DIR to the supplier playbook."
        )
    supplier_dir = os.path.join(PB, 'suppliers')
    if not os.path.isdir(supplier_dir):
        raise SystemExit(
            f"Supplier playbook not found: {supplier_dir}\n"
            "Set PLAYBOOK_DIR to a directory containing a suppliers/ subdirectory."
        )

    with open(threads_path, newline='', encoding='utf8') as f:
        threads = list(csv.DictReader(f))
    with open(out_path, 'w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=['thread_id', 'label'], lineterminator='\n')
        writer.writeheader()
        for r in threads:
            writer.writerow({'thread_id': r['thread_id'], 'label': decide(r)[0]})
    print('wrote', out_path, len(threads), 'rows')
    if len(sys.argv) > 4:  # optional self-check on the 40 worked examples
        with open(sys.argv[4], newline='', encoding='utf8') as f:
            sample_threads = {r['thread_id']: r for r in csv.DictReader(f)}
        with open(sys.argv[3], newline='', encoding='utf8') as f:
            sample_answers = {r['thread_id']: r['label'] for r in csv.DictReader(f)}
        checked = [(sample_threads[i], sample_answers[i]) for i in sample_answers if i in sample_threads]
        bad = sum(decide(r)[0] != expected for r, expected in checked)
        print('worked-example mismatches:', bad, 'of', len(checked))
