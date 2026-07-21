#!/usr/bin/env python3
"""
AI Avatar Video Generator
Create videos with AI presenters/avatars.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))


AVATAR_PRESETS = {
    'professional_male_1': {'style': 'business', 'gender': 'male', 'age': '30s'},
    'professional_female_1': {'style': 'business', 'gender': 'female', 'age': '30s'},
    'casual_male_1': {'style': 'casual', 'gender': 'male', 'age': '20s'},
    'casual_female_1': {'style': 'casual', 'gender': 'female', 'age': '20s'},
    'elder_male_1': {'style': 'professional', 'gender': 'male', 'age': '50s'},
    'elder_female_1': {'style': 'professional', 'gender': 'female', 'age': '50s'},
}

BACKGROUND_PRESETS = {
    'office': 'office_interior.jpg',
    'office_blur': 'office_blurred.jpg',
    'studio': 'studio_background.jpg',
    'gradient_blue': 'gradient_blue.jpg',
    'gradient_dark': 'gradient_dark.jpg',
    'outdoor': 'outdoor_scene.jpg',
    'custom': None,
}


def avatar_video(script_path: Optional[Path] = None, script_text: Optional[str] = None,
                avatar: str = 'professional_female_1', 
                background: str = 'office_blur',
                background_path: Optional[Path] = None,
                voice_id: Optional[str] = None,
                output: Optional[Path] = None,
                provider: str = 'local') -> Path:
    """
    Generate video with AI avatar presenter.
    
    Args:
        script_path: Path to script file
        script_text: Script text directly
        avatar: Avatar preset or custom ID
        background: Background preset
        background_path: Custom background image
        voice_id: Voice ID for TTS
        output: Output file path
        provider: AI avatar provider
        
    Returns:
        Path to generated video
    """
    print(f"🎭 Generating avatar video...")
    print(f"   Avatar: {avatar}")
    print(f"   Background: {background}")
    
    # Load script
    if script_path is not None and script_text is not None:
        raise ValueError("Provide exactly one of script_path or script_text, not both")
    if script_path is not None:
        if not script_path.is_file():
            raise FileNotFoundError(f"Script file not found: {script_path}")
        with open(script_path, 'r') as f:
            script = f.read()
    elif script_text:
        script = script_text
    else:
        raise ValueError("Please provide script_path or script_text")
    
    # Set output
    if output is None:
        output = Path("avatar_video.mp4")
    
    output.parent.mkdir(parents=True, exist_ok=True)

    if background == 'custom' and background_path is None:
        raise ValueError("Custom background requires --background-image")
    if background_path is not None and not background_path.is_file():
        raise FileNotFoundError(f"Custom background image not found: {background_path}")
    
    # Non-local requests must be fulfilled by the selected provider.
    if provider != 'local':
        return _generate_with_provider(
            script, avatar, background, voice_id, output, provider
        )

    if voice_id:
        raise NotImplementedError(
            "Local avatar voice synthesis is not implemented; "
            "omit --voice or select an implemented AI avatar provider"
        )
    # Explicit local mode creates a presentation-style video.
    return _generate_local(script, avatar, background, background_path, voice_id, output)


def _generate_with_provider(script: str, avatar: str, background: str,
                           voice_id: Optional[str], output: Path, 
                           provider: str) -> Path:
    """Generate using AI avatar provider (e.g., HeyGen, Synthesia)."""
    # This would integrate with actual avatar APIs
    # Placeholder for now
    raise NotImplementedError(f"Provider {provider} not implemented yet")


def _generate_local(script: str, avatar: str, background: str,
                   background_path: Optional[Path], voice_id: Optional[str],
                   output: Path) -> Path:
    """Generate locally using MoviePy with text slides."""
    from moviepy.editor import (ColorClip, TextClip, ImageClip,
                               CompositeVideoClip, concatenate_videoclips,
                               AudioFileClip)
    from moviepy.audio.fx.all import audio_fadein, audio_fadeout
    
    # Parse script into segments
    segments = parse_avatar_script(script)
    
    clips = []
    
    for i, segment in enumerate(segments):
        print(f"   Processing segment {i+1}/{len(segments)}")
        
        # Create background
        if background_path and background_path.exists():
            bg = ImageClip(str(background_path)).set_duration(segment['duration'])
        else:
            # Colored background based on preset
            bg_colors = {
                'office': (60, 60, 70),
                'office_blur': (50, 50, 60),
                'studio': (40, 40, 50),
                'gradient_blue': (30, 50, 80),
                'gradient_dark': (20, 20, 30),
            }
            color = bg_colors.get(background, (40, 40, 50))
            bg = ColorClip(size=(1920, 1080), color=color).set_duration(segment['duration'])
        
        # Avatar placeholder (colored circle with initials)
        avatar_info = AVATAR_PRESETS.get(avatar, {})
        initials = avatar[:2].upper() if not avatar_info.get('gender') else \
                   ('AM' if avatar_info['gender'] == 'male' else 'AF')
        
        avatar_text = TextClip(
            f"[AVATAR]\n{initials}",
            fontsize=40,
            color='white'
        ).set_duration(segment['duration']).set_position((100, 800))
        
        # Content text
        content = segment['text']
        
        # Handle slide markers
        if segment.get('type') == 'slide':
            text_clip = TextClip(
                content,
                fontsize=70,
                color='white',
                method='caption',
                size=(1400, None),
                align='center'
            ).set_duration(segment['duration']).set_position('center')
            
            clip = CompositeVideoClip([bg, text_clip])
        else:
            # Speech segment with avatar
            text_clip = TextClip(
                content,
                fontsize=50,
                color='white',
                method='caption',
                size=(1200, None),
                align='left'
            ).set_duration(segment['duration']).set_position((400, 400))
            
            clip = CompositeVideoClip([bg, avatar_text, text_clip])
        
        clips.append(clip)
    
    # Concatenate
    final = concatenate_videoclips(clips, method="compose")
    
    # Add voiceover if available (TTS would go here)
    # For now, just export
    
    final.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
    final.close()
    
    print(f"✓ Avatar video saved: {output}")
    return output


def parse_avatar_script(script: str) -> list:
    """
    Parse avatar script into segments.
    
    Format:
    [SLIDE: Title]
    Content for slide
    
    Speech content here
    Can be multiple paragraphs
    
    [SLIDE: Another Title]
    More content
    """
    segments = []
    current_text = []
    current_duration = 0
    current_type = 'speech'
    
    # Estimate 150 words per minute for duration calculation
    words_per_second = 150 / 60
    
    lines = script.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        # Check for slide marker
        if line.startswith('[SLIDE:') or line.startswith('[slide:'):
            # Save previous segment
            if current_text:
                text = ' '.join(current_text)
                word_count = len(text.split())
                duration = max(3, word_count / words_per_second)
                
                segments.append({
                    'type': current_type,
                    'text': text,
                    'duration': duration
                })
                current_text = []
            
            # Start new slide
            title = line[line.find(':')+1:line.find(']')].strip()
            current_type = 'slide'
            current_text = [title]
            
        else:
            current_text.append(line)
            current_type = 'speech'
    
    # Don't forget last segment
    if current_text:
        text = ' '.join(current_text)
        word_count = len(text.split())
        duration = max(3, word_count / words_per_second)
        
        segments.append({
            'type': current_type,
            'text': text,
            'duration': duration
        })
    
    # If no segments, treat whole script as one
    if not segments:
        word_count = len(script.split())
        duration = max(5, word_count / words_per_second)
        segments = [{'type': 'speech', 'text': script, 'duration': duration}]
    
    return segments


def list_avatars():
    """List available avatar presets."""
    print("Available avatars:")
    for name, info in AVATAR_PRESETS.items():
        print(f"  • {name} - {info['gender']}, {info['age']}, {info['style']}")
    
    print("\nAvailable backgrounds:")
    for name in BACKGROUND_PRESETS:
        print(f"  • {name}")


def main():
    parser = argparse.ArgumentParser(description='AI Avatar Video Generator')
    script_group = parser.add_mutually_exclusive_group()
    script_group.add_argument('--script', '-s', type=Path, help='Script file path')
    script_group.add_argument('--text', '-t', help='Script text')
    parser.add_argument('--avatar', '-a', default='professional_female_1',
                       help='Avatar preset or ID')
    parser.add_argument('--background', '-b', default='office_blur',
                       choices=list(BACKGROUND_PRESETS.keys()),
                       help='Background preset')
    parser.add_argument('--background-image', type=Path,
                       help='Custom background image')
    parser.add_argument('--voice', '-v', help='Voice ID for TTS')
    parser.add_argument('--output', '-o', type=Path, default='avatar_video.mp4',
                       help='Output file')
    parser.add_argument('--provider', '-p', default='local',
                       choices=['local', 'heygen', 'synthesia', 'd-id'],
                       help='Avatar provider')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available avatars')
    
    args = parser.parse_args()
    
    if args.list:
        list_avatars()
        return 0
    
    if not args.script and not args.text:
        print("✗ Please provide --script or --text")
        return 1
    
    try:
        result = avatar_video(
            script_path=args.script,
            script_text=args.text,
            avatar=args.avatar,
            background=args.background,
            background_path=args.background_image,
            voice_id=args.voice,
            output=args.output,
            provider=args.provider
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
