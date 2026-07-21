#!/usr/bin/env python3
"""
create_storyboard.py - Generate video storyboards matching AI model capabilities
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import timedelta

# Ensure scripts/ is on path regardless of where the caller runs from
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_database import get_model, calculate_cost, list_models

def format_time(seconds):
    """Format seconds as HH:MM:SS"""
    return str(timedelta(seconds=int(seconds)))

def generate_segment_prompt(topic, segment_num, total_segments, style="neutral"):
    """Generate a prompt for a video segment"""
    
    prompts = {
        "intro": [
            f"Opening shot establishing {topic}, professional lighting",
            f"Wide shot introducing {topic} theme, cinematic",
            f"Dynamic intro to {topic}, eye-catching visuals"
        ],
        "middle": [
            f"Medium shot showing {topic} details, engaging",
            f"Close-up of key {topic} elements, clear focus",
            f"Action shot demonstrating {topic}, dynamic movement"
        ],
        "outro": [
            f"Closing shot summarizing {topic}, memorable",
            f"Final image reinforcing {topic} message",
            f"Call-to-action visual for {topic}, compelling"
        ]
    }
    
    if segment_num == 0:
        return prompts["intro"][0]
    elif segment_num == total_segments - 1:
        return prompts["outro"][0]
    else:
        return prompts["middle"][segment_num % len(prompts["middle"])]

class StoryboardError(Exception):
    """A named, non-recoverable storyboard failure.

    T0-60: the failure branch used to print to stdout, return None and let the
    process exit 0, so a caller that branches on the exit code proceeded as if a
    storyboard file existed. Every failure now raises, main() prints it on stderr
    and exits non-zero.
    """


def create_storyboard(duration, model_id, topic, style="neutral"):
    """Create a complete storyboard.

    Raises StoryboardError when the model is unknown or the requested duration
    yields no clips. Never returns a storyboard with an empty segment list.
    """

    model = get_model(model_id)
    if not model:
        raise StoryboardError(
            f"AF-STORYBOARD-UNKNOWN-MODEL: unknown model '{model_id}'. "
            f"Available: {', '.join(list_models())}"
        )

    # Calculate segments
    clip_duration = model["durations"][0]
    if clip_duration <= 0:
        raise StoryboardError(
            f"AF-STORYBOARD-EMPTY: model '{model_id}' declares a clip duration of "
            f"{clip_duration}s; a storyboard cannot be segmented against it"
        )
    num_clips = duration // clip_duration
    if duration % clip_duration > 0:
        num_clips += 1

    # T0-60: a zero clip count writes a storyboard with no segments. Assert the
    # count BEFORE any file is written, so no empty artifact is ever emitted.
    if num_clips <= 0:
        raise StoryboardError(
            f"AF-STORYBOARD-EMPTY: duration {duration}s against model '{model_id}' "
            f"({clip_duration}s per clip) yields {num_clips} clips — a storyboard "
            f"needs at least one segment. Request a duration of at least 1 second."
        )

    cost_info = calculate_cost(model_id, duration)
    
    # Generate segments
    segments = []
    current_time = 0
    
    for i in range(num_clips):
        segment = {
            "segment_number": i + 1,
            "start_time": format_time(current_time),
            "end_time": format_time(min(current_time + clip_duration, duration)),
            "duration": min(clip_duration, duration - current_time),
            "prompt": generate_segment_prompt(topic, i, num_clips, style),
            "notes": ""
        }
        segments.append(segment)
        current_time += clip_duration
    
    storyboard = {
        "project": {
            "topic": topic,
            "total_duration": format_time(duration),
            "style": style
        },
        "model": {
            "id": model_id,
            "name": model["name"],
            "provider": model["provider"],
            "clip_duration": clip_duration,
            "resolution": model["resolution"]
        },
        "calculations": {
            "num_segments": num_clips,
            "cost_per_segment": cost_info["cost_per_clip"],
            "estimated_total_cost": cost_info["total_cost"]
        },
        "segments": segments
    }
    
    return storyboard

def export_to_json(storyboard, filename):
    """Export storyboard to JSON"""
    with open(filename, 'w') as f:
        json.dump(storyboard, f, indent=2)
    print(f"Exported to JSON: {filename}")

def export_to_markdown(storyboard, filename):
    """Export storyboard to Markdown"""
    with open(filename, 'w') as f:
        f.write(f"# {storyboard['project']['topic']} - Storyboard\n\n")
        f.write(f"**Model:** {storyboard['model']['name']}\n\n")
        f.write(f"**Total Duration:** {storyboard['project']['total_duration']}\n\n")
        f.write(f"**Segments:** {storyboard['calculations']['num_segments']}\n\n")
        f.write(f"**Estimated Cost:** ${storyboard['calculations']['estimated_total_cost']}\n\n")
        f.write("---\n\n")
        
        for seg in storyboard['segments']:
            f.write(f"## Segment {seg['segment_number']}\n\n")
            f.write(f"**Time:** {seg['start_time']} - {seg['end_time']}\n\n")
            f.write(f"**Duration:** {seg['duration']}s\n\n")
            f.write(f"**Prompt:** {seg['prompt']}\n\n")
            if seg['notes']:
                f.write(f"**Notes:** {seg['notes']}\n\n")
            f.write("---\n\n")
    
    print(f"Exported to Markdown: {filename}")

def main():
    parser = argparse.ArgumentParser(description='Create video storyboard')
    parser.add_argument('--duration', type=int, required=True, help='Total video duration in seconds')
    parser.add_argument('--model', type=str, required=True, help='AI model ID (veo-3-1, sora-10s, etc.)')
    parser.add_argument('--topic', type=str, required=True, help='Video topic/theme')
    parser.add_argument('--style', type=str, default='neutral', help='Visual style')
    parser.add_argument('--output', type=str, default='storyboard', help='Output filename prefix')
    
    args = parser.parse_args()
    
    print(f"Creating storyboard for {args.duration}s {args.topic} video using {args.model}...")

    try:
        storyboard = create_storyboard(args.duration, args.model, args.topic, args.style)
    except StoryboardError as exc:
        # T0-60: error text on STDERR and a non-zero exit, so a caller that
        # branches on the exit code never proceeds believing a storyboard exists.
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    export_to_json(storyboard, f"{args.output}.json")
    export_to_markdown(storyboard, f"{args.output}.md")

    print("\n✅ Storyboard created!")
    print(f"Segments: {storyboard['calculations']['num_segments']}")
    print(f"Estimated cost: ${storyboard['calculations']['estimated_total_cost']}")
    return 0

if __name__ == '__main__':
    sys.exit(main())