from services.entity_extractor import _build_extraction_text, _normalize_canonical


class TestNormalizeCanonical:
    def test_strips_sir(self):
        assert _normalize_canonical("abhi sir") == "abhi"

    def test_strips_maam(self):
        assert _normalize_canonical("anita ma'am") == "anita"

    def test_strips_madam(self):
        assert _normalize_canonical("anita madam") == "anita"

    def test_strips_ji(self):
        assert _normalize_canonical("gupta ji") == "gupta"

    def test_strips_sahab(self):
        assert _normalize_canonical("khan sahab") == "khan"

    def test_strips_uncle(self):
        assert _normalize_canonical("ramesh uncle") == "ramesh"

    def test_strips_aunty(self):
        assert _normalize_canonical("meera aunty") == "meera"

    def test_strips_bhai(self):
        assert _normalize_canonical("aman bhai") == "aman"

    def test_strips_didi(self):
        assert _normalize_canonical("pooja didi") == "pooja"

    def test_strips_anna(self):
        assert _normalize_canonical("suresh anna") == "suresh"

    def test_strips_akka(self):
        assert _normalize_canonical("lakshmi akka") == "lakshmi"

    def test_strips_garu(self):
        assert _normalize_canonical("rao garu") == "rao"

    def test_strips_amma(self):
        assert _normalize_canonical("revathi amma") == "revathi"

    def test_strips_ayya(self):
        assert _normalize_canonical("murthy ayya") == "murthy"

    def test_strips_dr(self):
        assert _normalize_canonical("Dr Mehta") == "mehta"

    def test_strips_dr_with_dot(self):
        assert _normalize_canonical("dr. rao") == "rao"

    def test_strips_mr(self):
        assert _normalize_canonical("Mr Gupta") == "gupta"

    def test_strips_mrs(self):
        assert _normalize_canonical("Mrs Iyer") == "iyer"

    def test_strips_ms(self):
        assert _normalize_canonical("Ms Shah") == "shah"

    def test_strips_prof(self):
        assert _normalize_canonical("Prof Menon") == "menon"

    def test_strips_professor(self):
        assert _normalize_canonical("Professor Mehta") == "mehta"

    def test_strips_shri(self):
        assert _normalize_canonical("Shri Rao") == "rao"

    def test_strips_prefix_and_suffix(self):
        assert _normalize_canonical("dr. rao sir") == "rao"

    def test_strips_prefix_and_south_suffix(self):
        assert _normalize_canonical("Prof Suresh anna") == "suresh"

    def test_plain_name_unchanged(self):
        assert _normalize_canonical("Sarah Chen") == "sarah chen"

    def test_company_like_name_unchanged(self):
        assert _normalize_canonical("Sequoia Capital") == "sequoia capital"

    def test_siri_not_affected(self):
        assert _normalize_canonical("Siri") == "siri"

    def test_bhaila_not_affected(self):
        assert _normalize_canonical("Bhaila") == "bhaila"

    def test_collapses_whitespace(self):
        assert _normalize_canonical("  Dr.   Rao   Sir  ") == "rao"

    def test_case_insensitive(self):
        assert _normalize_canonical("ABHI SIR") == "abhi"

    def test_empty_string(self):
        assert _normalize_canonical("") == ""


class TestBuildExtractionText:
    def test_includes_all_available_observation_text(self, mock_observation):
        mock_observation.voice_transcript = "Voice said FlexPay has 40% MoM growth."
        mock_observation.image_summary = "Screenshot contains Palantir logo."

        text = _build_extraction_text(mock_observation)

        assert "Title: Met Abhi sir at demo day" in text
        assert "Notes: Abhi sir is building an AI infra tool." in text
        assert "Voice transcript: Voice said FlexPay has 40% MoM growth." in text
        assert "Image description: Screenshot contains Palantir logo." in text
        assert "Sector tags: ai" in text

    def test_omits_empty_optional_parts(self, mock_observation):
        mock_observation.voice_transcript = ""
        mock_observation.image_summary = ""
        mock_observation.sector_tags = None

        text = _build_extraction_text(mock_observation)

        assert "Voice transcript:" not in text
        assert "Image description:" not in text
        assert "Sector tags:" not in text

    def test_handles_empty_tag_list(self, mock_observation):
        mock_observation.sector_tags = []

        text = _build_extraction_text(mock_observation)

        assert "Sector tags:" not in text
