"""Extractive policy and transcript answer formatting: exact source text only, never paraphrase.

summarize_policy keeps complete paragraphs (a lead-in stays with its list) and falls back to the
whole text whenever dropping a unit could remove a qualification, exception or cross-reference.
summarize_transcript groups exact turns by English/French cues; grouping is not a hardship decision.
"""
import re
import unicodedata

STOP={'the','and','for','are','can','how','may','who','why','not','our','you','any','its','has','was','did','does',
      'what','when','where','which','with','that','this','there','their','them','they','about','under','into','from',
      'have','will','would','should','must','could','many','much','policy','policies','customer','customers','agent',
      'agents','collection','collections','please','tell','explain','les','des','une','est','que','qui','pour','dans',
      'avec','sur','pas','quand','quel','quelle','comment','client','clients','politique'}
LIST_LINE=re.compile(r'^\s*(?:[-*+•]|\d+[.)]|[a-z][.)])\s',re.M)
QUALIFIER=re.compile(r"\b(?:unless|except\w*|exclud\w*|however|notwithstanding|subject to|provided that|only (?:if|when|where)"
                     r"|(?:does|do|shall|will) not apply|not eligible|not permitted|not allowed|should not|do not|don't|can't|never|no more than|at most|only|must not|may not|cannot|can not|shall not|prohibit\w*|sauf|a moins"
                     r"|toutefois|cependant|sous reserve|seulement si|uniquement si|ne s'applique pas|interdit\w*)\b")
BACKWARD=re.compile(r"\b(?:above|preceding|previous|foregoing|these|this section|ci-dessus|precedent\w*|notwithstanding"
                    r"|despite|nonobstant|malgre)\b|§")
FORWARD=re.compile(r'\b(?:below|following|ci-dessous|suivant\w*)\b')

CUSTOMER={'customer','client','cliente','cust','caller','debtor','borrower'}
AGENT={'agent','agente','collector','representative','rep','conseiller','conseillere','advisor'}
PAYMENT=re.compile(r'\b(?:pay|paying|payment|payments|paid|instal\w*|transfer|deposit|send|paiement\w*|payer|paierai\w*'
                   r'|paye|verse\w*|virement|depot|envoyer)\b')
COMMIT=re.compile(r"\b(?:i'll|i will(?! not)|i can(?!'t|not| not)|i could(?!n't| not)|i'm going to|i am going to|we'll"
                  r"|we will(?! not)|we can(?!'t|not| not)|je vais|je peux|je pourrai\w*|je paierai|on va|on peut)\b")
PROMISE=re.compile(r"\b(?:promise|commit\w*|je promets|je m'engage)\b")
NEG=re.compile(r"\b(?:can't|cannot|can not|couldn't|won't|will not|unable|not able|ne peux pas|ne pourrai pas"
               r"|pas les moyens|impossible)\b")
FINANCIAL=re.compile(r"\b(?:income|job|work|laid off|layoff|unemploy\w*|salary|wages?|paycheque|paycheck|payroll|hours"
                     r"|rent|mortgage|bills?|expenses?|medical|sick|illness|hospital|benefits?|ei|pension|budget|afford\w*"
                     r"|money|savings|debt|emploi|travail|salaire|paie|mise a pied|licenci\w*|chomage|loyer|hypotheque"
                     r"|factures?|depenses?|revenus?|heures|malad\w*|hopital|prestations?|argent|epargne|moyens)\b")
CONFIRM=re.compile(r"\b(?:confirm\w*|to recap|recap\w*|just to be clear|so you(?:'ll| will)|you(?:'ll| will) (?:pay|make|send)"
                   r"|i(?:'ve| have) (?:set up|scheduled|noted)|scheduled|reference number|pour confirmer|recapitul\w*"
                   r"|vous allez payer|vous paierez|j'ai (?:note|enregistre|programme))\b")
TITLES=[('financial','Customer circumstances (exact words; cues do not establish hardship)'),
        ('commitment','Payment commitments (exact customer words)'),
        ('other','Other customer statements (exact)'),
        ('agent','Agent confirmations (exact)')]


def _fold(text):
    text=unicodedata.normalize('NFKD',str(text).replace('’',"'"))
    return ''.join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text):return re.findall(r'[a-z0-9]+',_fold(text))


def _heading(unit):return all(l.lstrip().startswith('#') for l in unit.splitlines() if l.strip())


def _level(unit):return len(unit.lstrip())-len(unit.lstrip().lstrip('#'))


def _units(text):
    """Blank-line separated blocks; list blocks join the preceding lead-in so conditions stay attached."""
    parts=re.split(r'(\n(?:[ \t]*\n)+)',text);units=[]
    for k in range(0,len(parts),2):
        if not parts[k].strip():continue
        if units and LIST_LINE.match(parts[k]) and not _heading(units[-1]):units[-1]+=parts[k-1]+parts[k]
        else:units.append(parts[k])
    return units


def _scope(units,i):
    out=[]
    for j in range(i+1,len(units)):
        if _heading(units[j]) and _level(units[j])<=_level(units[i]):break
        out.append(j)
    return out


def _refers(unit,outward):
    body=_fold('\n'.join(l for l in unit.splitlines() if not l.lstrip().startswith('#')))
    # A forward reference inside a selected unit is satisfied when its list travels with it.
    return bool(BACKWARD.search(body) or FORWARD.search(body) and (outward or not LIST_LINE.search(unit)))


def summarize_policy(text,question):
    """Return complete source units relevant to the question, or the whole text when selection is unsafe."""
    text='' if text is None else str(text).replace('\r\n','\n').strip()
    if not text:return ''
    terms={w[:4] for w in _words(question or '') if len(w)>=3 and w not in STOP}
    units=_units(text);heads={i for i,u in enumerate(units) if _heading(u)}
    chosen=set()
    for i,u in enumerate(units):
        if terms and any(w.startswith(t) for w in _words(u) for t in terms):
            chosen.update(_scope(units,i) if i in heads else [i])
    chosen-=heads
    rest=[i for i in range(len(units)) if i not in chosen and i not in heads]
    if not chosen or not rest:return text
    section=lambda i:max([h for h in heads if h<i],default=-1)
    near={section(i) for i in chosen}
    if any(_refers(units[i],True) for i in rest) or any(_refers(units[i],False) for i in chosen):return text
    if any(QUALIFIER.search(_fold(units[i])) for i in rest):return text
    keep=chosen|{h for h in heads if chosen & set(_scope(units,h))}
    return '\n\n'.join(units[i] for i in sorted(keep))


def _stamp(turn):
    for key in ('start_sec','timestamp','ts','start','time'):
        value=turn.get(key)
        if value is not None and not isinstance(value,bool):
            return f'{value}s' if key=='start_sec' and isinstance(value,(int,float)) else str(value)
    return 'time n/a'


def summarize_transcript(turns):
    """Group exact customer/agent turns by cue, with original speaker labels and timestamps."""
    if isinstance(turns,dict):turns=turns.get('turns')
    if turns is None or isinstance(turns,(str,bytes)):turns=[]
    try:turns=list(turns)
    except TypeError:turns=[]
    groups={key:[] for key,_ in TITLES};omitted=0
    for turn in turns:
        if not isinstance(turn,dict) or not isinstance(turn.get('text'),str) or not turn['text'].strip():continue
        speaker=str(turn.get('speaker') or '').strip();role=_fold(speaker);said=_fold(turn['text'])
        line=f"- [{_stamp(turn)} {speaker}] {turn['text']}"
        if role in CUSTOMER:
            commitment=bool(PAYMENT.search(said) and (COMMIT.search(said) or PROMISE.search(said) and not NEG.search(said)))
            financial=bool(FINANCIAL.search(said) or PAYMENT.search(said) and NEG.search(said))
            if financial:groups['financial'].append(line)
            if commitment:groups['commitment'].append(line)
            if not financial and not commitment:groups['other'].append(line)
        elif role in AGENT:
            if CONFIRM.search(said):groups['agent'].append(line)
        else:omitted+=1
    lines=[]
    for key,title in TITLES:lines+=[title+':',*(groups[key] or ['- None found.'])]
    if omitted:lines.append(f'Turns not attributed to a customer or agent were omitted: {omitted}.')
    return '\n'.join(lines)
