from app.policy_summary import summarize_policy, summarize_transcript

GRACE = ("## §3.3 Grace period\n\n"
         "A promise to pay is considered broken when no payment is received within 3 business days after the promised date.\n\n"
         "Call notes are reviewed monthly by quality assurance.")


def sections(output):
    found, current = {}, None
    for line in output.splitlines():
        if line.startswith('- '):found[current].append(line)
        elif line.endswith(':'):current = line[:-1];found[current] = []
    return found


def test_policy_selects_complete_relevant_paragraph_with_heading():
    answer = summarize_policy(GRACE, 'When is a promise considered broken?')
    assert answer == GRACE.rsplit('\n\n', 1)[0]
    assert 'within 3 business days' in answer and 'quality assurance' not in answer


def test_policy_keeps_whole_section_when_unselected_text_has_exception():
    text = GRACE + '\n\nThe grace period does not apply unless the customer has an active hardship plan.'
    answer = summarize_policy(text, 'When is a promise considered broken?')
    assert answer == text
    assert 'does not apply unless' in answer


def test_policy_preserves_negation_numbers_and_exception_verbatim():
    rule = 'Agents must not place more than 3 call attempts in any 7-day period, except where the customer requests a call back.'
    text = f'## §5.2 Contact frequency\n\n{rule}\n\nQuality reviewers sample files monthly.'
    answer = summarize_policy(text, 'How many calls per week are allowed?')
    assert answer == f'## §5.2 Contact frequency\n\n{rule}'


def test_policy_list_item_keeps_its_lead_in_condition():
    unit = ('Outbound calls are permitted only when all of the following are true:\n\n'
            '- the customer has not asked to stop calls;\n- the time is between 8:00 and 21:00 local time.')
    text = f'## §5.2 Contact limits\n\n{unit}\n\nTraining records are retained for two years.'
    answer = summarize_policy(text, 'Is 21:00 local time allowed?')
    assert answer == f'## §5.2 Contact limits\n\n{unit}'
    assert 'has not asked to stop calls' in answer


def test_policy_output_is_extractive_and_falls_back_safely():
    for question in ['When is a promise considered broken?', 'weather tomorrow', '', None]:
        answer = summarize_policy(GRACE, question)
        assert all(part in GRACE for part in answer.split('\n\n'))
    assert summarize_policy(GRACE, 'weather tomorrow') == GRACE
    assert summarize_policy(GRACE, None) == GRACE
    assert summarize_policy(None, 'grace') == '' and summarize_policy(12, None) == '12'


TURNS = [
    {'speaker': 'agent', 'start_sec': 0, 'text': 'Hello, this is CIBC collections.'},
    {'speaker': 'customer', 'start_sec': 4.5, 'text': 'My hours were cut at work last month.'},
    {'speaker': 'customer', 'start_sec': 9, 'text': "I can't pay the full balance."},
    {'speaker': 'customer', 'start_sec': 15, 'text': 'I can pay $200 on October 15.'},
    {'speaker': 'agent', 'start_sec': 21, 'text': 'To confirm, you will pay $200 on October 15.'},
    {'speaker': 'customer', 'start_sec': 30, 'text': 'Thank you.'},
]


def test_transcript_groups_exact_turns_with_attribution():
    found = sections(summarize_transcript(TURNS))
    financial, commitments, other, agent = found.values()
    assert financial == ['- [4.5s customer] My hours were cut at work last month.', "- [9s customer] I can't pay the full balance."]
    assert commitments == ['- [15s customer] I can pay $200 on October 15.']
    assert other == ['- [30s customer] Thank you.']
    assert agent == ['- [21s agent] To confirm, you will pay $200 on October 15.']


def test_transcript_french_cues_keep_original_text():
    turns = {'turns': [{'speaker': 'client', 'start_sec': 3, 'text': "J'ai perdu mon emploi en août."},
                       {'speaker': 'client', 'start_sec': 8, 'text': 'Je peux payer 100 $ vendredi.'},
                       {'speaker': 'agent', 'start_sec': 12, 'text': 'Je confirme : 100 $ vendredi.'}]}
    financial, commitments, other, agent = sections(summarize_transcript(turns)).values()
    assert financial == ["- [3s client] J'ai perdu mon emploi en août."]
    assert commitments == ['- [8s client] Je peux payer 100 $ vendredi.']
    assert other == ['- None found.'] and agent == ['- [12s agent] Je confirme : 100 $ vendredi.']


def test_transcript_output_lines_are_only_input_turns_and_malformed_safe():
    texts = {t['text'] for t in TURNS}
    for line in summarize_transcript(TURNS).splitlines():
        if line.startswith('- ['):assert line.split('] ', 1)[1] in texts
    malformed = [None, 5, 'text', {'speaker': None, 'text': None}, {'speaker': 'customer'},
                 {'speaker': 'customer', 'text': 12}, {'speaker': 'system', 'start_sec': 1, 'text': 'Recording started.'}]
    output = summarize_transcript(malformed)
    assert 'Recording started.' not in output and output.endswith('omitted: 1.')
    for value in [None, 'abc', 7, {}, {'turns': 'bad'}]:
        assert summarize_transcript(value).count('- None found.') == 4


def test_policy_selection_retains_unmatched_eligibility_restriction():
    text='## Payment support\n\nA payment may be reduced to 50% for three months.\n\nBorrowers in insolvency are not eligible.'
    assert summarize_policy(text,'What is the reduced payment duration?')==text
