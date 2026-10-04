"""Shared API/benchmark path with optional Gemini and stable numeric answers."""
from functools import lru_cache
import os
import re

from app.gemini import GeminiClient, ProviderUnavailable
from app.settings import DB, DATASET

AGGREGATE_COLUMNS = frozenset('period disputes prior_broken broken_rate_pct promises site agent_site resolved_promises queue current_bucket avg_dpd cases_with_dpd open_cases province_code out_of_hours_pct calls channel cost_per_rpc_cad ptp_rate_pct right_party_contacts payroll_customers delayed_customers payroll_delay_share_pct contact_hour_local rpc_rate_pct attempts product_code product_type primary_product dpd_bucket delinquency_rate_pct delinquent_accounts accounts collected_cad certified_for_vulnerable_flag cure_30d_pct cases cases_open_at_start cure_rate_pct product chargeoff_cad roll_rate_pct attempts_per_case contacted_cases cost_per_contact_cad contacts test_cell kept_pct hardship_rate_pct promise_kept_rate_pct case_count outbound_attempts write_off_rate_pct from_bucket to_bucket'.split())


AGGREGATE_COLUMNS = AGGREGATE_COLUMNS | frozenset('ptp_channel overdue_cad open_hardship_cases average_days_to_cure cured_cases cases_with_days_to_cure cases_with_overdue sms_payment_link_clicked_pct payment_link_sms_sent clicked_sms'.split())


def _text_allowed():
    return os.getenv('COPILOT_GEMINI_TEXT_EVIDENCE', '0').lower() in ['1', 'true', 'yes']


def _units(source_id, text):
    """Keep complete paragraphs/turns, rather than context-changing fragments."""
    return {f'{source_id} paragraph:{i+1}': part.strip() for i, part in enumerate(text.split('\n\n'))
            if 10 <= len(part.strip()) <= 1800}


@lru_cache(maxsize=1)
def provider():
    return GeminiClient()


@lru_cache(maxsize=8)
def _engine(db_path, dataset_root, configured):
    from app.insights import InsightEngine
    return InsightEngine(db_path, dataset_root, planner=provider().plan if configured else None)


def engine(db_path=DB, dataset_root=DATASET):
    """Cache immutable policy retrieval; each SQL request keeps its own connection."""
    return _engine(str(db_path), str(dataset_root), provider().configured)


def _summary_sources(result, instance):
    rows = result.get('rows', [])
    if rows:
        if result.get('plan', {}).get('metric_id') in ['open_insolvency_cases','open_hardship_cases']:
            return {}  # Sensitive case flags and their balances stay local.
        if len(rows) > 10 or any(set(row) - AGGREGATE_COLUMNS for row in rows):
            return {}
        return {f'sql-result:{i+1}': '; '.join(f'{key.replace("_", " ")}: {value}' for key, value in row.items())
                for i, row in enumerate(rows)}
    documents = {}
    for source in result.get('sources', []):
        if not isinstance(source, dict):
            continue
        if source.get('document_id'):
            for section in getattr(instance, 'sections', []):
                if (section.get('id'), section.get('version'), section.get('section')) == (source.get('document_id'), source.get('version'), source.get('section')) and isinstance(section.get('text'), str):
                    documents.update(_units(f"{section['id']} v{section['version']} {section['section']}", section['text']))
        elif source.get('transcript_id') and _text_allowed() and len(result.get('sources', [])) == 1:
            # The deterministic engine has already checked transcript location
            # and extracted its source turns. No unrestricted path is opened here.
            documents.update(_units('transcript:' + source['transcript_id'], result['answer']))
    return documents


def answer(question, role='analyst', db_path=DB, dataset_root=DATASET):
    client = provider()
    client.begin_trace()
    instance = engine(db_path, dataset_root)
    result = instance.answer(question, role=role)
    if client.trace_metadata()['stages']['plan'] == 'generated' and (result.get('reason') or not result.get('plan')):
        client.mark('plan', 'fallback')
    if not result.get('refused') and not result.get('reason') and client.configured:
        sources = _summary_sources(result, instance)
        if sources:
            try:
                summary = client.summarise('collections answer', sources, question)
                # Keep CSV numeric tables and local source answers unchanged.
                # The UI displays this independently verified evidence selection.
                result['explanation'] = summary['text']
                result['explanation_sources'] = summary['source_ids']
            except ProviderUnavailable:
                client.mark('summary', 'fallback')
    metadata = client.trace_metadata()
    result['generation'] = metadata
    return result


def enrich_brief(payload):
    """Optional evidence presentation; never changes recommendation or draft."""
    client = provider()
    client.begin_trace()
    if client.configured:
        case_summary = payload['summary'] if _text_allowed() else payload['summary'].split('Financial evidence:')[0].strip()
        # Source IDs and note text remain local by default. Only approved case
        # totals and the already-determined rule explanation leave the machine.
        def redact(value):
            value=re.sub(r'\bCS-[\w-]+\b|\bNOTE-[\w-]+\b', '[source reference]', value)
            for source_id in [*payload.get('recorded_hardship_cases', []), payload.get('features', {}).get('note_id')]:
                if isinstance(source_id,str) and source_id:value=value.replace(source_id,'[source reference]')
            return value
        rule=redact(payload['recommendation_reason'])
        case_summary=redact(case_summary)
        sources = {'case-summary': case_summary, 'review-rule': rule}
        try:
            summary = client.summarise('review brief', sources)
            payload['summary_evidence'] = summary['text']
            payload['summary_sources'] = summary['source_ids']
        except ProviderUnavailable:
            client.mark('summary', 'fallback')
    payload['generation'] = client.trace_metadata()
    return payload
