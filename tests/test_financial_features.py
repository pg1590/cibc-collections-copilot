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
