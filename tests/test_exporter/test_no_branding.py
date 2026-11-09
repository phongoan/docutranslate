from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "docutranslate" / "template"


def test_export_templates_have_no_powered_by_footer():
    for template in TEMPLATE_DIR.glob("*.html"):
        assert "powered by" not in template.read_text(encoding="utf-8").lower(), template.name
