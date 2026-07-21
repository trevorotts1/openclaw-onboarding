#!/usr/bin/env python3
"""
Video Export Utility
Export videos in various formats and quality presets.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))


def export_video(input_path: Path, output: Optional[Path] = None,
                format: str = 'mp4', quality: str = 'web',
                codec: Optional[str] = None, fps: int = 30,
                audio_codec: str = 'aac', resize: Optional[str] = None,
                crop: Optional[str] = None, watermark: Optional[Path] = None) -> Path:
    """
    Export video with specified settings.
    
    Args:
        input_path: Input video file
        output: Output file path
        format: Output format (mp4, webm, mov, gif)
        quality: Quality preset (social, web, broadcast, cinema)
        codec: Video codec (libx264, libx265, prores)
        fps: Frames per second
        audio_codec: Audio codec
        resize: Target resolution (e.g., 1920x1080)
        crop: Crop region (e.g., 1920:1080:0:0)
        watermark: Watermark image
        
    Returns:
        Path to exported video
    """
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    from moviepy.video.fx.all import resize as resize_clip
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    
    print(f"📤 Exporting video...")
    print(f"   Input: {input_path}")
    print(f"   Format: {format}")
    print(f"   Quality: {quality}")
    
    # Load video
    video = VideoFileClip(str(input_path))
    
    # Apply quality preset
    if quality == 'social':
        target_height = 720
        bitrate = '2M'
    elif quality == 'web':
        target_height = 1080
        bitrate = '5M'
    elif quality == 'broadcast':
        target_height = 1080
        bitrate = '10M'
    elif quality == 'cinema':
        target_height = 2160
        bitrate = '20M'
    else:
        target_height = None
        bitrate = None
    
    # Resize if needed
    if target_height and video.h > target_height:
        video = video.resize(height=target_height)
    
    if resize:
        w, h = map(int, resize.split('x'))
        video = video.resize(newsize=(w, h))
    
    # Apply crop
    if crop:
        # Format: width:height:x:y
        parts = crop.split(':')
        if len(parts) == 4:
            w, h, x, y = map(int, parts)
            video = video.crop(x1=x, y1=y, x2=x+w, y2=y+h)
    
    # Add watermark
    if watermark and watermark.exists():
        logo = (ImageClip(str(watermark))
                .set_duration(video.duration)
                .resize(height=50)
                .set_position(('right', 'bottom'))
                .set_opacity(0.5))
        video = CompositeVideoClip([video, logo])
    
    # Determine codec
    if codec is None:
        codecs = {
            'mp4': 'libx264',
            'webm': 'libvpx',
            'mov': 'libx264',
        }
        codec = codecs.get(format, 'libx264')
    
    # Set output path
    if output is None:
        output = input_path.with_suffix(f'.{format}')
    
    # Special handling for GIF
    if format == 'gif':
        from moviepy.editor import VideoFileClip
        # GIF export with reduced colors and frame rate
        video.write_gif(
            str(output),
            fps=min(fps, 15),
            program='ffmpeg'
        )
    else:
        # Video export
        video.write_videofile(
            str(output),
            fps=fps,
            codec=codec,
            audio_codec=audio_codec if format != 'gif' else None,
            bitrate=bitrate,
            threads=4,
            preset='medium'
        )
    
    video.close()
    
    print(f"✓ Exported: {output}")
    return output


def batch_export(input_dir: Path, pattern: str = '*.mp4', **kwargs):
    """Export multiple videos with same settings."""
    from pathlib import Path
    
    results = []
    for video_file in input_dir.glob(pattern):
        try:
            output = export_video(video_file, **kwargs)
            results.append((video_file.name, True, output))
        except Exception as e:
            results.append((video_file.name, False, str(e)))
    
    print("\nBatch export complete:")
    for name, success, result in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Export video with settings')
    parser.add_argument('input', type=Path, help='Input video file')
    parser.add_argument('--output', '-o', type=Path, help='Output file')
    parser.add_argument('--format', '-f', default='mp4',
                       choices=['mp4', 'webm', 'mov', 'gif', 'avi'],
                       help='Output format')
    parser.add_argument('--quality', '-q', default='web',
                       choices=['social', 'web', 'broadcast', 'cinema'],
                       help='Quality preset')
    parser.add_argument('--codec', help='Video codec (libx264, libx265, prores)')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--resize', help='Resize to WxH (e.g., 1920x1080)')
    parser.add_argument('--crop', help='Crop to W:H:X:Y (e.g., 1920:1080:0:0)')
    parser.add_argument('--watermark', type=Path, help='Watermark image')
    parser.add_argument('--batch', action='store_true', help='Batch process directory')
    
    args = parser.parse_args()

    if args.batch and args.output is not None:
        print("✗ --output cannot be used with --batch; batch outputs are derived per input")
        return 2
    if args.batch and not args.input.is_dir():
        print("✗ --batch requires a directory input")
        return 2
    
    try:
        if args.batch and args.input.is_dir():
            results = batch_export(args.input, **{
                'format': args.format,
                'quality': args.quality,
                'codec': args.codec,
                'fps': args.fps,
                'resize': args.resize,
                'crop': args.crop,
                'watermark': args.watermark
            })
            succeeded = sum(1 for _, success, _ in results if success)
            failed = len(results) - succeeded
            print(f"Batch result: {succeeded} succeeded, {failed} failed")
            if not results:
                print("✗ Batch export failed; no input files matched the requested pattern")
                return 1
            if failed:
                print("✗ Batch export incomplete; one or more requested files failed")
                return 1
        else:
            result = export_video(
                input_path=args.input,
                output=args.output,
                format=args.format,
                quality=args.quality,
                codec=args.codec,
                fps=args.fps,
                resize=args.resize,
                crop=args.crop,
                watermark=args.watermark
            )
            print(f"\n📤 Export complete: {result}")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
