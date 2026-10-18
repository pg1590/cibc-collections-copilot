"""Live questions with typos in key collections words are read as intended, and the answer says so."""
import os

import pytest

os.environ.setdefault('COPILOT_GEMINI_ENABLED', '0')
from app.insights import correct_typos  # noqa: E402


@pytest.mark.parametrize('typed, read_as', [
    ('how many costumers have overdue amount of more than 900 dollars', 'how many customers have overdue amount of more than 900 dollars'),
    ('how many custmers owe more than $900', 'how many customers owe more than $900'),
    ('what is the promse kept rate in agust 2026', 'what is the promise kept rate in august 2026'),
    ('open cases in each provnce', 'open cases in each province'),
    ('how many hardhsip cases are open', 'how many hardship cases are open'),
])
def test_near_misses_of_key_words_are_corrected(typed, read_as):
    corrected, fixes = correct_typos(typed)
    assert corrected == read_as and fixes


@pytest.mark.parametrize('text', [
    'Which province has the highest promise-kept rate in August 2026?',
    'amounts promised by customs brokers',           # real words close to key words
    'cases contacted on insolvent customers',         # inflections and lookalikes
    'Which collectors made the most calls last month?',  # collectors are agents, not collections
    'cases with a contract dispute',
    'What is the average days past due of open cases by queue?',
    'How many outbound contact attempts did open cases receive, on average, by current bucket?',
])
def test_correct_words_are_left_alone(text):
    assert correct_typos(text) == (text, [])


def test_the_answer_says_what_was_corrected(tmp_path):
    from app.insights import InsightEngine
    engine = InsightEngine(tmp_path / 'missing.duckdb', tmp_path)
    result = engine.answer('What is the weather in Toronto tommorow for costumers?', 'supervisor')
    assert result['corrections'] == [{'typed': 'costumers', 'read_as': 'customers'}]
    assert '“costumers” as “customers”' in result['summary']
