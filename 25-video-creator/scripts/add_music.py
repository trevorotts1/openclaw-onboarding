#!/usr/bin/env python3
"""
Add Music and Audio
Add background music, mix audio levels, and apply audio effects.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))


def add_music(video_path: Path, music_source: Optional[str] = None,
              genre: Optional[str] = None, volume: float = 0.3,
              fade_in: float = 1.0, fade_out: float = 1.0,
              voiceover: Optional[Path] = None, voice_volume: float = 1.0,
              output: Optional[Path] = None, loop: bool = True) -> Path:
    """
    Add background music to video.
    
    Args:
        video_path: Input video file
        music_source: Path to music file
        genre: Music genre for built-in library
        volume: Music volume (0-1)
        fade_in: Fade in duration (seconds)
        fade_out: Fade out duration (seconds)
        voiceover: Path to voiceover audio
        voice_volume: Voiceover volume (0-1)
        output: Output file path
        loop: Loop music if shorter than video
        
    Returns:
        Path to output video
    """
    from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_audioclips
    from moviepy.audio.fx.all import audio_fadein, audio_fadeout, volumex
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if music_source and genre:
        raise ValueError("Choose either music_source or genre, not both")
    if music_source and not Path(music_source).is_file():
        raise FileNotFoundError(f"Requested music file not found: {music_source}")
    if voiceover and not voiceover.is_file():
        raise FileNotFoundError(f"Requested voiceover file not found: {voiceover}")
    
    print(f"🎵 Adding music to video...")
    print(f"   Video: {video_path}")
    
    # Load video
    video = VideoFileClip(str(video_path))
    video_duration = video.duration
    
    print(f"   Duration: {video_duration:.1f}s")
    
    # Build audio tracks
    audio_tracks = []
    
    # Add original video audio if present
    if video.audio is not None:
        original_audio = video.audio.fx(volumex, 1.0)
        audio_tracks.append(original_audio)
        print("   Preserving original audio")
    
    # Add background music
    if music_source or genre:
        music = load_music(music_source, genre, video_duration, loop)
        
        if music is None:
            source = music_source or f"genre '{genre}'"
            raise RuntimeError(f"Requested music is unavailable: {source}")

        # Apply effects
        music = music.fx(volumex, volume)
        music = music.fx(audio_fadein, fade_in)
        music = music.fx(audio_fadeout, fade_out)

        audio_tracks.append(music)
        print(f"   Added music (volume: {volume})")
    
    # Add voiceover
    if voiceover:
        voice = AudioFileClip(str(voiceover))
        voice = voice.fx(volumex, voice_volume)
        voice = voice.fx(audio_fadein, 0.2).fx(audio_fadeout, 0.5)
        audio_tracks.append(voice)
        print(f"   Added voiceover (volume: {voice_volume})")
    
    if not audio_tracks:
        video.close()
        raise RuntimeError("No requested audio could be attached")
    
    # Mix audio
    if len(audio_tracks) == 1:
        final_audio = audio_tracks[0]
    else:
        final_audio = CompositeAudioClip(audio_tracks)
    
    # Set audio on video
    final_video = video.set_audio(final_audio)
    
    # Set output path
    if output is None:
        output = video_path.with_stem(f"{video_path.stem}_with_music")
    
    # Export
    print(f"   Exporting to {output}...")
    final_video.write_videofile(
        str(output),
        fps=video.fps,
        codec='libx264',
        audio_codec='aac',
        threads=4
    )
    
    # Cleanup
    video.close()
    final_video.close()
    for track in audio_tracks:
        track.close()
    
    print(f"✓ Video saved: {output}")
    return output


def load_music(music_source: Optional[str], genre: Optional[str], 
               duration: float, loop: bool) -> Optional[AudioFileClip]:
    """
    Load music from file or generate from genre.
    
    Returns:
        AudioFileClip or None
    """
    from moviepy.editor import AudioFileClip, concatenate_audioclips
    
    # Try file path first
    if music_source:
        music_path = Path(music_source)
        if music_path.exists():
            music = AudioFileClip(str(music_path))
            
            # Loop if needed
            if loop and music.duration < duration:
                loops = int(duration / music.duration) + 1
                music = concatenate_audioclips([music] * loops)
            
            return music.subclip(0, duration)
        raise FileNotFoundError(f"Requested music file not found: {music_source}")
    
    # Try genre
    if genre:
        return get_genre_music(genre, duration)
    
    return None


def get_genre_music(genre: str, duration: float) -> Optional[AudioFileClip]:
    """
    Get music from built-in genre library.
    Placeholder - would connect to music library or generate.
    """
    # This would:
    # 1. Check local music library
    # 2. Generate music with AI if available
    # 3. Use royalty-free sources
    
    genre_files = {
        'upbeat': 'music/upbeat.mp3',
        'corporate': 'music/corporate.mp3',
        'calm': 'music/calm.mp3',
        'epic': 'music/epic.mp3',
        'lofi': 'music/lofi.mp3',
        'inspirational': 'music/inspirational.mp3',
        'tense': 'music/tense.mp3',
    }
    
    music_file = genre_files.get(genre.lower())
    
    if music_file and Path(music_file).exists():
        from moviepy.editor import AudioFileClip, concatenate_audioclips
        music = AudioFileClip(music_file)
        
        if music.duration < duration:
            loops = int(duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        
        return music.subclip(0, duration)
    
    print(f"   Genre '{genre}' not available in library")
    return None


def extract_audio(video_path: Path, output: Optional[Path] = None) -> Path:
    """
    Extract audio from video file.
    
    Args:
        video_path: Input video
        output: Output audio file path
        
    Returns:
        Path to extracted audio
    """
    from moviepy.editor import VideoFileClip
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    print(f"🔊 Extracting audio from {video_path}...")
    
    video = VideoFileClip(str(video_path))
    
    if video.audio is None:
        raise ValueError("Video has no audio track")
    
    if output is None:
        output = video_path.with_suffix('.mp3')
    
    video.audio.write_audiofile(str(output))
    video.close()
    
    print(f"✓ Audio saved: {output}")
    return output


def mix_audio_levels(audio_files: List[Path], volumes: List[float],
                    output: Path) -> Path:
    """
    Mix multiple audio files with specific volume levels.
    
    Args:
        audio_files: List of audio file paths
        volumes: Volume level for each file (0-1)
        output: Output mixed audio file
        
    Returns:
        Path to mixed audio
    """
    from moviepy.editor import AudioFileClip, CompositeAudioClip
    from moviepy.audio.fx.all import volumex
    
    if len(audio_files) != len(volumes):
        raise ValueError("Number of files must match number of volumes")
    
    print(f"🎚️  Mixing {len(audio_files)} audio tracks...")
    
    clips = []
    max_duration = 0
    
    for path, vol in zip(audio_files, volumes):
        clip = AudioFileClip(str(path))
        clip = clip.fx(volumex, vol)
        clips.append(clip)
        max_duration = max(max_duration, clip.duration)
        print(f"   {path.name} (volume: {vol})")
    
    # Mix
    mixed = CompositeAudioClip(clips)
    
    # Export
    mixed.write_audiofile(str(output), fps=44100)
    
    # Cleanup
    for clip in clips:
        clip.close()
    mixed.close()
    
    print(f"✓ Mixed audio saved: {output}")
    return output


def remove_audio(video_path: Path, output: Optional[Path] = None) -> Path:
    """Remove audio from video."""
    from moviepy.editor import VideoFileClip
    
    video = VideoFileClip(str(video_path))
    video_no_audio = video.without_audio()
    
    if output is None:
        output = video_path.with_stem(f"{video_path.stem}_noaudio")
    
    video_no_audio.write_videofile(str(output), fps=video.fps, codec='libx264')
    
    video.close()
    video_no_audio.close()
    
    print(f"✓ Video without audio: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description='Add music and audio to video')
    parser.add_argument('video', type=Path, help='Input video file')
    music_selection = parser.add_mutually_exclusive_group()
    music_selection.add_argument('--music', '-m', help='Background music file')
    music_selection.add_argument('--genre', '-g',
                                 choices=['upbeat', 'corporate', 'calm', 'epic',
                                          'lofi', 'inspirational', 'tense'],
                                 help='Music genre from library')
    parser.add_argument('--volume', type=float, default=0.3,
                       help='Music volume 0-1 (default: 0.3)')
    parser.add_argument('--fade-in', type=float, default=1.0,
                       help='Music fade in duration (seconds)')
    parser.add_argument('--fade-out', type=float, default=1.0,
                       help='Music fade out duration (seconds)')
    parser.add_argument('--voiceover', '-v', type=Path,
                       help='Voiceover audio file')
    parser.add_argument('--voice-volume', type=float, default=1.0,
                       help='Voiceover volume 0-1')
    parser.add_argument('--output', '-o', type=Path,
                       help='Output file')
    parser.add_argument('--no-loop', action='store_true',
                       help='Do not loop music if shorter than video')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Additional commands')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract audio from video')
    extract_parser.add_argument('video', type=Path, help='Input video')
    extract_parser.add_argument('--output', '-o', type=Path, help='Output audio file')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove audio from video')
    remove_parser.add_argument('video', type=Path, help='Input video')
    remove_parser.add_argument('--output', '-o', type=Path, help='Output video')
    
    # Mix command
    mix_parser = subparsers.add_parser('mix', help='Mix multiple audio files')
    mix_parser.add_argument('files', nargs='+', type=Path, help='Audio files')
    mix_parser.add_argument('--volumes', nargs='+', type=float, required=True,
                           help='Volume for each file (0-1)')
    mix_parser.add_argument('--output', '-o', type=Path, required=True,
                           help='Output file')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'extract':
            result = extract_audio(args.video, args.output)
            print(f"🎵 Audio: {result}")
            return 0
            
        elif args.command == 'remove':
            result = remove_audio(args.video, args.output)
            print(f"🔇 Video: {result}")
            return 0
            
        elif args.command == 'mix':
            result = mix_audio_levels(args.files, args.volumes, args.output)
            print(f"🎚️  Mixed: {result}")
            return 0
            
        else:
            # Default: add music
            if not args.music and not args.genre and not args.voiceover:
                print("✗ Please specify --music, --genre, or --voiceover")
                return 1
            
            result = add_music(
                video_path=args.video,
                music_source=args.music,
                genre=args.genre,
                volume=args.volume,
                fade_in=args.fade_in,
                fade_out=args.fade_out,
                voiceover=args.voiceover,
                voice_volume=args.voice_volume,
                output=args.output,
                loop=not args.no_loop
            )
            print(f"\n🎬 Video ready: {result}")
            return 0
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
