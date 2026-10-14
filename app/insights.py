"""Local intent planner: fixed SQL templates, current sources, no answer lookup."""
import calendar
import csv
import io
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date,timedelta
from pathlib import Path

import duckdb
from rank_bm25 import BM25Okapi
from app.settings import SNAPSHOT
from app.metric_plans import CATALOG, PlanError, PlanRefusal, compile_plan
from app.gemini import ProviderUnavailable
from app.policy_summary import STOP, summarize_policy, summarize_transcript
from app.features import normalize_text

ASOF=date.fromisoformat(SNAPSHOT)
MONTHS={m.lower():i for i,m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower():i for i,m in enumerate(calendar.month_abbr) if m})
MONTHS.update({'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12})
RESOLVED="('kept','partially_kept','broken')"
CHANNEL='coalesce(h.channel_v2,h.channel)'
PROVINCE_NAMES={'ontario':'ON','quebec':'QC','québec':'QC','alberta':'AB','manitoba':'MB','saskatchewan':'SK','british columbia':'BC','nova scotia':'NS','new brunswick':'NB','newfoundland':'NL','labrador':'NL','prince edward island':'PE','yukon':'YT','northwest territories':'NT','nunavut':'NU'}


def province_filter(q):
    """Accept one positive province; clarify exclusions and combined regions."""
    provinces={code for name,code in PROVINCE_NAMES.items() if re.search(r'\b'+name+r'\b',q)}
    codes=r'(?:on|qc|ab|bc|mb|sk|ns|nb|nl|pe|yt|nt|nu)'
    for match in re.finditer(r'\b(?:in|from|provinces?)\s+('+codes+r'\b(?:\s*(?:,|/|&|\band\b|\bor\b)\s*'+codes+r'\b)*)',q):
        provinces.update(code.upper() for code in re.findall(r'\b'+codes+r'\b',match[1]))
    for name in PROVINCE_NAMES:
        for match in re.finditer(r'\b'+name+r'\s*(?:,|/|&|\band\b|\bor\b)\s*('+codes+r')\b',q):
            provinces.add(match[1].upper())
    if len(provinces)>1 or re.search(r'\b(toronto|halifax|montreal|montréal|winnipeg|vancouver|calgary|edmonton|ottawa)\b',q):
        raise PlanError('Only one province can be used as a filter. A named city or site needs clarification; request a single province or a supported grouping.')
    if provinces and re.search(r'\b(?:excluding|exclude|except|outside|without|other than|apart from|not in|not from)\b',q):
        raise PlanError('Province exclusions are unsupported. Request one included province or a supported grouping.')
    return {'province':provinces.pop()} if provinces else {}


def tokens(text):return re.findall(r'[a-z0-9]+',text.lower())


def month_mentions(q):
    return [m for m in re.finditer(r'\b('+('|'.join(sorted(MONTHS,key=len,reverse=True)))+r')\b',q)
            if m.group(0)!='may' or re.search(r'\b(in|for|during|of|end of|from|to|through)\s+may\b|\bmay\s+\d{1,4}\b|[-–]\s*may\b',q)]


def explicit_period(q):
    return bool(month_mentions(q) or re.search(r'\b20\d{2}\b|\bq[1-4]\b|last month|previous month|this month|this year|last year|since|year[- ]to[- ]date|\bytd\b|\b(last|past|previous|trailing|rolling)\b.*\b(days?|weeks?|months?|years?)\b',q))


def prior_broken_cohort(q):
    return bool(re.search(r'(?:previously|prior|previous)\s+broken\s+(?:promises?|ptps?)',q))


def thirty_day_cure(q):
    return 'cure' in q and bool(re.search(r'within\s+30\s+days?|30[- ]day\s+cure|cure.*in\s+30\s+days?',q))


def _cohort_guards(q,metric):
    """Apply the same explicit-cohort limits to local and provider plans."""
    if CATALOG.get(metric,{}).get('snapshot_only') and re.search(r'\bopened|\bopening',q):
        raise PlanError('Snapshot case/account metrics cannot substitute for an opening-date cohort.')
    if metric=='average_days_to_cure' and re.search(r'\bopened|\bopening|\bwithin\s+\d+\s+days?',q):
        raise PlanError('Average cure time uses cases curing in the period. Opening-date cohorts and maximum cure-time filters require a separate definition.')
    if metric=='sms_payment_link_click_share' and not re.search(r'\bclick\w*\b',q):
        raise PlanError('This metric measures clicked payment-link SMS sends. Other link shares or payment rates need a separate definition.')
    if metric not in ['delinquency_rate','write_off_rate'] and re.search(r'\bvisa|\bmastercard|\bamex|\b(?:cards?|loans?|mortgages?)\b|line[- ]of[- ]credit|credit lines?|late[- ]stage|early[- ]stage',q):
        raise PlanError('A named product or stage is a cohort filter. Request a supported grouping over the documented population.')
    if metric=='open_insolvency_cases' and re.search(r'bankrupt|consumer proposal',q):
        raise PlanError('The insolvency hold flag does not distinguish bankruptcy from consumer proposals. Ask for all open cases on insolvency hold.')
    remaining=q
    if metric=='open_insolvency_cases':remaining=re.sub(r'insolvency\s+hold','',remaining)
    if re.search(r'\bhold\b|deceased|cease[- ]contact|bankrupt|consumer proposal|\bvulnerab|\bcomplaint|\bfraud|\bdisput|\bprogramme?\b',remaining):
        raise PlanError('Additional hold, programme or sensitive case-status filters require a separately defined cohort.')
    if re.search(r'\b\d+\s*[-–]\s*\d+\s*(?:dpd|days|bucket)|\b(?:in|only|with)\b.{0,20}\bbucket\s+\d+',q):
        raise PlanError('A named DPD bucket is a filter rather than a grouping; this cohort requires a separate definition.')
    if metric in ['open_hardship_cases','open_insolvency_cases'] and re.search(r'\b(?:not|without|exclude|excluding|except|no)\b.{0,45}\b(?:hardship|insolvency|bankruptcy|hold)\b|\b(?:hardship|insolvency|bankruptcy|hold)\b.{0,25}\b(?:false|absent)\b',q):
        raise PlanError('This snapshot metric counts cases with the recorded flag. A negated or excluded flag requires a separately defined cohort.')
    if metric=='broken_promise_rate' and re.search(r'\bnumber of broken|\bhow many broken|\bcount.*broken',q) and not re.search(r'\brate\b|\bshare\b',q):
        raise PlanError('Please clarify whether you need a count or a broken-promise rate; this metric compiler returns the rate among resolved promises.')
    if metric not in ['hardship_rate','open_hardship_cases'] and re.search(r'\bhardship\b',q):raise PlanError('Filtering this metric to hardship cases/accounts requires a separately defined cohort; please clarify the source flag and population.')
    province_filter(q)
    if re.search(r'\b(?:for|among|only|with|without|excluding|exclude|where)\b.*\b(?:late[- ]stage|early[- ]stage|closed|certified|uncertified|french|english|mortgage|gold|platinum|silver|secured|unsecured|1\s*[-–]\s*30)\b',q):
        raise PlanError('The requested cohort filter is unsupported. Specify the metric population and a supported grouping without custom filters.')
    if re.search(r'\bopen\s+cases?\b',q) and metric not in ['open_cases','average_dpd','open_overdue_amount','open_hardship_cases','open_insolvency_cases']:
        raise PlanError('Filtering this metric to currently open cases is not part of its compiled definition; please clarify the intended cohort.')
    if metric=='cure_rate' and 'opened' in q:
        raise PlanError('The certified cure rate uses cases open at the start of a calendar period. For cases opened during a month, please specify the follow-up window, such as 30 days from opening.')
    if metric=='delinquency_rate' and re.search(r'loan|lending|all accounts|mortgage|lines? of credit|\bloc\b',q):
        raise PlanError('This snapshot calculation supports active card accounts. The lending extract has no authoritative active-status field for this denominator.')
    if metric=='delinquency_rate' and re.search(r'\b(?:[2-9]|\d{2,})\s*\+?\s*(?:days? past due|dpd)|\b90\+|\b30\+|\b60\+',q):
        raise PlanError('The certified delinquency rate is 1+ DPD. A different DPD threshold needs a separately defined metric.')
    if metric=='delinquency_rate':
        thresholds=re.findall(r'\b(\d+)\s*(?:\+|or more|and above)?\s*(?:days? past due|dpd)|\bdpd\s*[>=]{1,2}\s*(\d+)',q)
        if any(int(a or b)!=1 for a,b in thresholds):raise PlanError('The certified delinquency rate is 1+ DPD; other thresholds require a separately defined metric.')


def date_range(question):
    """Resolve explicit months/ISO dates and snapshot-relative months."""
    q=question.lower();years=re.findall(r'\b(20\d{2})\b',q);year=int(years[-1]) if years else ASOF.year
    if re.search(r'year[- ]to[- ]date|\bytd\b',q):return date(ASOF.year,1,1),ASOF+timedelta(days=1)
    if re.search(r'\b(last|past|previous|trailing|rolling)\b.*\b(days?|weeks?|months?|years?)\b',q) and not re.search(r'last month|previous month|last year|(?:last|past|previous|trailing|rolling)\s+12\s+months',q):
        raise PlanError('Use explicit start and end dates for rolling days, weeks or other relative periods.')
    iso=re.findall(r'\b20\d{2}-\d{2}-\d{2}\b',q)
    if iso:
        try:parsed=[date.fromisoformat(x) for x in iso]
        except ValueError:raise PlanError('Please use valid ISO calendar dates.') from None
        if len(parsed)==2:
            if parsed[0]>parsed[1]:raise PlanError('The period start must precede the end.')
            return parsed[0],parsed[1]+timedelta(days=1)
        if len(parsed)>2:raise PlanError('Please specify exactly two period endpoints.')
        if re.search(r'\bsince\b|\bfrom\b',q):return parsed[0],ASOF+timedelta(days=1)
        if re.search(r'\bon\b|\bas of\b',q):return parsed[0],parsed[0]+timedelta(days=1)
        raise PlanError('For a single date, specify on that date or since that date; otherwise provide two ISO endpoints.')
    month_pattern='|'.join(sorted(MONTHS,key=len,reverse=True))
    same_month=re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:and|to|through|[-–])\s*(\d{1,2})(?:st|nd|rd|th)?\s+('+month_pattern+r')\b',q)
    named=list(re.finditer(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+('+month_pattern+r')\b(?:\s+(20\d{2}))?',q))
    try:
        if same_month:
            first=date(year,MONTHS[same_month[3]],int(same_month[1]));last=date(year,MONTHS[same_month[3]],int(same_month[2]))
            if first>last:raise PlanError('The period start must precede the end.')
            return first,last+timedelta(days=1)
        if len(named)==2:
            first,last=[date(int(m[3]) if m[3] else year,MONTHS[m[2]],int(m[1])) for m in named]
            if first>last:raise PlanError('The period start must precede the end.')
            return first,last+timedelta(days=1)
        if len(named)>2:raise PlanError('Please specify exactly two period endpoints.')
        if named:
            m=named[0];first=date(int(m[3]) if m[3] else year,MONTHS[m[2]],int(m[1]))
            trailing=re.search(r'\b(\d{1,2})\s+months?\s+(?:to|ending|ended|through)\s+',q)
            if trailing:
                months=int(trailing[1])
                if months<1:raise PlanError('Use a positive number of months.')
                end=first+timedelta(days=1)
                ordinal=end.year*12+end.month-1-months
                past_year,past_month=divmod(ordinal,12);past_month+=1
                return date(past_year,past_month,min(end.day,calendar.monthrange(past_year,past_month)[1])),end
            if re.search(r'\bsince\b|\bfrom\b',q):return first,ASOF+timedelta(days=1)
            if re.search(r'\bon\b|\bas of\b|\bdue\b',q):return first,first+timedelta(days=1)
            raise PlanError('For a single named day, specify on that date or since that date, or supply both period endpoints.')
    except PlanError:raise
    except ValueError:raise PlanError('Please use valid calendar days for the requested period.') from None
    found=[(m.start(),MONTHS[m.group(0)]) for m in month_mentions(q)]
    if re.search(r'\b\d{1,2}\s+months?\s+(?:to|ending|ended|through)\s+',q):
        raise PlanError('For a trailing month window, specify the ending day as well as the month and year.')
    if len(set(years))>1:raise PlanError('For a period spanning different years, please provide two ISO date endpoints.')
    if re.search(r'\b(?:last|past|previous|trailing|rolling)\s+12\s+months\b',q):return date(ASOF.year-1,ASOF.month,ASOF.day)+timedelta(days=1),ASOF+timedelta(days=1)
    if 'last month' in q or 'previous month' in q:
        end=ASOF.replace(day=1);return (end-timedelta(days=1)).replace(day=1),end
    quarter=re.search(r'\bq([1-4])\b',q)
    if quarter:
        month=(int(quarter[1])-1)*3+1;start=date(year,month,1)
        end=date(year+1,1,1) if month==10 else date(year,month+3,1)
        return start,min(end,ASOF+timedelta(days=1))
    if len(found)>=2:
        start=date(year,found[0][1],1);last=found[-1][1]
        end=date(year+1,1,1) if last==12 else date(year,last+1,1)
        return start,min(end,ASOF+timedelta(days=1))
    if found and re.search(r'\bsince\b',q) and not re.search(r'\b(?:to|until|through)\b',q):
        return date(year,found[0][1],1),ASOF+timedelta(days=1)
    if found:
        month=found[0][1];end=date(year+1,1,1) if month==12 else date(year,month+1,1)
        return date(year,month,1),min(end,ASOF+timedelta(days=1))
    if 'last year' in q:return date(ASOF.year-1,1,1),date(ASOF.year,1,1)
    if years or 'this year' in q:return date(year,1,1),min(date(year+1,1,1),ASOF+timedelta(days=1))
    return ASOF.replace(day=1),ASOF+timedelta(days=1)


def template_cohort(q):
    """Questions with separately reviewed cohorts keep their explicit templates."""
    return bool(re.search(r'late[- ]fee|champion|challenger|randomi[sz]ed.*pilot|certified.*pilot|payroll|\broll\b|worse bucket',q)
        or ('broken' in q and prior_broken_cohort(q))
        or thirty_day_cure(q)
        or (re.search(r'outside|out[- ]of[- ]hours',q) and 'hours' in q)
        or (('paid' in q or 'collected' in q) and 'promise' in q)
        or (re.search(r'charged off|charge-off|write[- ]off',q) and not 'rate' in q)
        or ('open cases' in q and re.search(r'attempts|touches',q)))


def detect_metric(q,strict=True):
    if re.search(r'\b(?:sms|text messages?)\b',q) and re.search(r'payment[- ]?links?',q):
        if strict and not re.search(r'click',q):raise PlanError('Please specify clicked payment-link SMS share; other SMS link metrics need a separate definition.')
        return 'sms_payment_link_click_share'
    if re.search(r'average|mean',q) and re.search(r'days? (?:to|until|before) cure|time to cure|cure (?:time|duration)',q):return 'average_days_to_cure'
    if re.search(r'\bopen\b',q) and re.search(r'\bcases?\b',q) and re.search(r'\binsolvency\b|\bbankruptcy\b|consumer proposal',q) and re.search(r'how many|count|number|overdue',q):return 'open_insolvency_cases'
    if re.search(r'\bopen\b',q) and re.search(r'\bcases?\b',q) and re.search(r'\bhardship\b',q) and re.search(r'how many|count|number',q):return 'open_hardship_cases'
    if re.search(r'\bopen\b',q) and re.search(r'\bcases?\b',q) and re.search(r'overdue|past[- ]due amount',q) and re.search(r'total|sum|amount|balance|how much',q):return 'open_overdue_amount'
    if re.search(r'broken[- ]promise|broken.*ptp|ptp.*break|promise.*break|break(?:ing)? rate.*(?:ptp|promise)',q):return 'broken_promise_rate'
    if re.search(r'promise[- ]kept|ptp.*kept|kept.*promise|promise.*kept|keep rate',q):return 'promise_kept_rate'
    if 'cost' in q and re.search(r'rpc|right[- ]party|right party',q):return 'cost_per_rpc'
    if 'cost' in q and re.search(r'contact|channel|attempt',q):return 'cost_per_contact'
    if re.search(r'ptp rate|promise rate|promises taken per|ptp per rpc',q):return 'ptp_rate'
    if re.search(r'right[- ]party|right party|rpc rate|reach rate',q):return 'rpc_rate'
    if re.search(r'average.*(days past due|dpd)|mean dpd|average arrears age',q):return 'average_dpd'
    if re.search(r'delinquency rate|delinquent share|arrears rate',q) or ('past due' in q and re.search(r'share|active.*accounts',q)):return 'delinquency_rate'
    if 'cure rate' in q:return 'cure_rate'
    if re.search(r'write[- ]off rate|charge[- ]off rate|loss rate',q):return 'write_off_rate'
    if 'hardship' in q and re.search(r'rate|share',q) and 'interest' not in q:return 'hardship_rate'
    if re.search(r'attempts per case|contact intensity|touches per case',q):return 'contact_attempts_per_case'
    if re.search(r'how much.*\bcollect\b|dollars collected|recoveries|amount collected',q):return 'collected_amount'
    if 'cases' in q and re.search(r'\bopen\b',q) and re.search(r'how many|count|number',q):return 'open_cases'
    return None


DIM_NAMES='queue|bucket|province|product|channel|hour|site|month'
GROUP_DIMS=r'(?:'+DIM_NAMES+r')s?\b'


def requested_dimensions(q):
    """Dimensions named after by/each/per/across; None when no grouping is requested."""
    trigger=re.search(r'\bby\b|\b(?:each|every|per)\s+(?='+GROUP_DIMS+r')|\bacross\s+(?:all\s+)?(?:the\s+)?(?='+GROUP_DIMS+r')',q)
    if not trigger:return None
    clause=q[trigger.end():]
    found=[d for d,p in [('queue',r'\bqueues?\b'),('bucket',r'\bbuckets?\b'),('province',r'\bprovinces?\b'),('product',r'\bproducts?\b'),('channel',r'\bchannels?\b'),('hour',r'\bhours?\b'),('site',r'\bsites?\b')] if re.search(p,clause)]
    if re.match(r'\s*(?:calendar\s+)?months?\b',clause):found.append('month')
    return found


NUMBER_WORDS={'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'eighteen':18,'twenty-four':24,'twenty four':24}
WINDOW=r'\b(?:last|past|previous|trailing|rolling)\s+(\d{1,2}|'+'|'.join(NUMBER_WORDS)+r')\s+(?:calendar\s+|complete\s+|full\s+)?months\b'
TREND_DEFAULT_MONTHS=6


def trend_kind(q):
    if re.search(r'\bby\s+(?:calendar\s+)?months?\b|\bmonthly\b|\bmonth[- ](?:by|on|over)[- ]month\b|\b(?:per|each|every)\s+month\b|\btrend\w*\b|\bover\s+time\b|\bhow\s+(?:has|have|did)\b.*\bchang\w*',q):return 'explicit'
    return 'window' if re.search(WINDOW,q) else None


def trend_range(q):
    """Whole calendar months: last N complete months, an explicit period, or the default window."""
    window=re.search(WINDOW,q)
    if window:
        n=int(window[1]) if window[1].isdigit() else NUMBER_WORDS[window[1]]
        if not 1<=n<=36:raise PlanError('Monthly trends support 1 to 36 complete months.')
    elif explicit_period(q):return date_range(q)
    else:n=TREND_DEFAULT_MONTHS
    end=ASOF.replace(day=1);year,month=divmod(end.year*12+end.month-1-n,12)
    return date(year,month+1,1),end


RANK_WORDS={'highest':'desc','most':'desc','top':'desc','largest':'desc','biggest':'desc','greatest':'desc','maximum':'desc','lowest':'asc','least':'asc','fewest':'asc','bottom':'asc','smallest':'asc','minimum':'asc','best':'good','worst':'bad'}
RANK_DIMS=[('province',r'provinces?'),('queue',r'queues?'),('product',r'products?'),('bucket',r'buckets?'),('channel',r'channels?'),('site',r'sites?'),('hour',r'hours?'),('month',r'months?')]
PEOPLE=r'\b(?:agents?|collectors?|reps?|representatives?|employees?|staff(?: members?)?|team members?)\b(?!\s+sites?)'


def agent_ranking(q):
    """Individual agent performance is a people-management question, not a portfolio aggregate."""
    if not re.search(PEOPLE,q):return
    person=PEOPLE[2:]
    ranked=r'\b(?:rank\w*|leaderboard|scorecard|top|bottom|best|worst|highest|lowest|most|least|fewest|strongest|weakest|fastest|slowest|better|worse)\b'
    measure=r'\b(?:collect\w*|money|dollars?|amounts?|paid|payments?|promises?|ptps?|rpc|contacts?|calls?|cures?|cured|rates?|cases|performance|performing|results?|kpis?|productiv\w*|handle time|qa|scores?|complaints?|revenue|recover\w*|kept|broken|outcomes?)\b'
    which=re.search(r'\b(?:which|what|who(?:\s+(?:is|are|was|were))?)\s+(?:(?:the|our)\s+)?(?:\w+\s+)?'+person,q)
    adjacent=re.search(r'\b(?:top|bottom|best|worst|strongest|weakest|highest|lowest)(?:[- ]performing)?\s+(?:\d+\s+)?(?:performing\s+)?'+person,q)
    per=re.search(r'\b(?:per|by|each|every|individual)\s+'+person+r'|\bagent[- ]level\b|'+person+r'\s+(?:leaderboard|scorecard|ranking)',q)
    if (which and re.search(ranked,q)) or adjacent or (per and (re.search(measure,q) or detect_metric(q,strict=False))) or (re.search(r'\brank\w*\b',q) and re.search(measure,q)):
        raise PlanError('Individual agent performance rankings are not provided here: they are people-management information for team leads, and per-agent samples are small. I can compare sites, queues or channels instead.')


def ranking(q):
    """Return the requested ranking dimension/direction and the plain grouped question."""
    word=re.search(r'(?<!at )\b('+'|'.join(RANK_WORDS)+r')\b',q)
    verb=re.search(r'\b(?:rank(?:ed|ing)?|sort(?:ed)?)\b',q)
    if not word and not verb:return None
    pq=q.rstrip(' ?.!');dimension=None
    which=re.search(r'\b(?:which|what)\s+((?:[a-z]+\s+)?[a-z]+?)s?\s+(?:has|had|have|is|was|were|are|shows?|showed|gets?|got|sees?|saw|recorded|records|did|does|do|with|performs?|performed)\b',pq)
    if which and not re.search(r'\b(?:rate|share|percentage|number|amount|cost|value|metric|time|is|was|the)\b',which[1]):
        phrase=which[1]
        dimension=next((d for d,p in RANK_DIMS if re.search(r'\b'+p+r'\b',phrase)),None)
        if dimension is None:
            if re.search(r'customer|client|account|case|borrower|person|people',phrase):
                raise PlanError('Rankings of individual customers, accounts or cases are not provided. I can rank aggregate groups: province, queue, product, bucket, channel, site, hour or month.')
            raise PlanError(f'"{phrase}" is not a supported ranking group. Rankings are supported by province, queue, product, bucket, channel, site, hour or month, where the measure defines that grouping.')
        pq=pq[:which.start()]+' '+pq[which.end():]
    else:
        listed=re.search(r'\b(?:rank(?:ed|ing)?|sort(?:ed)?)\s+(?:the\s+|all\s+)?('+DIM_NAMES+r')s?\s+(?:by|on)\b',pq)
        if listed:
            dimension=listed[1]
            pq=pq[:listed.start()]+' '+pq[listed.end():]
        elif adjacent:=re.search(r'(?<!at )\b(?:'+'|'.join(RANK_WORDS)+r')\s+(?:\d+\s+)?(?:performing\s+)?('+DIM_NAMES+r')s?\b',pq) or re.search(r'\b('+DIM_NAMES+r')s?\s+(?:with|having|that has|that had)\s+(?:the\s+)?(?:'+'|'.join(RANK_WORDS)+r')\b',pq):
            dimension=adjacent[1];pq=pq[:adjacent.start()]+' '+pq[adjacent.end():]
        else:
            found=requested_dimensions(pq)
            if not found and word and detect_metric(q,strict=False) and re.search(r'\b(?:queue|bucket|province|product|channel|site)s?\b',pq):
                raise PlanError('Please say which grouping to rank, for example "Which queue has the highest cure rate in August 2026?"')
            if not found:return None
            if len(found)!=1:raise PlanError('Rankings use one grouping at a time: province, queue, product, bucket, channel, site, hour or month.')
            dimension=found[0]
    direction=RANK_WORDS[word[1]] if word else 'desc'
    pq=re.sub(r'(?<!at )\b(?:the\s+)?(?:'+'|'.join(RANK_WORDS)+r')\b|\b(?:rank(?:ed|ing)?|sort(?:ed)?)\b',' ',pq)
    if (requested_dimensions(pq) or [])!=[dimension]:pq+=' by '+dimension
    if not re.search(r'\b(?:rate|share|percent\w*|ratio|average|mean|cost|amount|total|overdue|balance|how many|number|count|per)\b',pq):pq='how many '+pq
    if re.search(r'\b(?:how many|number of)\s+(?:collections?\s+)?cases\b',pq) and not re.search(r'\bopen|\bclosed|\bcured|\bhardship|\binsolvency|\bbankrupt',pq):
        pq=re.sub(r'\b(how many|number of)\s+(?:collections?\s+)?cases\b',r'\1 open cases',pq)  # current caseload; open means no recorded outcome
    return {'dimension':dimension,'direction':direction,'word':word[1] if word else 'rank','question':re.sub(r'\s+',' ',pq).strip()}


# label, unit, value column, good direction, count noun (singular, plural) for counts
METRIC_INFO={
    'promise_kept_rate':('promise-kept rate','pct','promise_kept_rate_pct','up','What was the promise-kept rate{period}{group}?'),
    'broken_promise_rate':('broken-promise rate','pct','broken_rate_pct','down','What was the broken-promise rate{period}{group}?'),
    'rpc_rate':('right-party contact rate','pct','rpc_rate_pct','up','What was the right-party contact rate{period}{group}?'),
    'ptp_rate':('PTP rate','pct','ptp_rate_pct','up','What was the PTP rate{period}{group}?'),
    'cost_per_contact':('cost per contact','cad','cost_per_contact_cad','down','What was the cost per contact{period}{group}?'),
    'cost_per_rpc':('cost per right-party contact','cad','cost_per_rpc_cad','down','What was the cost per right-party contact{period}{group}?'),
    'hardship_rate':('hardship rate of cases opened','pct','hardship_rate_pct','down','What was the hardship rate of cases opened{period}{group}?'),
    'cure_rate':('cure rate','pct','cure_rate_pct','up','What was the cure rate{period}{group}?'),
    'average_dpd':('average days past due of open cases','days','avg_dpd','down','What is the average days past due of open cases{group}?'),
    'contact_attempts_per_case':('outbound attempts per contacted case','ratio','attempts_per_case','down','How many outbound attempts per case did we make{period}{group}?'),
    'delinquency_rate':('card delinquency rate (1+ DPD)','pct','delinquency_rate_pct','down','What is the card delinquency rate{group}?'),
    'write_off_rate':('write-off rate','pct','write_off_rate_pct','down','What was the write-off rate{period}{group}?'),
    'open_cases':('open cases','count','open_cases',None,'How many open cases are there{group}?'),
    'open_overdue_amount':('total overdue on open cases','cad','overdue_cad',None,'What is the total overdue on open cases{group}?'),
    'open_hardship_cases':('open cases with recorded hardship','count','open_hardship_cases',None,'How many open cases have recorded hardship{group}?'),
    'open_insolvency_cases':('open cases on insolvency hold','count','open_cases',None,'How many open cases are on insolvency hold{group}?'),
    'average_days_to_cure':('average days to cure','days','average_days_to_cure','down','What was the average days to cure for cases cured{period}{group}?'),
    'sms_payment_link_click_share':('share of payment-link SMS clicked','pct','sms_payment_link_clicked_pct','up','What share of SMS payment links were clicked{period}{group}?'),
}
COUNT_NOUNS={'resolved_promises':('resolved promise','resolved promises'),'attempts':('outbound call attempt','outbound call attempts'),'right_party_contacts':('right-party contact','right-party contacts'),
    'contacts':('contact','contacts'),'cases':('case opened','cases opened'),'cases_open_at_start':('case open at the start','cases open at the start'),'cases_with_dpd':('open case with DPD','open cases with DPD'),
    'contacted_cases':('contacted case','contacted cases'),'accounts':('account','accounts'),'cured_cases':('cured case','cured cases'),'payment_link_sms_sent':('payment-link SMS','payment-link SMS sends'),
    'open_cases':('open case','open cases'),'promises':('promise','promises'),'calls':('call','calls')}
SMALL_SAMPLE=30
PROVINCE_LABELS={'AB':'Alberta','BC':'British Columbia','MB':'Manitoba','NB':'New Brunswick','NL':'Newfoundland and Labrador','NS':'Nova Scotia','NT':'Northwest Territories','NU':'Nunavut','ON':'Ontario','PE':'Prince Edward Island','QC':'Quebec','SK':'Saskatchewan','YT':'Yukon'}
DIM_COLUMNS={'province':{'province_code','province'},'queue':{'queue'},'bucket':{'current_bucket','dpd_bucket'},'product':{'product','product_code','product_type','primary_product'},'channel':{'channel','ptp_channel'},'site':{'site','agent_site'},'hour':{'contact_hour_local'},'month':{'month'},'role':{'role'}}


def first_sentence(text):
    text=re.sub(r'\s+',' ',str(text or '')).strip()
    match=re.search(r'^(.+?[.!?])(?:\s|$)',text)
    return match[1] if match else (text+'.' if text else '')


QUESTION_STOP=STOP|{'can','we','is','a','an','to','of','on','in','it','be','do','i','someone','reason','allowed','per','long','get','or','if','at','by','as','me','us','last','long','some','say','says'}
SOURCE_LABELS=[('POL-','Policy'),('PRC-','Procedure'),('FAQ-','FAQ'),('HPT-','Programme terms'),('IR-','Incident report'),('SCR-','Call script'),('REG-','Regulatory summary'),('REL-','Release note'),('DC-','Data contract')]


def _stem(word):
    for suffix in ('ed','es','s'):
        if len(word)>len(suffix)+2 and word.endswith(suffix):word=word[:-len(suffix)];break
    return word[:-1] if len(word)>3 and word.endswith('e') else word


def _terms(text):return [_stem(w) for w in re.findall(r'[a-z0-9]+',text.lower()) if w not in QUESTION_STOP]


GENERIC_TERMS={_stem(w) for w in 'customer customers client clients contact contacts contacted payment payments pay paid agent agents call calls called phone collect collected collection collections account accounts case cases policy policies procedure procedures rule rules bank money need needs want get first today now exist exists available option options program programs programme programmes plan plans record records detail details information info email address name names number time day days week weeks month months year make take give show tell know use help happen happens allow allowed apply applies say says about thing things way ok okay please explain which what when where who why how contacting calling paying collecting asking'.split()}


def _source_sentences(text):
    """Exact source sentences: markdown emphasis removed, wrapped lines joined, headings/notes/questions skipped."""
    units,table=[],0
    for block in re.split(r'\n\s*\n',text):
        current=[]
        for line in block.splitlines():
            stripped=line.strip()
            if not stripped or stripped.startswith(('#','>')):continue
            if stripped.startswith('|'):
                table+=1;cells=[c.strip() for c in stripped.strip('|').split('|')]
                if table>1 and not all(re.fullmatch(r':?-+:?',c) for c in cells):units.append(' | '.join(cells))
                continue
            table=0
            if re.match(r'(?:[-*+•]|\d+[.)])\s',stripped):
                if current:units.append(' '.join(current))
                current=[re.sub(r'^(?:[-*+•]|\d+[.)])\s+','',stripped)]
            else:current.append(stripped)
        if current:units.append(' '.join(current))
    sentences=[]
    for unit in units:
        unit=re.sub(r'\*\*|__|`','',unit)
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])',unit):
            if len(sentence.split())>=4 and not sentence.endswith('?') and not (re.match(r'\w+:\s',sentence) and len(sentence.split())<6):sentences.append(sentence.strip())
    return sentences


def _match(a,b):return a==b or (min(len(a),len(b))>=4 and (a.startswith(b) or b.startswith(a)))


def policy_quote(question,sections):
    """The cited sentence that best matches the question (rarity-weighted terms and in-order pairs, primary section first, ties to the shorter); never paraphrased."""
    wanted=list(dict.fromkeys(_terms(question)));ordered=_terms(question)
    candidates=[(section,sentence,_terms(sentence)) for section in sections for sentence in _source_sentences(summarize_policy(section['text'],question))]
    if not candidates or not wanted:return None
    has=lambda w,terms:any(_match(w,t) for t in terms)
    parts=re.split(r'(?<=[.!?])\s+',question.strip());focus=set(_terms(parts[-1])) if len(parts)>1 else set()
    # Rare terms weigh more; terms in the closing question (after any context sentence) weigh 1.5x.
    weight={w:math.log(1+len(candidates)/max(1,sum(has(w,c[2]) for c in candidates)))*(1.5 if w in focus else 1) for w in wanted}
    best=None
    for section,sentence,terms in candidates:
        hits=[w for w in wanted if has(w,terms)]
        if not hits:continue
        pairs=sum(weight[a]+weight[b] for a,b in set(zip(ordered,ordered[1:])) if any(_match(a,x) and _match(b,y) for x,y in zip(terms,terms[1:])))
        # Routing ranks the cited sections; the first is the primary authority.
        score=(round((sum(weight[w] for w in hits)+pairs)*(1.25 if section is sections[0] else 1),6),-len(terms))
        if best is None or score>best[0]:best=(score,section,sentence)
    if not best:return None
    _,section,sentence=best
    label=next((name for prefix,name in SOURCE_LABELS if section['id'].startswith(prefix)),'Source')
    text=f'{label} {section["id"]} v{section["version"]}'+('' if section['section']=='document' else f' {section["section"]}')+f': "{sentence}"'
    if re.search(r'reduced[- ]payment|hp-loan-red3',question.lower()) and re.search(r'how long|\blast\b|duration|how many months',question.lower()):
        text+=' FAQ-COLL-001 Q1 says 6 months; that conflicts with this policy and is not followed.'
    return text


def _num(value):
    if isinstance(value,bool):return str(value).lower()
    if isinstance(value,int):return f'{value:,}'
    if isinstance(value,float):return f'{value:,.2f}'.rstrip('0').rstrip('.')
    return str(value)


def _value(value,unit):
    if value is None:return 'not available'
    if unit=='pct':return _num(value)+'%'
    if unit=='cad':return f'${value:,.2f}'
    if unit=='days':return _num(value)+' days'
    return _num(value)


def _day(d):return f'{d.day} {calendar.month_name[d.month]} {d.year}'


def _month(label):
    try:year,month=str(label).split('-');return f'{calendar.month_name[int(month)]} {year}'
    except ValueError:return str(label)


def _group(value,column=''):
    if value is None:return 'unknown'
    if column in ('province_code','province') and value in PROVINCE_LABELS:return f'{PROVINCE_LABELS[value]} ({value})'
    if column=='month':return _month(value)
    if column=='contact_hour_local':return f'hour {value}:00'
    return str(value).replace('_',' ')


def period_label(meta,metric=None):
    try:start,end=date.fromisoformat(meta['start_date']),date.fromisoformat(meta['end_date'])
    except (KeyError,TypeError,ValueError):return ''
    if CATALOG.get(metric,{}).get('snapshot_only') or (start,end)==(ASOF,ASOF+timedelta(days=1)):return f'as of {_day(ASOF)}'
    last=end-timedelta(days=1)
    if start.day==1 and (start.year,start.month)==(last.year,last.month):
        return f'in {calendar.month_name[start.month]} {start.year}'+('' if end.day==1 else f' (to {_day(last)})')
    if (start.month,start.day)==(1,1) and start.year==last.year and (end==date(start.year+1,1,1) or end==ASOF+timedelta(days=1)):
        return f'in {start.year}'+('' if end.month==1 and end.day==1 else f' (to {_day(last)})')
    return f'from {_day(start)} to {_day(last)}'


def _count_text(row,columns,value_column):
    index=columns.index(value_column)+1 if value_column in columns else 2
    if index>=len(columns) or not isinstance(row.get(columns[index]),(int,float)) or isinstance(row.get(columns[index]),bool):return '',None
    column=columns[index];count=row[column];one,many=COUNT_NOUNS.get(column,(column.replace('_',' '),column.replace('_',' ')))
    return f'{_num(count)} {one if count==1 else many}',count


def _known(rows,group):return [r for r in rows if r.get(group) not in (None,'unknown','')]


def summarize(rows,meta,refused=None,clarification=None):
    """One plain-English sentence from computed rows; no model, no new numbers."""
    text=_summarize(rows,meta,refused,clarification)
    return text[:1].upper()+text[1:]


def _summarize(rows,meta,refused=None,clarification=None):
    if refused:return 'Not answered: '+first_sentence(refused)
    if clarification:return 'I need a clearer question: '+first_sentence(clarification)
    if not rows:return 'No records matched this question for the requested period.'
    meta=meta or {};columns=list(rows[0]);kind=meta.get('kind')
    if kind=='promise_count':
        status=meta['metric_id'].replace('_promises','');row=rows[0]
        return f"{_num(row[status+'_promises'])} promises due {period_label(meta)[3:] if period_label(meta).startswith('in ') else period_label(meta)} were {status.replace('_',' ')}, out of {_num(row['resolved_promises'])} resolved ({_value(row[status+'_rate_pct'],'pct')})."
    if kind=='hardship_programmes':
        names=', '.join(f"{r['program_name']} ({r['program_id']}, {r['duration_months']} month{'s' if r['duration_months']!=1 else ''})" for r in rows)
        scope=meta.get('products_label') or 'all products'
        return f"{len(rows)} hardship programme{'s are' if len(rows)!=1 else ' is'} available for {scope} as of {_day(ASOF)}: {names} (POL-COLL-004 §4.2, HPT-2026)."
    metric=meta.get('metric_id');grouping=meta.get('grouping','none');rank=meta.get('ranking')
    if kind=='count' or metric in METRIC_INFO:
        if kind=='count':
            label,unit,value_column,good={'customers':('customers','count','customers',None),'customers_with_open_cases':('customers with open cases','count','customers_with_open_cases',None),'agents':('active agents','count','active_agents',None)}[metric]
            period=f'as of {_day(ASOF)}'
        else:
            label,unit,value_column,good,_=METRIC_INFO[metric];period=period_label(meta,metric)
            if metric=='open_insolvency_cases' and value_column not in columns:value_column='overdue_cad'
            if value_column not in columns:value_column=columns[1 if grouping!='none' else 0]
        province=(meta.get('filters') or {}).get('province');site=(meta.get('filters') or {}).get('site')
        region=f' in {PROVINCE_LABELS.get(province,province)}' if province else f' at the {site} site' if site else ''
        if grouping=='none':
            row=rows[0];value=_value(row.get(value_column),unit);count,_n=_count_text(row,columns,value_column)
            if kind=='count':
                if metric=='agents':return f"{_num(row['active_agents'])} agents{region} are active, out of {_num(row['agent_records'])} agent records {period}."
                if metric=='customers_with_open_cases':return f'{value} customers{region} have at least one open collections case {period}.'
                return f'There are {value} customers{region} in the resolved C360 customer table {period}.'
            if metric=='open_insolvency_cases':return f"There are {_num(row.get('open_cases'))} open cases on insolvency hold{region} {period}, with {_value(row.get('overdue_cad'),'cad')} overdue."
            if metric=='open_overdue_amount':return f"Open cases{region} have {value} overdue in total {period} ({count})."
            if unit=='count':return f'There are {value} {label}{region} {period}.'
            return f'The {label}{region} {period} was {value}'+(f' ({count}).' if count else '.')
        group=columns[0]
        if grouping=='month' and not rank:
            known=[r for r in rows if r.get(value_column) is not None]
            if not known:return f'No {label} values were available by month.'
            first,last=known[0],known[-1]
            if len(known)==1:return f'The {label}{region} in {_month(first[group])} was {_value(first[value_column],unit)} (the only month with data in the period).'
            peak=max(known,key=lambda r:r[value_column]);low=min(known,key=lambda r:r[value_column])
            partial=' (latest month partial)' if meta.get('end_date')==(ASOF+timedelta(days=1)).isoformat() and str(last[group])==ASOF.strftime('%Y-%m') else ''
            return f'The {label}{region} moved from {_value(first[value_column],unit)} in {_month(first[group])} to {_value(last[value_column],unit)} in {_month(last[group])}{partial}; highest {_value(peak[value_column],unit)} in {_month(peak[group])}, lowest {_value(low[value_column],unit)} in {_month(low[group])} ({len(known)} months).'
        known=[r for r in _known(rows,group) if r.get(value_column) is not None] or [r for r in rows if r.get(value_column) is not None]
        if not known:return f'No {label} values were available by {grouping}.'
        if rank:
            top=known[0];direction=rank['direction'];count,n=_count_text(top,columns,value_column)
            word=('most' if direction=='desc' else 'fewest') if unit=='count' or kind=='count' else ('highest' if direction=='desc' else 'lowest')
            caution='; small sample, treat with caution' if n is not None and n<SMALL_SAMPLE and word in ('highest','lowest') else ''
            detail=f' ({count}{caution})' if count else ''
            ties=[r for r in known[1:] if r[value_column]==top[value_column]]
            if ties:
                names=[_group(r[group],group) for r in [top,*ties]]
                listed=', '.join(names[:-1])+' and '+names[-1] if len(names)<=4 else f'{len(names)} groups'
                return f'{listed} are tied for the {word} {label}{region} {period} at {_value(top[value_column],unit)}.'
            text=f'{_group(top[group],group)} has the {word} {label}{region} {period} at {_value(top[value_column],unit)}{detail}'
            if caution:
                solid=next((r for r in known if (_count_text(r,columns,value_column)[1] or 0)>=SMALL_SAMPLE),None)
                if solid:text+=f'; among groups with at least {SMALL_SAMPLE} {COUNT_NOUNS.get(columns[columns.index(value_column)+1],("","records"))[1]}, {_group(solid[group],group)} is {word} at {_value(solid[value_column],unit)} ({_count_text(solid,columns,value_column)[0]})'
            return text+'.'
        high=max(known,key=lambda r:r[value_column]);low=min(known,key=lambda r:r[value_column])
        return f'{label[0].upper()+label[1:]}{region} {period} by {grouping.replace("_"," ")}: highest {_group(high[group],group)} at {_value(high[value_column],unit)}, lowest {_group(low[group],group)} at {_value(low[value_column],unit)} ({len(rows)} groups).'
    # Reviewed fixed templates: describe the returned cells without inventing a definition.
    numeric=[c for c in columns if all(isinstance(r.get(c),(int,float)) and not isinstance(r.get(c),bool) for r in rows if r.get(c) is not None)]
    def cell(column,value):
        unit='pct' if column.endswith('_pct') else 'cad' if column.endswith('_cad') else None
        return _value(value,unit)
    def name(column):return re.sub(r'_(pct|cad)$','',column).replace('_',' ')
    if len(rows)==1:
        return 'Result: '+'; '.join(f'{name(c)} {cell(c,rows[0][c])}' for c in columns)+'.'
    group=columns[0];values=[c for c in numeric if c!=group]
    if not values:return f'{len(rows)} rows returned.'
    value=values[0];known=[r for r in rows if r.get(value) is not None]
    if len(rows)<=3:return f'{name(value).capitalize()} by {name(group)}: '+'; '.join(f'{_group(r[group],group)} {cell(value,r[value])}' for r in rows)+'.'
    high=max(known,key=lambda r:r[value]);low=min(known,key=lambda r:r[value])
    return f'{name(value).capitalize()} by {name(group)}: highest {_group(high[group],group)} at {cell(value,high[value])}, lowest {_group(low[group],group)} at {cell(value,low[value])} ({len(rows)} groups).'


SITES={'Calgary':'calgary','Halifax':'halifax','Montréal':'montr[eé]al','Toronto':'toronto','Windsor':'windsor','vendor':'vendor'}
PROVINCES=('AB','BC','MB','NB','NL','NS','NT','NU','ON','PE','QC','SK','YT')
CUSTOMER_PROVINCE="CASE upper(replace(trim(province),'.','')) WHEN 'ONT' THEN 'ON' WHEN 'ONTARIO' THEN 'ON' WHEN 'ALTA' THEN 'AB' WHEN 'ALBERTA' THEN 'AB' WHEN 'QUEBEC' THEN 'QC' WHEN 'QUÉBEC' THEN 'QC' WHEN 'PQ' THEN 'QC' WHEN 'MAN' THEN 'MB' WHEN 'SASK' THEN 'SK' WHEN 'NFLD' THEN 'NL' ELSE coalesce(upper(replace(trim(province),'.','')),'unknown') END"
PROGRAMME_PRODUCTS=[(r'credit cards?|\bcards?\b',['card']),(r'personal loans?',['personal_loan']),(r'(?:auto|car|vehicle) loans?',['auto_loan']),(r'lines? of credit|\blocs?\b|credit lines?',['loc']),(r'mortgages?',['mortgage']),(r'overdrafts?',['overdraft']),(r'\bloans?\b',['personal_loan','auto_loan'])]
PRODUCT_LABELS={'card':'cards','personal_loan':'personal loans','auto_loan':'auto loans','loc':'lines of credit','mortgage':'mortgages','overdraft':'overdrafts'}
WORK_QUEUE=r'\b(?:which|what)\s+(?:\w+\s+)?(?:customers|accounts|cases|clients|borrowers|debtors)\b.*\b(?:call|contact|phone|prioriti[sz]\w*|chase|work|reach)\w*\b|\bwho\s+(?:should|do|must|to)\s+(?:we\s+|i\s+)?(?:call|contact|prioriti[sz]e|chase|phone|work)\b|(?<!not )\b(?:call|contact|work)\s+(?:list|order)\b'
WORK_QUEUE_SUGGESTIONS=['How many open cases are there by bucket?','How many open cases have recorded hardship by queue?','What is the average days past due of open cases by queue?']
DEFAULT_SUGGESTIONS=['What was the promise-kept rate in August 2026 by queue?','Which province has the highest cure rate in August 2026?','How many open cases are there by bucket?']


def programme_intent(q):
    """List questions about available hardship programmes, not terms of a named programme."""
    product=any(re.search(p,q) for p,_ in PROGRAMME_PRODUCTS)
    named=re.search(r'\bprogramm?es?\b|\bprograms?\b|\b(?:plans?|options?|arrangements?)\b',q) and re.search(r'\bhardship\b|\brelief\b|\bassistance\b',q)
    listed=re.search(r'\bprogramm?es?\b|\bprograms?\b|\b(?:hardship|relief|payment)\s+(?:plans?|options?)\b|\boptions?\b',q) and product
    getting=re.search(r'\bwhat\s+(?:can|could)\s+(?:a|the|this)\s+customer\s+with\s+(?:an?\s+)?.+\b(?:get|have|receive|be offered)\b',q) and product
    return bool((named or listed or getting)
        and (product or re.search(r'\bavailable\b|\b(?:which|what)\b|\blist\b|\btypes? of\b|\bkinds? of\b',q))
        and not re.search(r'how long|duration|\blast\b|income|evidence|how much|share of|how many|\brate\b|\bcount\b|before asking|\bcases?\b|\bstop\b|\bmust\b|\bshould\b|\brequire\w*|\bspecialists?\b|\breview\w*',q))



@dataclass
class Plan:
    sql:str
    params:list
    note:str=''
    metadata:dict=None


class InsightEngine:
    def __init__(self,db_path,dataset_root,planner=None):
        self.db_path=Path(db_path).resolve();self.dataset_root=Path(dataset_root).resolve()
        self.planner=planner
        self.sections=self._documents()
        self.index=BM25Okapi([tokens(x['text']) for x in self.sections]) if self.sections else None

    def _documents(self):
        path=self.dataset_root/'data/reference_documents.csv'
        if not path.exists():return []
        sections=[]
        with path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row['superseded_by'] or row['effective_date']>SNAPSHOT:continue
                file=(self.dataset_root/'files'/row['file_path']).resolve()
                if not file.is_relative_to((self.dataset_root/'files/docs').resolve()) or not file.exists():continue
                text=file.read_text(encoding='utf-8')
                if not re.search(r'^## ',text,flags=re.M):
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':'document','text':text.strip(),'path':file.relative_to(self.dataset_root).as_posix()})
                for part in re.split(r'(?=^## )',text,flags=re.M):
                    heading=part.splitlines()[0] if part.splitlines() else ''
                    if not heading.startswith('## '):continue
                    section=re.search(r'(§[\d.]+|Q\d+)',heading)
                    sections.append({'id':row['doc_id'],'version':row['version'],'type':row['doc_type'],'language':row['language'],'section':section.group(0) if section else heading,'text':part.strip(),'path':file.relative_to(self.dataset_root).as_posix()})
        return sections

    def _connect(self):
        c=duckdb.connect(str(self.db_path),read_only=True)
        c.execute("SET memory_limit='1GB'");c.execute('SET threads=2')
        trusted=str(self.dataset_root/'data').replace("'","''")
        if c.execute("SELECT current_setting('enable_external_access')").fetchone()[0]:
            c.execute(f"SET allowed_directories=['{trusted}/']")
            c.execute('SET enable_external_access=false')
        return c

    @staticmethod
    def _refusal(q):
        q=normalize_text(q)
        if re.search(r'weather|forecast.*(toronto|tomorrow)|sports|bitcoin|stock price',q):return 'This question is outside the collections dataset and policies.'
        if re.search(r'\b(sue|lawsuit|legal advice)\b',q):return 'I cannot give a legal decision about suing a customer. Refer the case to the authorized legal/compliance team.'
        protected=re.search(r'\b(gender|marital|citizenship|newcomer|household|ethnic\w*|religion|religious|church|mosque|synagogue|temple|faith|accent|disability|accessibility|age|race|sex|nationality|immigrants?|indigenous|seniors?|elderly|pregnan\w*|genetic\w*|women|men|sexe|origine|handicap)\b|national origin|sexual orientation|family status|mental health|postal code|neighbou?rhood|surname|etat civil|customers?\s+(?:over|under|older than|younger than)\s+\d+',q)
        decision=r'\brank|prioriti[sz]|\btarget|\bexclude|\bdeny|\blist|\bexport|\bshow|\bby\b|call.*(?:first|last|later)|\bdisclose|\brepayment\b|pay.*(?:reliab|predict)|\bscore|\bsegment|\bweight|\bskip|\bavoid|\bremove|deprioriti|prioriser|cibler|exclure|refuser|\bselon\b|\bpar\b'
        if protected and re.search(decision,q):return 'Protected attributes and proxies such as religious attendance cannot be used to predict repayment, prioritize calls, make collection decisions or disclose individual sensitive attributes.'
        language_decision=r'\brank|prioriti[sz]|\btarget|\bexclude|\bdeny|call.*(?:first|last|later)|\brepayment\b|pay.*(?:reliab|predict)|\bscore|\bsegment|\bweight|\bskip|\bavoid|\bremove|deprioriti|prioriser|cibler|exclure|refuser'
        if re.search(r'\b(language|langue|french|english|francophone|anglophone)\b',q) and re.search(language_decision,q):return 'Language cannot be used to predict repayment, rank customers or make collection decisions.'
        if re.search(r'\bvulnerab\w*\b',q) and re.search(r'\bbottom\b|deprioriti[sz]|lower.*priority|less.*priority|prioriti[sz].*(?:call|repay)|predict.*(?:pay|repay)|rarely pay|\bskip|call.*last|remove.*dial',q):return 'Vulnerability is a safeguard, not a repayment risk factor. Do not deprioritize support or use vulnerability to predict repayment; route to a certified agent under POL-COLL-004 v4.2 §4.5.'
        if re.search(r'(stop|exclude|deny|withdraw|withhold).*hardship|hardship.*(stop offering|exclude|deny)|(?:do not|don.t|never|avoid)\s+(?:offer|provide|give)\b.*hardship',q):return 'Hardship support cannot be denied using geography or a proxy for protected grounds.'
        if re.search(r'\b(export|list|give|show)\b',q) and re.search(r'\b(every|all)\b',q) and re.search(r'\b(phone|email|address|names)\b|date of birth|\bdob\b',q):return 'Bulk export of customer identifiers and contact details is not permitted.'
        detail=r"phone(?:\s+numbers?)?|e-?mail(?:\s+address)?|(?:home\s+|mailing\s+)?address|\bname\b|surname|\bsin\b|social insurance number|date of birth|\bdob\b|birthday|account numbers?|card numbers?|contact (?:details|info\w*)|details|record|profile|postal code|balance"
        named=(re.search(r'(?:'+detail+r')\b.{0,25}\b(?:of|for)\s+(?:the\s+)?customer\s+(?!(?:with|who|in|that|on|at|whose|are|is|has|have|named|complaints?|cases?|accounts?|service|support|contact|consent|hardship|vulnerab\w*|segment\w*)\b)[a-z][\w-]*',q)
            or re.search(r"\bcustomer\s+[a-z][\w-]*(?:\s+[a-z]+)?['’]s\s+(?:"+detail+')',q))
        if (re.search(r'\b(?!hpt-)[a-z]{3}-\d{4}\b',q) and re.search(detail+r'|\bcustomer\b',q)) or named:
            return 'Individual customer details are shown on the Customers page, where access is checked for your role.'
        pii=r"(?:phone|telephone|mobile|cell(?:phone)?|contact)\s*(?:numbers?|details|info\w*)|\be-?mails\b|\be-?mail\s+address(?:es)?|\baddress(?:es)?\b|\bnames\b|\bsurnames?\b|\bsins?\b|social insurance numbers?|dates?\s+of\s+birth|\bdobs?\b|birthdays?|\b(?:account|card|chequing|bank)\s+numbers?|postal codes?"
        people=r'(?:customers|clients|borrowers|debtors|customer|client|borrower)\b'
        requested=(re.search(r'(?:'+pii+r')\s+(?:\w+\s+){0,2}?(?:of|for|from|belonging to)\s+(?:\w+\s+){0,3}?'+people,q)
            or re.search(r"\b(?:customers?|clients?|borrowers?)(?:'s|')?\s+(?:"+pii+')',q)
            or (re.search(r'\bwho are (?:the|our|these|all)\s+(?:\w+\s+)?(?:customers|clients|borrowers)\b',q) and re.search(pii,q)))
        listed=re.search(r'\b(?:list|export|dump|download|pull)\s+(?:me\s+)?(?:the\s+|all\s+(?:the\s+)?|every\s+|of\s+)?(?:customers|clients|borrowers)\b|\b(?:give|show|send)\s+me\s+(?:a\s+list\s+of\s+|the\s+|all\s+(?:the\s+)?)?(?:customers|clients|borrowers)\s+(?:with|who|in|that|on)\b|\blist of (?:customers|clients|borrowers)\b',q)
        records=(re.search(r"\b(?:all|every|entire|full|whole)\s+(?:the\s+|our\s+)?customer(?:s|['’]s)?\s+(?:records?|data|details|profiles?|information|info|list|database|files?|names?|postal codes?|addresses|e-?mails|phones?)\b",q)
            or (re.search(r'spreadsheet|\bcsv\b|excel|\bfile\b|download|export',q) and re.search(r'\b(?:every|all|each)\s+customer',q)))
        if (requested or listed or records) and not re.search(r'^\s*(?:how many|what share|what percentage|what proportion|what fraction)\b|\bnumber of\b',q):
            return 'Bulk export of customer identifiers and contact details is not permitted.'
        if re.search(r'ignore.*(instruction|policy)|read_(csv|text|parquet)|/etc/|\b(attach|drop table|delete from|update .*set)\b',q):return 'This interface accepts collections questions, not commands, files or arbitrary SQL.'
        return None

    def answer(self,question,role='analyst'):
        start=time.perf_counter();q=question.strip();lower=q.lower()
        result={'answer':'','sql_or_sources':'','refused':False,'reason':None,'rows':[],'sources':[],'execution_ms':0,'snapshot_date':SNAPSHOT}
        reason=self._refusal(lower)
        if role not in ['analyst','supervisor']:reason='Portfolio questions require an analyst or supervisor. Use assigned-customer briefs.'
        rank=None;plan_q=lower
        if reason:result.update(answer=reason,refused=True,reason=reason)
        else:
            try:
                if re.search(r'\bCS-\d{4}-\d+\b',q,re.I) and re.search(r'summari[sz]|recorded call|resume|appel',lower):
                    self._transcript(q,result)
                elif programme_intent(lower):
                    self._programmes(lower,result)
                else:
                    if re.search(WORK_QUEUE,lower):
                        raise PlanError('Call order is set on the Work queue page, which orders assigned cases by fixed policy rules (holds, contact limits, promises due). This question box answers portfolio-level questions.')
                    agent_ranking(lower)
                    rank=ranking(lower);plan_q=rank['question'] if rank else lower
                    case_count=bool(re.search(r'\bcases?\b',plan_q) and re.search(r'how many|count|number|total|how much',plan_q))
                    policy_first=not case_count and bool(re.search(r'grace period|(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken|express consent|national do not call|consumer proposal',plan_q) or (re.search(r'\bpolicy|procedure|programme|program\b',plan_q) and not re.search(r'\brate\b|\bshare\b|\baverage\b',plan_q)))
                    plan=None if policy_first else self._plan(plan_q)
                    if plan is None and not policy_first and self.planner:
                        try:
                            plan=compile_plan(self.planner(q,CATALOG))
                        except ProviderUnavailable:
                            pass  # Optional provider failures keep local retrieval available.
                        except PlanError as exc:
                            if isinstance(exc,PlanRefusal):result.update(answer=str(exc),refused=True,reason='provider_refusal')
                            else:
                                self._policy(lower,result)
                                if not result.get('sources'):result.update(answer='Please specify a supported collections metric, grouping and period, or a policy topic.',refused=False,reason='clarification_required')
                    if plan:
                        self._verify(plan,plan_q,rank)
                        self._execute(plan,result,rank,plan_q)
                    elif rank and not result['answer']:
                        raise PlanError('Rankings are available for the supported collections measures (rates, costs, averages and open-case counts) by province, queue, product, bucket, channel, site, hour or month.')
                    elif not result['answer']:self._policy(lower,result)
            except PlanError as exc:
                result.update(answer=str(exc),reason='clarification_required')
            except (duckdb.Error,OSError,ValueError,KeyError) as exc:
                result['answer']='The requested result is currently unavailable. '+str(exc)[:400]
                result['reason']='execution_error';result['refused']=False
        if result['reason']=='clarification_required' and not result['refused']:
            result['suggestions']=self._suggestions(lower)
        result['summary']=self._summary(result,lower)
        result['execution_ms']=round((time.perf_counter()-start)*1000,2)
        return result

    @staticmethod
    def _verify(plan,q,rank=None):
        """A plan must preserve the requested metric cohort, province, period, grouping and ranking."""
        meta=getattr(plan,'metadata',None) or {}
        if meta and 'kind' not in meta:
            _cohort_guards(q,meta['metric_id'])
            if meta.get('filters',{})!=province_filter(q):
                raise PlanError('The validated plan does not preserve the requested province; please clarify the cohort.')
            if explicit_period(q):
                wanted=trend_range(q) if meta['grouping']=='month' else date_range(q)
                planned=(date.fromisoformat(meta['start_date']),date.fromisoformat(meta['end_date']))
                if wanted!=planned:raise PlanError('The validated plan does not preserve the requested period; please clarify the start and end dates.')
            grouping_question=re.sub(r'\bby\s+(?:sms|text(?: messages?)?)\b','via SMS',q) if meta['metric_id']=='sms_payment_link_click_share' else q
            if re.search(r'\bby\b',grouping_question):
                clause=re.split(r'\bby\b',grouping_question,maxsplit=1)[1]
                dimensions=[name for name in ['queue','bucket','province','product','channel','hour','site'] if re.search(r'\b'+name+r'\b',clause)]
                if re.match(r'\s*(?:calendar\s+)?months?\b',clause):dimensions.append('month')
                if len(dimensions)!=1:raise PlanError('Specify one supported grouping dimension.')
                wanted_group=dimensions[0]
                if wanted_group=='site' and meta['metric_id'] in ['rpc_rate','ptp_rate','cost_per_contact','cost_per_rpc']:wanted_group='agent_site'
                if wanted_group!=meta['grouping']:raise PlanError('The validated plan does not preserve the requested grouping; please clarify the grouping.')
        if rank and meta:
            if meta.get('grouping') not in ({'site','agent_site'} if rank['dimension']=='site' else {rank['dimension']}):
                raise PlanError(f"This measure cannot be ranked by {rank['dimension']}; please choose one of its supported groupings.")
            metric=meta.get('metric_id');info=METRIC_INFO.get(metric)
            if info and rank['word'] in ('most','fewest','least') and info[1]!='count' and metric!='open_overdue_amount' and not re.search(r'\b(?:rate|share|percent\w*|ratio|average|mean|cost|per)\b',q):
                raise PlanError(f"'{rank['word'].capitalize()}' asks for a count, but the reviewed measure here is the {info[0]}, not a count. Ask for the highest or lowest {info[0]} instead.")
            if rank['direction'] in ('good','bad'):
                good=info[3] if info else None
                if good is None:raise PlanError('"Best" and "worst" are ambiguous for this measure; ask for the highest or lowest value instead.')
                rank['direction']='desc' if (rank['direction']=='good')==(good=='up') else 'asc'

    def _execute(self,plan,result,rank=None,q=''):
        with self._connect() as c:
            cursor=c.execute(plan.sql,plan.params);columns=[x[0] for x in cursor.description]
            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
        meta=dict(getattr(plan,'metadata',None) or {})
        if rank:
            if rank['direction'] in ('good','bad'):raise PlanError('"Best" and "worst" are ambiguous for this result; ask for the highest or lowest value instead.')
            if not rows or columns[0] not in DIM_COLUMNS.get(rank['dimension'],set()):
                raise PlanError(f"This calculation does not provide a breakdown by {rank['dimension']}; please choose a supported grouping.")
            value=columns[1]
            if meta.get('metric_id')=='open_insolvency_cases' and not re.search(r'overdue|amount|balance|dollar',q):value='open_cases'
            # Full grouped table, best first; missing values last; stable by group name.
            rows.sort(key=lambda r:str(r[columns[0]]))
            rows.sort(key=lambda r:(r[value] is None,-(r[value] or 0) if rank['direction']=='desc' else (r[value] or 0)))
            if value!=columns[1]:columns=[columns[0],value,*[c for c in columns[1:] if c!=value]];rows=[{c:r[c] for c in columns} for r in rows]
            meta['ranking']={'dimension':rank['dimension'],'direction':rank['direction']}
        result['rows']=rows;buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=columns,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        result['answer']=buf.getvalue().strip()+('\n'+plan.note if plan.note else '')
        result['sql_or_sources']=plan.sql+'\nBound parameters: '+json.dumps(plan.params,default=str)
        result['sources']=sorted(set(re.findall(r'(?:curated|gold)\.([a-z_]+)',plan.sql)))
        if meta:result['plan']=meta

    def _summary(self,result,q):
        if result['refused']:return summarize(None,None,refused=result['answer'] or result['reason'])
        if result['reason']=='clarification_required':return summarize(None,None,clarification=result['answer'])
        if result['reason']=='execution_error':return 'The result is currently unavailable, so no number is shown.'
        if result.get('plan') or result['sql_or_sources'].startswith(('SELECT','WITH')):
            if result['rows'] or 'transcript_id' not in result['sql_or_sources']:
                return summarize(result['rows'],result.get('plan'))
        sources=[s for s in result['sources'] if isinstance(s,dict)]
        if sources and sources[0].get('transcript_id') or result['answer'].startswith('No recorded transcript'):
            return first_sentence(result['answer'].splitlines()[0])
        documents=[s for s in sources if s.get('document_id')]
        if documents:
            cited=[x for s in documents for x in self.sections if (x['id'],x['version'],x['section'])==(s['document_id'],s['version'],s['section'])]
            quote=policy_quote(q,cited)
            if quote:return quote
            return 'Answered from '+' and '.join(f"{s['document_id']} v{s['version']} {s['section']}" for s in documents)+'; the exact source text is quoted below.'
        return first_sentence(result['answer']) if result['answer'] else 'No answer was produced.'

    def _plan(self,q):
        q=q.lower()
        counted=self._count_plan(q) or self._promise_count_plan(q)
        if counted:return counted
        trend=trend_kind(q)
        if trend:
            planned=self._trend_plan(q,trend)
            if planned:return planned
        start,end=date_range(q);period=[start,end]
        if start>=end:raise PlanError('The requested period is reversed or falls after the dataset snapshot.')
        if re.search(r'\bpilot\b',q) and re.search(r'certified|randomi[sz]ed',q) and not ('certified' in q and 'cure' in q and 'hardship' in q):
            raise PlanError('The supported pilot comparison measures 30-day cure from first assignment on recorded-hardship cases, grouped by agent certification. Other pilot cohorts need clarification.')
        if re.search(r'champion|challenger',q) and not re.search(r'promise|ptp',q):raise PlanError('The supported randomized strategy comparison measures promise-kept rate; other strategy metrics need a defined cohort.')
        generic=self._generic_plan(q,start,end)
        if generic:return generic
        if 'late-fee' in q or 'late fee' in q:
            # Comparison uses explicit dates, prior interval has identical length.
            days=re.search(r'between (\d{1,2}) and (\d{1,2})',q)
            if not days:raise PlanError('Please specify the two days and month for the late-fee dispute comparison.')
            first=int(days[1]);last=int(days[2])
            if first>last:raise PlanError('The comparison end day must follow the start day.')
            try:a=start.replace(day=first);b=start.replace(day=last)+timedelta(days=1)
            except ValueError:raise PlanError('Please use valid calendar days for the comparison.') from None
            prior=a-(b-a)
            if b>ASOF+timedelta(days=1):raise PlanError('The requested dispute comparison extends beyond the dataset snapshot.')
            current_label=f'{a.day}-{(b-timedelta(days=1)).day} {calendar.month_abbr[a.month]}'
            previous_label=f'{prior.day}-{(a-timedelta(days=1)).day} {calendar.month_abbr[prior.month]}'
            return Plan("SELECT CASE WHEN contact_ts_local>=? THEN ? ELSE ? END period,count(*) disputes FROM curated.contact_history WHERE dispute_raised_flag AND contact_ts_local>=? AND contact_ts_local<? GROUP BY 1 ORDER BY 1",[a,current_label,previous_label,prior,b],'Counts use recorded dispute flags; the source does not supply a separate late-fee-only dispute category. Incident IR-2026-0914 describes the posting-delay context.')
        if ('broken' in q or 'break rate' in q) and ('promise' in q or 'ptp' in q):
            if prior_broken_cohort(q):
                dated=explicit_period(q)
                return Plan(f"SELECT least(prior_broken_ptp_count,3) prior_broken,round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay WHERE ptp_status IN {RESOLVED}"+(' AND ptp_due_date>=? AND ptp_due_date<?' if dated else '')+' GROUP BY 1 ORDER BY 1',period if dated else [],'prior_broken=3 means three or more; open/cancelled promises excluded. '+('Uses the requested due-date period.' if dated else 'Uses all resolved promises in the extract; no period was supplied.'))
            if 'site' in q:
                return Plan(f"SELECT coalesce(a.site,'self_serve') site,round(100.0*avg(CASE WHEN p.ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) promises FROM curated.promises_to_pay p LEFT JOIN curated.agents a USING(agent_id) WHERE p.ptp_due_date>=? AND p.ptp_due_date<? AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",period)
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='broken' THEN 1 ELSE 0 END),1) broken_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if re.search(r'average.*(days past due|dpd)|mean dpd',q):
            group='queue' if 'queue' in q else 'current_bucket' if 'bucket' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(avg(current_dpd),1) avg_dpd,count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(" GROUP BY 1 ORDER BY 1" if group else ''),[])
        if re.search(r'\boutside\b|\bout[- ]of[- ]hours\b',q) and ('hours' in q or 'calling hours' in q):
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:customer )?province',q):raise PlanError('Out-of-hours calling supports grouping by customer province only.')
            return Plan(f"SELECT c.province_code,round(100.0*avg(CASE WHEN NOT h.within_permitted_hours_flag THEN 1 ELSE 0 END),2) out_of_hours_pct,count(*) calls FROM curated.contact_history h JOIN curated.collections_cases c USING(case_id) WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'cost' in q and ('rpc' in q or 'right-party' in q or 'right party' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(sum(h.contact_cost_cad)/nullif(sum(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),0),2) cost_per_rpc_cad FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('ptp rate' in q or 'promise rate' in q or 'promises taken per' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(100.0*sum(CASE WHEN h.ptp_made_flag THEN 1 ELSE 0 END)/nullif(count(*),0),2) ptp_rate_pct,count(*) right_party_contacts FROM curated.contact_history h WHERE h.rpc_flag AND {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if 'payroll' in q and ('delay' in q or 'late' in q or 'week' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError(f'This payroll calculation supports an ungrouped {SNAPSHOT} customer snapshot. Historical or grouped payroll cohorts need clarification.')
            open_filter="AND EXISTS(SELECT 1 FROM gold.cases c WHERE c.customer_id=x.customer_id AND c.outcome IS NULL)" if 'open' in q else ''
            return Plan(f"WITH payroll AS(SELECT x.customer_id,bool_or(a.payroll_delay_days>7) delayed FROM curated.deposit_accounts a JOIN gold.identity_crosswalk x ON x.source_system='core' AND x.status='matched' AND x.source_key=a.src_customer_ref WHERE a.product_type='chequing' AND a.payroll_deposit_flag AND a.snapshot_date=? {open_filter} GROUP BY 1) SELECT count(*) payroll_customers,count(*) FILTER(WHERE delayed) delayed_customers,round(100.0*avg(CASE WHEN delayed THEN 1 ELSE 0 END),2) payroll_delay_share_pct FROM payroll",[ASOF],'Uses accepted core-to-C360 matches; unresolved identities are excluded and reported in data quality.')
        if 'right-party' in q or 'right party' in q or 'rpc rate' in q:
            group='h.contact_hour_local' if 'hour' in q else CHANNEL if 'channel' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END),1) rpc_rate_pct,count(*) attempts FROM curated.contact_history h WHERE {CHANNEL}='call' AND h.direction='outbound' AND h.contact_ts_local>=? AND h.contact_ts_local<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period)
        if ('past due' in q and ('share' in q or 'delinquency' in q) or 'delinquency rate' in q) and not ('roll' in q or 'worse bucket' in q):
            table='card_accounts' if 'card' in q else 'loan_accounts';group='product_code' if table=='card_accounts' else 'product_type'
            active="account_status IN ('active','blocked')" if table=='card_accounts' else 'NOT coalesce(chargeoff_flag,false)'
            return Plan(f"SELECT {group},round(100.0*avg(CASE WHEN dpd>=1 THEN 1 ELSE 0 END),2) delinquency_rate_pct,count(*) accounts FROM curated.{table} WHERE snapshot_date=? AND {active} AND dpd IS NOT NULL GROUP BY 1 ORDER BY 1",[ASOF],'Accounts with missing DPD are excluded and counted in the data-quality checks.')
        if re.search(r'\bpaid\b|\bcollect(?:ed)?\b',q) and 'promise' in q and not ('kept' in q or 'rate' in q):
            if re.search(r'\bby\b',q):raise PlanError('The supported promise-payment total is ungrouped. Please request the total or clarify the required payment cohort.')
            return Plan('SELECT round(sum(amount_paid_against),2) collected_cad FROM curated.promises_to_pay WHERE paid_date>=? AND paid_date<?',period,'Payment amounts recorded against promises only; this does not include all collection-account payments.')
        if 'certified' in q and ('pilot' in q or 'random' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError('The supported pilot comparison uses all mature first assignments and groups only by agent certification; custom periods/groupings need clarification.')
            return Plan("""WITH first_assignment AS(SELECT case_id,certified_for_vulnerable_flag,assigned_ts,hardship_flag_at_assignment FROM curated.case_assignment_history WHERE assignment_method='randomised_pilot' QUALIFY row_number() OVER(PARTITION BY case_id ORDER BY assigned_ts,assignment_id)=1)
+SELECT a.certified_for_vulnerable_flag,round(100.0*avg(CASE WHEN c.cure_flag AND c.cure_date>=cast(a.assigned_ts AS DATE) AND c.cure_date<=cast(a.assigned_ts AS DATE)+30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM first_assignment a JOIN curated.collections_cases c USING(case_id) WHERE a.hardship_flag_at_assignment AND cast(a.assigned_ts AS DATE)<=? AND NOT coalesce(c.insolvency_hold_flag,false) AND NOT coalesce(c.deceased_hold_flag,false) GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[ASOF-timedelta(days=30)],'Observed 30-day cures measured from first randomized pilot assignment, when the certification treatment starts; only assignments with 30 observed days are included. Hardship is recorded at the first assignment. Current insolvency/deceased holds are excluded in line with the cure definition; historical hold status is unavailable. This descriptive comparison does not establish causality or customer eligibility.')
        if thirty_day_cure(q):
            if re.search(r'\bby\b|\bhardship\b|\b1\s*[-–]\s*30\b',q):raise PlanError('The 30-day opening cohort currently supports the ungrouped source population, excluding insolvency/deceased holds.')
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_flag AND days_to_cure<=30 THEN 1 ELSE 0 END),2) cure_30d_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<? AND case_open_date<=? AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',[*period,ASOF-timedelta(days=30)],'Cures within 30 days of opening; only cases with 30 observed days by the snapshot. Current insolvency/deceased holds excluded.')
        if 'cure rate' in q:
            return Plan('SELECT round(100.0*avg(CASE WHEN cure_date>=? AND cure_date<? THEN 1 ELSE 0 END),2) cure_rate_pct,count(*) cases_open_at_start FROM curated.collections_cases WHERE case_open_date<? AND (outcome_date>=? OR outcome IS NULL) AND NOT coalesce(insolvency_hold_flag,false) AND NOT coalesce(deceased_hold_flag,false)',[*period,start,start])
        if 'charged off' in q or 'charge-off' in q or 'write off' in q or 'write-off' in q:
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:primary )?product',q):raise PlanError('Charge-off counts and amounts support grouping by product only.')
            anchored=bool(re.search(r'\b\d{1,2}\s+months?\s+(?:to|ending|ended|through)\s+',q))
            trailing=not anchored and (bool(re.search(r'12\s+months|last year',q)) or not explicit_period(q))
            since=date(ASOF.year-1,ASOF.month,ASOF.day)+timedelta(days=1) if trailing else start
            until=ASOF if trailing else end-timedelta(days=1)
            return Plan("""WITH accounts AS(SELECT 'card' product,chargeoff_date,chargeoff_amount FROM curated.card_accounts UNION ALL SELECT product_type,chargeoff_date,chargeoff_amount FROM curated.loan_accounts)
+SELECT product,count(*) accounts,round(sum(chargeoff_amount),2) chargeoff_cad FROM accounts WHERE chargeoff_date>=? AND chargeoff_date<=? GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[since,until],f'Charge-off counts and amounts by product from {since} through {until}; this is not the write-off rate.')
        if ('roll' in q or 'worse bucket' in q):
            months=[MONTHS[m.group(0)] for m in re.finditer(r'\b('+('|'.join(sorted(MONTHS,key=len,reverse=True)))+r')\b',q)]
            if len(months)!=2:raise PlanError('Roll rate needs two explicit month-end snapshots and a starting DPD bucket.')
            first=date(start.year,months[0],calendar.monthrange(start.year,months[0])[1]);last=date(start.year,months[1],calendar.monthrange(start.year,months[1])[1])
            if first>=last or last>date(2026,6,30):raise PlanError('Available monthly snapshots end on 30 June 2026. Choose two ordered month ends within that coverage.')
            if not re.search(r'1\s*[-–]\s*30',q):raise PlanError('This roll-rate calculation supports accounts starting at 1–30 DPD. Please specify that cohort.')
            buckets=re.findall(r'\b(\d+)\s*[-–]\s*(\d+)\b',q)
            if any((a,b) not in [('1','30'),('31','60')] for a,b in buckets):raise PlanError('Supported roll destinations are any worse bucket, or specifically 31–60 DPD; other destinations need a reviewed cohort.')
            if re.search(r'\bby\b',q) and not re.search(r'\bby\s+(?:primary\s+)?product',q):raise PlanError('This roll-rate calculation supports grouping by product only.')
            destination='b.dpd BETWEEN 31 AND 60' if re.search(r'31\s*[-–]\s*60',q) else 'b.dpd>30'
            return Plan("""WITH s AS(SELECT account_id,product_type,coalesce(try_cast(month_end_date AS DATE),cast(try_strptime(month_end_date,['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE)) me,dpd FROM curated.account_monthly_snapshot WHERE dpd IS NOT NULL)
+SELECT a.product_type,round(100.0*avg(CASE WHEN DESTINATION THEN 1 ELSE 0 END),1) roll_rate_pct,count(*) accounts FROM s a JOIN s b ON a.account_id=b.account_id AND b.me=? WHERE a.me=? AND a.dpd BETWEEN 1 AND 30 GROUP BY 1 ORDER BY 1""".replace('\n+','\n').replace('DESTINATION',destination),[last,first],'Matched-account cohort with known DPD at both requested month ends; missing endpoints are excluded. DPD defines buckets. This public-reference cohort does not reconstruct historical insolvency holds.')
        if ('outbound' in q or 'contact' in q) and ('attempts' in q or 'touches' in q) and ('average' in q or 'on average' in q or 'per case' in q):
            if explicit_period(q):raise PlanError('This all-open-case measure uses lifetime observed outbound attempts. For a contact-date period, ask for attempts per case in that period and specify its grouping.')
            if re.search(r'\bby\b',q) and not re.search(r'\bby (?:current )?bucket',q):raise PlanError('The all-open-case lifetime-attempts calculation supports grouping by current bucket. For contact-date period attempts, specify a period and supported grouping.')
            return Plan(f"""WITH attempts AS(SELECT case_id,count(*) n FROM curated.contact_history h WHERE h.direction='outbound' AND {CHANNEL}!='system' GROUP BY 1)
+SELECT c.current_bucket,round(avg(coalesce(a.n,0)),2) attempts_per_case,count(*) open_cases FROM curated.collections_cases c LEFT JOIN attempts a USING(case_id) WHERE c.outcome IS NULL GROUP BY 1 ORDER BY 1""".replace('\n+','\n'),[],'Includes open cases with zero outbound attempts in the denominator.')
        if 'cost' in q and ('contact' in q or 'channel' in q):
            return Plan(f"SELECT {CHANNEL} channel,round(avg(h.contact_cost_cad),2) cost_per_contact_cad,count(*) contacts FROM curated.contact_history h WHERE {CHANNEL}!='system' AND h.contact_ts_local>=? AND h.contact_ts_local<? GROUP BY 1 ORDER BY 1",period)
        if ('champion' in q or 'challenger' in q) and ('promise' in q or 'ptp' in q):
            if re.search(r'\bby\b',q) or explicit_period(q):raise PlanError('The supported randomized strategy comparison uses all resolved promises and groups by test cell; custom groups/periods need clarification.')
            return Plan(f"SELECT c.test_cell,round(100.0*avg(CASE WHEN p.ptp_status='kept' THEN 1 ELSE 0 END),1) kept_pct,count(*) promises FROM curated.promises_to_pay p JOIN curated.collections_cases c USING(case_id) WHERE c.assignment_method='random' AND c.test_cell IN ('champion','challenger_A','challenger_B') AND p.ptp_status IN {RESOLVED} GROUP BY 1 ORDER BY 1",[],'Only randomized cases are compared. Rule-based assignments are confounded.')
        if 'hardship' in q and ('rate' in q or 'share' in q) and not ('interest' in q):
            group='primary_product' if 'product' in q else 'province_code' if 'province' in q else None
            return Plan(f"SELECT {group+',' if group else ''}round(100.0*avg(CASE WHEN hardship_flag THEN 1 ELSE 0 END),1) hardship_rate_pct,count(*) cases FROM curated.collections_cases WHERE case_open_date>=? AND case_open_date<?"+(' GROUP BY 1 ORDER BY 1' if group else ''),period,'This measures recorded hardship flags, not independently verified true hardship.')
        if ('promise' in q or 'ptp' in q) and ('kept' in q or 'keep rate' in q):
            return Plan(f"SELECT round(100.0*avg(CASE WHEN ptp_status='kept' THEN 1 ELSE 0 END),1) promise_kept_rate_pct,count(*) resolved_promises FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}",period)
        if ('cases' in q and re.search(r'\bopen\b',q)) and ('how many' in q or 'count' in q or 'number' in q):
            group='current_bucket' if 'bucket' in q else 'queue' if 'queue' in q else 'primary_product' if 'product' in q else None
            return Plan(f"SELECT {group+',' if group else ''}count(*) open_cases FROM curated.collections_cases WHERE outcome IS NULL"+(' GROUP BY 1 ORDER BY 1' if group else ''),[],'Open means no recorded outcome. Reported current_bucket values are retained; DPD/bucket discrepancies are reported separately.')
        return None

    def _generic_plan(self,q,start,end,force_grouping=None):
        """Recognize common intents locally; compile the same allowlist as Gemini."""
        if re.search(r'average|mean',q) and re.search(r'\bcure',q) and re.search(r'\bwithin\s+\d+\s+days?',q):
            raise PlanError('Average cure time with a maximum-days filter requires a separately defined cohort.')
        if 'cases' in q and re.search(r'\bopened\b',q) and re.search(r'how many|count|number',q):
            raise PlanError('Currently open cases and cases opened during a period are different populations. This count supports currently open cases; an opening-date count needs a separate cohort.')
        # These questions specify different cohorts and retain explicit templates.
        if template_cohort(q):return None
        metric=detect_metric(q)
        if metric is None:return None
        _cohort_guards(q,metric)
        filters=province_filter(q)
        grouping=force_grouping or 'none'
        grouping_question=re.sub(r'\bby\s+(?:sms|text(?: messages?)?)\b','via SMS',q) if metric=='sms_payment_link_click_share' else q
        found=None if force_grouping else requested_dimensions(grouping_question)
        if found is not None:
            if len(found)!=1:raise PlanError('Please choose one supported grouping: '+', '.join(CATALOG.get(metric,{}).get('groupings',[]))+'.')
            grouping=found[0]
            if grouping=='site' and metric in ['rpc_rate','ptp_rate','cost_per_contact','cost_per_rpc']:grouping='agent_site'
        if CATALOG.get(metric,{}).get('snapshot_only'):
            exact_snapshot=bool(re.search(r'\bas of\s+'+SNAPSHOT+r'\b|\bon\s+'+SNAPSHOT+r'\b',q))
            if explicit_period(q) and not exact_snapshot and (start,end)!=(ASOF,ASOF+timedelta(days=1)):
                raise PlanError(f'This calculation supports only the {SNAPSHOT} snapshot; historical reconstruction is unavailable.')
            start,end=ASOF,ASOF+timedelta(days=1)
        plan=compile_plan({'metric_id':metric,'grouping':grouping,'start_date':start.isoformat(),'end_date':end.isoformat(),'filters':filters,'clarification':None,'refuse':False,'refuse_reason':None})
        if not CATALOG[metric].get('snapshot_only') and not explicit_period(q) and not force_grouping:
            plan.note+=' No period was supplied; this answer uses the snapshot month to date.'
        return plan

    def _count_plan(self,q):
        """Customer and agent headcounts from reviewed tables; unknown qualifiers clarify."""
        target=re.search(r'\b(?:how many|number of|count of|total number of|total)\s+(?:(?:active|distinct|unique|current|existing|collections?|our|the|of|individual|resolved)\s+){0,3}(customers?|clients?|borrowers?|agents?|collectors?)\b',q)
        if not target or template_cohort(q):return None
        agents=target[1].startswith(('agent','collector'))
        text=q.replace(SNAPSHOT,' ')
        for name in sorted(PROVINCE_NAMES,key=len,reverse=True):text=re.sub(r'\b'+name+r'\b',' ',text)
        allowed=set('how many number of count total the a an are is there do does we have has had in our with at least one currently today now right as on bank maple portfolio overall all distinct unique by each per across altogether what s exist existing individual resolved c360 there'.split())
        if agents:
            allowed|=set('agents agent collectors collector active working work employed site sites role roles'.split())|{x for s in SITES for x in tokens(s)}
        else:
            allowed|=set('customers customer clients client borrowers borrower open case cases collection collections province provinces'.split())|{c.lower() for c in PROVINCES}
        extra=[w for w in tokens(text) if w not in allowed]
        if extra:
            raise PlanError('I can count customers (overall, in one province, by province, or those with open cases) and agents (overall, at one site, by site or by role). That extra condition is not a reviewed count filter.')
        dims=requested_dimensions(q) or []
        if agents:
            if any(re.search(r'\b'+name+r'\b',q) for name in PROVINCE_NAMES):raise PlanError('Agents are recorded by site, not province. Ask for agents by site or at one site.')
            group='role' if re.search(r'\b(?:by|per|each)\s+roles?\b',q) else 'site' if dims==['site'] else None
            if dims and dims!=['site']:raise PlanError('Agent counts support grouping by site or role.')
            site=next((label for label,pattern in SITES.items() if re.search(r'\b'+pattern+r'\b',q)),None)
            params=[site] if site else []
            prefix=f"coalesce({group},'unknown') AS {group}, " if group else ''
            sql=f"SELECT {prefix}count(*) FILTER (WHERE status='active') active_agents, count(*) agent_records FROM curated.agents"+(' WHERE site=?' if site else '')+(' GROUP BY 1 ORDER BY 1' if group else '')
            meta={'kind':'count','metric_id':'agents','grouping':group or 'none','filters':{'site':site} if site else {}}
            return Plan(sql,params,'Agent records from curated.agents; active means status=active (inactive records include terminated staff and leave).',meta)
        filters=province_filter(q)
        if dims and dims!=['province']:raise PlanError('Customer counts support grouping by province only.')
        open_cases=bool(re.search(r'\bopen\b|\bin\s+collections?\b',q))
        table,column=('gold.customer_summary','customers_with_open_cases') if open_cases else ('gold.customers','customers')
        where=['open_cases>0'] if open_cases else []
        if filters:where.append(CUSTOMER_PROVINCE+'=?')
        group=dims==['province']
        sql=f"SELECT {CUSTOMER_PROVINCE+' AS province, ' if group else ''}count(*) {column} FROM {table}"+(' WHERE '+' AND '.join(where) if where else '')+(' GROUP BY 1 ORDER BY 1' if group else '')
        note='Resolved C360 customers (gold.customers, one row per customer after identity matching).' if not open_cases else 'Customers with at least one open collections case in the C360 summary (gold.customer_summary.open_cases>0); open cases without a resolved identity are not counted.'
        if filters or group:note+=" Province comes from the customer profile, normalized from source variants such as 'Ont.' and 'PQ'; missing provinces are 'unknown'."
        meta={'kind':'count','metric_id':column,'grouping':'province' if group else 'none','filters':filters}
        return Plan(sql,[filters['province']] if filters else [],note,meta)

    def _promise_count_plan(self,q):
        """How many promises due in a period were broken/kept, with the resolved denominator and rate."""
        if not re.search(r'\b(?:how many|number of|count of|count)\b',q) or not re.search(r'\bpromises?\b|\bptps?\b',q) or re.search(r'\brates?\b|\bshare\b|percent',q) or prior_broken_cohort(q) or template_cohort(q):return None
        status='partially_kept' if re.search(r'partial',q) else 'broken' if re.search(r'\bbroken\b|\bbroke\b',q) else 'kept' if re.search(r'\bkept\b',q) else None
        if not status:return None
        if requested_dimensions(q) or province_filter(q):raise PlanError('Promise counts are available for the whole portfolio and one period. For groupings or a province, ask for the promise-kept or broken-promise rate, which reports resolved promises per group.')
        start,end=date_range(q)
        if start>=end:raise PlanError('The requested period is reversed or falls after the dataset snapshot.')
        sql=f"SELECT count(*) FILTER (WHERE ptp_status='{status}') {status}_promises, count(*) resolved_promises, round(100.0*avg(CASE WHEN ptp_status='{status}' THEN 1 ELSE 0 END),1) {status}_rate_pct FROM curated.promises_to_pay WHERE ptp_due_date>=? AND ptp_due_date<? AND ptp_status IN {RESOLVED}"
        note='Counts promises by due date; resolved means kept, partially kept or broken (open and cancelled promises are excluded).'+('' if explicit_period(q) else ' No period was supplied; this answer uses the snapshot month to date.')
        return Plan(sql,[start,end],note,{'kind':'promise_count','metric_id':f'{status}_promises','grouping':'none','start_date':start.isoformat(),'end_date':end.isoformat()})

    def _trend_plan(self,q,kind):
        metric=None if template_cohort(q) else detect_metric(q,strict=kind=='explicit')
        if metric is None and kind=='explicit' and re.search(r'\bopen\b.*\bcases?\b',q):metric='open_cases'
        others=[d for d in (requested_dimensions(q) or []) if d!='month']
        if metric is None or 'month' not in CATALOG.get(metric,{}).get('groupings',[]) or others:
            if kind=='window':return None
            if others and metric:raise PlanError(f"A monthly trend can be shown overall or for one province, but not split by {others[0]} as well. Ask for the trend, or for the {others[0]} breakdown in one period.")
            if metric in CATALOG:raise PlanError(f"Monthly trends are not available for {METRIC_INFO[metric][0]}: it {'is a '+SNAPSHOT+' snapshot without reviewed history' if CATALOG[metric].get('snapshot_only') else 'has no reviewed monthly definition'}. Trends cover promise-kept, broken-promise, right-party contact, PTP, cure and hardship rates, contact costs, attempts per case, days to cure and SMS link clicks.")
            raise PlanError('Monthly trends cover promise-kept, broken-promise, right-party contact, PTP, cure and hardship rates, contact costs, attempts per case, days to cure and SMS link clicks.')
        start,end=trend_range(q)
        if start>=end:raise PlanError('The requested trend period is empty or falls after the dataset snapshot.')
        plan=self._generic_plan(q,start,end,force_grouping='month')
        if plan and not explicit_period(q):
            plan.note+=f' No period was supplied; this shows the last {TREND_DEFAULT_MONTHS} complete months ({_month(start.strftime("%Y-%m"))} to {_month((end-timedelta(days=1)).strftime("%Y-%m"))}).'
        elif plan and re.search(WINDOW,q):
            plan.note+=f' "Last N months" means complete calendar months before the snapshot month; September 2026 (to {SNAPSHOT}) is excluded.'
        return plan

    def _programmes(self,q,result):
        """Hardship programmes effective at the snapshot, from the reviewed programme table."""
        products=[];text=q
        for pattern,codes in PROGRAMME_PRODUCTS:
            if re.search(pattern,text):
                products+=[c for c in codes if c not in products];text=re.sub(pattern,' ',text)
        sql='SELECT program_id,version,program_name,product_types,description,duration_months,payment_reduction_pct,requires_income_evidence,max_dpd,approver_level,policy_section FROM curated.hardship_programs WHERE effective_from<=? AND (effective_to IS NULL OR effective_to>=?)'
        params=[ASOF,ASOF]
        if products:sql+=' AND ('+' OR '.join(['product_types LIKE ?']*len(products))+')';params+=[f'%"{p}"%' for p in products]
        sql+=' ORDER BY program_id'
        with self._connect() as c:
            cursor=c.execute(sql,params);columns=[x[0] for x in cursor.description]
            rows=[dict(zip(columns,row)) for row in cursor.fetchall()]
        notes=[f'Programme versions effective on {SNAPSHOT}; superseded and future versions are excluded.',
               'POL-COLL-004 v4.2 §4.2 requires offering at least one eligible option before asking for payment; eligibility (DPD limit, months on book, insolvency, prior broken plans) is checked per customer.']
        if re.search(r'\bloans?\b',q) and not re.search(r'personal loans?|auto loans?|car loans?|mortgage|line of credit',q):notes.append("'Loans' matched personal and auto loans; ask about mortgages or lines of credit separately.")
        red3=next((r for r in rows if r['program_id']=='HP-LOAN-RED3'),None)
        if red3:notes.append(f"HP-LOAN-RED3 lasts {red3['duration_months']} months per POL-COLL-004 §4.2 and the programme table; FAQ-COLL-001 Q1 says 6 months, which conflicts with the policy and is not followed.")
        buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=columns,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        result['rows']=rows;result['answer']=buf.getvalue().strip()+'\n'+' '.join(notes)
        docs=[]
        for doc,section,version,path in [('POL-COLL-004','§4.2','4.2','files/docs/policy/POL-COLL-004_v4.2_EN.md'),('HPT-2026','document','2026.1','files/docs/terms/HPT-2026_v2026.1_EN.md')]:
            loaded=next((s for s in self.sections if (s['id'],s['section'])==(doc,section)),None)
            docs.append({'document_id':doc,'version':loaded['version'] if loaded else version,'section':section,'path':loaded['path'] if loaded else path})
        result['sources']=['hardship_programs',*docs]
        result['sql_or_sources']=sql+'\nBound parameters: '+json.dumps(params,default=str)+'\n'+'; '.join(f"{d['document_id']} v{d['version']} {d['section']} ({d['path']})" for d in docs)
        label=' and '.join(PRODUCT_LABELS.get(p,p) for p in products) if products else ''
        if set(products)=={'personal_loan','auto_loan'}:label='personal and auto loans'
        result['plan']={'kind':'hardship_programmes','metric_id':'hardship_programmes','start_date':SNAPSHOT,'products':products,'products_label':label}

    def _answerable(self,question):
        lower=question.lower()
        try:
            if self._refusal(lower):return False
            if programme_intent(lower):return True
            if re.search(WORK_QUEUE,lower):return False
            agent_ranking(lower);rank=ranking(lower);pq=rank['question'] if rank else lower
            plan=self._plan(pq)
            if plan is None or (rank and not getattr(plan,'metadata',None)):return False
            self._verify(plan,pq,dict(rank) if rank else None)
            return True
        except PlanError:return False

    def _suggestions(self,q):
        """Two or three closest questions the engine can answer, each checked by the planner."""
        try:metric=detect_metric(q,strict=False)
        except PlanError:metric=None
        if metric not in METRIC_INFO:metric='open_cases' if re.search(r'\bopen\b.*\bcases?\b',q) else None
        try:start,end=date_range(q) if explicit_period(q) else (None,None)
        except PlanError:start,end=None,None
        if start and start.day==1 and end in (date(start.year+(start.month==12),start.month%12+1,1),ASOF+timedelta(days=1)) and (end-timedelta(days=1)).month==start.month:
            period=f' in {calendar.month_name[start.month]} {start.year}'
        elif start and end>start:period=f' from {start.isoformat()} to {(end-timedelta(days=1)).isoformat()}'
        else:
            last=ASOF.replace(day=1)-timedelta(days=1);period=f' in {calendar.month_name[last.month]} {last.year}'
        candidates=list(WORK_QUEUE_SUGGESTIONS) if re.search(WORK_QUEUE,q) else []
        if re.search(r'\bcustomers?\b|\bclients?\b',q) and re.search(r'how many|number of|count',q):
            candidates+=['How many customers do we have?','How many customers have open cases?','How many customers do we have by province?']
        if re.search(PEOPLE,q) and not metric and not re.search(r'how many|number of|count',q):
            if re.search(r'collect|money|paid|payments?|dollars?|recover',q):candidates.append(f'How much was paid against promises{period}?')
            candidates+=[f'Which site has the highest promise-kept rate{period}?',f'Which site has the highest right-party contact rate{period}?','How many agents do we have by site?']
        if re.search(r'\bagents?\b',q) and re.search(r'how many|number of|count',q) and not metric:
            candidates+=['How many agents are there?','How many agents do we have by site?']
        if metric:
            label,_,_,_,template=METRIC_INFO[metric];groups=CATALOG[metric]['groupings']
            ask=lambda group='',region='',when=period:template.format(period=(region+when) if '{period}' in template else '',group=group)
            mentioned=[code for name,code in PROVINCE_NAMES.items() if re.search(r'\b'+name+r'\b',q)]
            people=re.search(PEOPLE,q)
            window=re.search(WINDOW,q);asked=[d for d in (requested_dimensions(q) or []) if d!='month']
            if window and '{period}' in template:
                try:
                    first,until=trend_range(q)
                    for d in asked or ['']:candidates.append(ask(' by '+d if d else '',when=f' from {first.isoformat()} to {(until-timedelta(days=1)).isoformat()}'))
                except PlanError:pass
            if people and ('site' in groups or 'agent_site' in groups):candidates.append(f"Which site has the highest {label}{period}?" if METRIC_INFO[metric][1]!='count' else ask(' by site'))
            for code in dict.fromkeys(mentioned):
                if len(mentioned)>1:candidates.append(ask(region=f' in {PROVINCE_LABELS[code]}'))
            rank=re.search(r'(?<!at )\b(?:most|fewest|least|highest|lowest|best|worst|top|bottom)\b',q)
            if rank and METRIC_INFO[metric][1]!='count':
                dims=[d for d in ['province','queue','product','channel','site','bucket'] if re.search(r'\b'+d+r's?\b',q) and (d in groups or (d=='site' and 'agent_site' in groups))]
                for d in dims or ['province']:candidates+=[f'Which {d} has the highest {label}{period}?',f'Which {d} has the lowest {label}{period}?']
            if 'province' in groups:candidates.append(ask(' by province'))
            if 'month' in groups:candidates.append(template.format(period='',group=' by month over the last 6 months'))
            for g in groups:
                if g not in ('none','month','province','prior_broken'):candidates.append(ask(' by '+g.replace('agent_site','site')))
            candidates.append(ask())
        candidates+=DEFAULT_SUGGESTIONS
        chosen=[]
        for candidate in dict.fromkeys(candidates):
            if candidate.lower().rstrip('?')!=q.rstrip('?') and self._answerable(candidate):chosen.append(candidate)
            if len(chosen)==3:break
        return chosen

    def _policy(self,q,result):
        unsupported='I could not match this to a supported measure. Supported: promise-kept and broken-promise rates, right-party contact and PTP rates, cost per contact or RPC, cure, hardship, delinquency and write-off rates, average DPD, attempts per case, days to cure, open-case counts and overdue totals, customer and agent counts, hardship programmes, and collections policy topics.'
        if not re.search(r'collection|hardship|call|contact|promise|\bptp|broken|payment|phone|\bsms\b|text message|consent|bankrupt|consumer proposal|fraud|dispute|complaint|grace|metric|financial|dialer|agent|programme|program|policy|procedure|accommodation|accessibility|dncl|casl|e-?mail|voicemail|remind|letter|lawyer|represent|trustee|counsell?or|language|french|holiday|cease',q):
            if re.search(r'\b(?:rate|ratio|share|percentage|kpi|metric)\b',q):
                result.update(answer=unsupported,reason='clarification_required');return
            reason='This question is outside the collections dataset and policies.'
            result.update(answer=reason,refused=True,reason=reason);return
        preferred=[]
        if re.search(r'fraud|fraudulent|unauthori[sz]ed.*(?:charge|transaction)',q):preferred=[('PRC-COLL-012','§6.1')]
        elif re.search(r'complain|dissatisf|complaint',q):preferred=[('POL-COLL-007','§8.1')]
        elif 'casl' in q or 'email' in q and 'consent' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'national do not call' in q or 'dncl' in q:preferred=[('POL-COLL-001','§5.3')]
        elif 'consumer proposal' in q or 'bankruptcy' in q:preferred=[('POL-COLL-001','§7.3')]
        elif re.search(r'\bcease\b|stop (?:contacting|calling|texting|emailing)|(?:not|never) (?:to )?(?:contact|call) (?:them|him|her|me)\b|do not contact|lawyer|legal representative|\brepresent\w*|trustee|counsell?or|third[- ]part|power of attorney',q):preferred=[('POL-COLL-001','§5.4')]
        elif re.search(r'\blanguages?\b|\bfrench\b|\bfrancophone',q):preferred=[('POL-COLL-001','§5.5')]
        elif re.search(r'attempt|calls?\b|phone|contact|reach',q) and re.search(r'week|7[- ]days?|seven days',q):preferred=[('POL-COLL-001','§5.2')]
        elif re.search(r'calling hours|call.*(?:before|after)\s*\d|permitted.*hours|hours.*(?:call|contact)|(?:call|contact).*hours|sundays?|statutory holidays?',q):preferred=[('POL-COLL-001','§5.1')]
        elif re.search(r'income.*evidence|evidence.*income|proof.*income|income.*proof',q):preferred=[('POL-COLL-004','§4.3'),('POL-COLL-004','§4.2'),('HPT-2026','document')]
        elif 'hours' in q and ('cut' in q or 'reduced' in q) or 'before' in q and 'payment' in q:preferred=[('POL-COLL-004','§4.2')]
        elif '3-month' in q or re.search(r'reduced[- ]payment',q):preferred=[('POL-COLL-004','§4.2'),('HPT-2026','document')]
        elif 'grace' in q or re.search(r'(?:considered|counts? as|treated as|deemed)\s+(?:a\s+)?broken',q):preferred=[('PRC-COLL-010','§3.3')]
        elif 'volume' in q and ('drop' in q or '23' in q or '24' in q):preferred=[('IR-2026-0923','document'),('IR-2026-0923','§1'),('IR-2026-0923','§2')]
        matches=[s for pair in preferred for s in self.sections if (s['id'],s['section'])==pair and s['language']=='EN']
        data_question=re.search(r'\b(?:rate|ratio|share|percentage|kpi|trend|average|how many|number of|count|total|highest|lowest)\b',q) and not re.search(r'polic|procedure|allowed|permitted|\bcan (?:we|i|an?)\b|\bmay (?:we|i)\b|\bmust\b|\bshould\b|\brules?\b|requir|\bneed\b|what happens|eligib|consent|\blaw|legal|\bdo we\b|\bwhat do\b',q)
        if not matches and data_question:
            result.update(answer=unsupported,reason='clarification_required');return
        if not matches and self.index:
            scores=self.index.get_scores(tokens(q));ranked=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)
            matches=[self.sections[i] for i in ranked[:2] if scores[i]>2 and self.sections[i]['language']=='EN']
            # Keyword retrieval must have one quotable sentence covering most topical (non-generic) question terms.
            topical=set(w for w in _terms(q) if w not in GENERIC_TERMS and len(w)>=3)
            def covered(section):return max([len({w for w in topical if any(_match(w,t) for t in _terms(x))}) for x in _source_sentences(summarize_policy(section['text'],q))] or [0])
            matches=[s for s in matches if topical and 2*covered(s)>len(topical)]
            if not matches:
                result.update(answer='I could not find a policy section or supported measure that answers this. '+unsupported.split('. ',1)[1],reason='clarification_required');return
        if any((s['id'],s['section'])==('FAQ-COLL-001','Q1') for s in matches):
            # FAQ Q1 (6 months) conflicts with POL-COLL-004 §4.2 and the programme table (3 months); policy prevails.
            policy=[s for s in self.sections if (s['id'],s['section'])==('POL-COLL-004','§4.2') and s['language']=='EN']
            matches=policy+[s for s in matches if (s['id'],s['section'])!=('FAQ-COLL-001','Q1') and s not in policy]
        if not matches:
            result['answer']='Please specify a supported collections metric, period, grouping, policy topic or case call summary.'
            result['reason']='clarification_required';return
        result['sources']=[{'document_id':s['id'],'version':s['version'],'section':s['section'],'path':s['path']} for s in matches]
        result['answer']='\n\n'.join(summarize_policy(s['text'],q) for s in matches)
        result['sql_or_sources']='; '.join(f"{s['id']} v{s['version']} {s['section']} ({s['path']})" for s in matches)

    def _transcript(self,q,result):
        case=re.search(r'\bCS-\d{4}-\d+\b',q,re.I).group(0).upper()
        sql='SELECT transcript_id,call_start_ts,file_path,language FROM curated.call_transcripts WHERE case_id=? ORDER BY call_start_ts DESC,transcript_id DESC LIMIT 1'
        with self._connect() as c:row=c.execute(sql,[case]).fetchone()
        if not row:
            result.update(answer='No recorded transcript was found for this case.',sql_or_sources=sql+'\nBound parameters: '+json.dumps([case]));return
        path=(self.dataset_root/'files'/row[2]).resolve()
        allowed=(self.dataset_root/'files/transcripts').resolve()
        if not path.is_relative_to(allowed):raise ValueError('Transcript source path is outside the release.')
        transcript=json.loads(path.read_text(encoding='utf-8'));turns=transcript.get('turns',[])
        result['answer']=f"Most recent recorded call on {case}: {row[1]}, transcript {row[0]}, language {row[3]}.\n"+summarize_transcript(turns)
        result['sources']=[{'case_id':case,'transcript_id':row[0],'call_start':str(row[1]),'file_path':row[2]}]
        result['sql_or_sources']=sql+'\nBound parameters: '+json.dumps([case])+f'\ntranscript:{row[0]} ({row[2]}); exact turn timestamps above'
