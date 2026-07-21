#!/usr/bin/env python3
"""
Image-to-Video Converter
Animate static images into video with various motion effects.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from ai_providers import AIProvider


def image_to_video(image_path: Path, output: Optional[Path] = None,
                  motion: str = 'ken_burns', duration: float = 5.0,
                  resolution: Optional[str] = None, zoom_direction: str = 'in',
                  music: Optional[str] = None, provider: str = 'local') -> Path:
    """
    Convert image to video with motion effects.
    
    Args:
        image_path: Path to input image
        output: Output video path
        motion: Motion type (zoom, pan, ken_burns, none)
        duration: Video duration in seconds
        resolution: Output resolution (None = match image)
        zoom_direction: 'in' or 'out' for zoom effect
        music: Background music file
        provider: AI provider (local uses MoviePy)
        
    Returns:
        Path to generated video
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    print(f"🖼️  Converting image to video...")
    print(f"   Image: {image_path}")
    print(f"   Motion: {motion}")
    print(f"   Duration: {duration}s")
    
    # Set output path
    if output is None:
        output = image_path.with_suffix('.mp4')
    
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Non-local requests must be fulfilled by the selected provider.
    if provider != 'local':
        config = load_config()
        ai = AIProvider(provider, config.get('video_providers', {}))
        return ai.image_to_video(
            image_path=image_path,
            prompt=f"{motion} motion effect",
            duration=int(duration),
            output=output
        )

    from moviepy.editor import ImageClip, AudioFileClip
    from moviepy.audio.fx.all import audio_fadein, audio_fadeout, volumex
    
    # Local processing with MoviePy
    clip = ImageClip(str(image_path))
    
    # Apply resolution if specified
    if resolution:
        res_map = {'720p': (1280, 720), '1080p': (1920, 1080), '4k': (3840, 2160)}
        target_size = res_map.get(resolution)
        if target_size:
            clip = clip.resize(newsize=target_size)
    
    # Apply motion effect
    if motion == 'zoom':
        clip = apply_zoom(clip, duration, zoom_direction)
        
    elif motion == 'ken_burns':
        clip = apply_ken_burns(clip, duration)
        
    elif motion == 'pan_left':
        clip = apply_pan(clip, duration, 'left')
        
    elif motion == 'pan_right':
        clip = apply_pan(clip, duration, 'right')
        
    elif motion == 'pan_up':
        clip = apply_pan(clip, duration, 'up')
        
    elif motion == 'pan_down':
        clip = apply_pan(clip, duration, 'down')
        
    elif motion == 'none':
        clip = clip.set_duration(duration)
        
    else:
        raise ValueError(f"Unknown motion effect: {motion}")
    
    # Add music if provided
    if music:
        print(f"   Adding music: {music}")
        music_clip = AudioFileClip(str(music))
        
        # Loop or trim music
        if music_clip.duration < duration:
            from moviepy.editor import concatenate_audioclips
            loops = int(duration / music_clip.duration) + 1
            music_clip = concatenate_audioclips([music_clip] * loops)
        
        music_clip = music_clip.subclip(0, duration)
        music_clip = music_clip.fx(volumex, 0.3)
        music_clip = music_clip.fx(audio_fadein, 0.5).fx(audio_fadeout, 0.5)
        
        clip = clip.set_audio(music_clip)
    
    # Export
    print(f"   Exporting to {output}...")
    clip.write_videofile(
        str(output),
        fps=30,
        codec='libx264',
        audio_codec='aac' if music else None,
        threads=4
    )
    
    clip.close()
    
    print(f"✓ Video saved: {output}")
    return output


def apply_zoom(clip, duration: float, direction: str = 'in'):
    """Apply zoom effect to image."""
    from moviepy.editor import vfx
    
    if direction == 'in':
        # Start at 1x, zoom to 1.3x
        def resize_func(t):
            return 1 + 0.3 * (t / duration)
    else:  # zoom out
        # Start at 1.3x, zoom to 1x
        def resize_func(t):
            return 1.3 - 0.3 * (t / duration)
    
    clip = clip.resize(resize_func).set_duration(duration)
    
    # Center the zoom
    def position_func(t):
        scale = resize_func(t)
        w, h = clip.size
        new_w, new_h = w * scale, h * scale
        return ((w - new_w) / 2, (h - new_h) / 2)
    
    return clip.set_position(position_func)


def apply_ken_burns(clip, duration: float):
    """
    Apply Ken Burns effect - slow pan and zoom.
    Combines slow zoom with subtle pan movement.
    """
    from moviepy.editor import vfx
    import random
    
    # Start slightly zoomed in (1.2x) and pan
    start_scale = 1.2
    end_scale = 1.3
    
    # Random pan direction
    pan_x = random.choice([-0.1, 0.1])
    pan_y = random.choice([-0.05, 0.05])
    
    def transform(get_frame, t):
        frame = get_frame(t)
        progress = t / duration
        
        # Calculate scale and position
        scale = start_scale + (end_scale - start_scale) * progress
        x_offset = pan_x * progress * frame.shape[1]
        y_offset = pan_y * progress * frame.shape[0]
        
        # Resize
        from scipy.ndimage import zoom
        zoomed = zoom(frame, (scale, scale, 1), order=1)
        
        # Calculate crop region
        h, w = zoomed.shape[:2]
        ch, cw = frame.shape[:2]
        
        x1 = int((w - cw) / 2 + x_offset)
        y1 = int((h - ch) / 2 + y_offset)
        x1 = max(0, min(x1, w - cw))
        y1 = max(0, min(y1, h - ch))
        
        return zoomed[y1:y1+ch, x1:x1+cw]
    
    # Use MoviePy's standard approach instead
    # Simple zoom with position shift
    def resize_func(t):
        return start_scale + (end_scale - start_scale) * t / duration
    
    def pos_func(t):
        scale = resize_func(t)
        w, h = clip.size
        new_w, new_h = w * scale, h * scale
        progress = t / duration
        x = (w - new_w) / 2 + pan_x * w * 0.2 * progress
        y = (h - new_h) / 2 + pan_y * h * 0.1 * progress
        return (x, y)
    
    return clip.resize(resize_func).set_position(pos_func).set_duration(duration)


def apply_pan(clip, duration: float, direction: str):
    """Apply pan movement to image."""
    w, h = clip.size
    
    # Start and end positions based on direction
    if direction == 'left':
        start_pos = (0, 'center')
        end_pos = (-w * 0.2, 'center')
    elif direction == 'right':
        start_pos = (-w * 0.2, 'center')
        end_pos = (0, 'center')
    elif direction == 'up':
        start_pos = ('center', 0)
        end_pos = ('center', -h * 0.2)
    else:  # down
        start_pos = ('center', -h * 0.2)
        end_pos = ('center', 0)
    
    # Need to zoom in slightly to allow panning
    clip = clip.resize(1.2)
    
    def pos_func(t):
        progress = t / duration
        if direction in ('left', 'right'):
            x = start_pos[0] + (end_pos[0] - start_pos[0]) * progress if isinstance(start_pos[0], (int, float)) else 0
            return (x, 'center')
        else:
            y = start_pos[1] + (end_pos[1] - start_pos[1]) * progress if isinstance(start_pos[1], (int, float)) else 0
            return ('center', y)
    
    return clip.set_position(pos_func).set_duration(duration)


def load_config():
    """Load optional configuration."""
    import json
    config_path = Path.home() / ".openclaw" / "video-creator" / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description='Convert image to video with motion')
    parser.add_argument('image', type=Path, help='Input image file')
    parser.add_argument('--output', '-o', type=Path, help='Output video file')
    parser.add_argument('--motion', '-m', default='ken_burns',
                       choices=['zoom', 'ken_burns', 'pan_left', 'pan_right', 
                               'pan_up', 'pan_down', 'none'],
                       help='Motion effect type')
    parser.add_argument('--duration', '-d', type=float, default=5.0,
                       help='Video duration in seconds')
    parser.add_argument('--resolution', '-r', choices=['720p', '1080p', '4k'],
                       help='Output resolution')
    parser.add_argument('--zoom-direction', choices=['in', 'out'], default='in',
                       help='Zoom direction (for zoom motion)')
    parser.add_argument('--music', help='Background music file')
    parser.add_argument('--provider', default='local',
                       choices=['local', 'kieai', 'runway', 'pika'],
                       help='AI provider for generation')
    
    args = parser.parse_args()
    
    if not args.image.exists():
        print(f"✗ Image not found: {args.image}")
        return 1
    
    try:
        result = image_to_video(
            image_path=args.image,
            output=args.output,
            motion=args.motion,
            duration=args.duration,
            resolution=args.resolution,
            zoom_direction=args.zoom_direction,
            music=args.music,
            provider=args.provider
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
