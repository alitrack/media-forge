"""Tests for HtmlVideoTemplateEngine."""

import os
import sys
import subprocess
import tempfile

import pytest

# Ensure mediaforge is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mediaforge.render.base import RenderError, get_render_engine, list_engines
from mediaforge.render.html_video_templates import TEMPLATE_DIR, HtmlVideoTemplateEngine
from mediaforge.types import ContentStyle, Script, Segment


def seg(text: str, speaker: str = "host") -> Segment:
    return Segment(speaker=speaker, voice_id=speaker, text=text)


def scr(title: str = "Test", segments=None) -> Script:
    return Script(title=title, style=ContentStyle.INTERVIEW, segments=segments or [])


class TestEngineRegistration:
    def test_engine_in_list(self):
        assert "html-video-templates" in list_engines()

    def test_factory_creates_instance(self):
        engine = get_render_engine("html-video-templates", template="swiss-grid")
        assert isinstance(engine, HtmlVideoTemplateEngine)
        assert engine.name == "html-video-templates"
        assert engine.template == "swiss-grid"

    def test_factory_default_template(self):
        engine = get_render_engine("html-video-templates")
        assert engine.template == "swiss-grid"

    def test_factory_with_template_param(self):
        engine = get_render_engine("html-video-templates", template="kinetic-type")
        assert engine.template == "kinetic-type"

    def test_factory_invalid_template_no_error(self):
        engine = get_render_engine("html-video-templates", template="nonexistent")
        assert engine.template == "nonexistent"


class TestAvailable:
    def test_available_returns_bool(self):
        assert isinstance(HtmlVideoTemplateEngine.available(), bool)

    def test_available_with_templates(self):
        assert os.path.isdir(TEMPLATE_DIR)
        assert HtmlVideoTemplateEngine.available() is True


class TestListTemplates:
    def test_returns_dict(self):
        assert isinstance(HtmlVideoTemplateEngine.list_templates(), dict)

    def test_count(self):
        templates = HtmlVideoTemplateEngine.list_templates()
        assert len(templates) >= 3

    def test_includes_expected(self):
        templates = HtmlVideoTemplateEngine.list_templates()
        for name in ["swiss-grid", "kinetic-type", "warm-grain"]:
            assert name in templates

    def test_descriptions(self):
        for name, desc in HtmlVideoTemplateEngine.list_templates().items():
            assert desc, f"Template '{name}' has empty description"


class TestTemplateLoading:
    def test_load_valid(self):
        engine = HtmlVideoTemplateEngine(template="swiss-grid")
        html = engine._load_template()
        assert "<html" in html.lower()
        assert len(html) > 1000

    def test_load_invalid_raises(self):
        engine = HtmlVideoTemplateEngine(template="nonexistent")
        with pytest.raises(RenderError, match="Template not found"):
            engine._load_template()

    def test_inject_title(self):
        engine = HtmlVideoTemplateEngine()
        html = engine._inject_content("{{TITLE}}", scr("Test Title"))
        assert "Test Title" in html
        assert "{{TITLE}}" not in html

    def test_inject_subtitle(self):
        html = HtmlVideoTemplateEngine()._inject_content(
            "{{SUBTITLE}}", scr("T", [seg("Subtitle text")])
        )
        assert "Subtitle text" in html

    def test_inject_body(self):
        html = HtmlVideoTemplateEngine()._inject_content(
            "{{BODY}}", scr("T", [seg("Line one"), seg("Line two")])
        )
        assert "Line one" in html
        assert "Line two" in html

    def test_inject_segments(self):
        html = HtmlVideoTemplateEngine()._inject_content(
            "{{SEGMENT_0_TEXT}} {{SEGMENT_1_TEXT}}",
            scr("T", [seg("First"), seg("Second")]),
        )
        assert "First" in html
        assert "Second" in html

    def test_inject_cleans_unused(self):
        html = HtmlVideoTemplateEngine()._inject_content(
            "text {{SEGMENT_99_TEXT}} text", scr()
        )
        assert "{{SEGMENT_99_TEXT}}" not in html

    def test_inject_empty_script(self):
        html = HtmlVideoTemplateEngine()._inject_content(
            "{{TITLE}} {{BODY}} {{SUBTITLE}}", scr("")
        )
        assert "MediaForge" in html
        assert "No content" in html


class TestRender:
    @pytest.fixture
    def minimal_script(self):
        return scr("Test Video", [
            seg("This is the first segment of the test video."),
            seg("And this is the second segment for testing."),
        ])

    @pytest.fixture
    def audio_path(self):
        path = os.path.join(tempfile.mkdtemp(), "silent.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", "3", "-q:a", "9", "-acodec", "libmp3lame", path,
        ], capture_output=True)
        assert os.path.exists(path)
        return path

    def test_render_produces_valid_mp4(self, minimal_script, audio_path):
        output = os.path.join(tempfile.mkdtemp(), "output.mp4")
        engine = HtmlVideoTemplateEngine(template="swiss-grid")
        result = engine.render(minimal_script, audio_path, output)
        assert result == output
        assert os.path.exists(output)
        assert os.path.getsize(output) > 1000
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", output,
        ], capture_output=True, text=True)
        assert float(probe.stdout.strip()) > 0.5

    def test_render_kinetic_type(self, minimal_script, audio_path):
        output = os.path.join(tempfile.mkdtemp(), "output.mp4")
        result = HtmlVideoTemplateEngine(template="kinetic-type").render(
            minimal_script, audio_path, output
        )
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000

    def test_render_missing_audio(self, minimal_script):
        with pytest.raises(RenderError, match="Audio file not found"):
            HtmlVideoTemplateEngine().render(minimal_script, "/no/audio.mp3", "/tmp/out.mp4")

    def test_render_invalid_template(self, minimal_script, audio_path):
        with pytest.raises(RenderError, match="Template not found"):
            HtmlVideoTemplateEngine(template="nonexistent").render(
                minimal_script, audio_path, "/tmp/out.mp4"
            )
