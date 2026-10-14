from app.features import text_features,evidence


def test_financial_cues_in_english_and_french():
    assert text_features('My hours were cut at work; I cannot pay this month.')['income_reduction']==1
    assert text_features('Mes heures sont réduites. Je ne peux pas payer.')['income_reduction']==1
    assert text_features('Le salaire est en retard.')['income_delay']==1
    assert any(text_features('The position eliminated in April.').values())


def test_protected_attributes_do_not_change_classifier_vector():
    financial='My hours were cut and I cannot pay.'
    a=text_features(financial+' Female, married, newcomer, disability, accessibility needs, accent.')
    b=text_features(financial+' Male, single, Canadian citizen, no accessibility needs.')
    assert a==b==text_features(financial)
    assert not any(text_features('Female married newcomer accessibility accent gender citizenship').values())


def test_evidence_is_original_source_text():
    text='Account checked. My hours were cut. Please call next week.'
    spans=evidence(text)
    assert spans==['My hours were cut.']
    assert all(s in text for s in spans)


import duckdb
import pytest
from app.features import PATTERNS,TEXT_FEATURES,VERSION,definitions,normalize_text


@pytest.mark.parametrize('text,cue', [
    ('Spoke to customer. Got laid off last month.', 'income_loss'),
    ('Parlé au client. Mis à pied en avril.', 'income_loss'),
    ('Mis � pied en mai.', 'income_loss'),  # mojibake accent from the source extract
    ('On strike since May, no paycheque.', 'income_loss'),
    ('Client en grève depuis mars.', 'income_loss'),
    ('Shifts cut at the plant since Apr.', 'income_reduction'),
    ('Lost overtime at work, less pay now.', 'income_reduction'),
    ('Un seul revenu maintenant.', 'income_reduction'),
    ('Heures coupées à l’usine depuis mai.', 'income_reduction'),
    ('Waiting on EI, applied 3 wks ago.', 'income_delay'),
    ("Attend l'AE, demande faite il y a 3 sem.", 'income_delay'),
    ('Money is tight right now.', 'payment_difficulty'),
    ('Says struggling a bit.', 'payment_difficulty'),
    ("C'est serré ce mois-ci.", 'payment_difficulty'),
    ('Difficile financièrement ces temps-ci.', 'payment_difficulty'),
    ('Asked if pmt can be reduced.', 'hardship_request'),
    ('Asked about hardship options.', 'hardship_request'),
    ('Demande si pmt peut être réduit. Réf. équipe difficultés.', 'hardship_request'),
    ('Mortgage renewed at higher rate.', 'expense_pressure'),
    ('Payment went up after rate reset in Jun.', 'expense_pressure'),
    ('Hypothèque renouvelée à un taux plus élevé.', 'expense_pressure'),
    ('On medical leave since Apr.', 'illness_or_injury'),
    ('On short term disability, claim pending.', 'illness_or_injury'),
    ('En arrêt maladie depuis mai.', 'illness_or_injury'),
    ('Hospitalisé le mois dernier.', 'illness_or_injury'),
    ('Split w/ partner in Apr, moved out.', 'separation'),
    ('Client en séparation.', 'separation'),
    ('Evacuated due to wildfire in May.', 'disaster_or_evacuation'),
    ('Maison inondée.', 'disaster_or_evacuation'),
    ('Évacué à cause des feux en juin.', 'disaster_or_evacuation'),
])
def test_v2_cues_fire_in_english_and_french(text,cue):
    assert text_features(text)[cue]==1


@pytest.mark.parametrize('text', [
    'Will try to pay $13 Feb 27, very rude, hung up, escalated to TL.',  # v1 matched pay...escalated
    'Will pay after payday. Sent pmt link.',
    'Forgot the due date. PTP $105 Feb 4.',
    'Says pmt not applied. Dispute opened.',
    'Paiera après la paie. Rappel prévu.',
    # s4.5 vulnerability markers and the vulnerability tag are not hardship cues.
    'Cust vulnerable - financial hardship. Sent pmt link.',
    'Serious illness in family. Recently bereaved. Cust crying. Mentioned anxiety, very stressed.',
    # s4.6 protected grounds never fire a cue.
    'Mentioned being pregnant. Mentioned attending church. Said they are originally from overseas. Marital status separated, single parent. Disability, accessibility needs.',
    'Client vulnérable. A mentionné être enceinte. Deuil récent.',
])
def test_v2_cues_do_not_fire_on_nonfinancial_or_protected_text(text):
    assert not any(text_features(text).values())


def test_every_pattern_compiles_and_matches_identically_in_duckdb():
    samples=['Got laid off last month; money is tight right now.','Mis � pied en mai. Demande si pmt peut �tre r�duit.',
      'Hypothèque renouvelée à un taux plus élevé.','Escalated to TL.','Evacuated due to wildfire; on medical leave.']
    with duckdb.connect() as c:
        for name,pattern in PATTERNS.items():
            c.execute("select regexp_matches('x', '"+pattern.replace("'","''")+"')").fetchall()
            for s in samples:
                got=c.execute("select regexp_matches(lower(strip_accents(?)), '"+pattern.replace("'","''")+"')",[s]).fetchone()[0]
                assert got==bool(text_features(s)[name]),(name,s)


def test_feature_list_version_and_definitions_track_patterns():
    assert VERSION=='c360-financial-v2' and TEXT_FEATURES==list(PATTERNS) and len(TEXT_FEATURES)==9
    cues=[d['name'] for d in definitions() if d['type']=='binary']
    assert cues==TEXT_FEATURES
    assert normalize_text('Réf. ÉQUIPE') == 'ref. equipe'
