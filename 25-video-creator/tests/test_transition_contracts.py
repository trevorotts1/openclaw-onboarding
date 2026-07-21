import pytest


class DummyClip:
    duration = 2.0

    def fadeout(self, _duration):
        return self

    def fadein(self, _duration):
        return self


def test_every_advertised_transition_is_implemented_or_rejected(load_script):
    transitions = load_script("transitions")
    unsupported = {
        "crossfade", "zoom_in", "zoom_out", "flip_horizontal",
        "flip_vertical", "spin", "pixelate",
        # slide_* renders identically in every direction under
        # concatenate_videoclips(method="compose"), which re-centers each clip
        # and drops slide_in's position animation.
        "slide_left", "slide_right", "slide_up", "slide_down",
    }
    assert unsupported.isdisjoint(transitions.Transitions.AVAILABLE)

    with pytest.raises(ValueError, match="Unsupported transition"):
        transitions.Transitions.apply_transition(DummyClip(), DummyClip(), "pixelate")

    for direction in ("left", "right", "up", "down"):
        with pytest.raises(ValueError, match="Unsupported transition"):
            transitions.Transitions.apply_transition(
                DummyClip(), DummyClip(), f"slide_{direction}"
            )


def test_assembly_never_aliases_an_unknown_transition_to_fade(load_script):
    assembly = load_script("multi_clip_assembly")

    for name in ("slide_up", "slide_left", "slide_right", "wipe", "zoom_in"):
        with pytest.raises(ValueError, match="Unsupported transition"):
            assembly.apply_transition(DummyClip(), DummyClip(), name)


def real_frame_signature(parts):
    from moviepy.editor import concatenate_videoclips

    final = concatenate_videoclips(parts, method="compose")
    try:
        return tuple(
            final.get_frame(min(final.duration - 0.001, final.duration * fraction)).tobytes()
            for fraction in (0.35, 0.45, 0.5, 0.55, 0.65)
        )
    finally:
        final.close()


def real_color_clips():
    from moviepy.editor import ColorClip

    return (
        ColorClip((24, 16), color=(255, 0, 0), duration=1),
        ColorClip((24, 16), color=(0, 0, 255), duration=1),
    )


def _signature_of(apply, transition_name):
    clip_a, clip_b = real_color_clips()
    return real_frame_signature(apply(clip_a, clip_b, transition_name, 0.25))


@pytest.mark.parametrize(
    "transition_name",
    ["wipe_left", "wipe_right", "wipe_up", "wipe_down"],
)
def test_every_retained_library_effect_is_distinct_from_fade(
    load_script, transition_name
):
    transitions = load_script("transitions")
    apply = transitions.Transitions.apply_transition
    assert _signature_of(apply, transition_name) != _signature_of(apply, "fade")


# Distinctness from `fade` alone is not enough: four advertised slide directions
# once rendered byte-identical frames to one another while each still differed
# from fade, so a requested direction was silently replaced by a different one.
# Every advertised variant must render distinctly from EVERY other variant.
def test_no_two_advertised_library_effects_render_identically(load_script):
    transitions = load_script("transitions")
    apply = transitions.Transitions.apply_transition
    rendered = {}
    for name in transitions.Transitions.AVAILABLE:
        if name == "none":
            continue
        signature = _signature_of(apply, name)
        collision = rendered.get(signature)
        assert collision is None, (
            f"advertised transitions {collision!r} and {name!r} render identical "
            "frames; a caller asking for one silently receives the other"
        )
        rendered[signature] = name


def test_no_two_advertised_assembly_effects_render_identically(load_script):
    assembly = load_script("multi_clip_assembly")
    rendered = {}
    for name in assembly.SUPPORTED_TRANSITIONS:
        if name == "none":
            continue
        signature = _signature_of(assembly.apply_transition, name)
        collision = rendered.get(signature)
        assert collision is None, (
            f"advertised transitions {collision!r} and {name!r} render identical "
            "frames; a caller asking for one silently receives the other"
        )
        rendered[signature] = name
