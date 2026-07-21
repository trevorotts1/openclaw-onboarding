#!/usr/bin/env python3
"""
Multi-Clip Assembly
Combine multiple video clips with transitions and effects.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))


# `slide_*` is deliberately not advertised here.  Assembly concatenates with
# concatenate_videoclips(method="compose"), which re-applies
# set_position('center') to every clip and discards the position animation
# slide_in installs, so slide_left and slide_right rendered byte-identical
# output and the requested direction was never delivered.
SUPPORTED_TRANSITIONS = (
    'fade', 'none',
)


def get_resolution(preset: str) -> Tuple[int, int]:
    """Get dimensions from quality preset."""
    presets = {
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '4k': (3840, 2160),
        'vertical': (1080, 1920),
        'square': (1080, 1080),
        'social': (1080, 1920),
    }
    return presets.get(preset, (1920, 1080))


def apply_transition(clip1, clip2, transition_type: str, duration: float = 0.5):
    """
    Apply transition between two clips.
    
    Args:
        clip1: First video clip
        clip2: Second video clip
        transition_type: Type of transition
        duration: Transition duration in seconds
        
    Returns:
        List of clips with transition applied
    """
    if transition_type not in SUPPORTED_TRANSITIONS:
        raise ValueError(f"Unsupported transition: {transition_type}")

    if transition_type == 'none' or duration <= 0:
        return [clip1, clip2]
    
    if transition_type == 'fade':
        # Crossfade
        clip1 = clip1.fadeout(duration)
        clip2 = clip2.fadein(duration)
        return [clip1, clip2]
    
    raise ValueError(f"Unsupported transition: {transition_type}")


def assemble_clips(clip_paths: List[Path], transition: str = 'fade',
                  transition_duration: float = 0.5, target_duration: Optional[float] = None,
                  music: Optional[str] = None, output: Optional[Path] = None,
                  resolution: str = '1080p', fps: int = 30) -> Path:
    """
    Assemble multiple clips into single video.
    
    Args:
        clip_paths: List of video file paths
        transition: Transition type between clips
        transition_duration: Length of transition in seconds
        target_duration: Max duration per clip (None = full clip)
        music: Existing background music file
        output: Output file path
        resolution: Output resolution preset
        fps: Frames per second
        
    Returns:
        Path to output video
    """
    if not clip_paths:
        raise ValueError("No input clips provided")
    if music and not Path(music).is_file():
        raise FileNotFoundError(f"Requested music file is unavailable: {music}")

    from moviepy.editor import VideoFileClip, concatenate_videoclips
    
    print(f"🎬 Assembling {len(clip_paths)} clips...")
    print(f"   Transition: {transition}")
    print(f"   Resolution: {resolution}")
    
    # Load and prepare clips
    target_width, target_height = get_resolution(resolution)
    clips = []
    failed_inputs = []
    
    for i, path in enumerate(clip_paths):
        if not path.exists():
            print(f"   ✗ Missing requested clip: {path}")
            failed_inputs.append((path, "file not found"))
            continue
            
        print(f"   Loading: {path.name}")
        
        try:
            clip = VideoFileClip(str(path))
            
            # Trim if target duration specified
            if target_duration and clip.duration > target_duration:
                clip = clip.subclip(0, target_duration)
            
            # Resize to target resolution (maintaining aspect ratio)
            if clip.w != target_width or clip.h != target_height:
                clip = clip.resize(newsize=(target_width, target_height))
            
            clips.append(clip)
            
        except Exception as e:
            print(f"   ✗ Error loading {path}: {e}")
            failed_inputs.append((path, str(e)))

    if failed_inputs:
        for clip in clips:
            clip.close()
        details = "; ".join(f"{path}: {reason}" for path, reason in failed_inputs)
        raise RuntimeError(f"Cannot assemble all requested clips: {details}")
    
    if not clips:
        raise RuntimeError("No valid clips to assemble")
    
    # Apply transitions
    if len(clips) > 1 and transition != 'none':
        print(f"   Applying {transition} transitions...")
        
        final_clips = [clips[0]]
        
        for i in range(1, len(clips)):
            transitioned = apply_transition(
                final_clips[-1], 
                clips[i], 
                transition, 
                transition_duration
            )
            final_clips = final_clips[:-1] + transitioned
        
        clips = final_clips
    
    # Concatenate all clips
    print("   Concatenating clips...")
    final_video = concatenate_videoclips(clips, method="compose")
    
    # Add background music
    if music:
        final_video = add_background_music(final_video, music)
    
    # Set output path
    if output is None:
        output = Path("assembled_video.mp4")
    
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Export
    print(f"   Exporting to {output}...")
    final_video.write_videofile(
        str(output),
        fps=fps,
        codec='libx264',
        audio_codec='aac',
        threads=4,
        preset='medium'
    )
    
    # Cleanup
    final_video.close()
    for clip in clips:
        clip.close()
    
    print(f"✓ Video saved: {output}")
    return output


def add_background_music(video, music_source: str, volume: float = 0.3):
    """
    Add background music to video.
    
    Args:
        video: Video clip
        music_source: File path or genre name
        volume: Music volume (0-1)
        
    Returns:
        Video with music added
    """
    from moviepy.editor import AudioFileClip, CompositeAudioClip
    from moviepy.audio.fx.all import audio_fadein, audio_fadeout, volumex
    
    # Check if music_source is a file or genre
    music_path = Path(music_source)
    
    if not music_path.is_file():
        raise FileNotFoundError(
            f"Requested music file is unavailable: {music_source}. "
            "Genre substitution is not supported; provide an audio file path."
        )
    music = AudioFileClip(str(music_path))
    
    # Loop or trim music to match video
    if music.duration < video.duration:
        # Loop music
        loops = int(video.duration / music.duration) + 1
        music = concatenate_audioclips([music] * loops)
    
    music = music.subclip(0, video.duration)
    
    # Adjust volume
    music = music.fx(volumex, volume)
    
    # Fade in/out
    music = music.fx(audio_fadein, 1.0).fx(audio_fadeout, 1.0)
    
    # Mix with existing audio or use as only audio
    if video.audio is not None:
        final_audio = CompositeAudioClip([video.audio, music])
    else:
        final_audio = music
    
    return video.set_audio(final_audio)


def get_music_by_genre(genre: str, duration: float):
    """Get background music by genre (placeholder for library)."""
    # This would load from a music library
    # For now, return None - user should provide file path
    print(f"   Note: Genre '{genre}' not implemented, provide file path instead")
    return None


def concatenate_audioclips(clips):
    """Concatenate audio clips."""
    from moviepy.editor import concatenate_audioclips as concat
    return concat(clips)


def main():
    parser = argparse.ArgumentParser(description='Assemble multiple video clips')
    parser.add_argument('clips', nargs='+', type=Path, help='Input video files')
    parser.add_argument('--transition', '-t', default='fade',
                       choices=SUPPORTED_TRANSITIONS,
                       help='Transition type between clips')
    parser.add_argument('--transition-duration', type=float, default=0.5,
                       help='Transition duration in seconds')
    parser.add_argument('--duration', type=float,
                       help='Max duration per clip (seconds)')
    parser.add_argument('--music', '-m', help='Background music file')
    parser.add_argument('--output', '-o', type=Path, default='assembled.mp4',
                       help='Output filename')
    parser.add_argument('--resolution', '-r', default='1080p',
                       choices=['720p', '1080p', '4k', 'vertical', 'square', 'social'],
                       help='Output resolution')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    
    args = parser.parse_args()
    
    try:
        result = assemble_clips(
            clip_paths=args.clips,
            transition=args.transition,
            transition_duration=args.transition_duration,
            target_duration=args.duration,
            music=args.music,
            output=args.output,
            resolution=args.resolution,
            fps=args.fps
        )
        print(f"\n🎥 Video ready: {result}")
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
