"""Natural-language questions must always produce read-only SQL.

The upstream generator sent anything its templates did not recognise to a
local LLM and failed outright when none was running - which is the default
here. These tests pin the rule-based path: every ordinary question yields
SQL without requiring a language model.
"""

import pytest

QUESTIONS = [
    "how many door events today",
    "latest temperature reading",
    "average temperature today",
    "average temperature in the last 2 hours",
    "show me the latest sensor activity",
    "what happened in the last hour",
    "which devices are active",
    "list all devices",
    "how many records do we have",
    "what is the temperature",
    "show me door activity",
    "any smoke alarms today",
    "who was seen by misty",
    "overview of all",
]


@pytest.mark.parametrize("question", QUESTIONS)
def test_every_question_yields_sql_without_a_model(nlp_modules, question):
    """No Ollama is running in this environment - and none is needed."""
    assert nlp_modules.USE_LLM_SQL is False, "the LLM path must be opt-in"
    sql = nlp_modules.generate_sql(question)
    assert sql.strip().lower().startswith(("select", "with"))
    assert sql.strip().endswith(";")
    assert nlp_modules.CONTINUUM_TABLE in sql


def test_questions_about_devices_and_records_are_actionable(nlp_modules):
    """The gate used to reject these, so they never reached a query."""
    for question in QUESTIONS:
        assert nlp_modules.is_actionable(question), question


@pytest.mark.parametrize("chatter", ["hi", "hello", "thanks", "help", "?"])
def test_chit_chat_is_not_sent_to_the_continuum(nlp_modules, chatter):
    assert not nlp_modules.is_actionable(chatter)


def test_unrecognised_question_falls_back_deterministically(nlp_modules):
    sql = nlp_modules.generate_sql("what happened in the last hour")
    assert "ORDER BY" in sql.upper()
    assert "LIMIT" in sql.upper()


def test_counting_question_falls_back_to_a_count(nlp_modules):
    sql = nlp_modules.generate_sql("how many records do we have")
    assert "COUNT(*)" in sql.upper()


def test_device_listing_groups_by_device(nlp_modules):
    sql = nlp_modules.generate_sql("which devices are active")
    assert "GROUP BY" in sql.upper()
    assert "device_name" in sql


def test_telemetry_questions_select_the_readings(nlp_modules):
    """A THP device has no event - asking for it must return the values."""
    sql = nlp_modules.generate_sql("latest temperature reading")
    assert "contextvalue.temperature" in sql
    assert "contextvalue.humidity" in sql


def test_raw_sql_passes_through(nlp_modules):
    sql = nlp_modules.generate_sql("SELECT COUNT(*) FROM qprime.continuum;")
    assert sql.strip().startswith("SELECT")


def test_a_write_smuggled_into_raw_sql_is_refused(nlp_modules):
    with pytest.raises(RuntimeError, match="non-SELECT"):
        nlp_modules.generate_sql("SELECT 1; DROP TABLE edge_store;")


@pytest.mark.parametrize("hostile", ["DROP TABLE edge_store;", "delete everything"])
def test_destructive_phrasing_never_becomes_a_write(nlp_modules, hostile):
    """The fallback only ever builds SELECTs, and the core refuses the rest."""
    assert not nlp_modules.is_actionable(hostile)
    assert nlp_modules.generate_sql(hostile).strip().lower().startswith("select")
