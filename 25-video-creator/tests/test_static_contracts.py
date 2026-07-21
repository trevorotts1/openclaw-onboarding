import ast
import json
import re
import shlex


def parser_contract(script_path):
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    options = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        flags = [
            value.value
            for value in node.args
            if isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.startswith("--")
        ]
        if not flags:
            continue
        choices = None
        for keyword in node.keywords:
            if keyword.arg == "choices" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                choices = [item.value for item in keyword.value.elts]
        for flag in flags:
            options[flag] = choices
    return options


def documented_python_commands(markdown):
    for block in re.findall(r"```bash\n(.*?)```", markdown, flags=re.DOTALL):
        logical = re.sub(r"\\\n\s*", " ", block)
        for match in re.finditer(
            r"python3?\s+scripts/([a-z_]+\.py)\s+([^\n]+)", logical
        ):
            yield match.group(1), shlex.split(match.group(2), comments=True)


def test_every_documented_example_uses_supported_cli_options(skill_root):
    markdown = (skill_root / "EXAMPLES.md").read_text(encoding="utf-8")
    checked = 0
    for script_name, tokens in documented_python_commands(markdown):
        options = parser_contract(skill_root / "scripts" / script_name)
        for index, token in enumerate(tokens):
            if not token.startswith("--"):
                continue
            checked += 1
            assert token in options, f"{script_name} does not accept {token}"
            if index + 1 < len(tokens):
                assert tokens[index + 1] not in {"<<", "<", ">"}
            choices = options[token]
            if choices and index + 1 < len(tokens):
                value = tokens[index + 1]
                if not value.startswith("$"):
                    assert value in choices, f"{script_name} rejects {token} {value}"
    assert checked >= 20


def test_documented_template_payloads_match_validated_schemas(skill_root):
    markdown = (skill_root / "EXAMPLES.md").read_text(encoding="utf-8")
    payloads = {
        name: json.loads(body)
        for name, body in re.findall(
            r"cat > ([\w.-]+\.json) << 'EOF'\n(.*?)\nEOF", markdown, re.DOTALL
        )
    }
    schemas = {
        "product_showcase": (
            {"product_name", "images", "features"},
            {"product_name", "images", "features", "tagline", "price", "call_to_action", "music", "duration"},
        ),
        "social_post": (
            {"headline"},
            {"headline", "subheadline", "platform", "duration", "music"},
        ),
        "tutorial": (
            {"title", "sections"},
            {"title", "instructor", "sections", "music"},
        ),
        "podcast_clip": (
            {"audio_file"},
            {"audio_file", "quote_text", "speaker", "podcast_name", "duration"},
        ),
    }
    commands = re.findall(
        r"template_video\.py\s+(\w+)\s+--data\s+([\w.-]+\.json)", markdown
    )
    assert len(commands) >= 6
    for template_name, filename in commands:
        data = payloads[filename]
        required, allowed = schemas[template_name]
        assert required <= set(data), f"{filename} lacks required fields"
        assert set(data) <= allowed, f"{filename} contains rejected fields"
        if "music" in data:
            assert "/" in data["music"], f"{filename} uses a genre instead of a file"
        if template_name == "tutorial":
            for section in data["sections"]:
                assert set(section) == {"heading", "content", "duration"}


def test_template_readme_matches_validator_and_labels_samples(skill_root):
    readme = (skill_root / "templates" / "README.md").read_text(encoding="utf-8")
    for marker in (
        "illustrative legacy samples",
        "--output",
        "event_name`, `date`, `location`, `description",
        "Required: `title`, `message`",
        "Only `product_showcase`, `social_post`, and `tutorial` accept `music`",
    ):
        assert marker in readme
    for stale_claim in (
        "All templates support the `music` field",
        "`rating` - Star rating",
        "`visualizer_style` - Audio visualization",
    ):
        assert stale_claim not in readme


def test_documented_template_catalog_matches_runtime(skill_root):
    docs = "\n".join(
        (skill_root / name).read_text(encoding="utf-8")
        for name in ("INSTRUCTIONS.md", "QC.md", "templates/README.md")
    )
    for template_name in (
        "product_showcase",
        "social_post",
        "tutorial",
        "testimonial",
        "podcast_clip",
        "event_promo",
        "announcement",
    ):
        assert template_name in docs
    assert "five built-in templates" not in docs.lower()


def test_all_version_markers_share_one_version_domain(skill_root):
    raw_version = (skill_root / "skill-version.txt").read_text().strip()
    version = raw_version[1:] if raw_version.startswith("v") else raw_version
    changelog = (skill_root / "CHANGELOG.md").read_text(encoding="utf-8")
    init_source = (skill_root / "scripts" / "__init__.py").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog
    assert "skill-version.txt" in init_source
    assert not re.search(r'^__version__\s*=\s*["\']', init_source, flags=re.MULTILINE)


def test_documented_output_defaults_match_primary_clis(skill_root):
    core = (skill_root / "CORE_UPDATES.md").read_text(encoding="utf-8")
    qc = (skill_root / "QC.md").read_text(encoding="utf-8")
    combined = core + qc
    assert "`~/Videos/Output/`" not in combined
    for expected in (
        "current working directory",
        "beside the input script",
        "`assembled.mp4`",
    ):
        assert expected in core
        assert expected in qc


def test_bundled_script_uses_only_supported_directives(skill_root):
    sample = (skill_root / "templates" / "sample_script.txt").read_text(
        encoding="utf-8"
    )
    for unsupported in ("TRANSITION:", "IMAGE:", "VOICEOVER:", "BGM:"):
        assert unsupported not in sample
    examples = (skill_root / "EXAMPLES.md").read_text(encoding="utf-8")
    for unsupported in ("TRANSITION:", "IMAGE:", "VOICEOVER:", "BGM:", "VISUAL:"):
        assert unsupported not in examples


def test_instructions_describe_script_and_provider_option_limits(skill_root):
    instructions = (skill_root / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "Complete video with scenes, transitions, and captions" not in instructions
    assert "bracketed scene descriptions plus `TEXT` and `DURATION`" in instructions
    assert "`TRANSITION` and `IMAGE` directives are rejected" in instructions
    assert "`--seed` and `--negative-prompt` are KIE-only options" in instructions
    assert "Runway, Pika, or mock is rejected with a nonzero exit" in instructions
