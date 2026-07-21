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
    }
    assert unsupported.isdisjoint(transitions.Transitions.AVAILABLE)

    with pytest.raises(ValueError, match="Unsupported transition"):
        transitions.Transitions.apply_transition(DummyClip(), DummyClip(), "pixelate")


def test_assembly_never_aliases_an_unknown_transition_to_fade(load_script):
    assembly = load_script("multi_clip_assembly")

    with pytest.raises(ValueError, match="Unsupported transition"):
        assembly.apply_transition(DummyClip(), DummyClip(), "slide_up")


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


@pytest.mark.parametrize("transition_name", ["slide_left", "slide_right"])
def test_every_retained_assembly_effect_is_distinct_from_fade(
    load_script, transition_name
):
    assembly = load_script("multi_clip_assembly")
    fade_a, fade_b = real_color_clips()
    effect_a, effect_b = real_color_clips()
    fade = real_frame_signature(assembly.apply_transition(fade_a, fade_b, "fade", 0.25))
    effect = real_frame_signature(
        assembly.apply_transition(effect_a, effect_b, transition_name, 0.25)
    )
    assert effect != fade


@pytest.mark.parametrize(
    "transition_name",
    [
        "slide_left", "slide_right", "slide_up", "slide_down",
        "wipe_left", "wipe_right", "wipe_up", "wipe_down",
    ],
)
def test_every_retained_library_effect_is_distinct_from_fade(
    load_script, transition_name
):
    transitions = load_script("transitions")
    fade_a, fade_b = real_color_clips()
    effect_a, effect_b = real_color_clips()
    fade = real_frame_signature(
        transitions.Transitions.apply_transition(fade_a, fade_b, "fade", 0.25)
    )
    effect = real_frame_signature(
        transitions.Transitions.apply_transition(
            effect_a, effect_b, transition_name, 0.25
        )
    )
    assert effect != fade
